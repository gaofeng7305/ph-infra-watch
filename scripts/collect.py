#!/usr/bin/env python3
"""Fetch configured RSS discovery feeds and publish a resilient JSON snapshot."""
from __future__ import annotations
import hashlib
import email.utils
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
DATA_FILE = ROOT / "site" / "data" / "data.json"
MAX_FEED_BYTES = 2_000_000
MAX_ITEMS = 2000

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def run_status_exit_code(run_status: str) -> int:
    return 1 if run_status == "error" else 0

def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit((url or "").strip())
    if parts.scheme.lower() != "https" or not parts.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urllib.parse.urlunsplit(("https", parts.netloc.lower(), parts.path or "/",
                                    urllib.parse.urlencode(query), ""))

def stable_id(url: str, title: str = "") -> str:
    seed = canonical_url(url) or re.sub(r"\s+", " ", title.strip().lower())
    return "lead-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

def timestamp_key(value: str | None) -> float:
    """Parse RSS RFC 2822 and ISO timestamps for reliable chronological sorting."""
    if not value:
        return 0.0
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()

def is_cms_placeholder(title: str) -> bool:
    return bool(re.match(r"^untitled(?:\s|$)", (title or "").strip(), re.IGNORECASE))

def _text(node: ET.Element, name: str) -> str:
    child = next((candidate for candidate in list(node) if candidate.tag.rsplit("}", 1)[-1] == name), None)
    if child is None:
        return ""
    value = "".join(child.itertext()).strip()
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value)[:1200]

def parse_feed(xml_bytes: bytes, source: dict[str, Any], observed_at: str | None = None) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    entries = root.findall("./channel/item")
    if not entries:
        entries = [node for node in root.iter() if node.tag.endswith("entry")]
    observed_at = observed_at or now_iso()
    results = []
    for node in entries:
        title = _text(node, "title")
        # Google News may return CMS placeholder entries as if they were articles.
        if is_cms_placeholder(title):
            continue
        link = _text(node, "link")
        if not link:
            link_node = next((candidate for candidate in list(node) if candidate.tag.rsplit("}", 1)[-1] == "link"), None)
            if link_node is not None:
                link = link_node.attrib.get("href", "")
        link = canonical_url(link)
        if not title or not link:
            continue
        summary = _text(node, "description") or _text(node, "summary") or _text(node, "encoded")
        published = _text(node, "pubDate") or _text(node, "published") or _text(node, "updated") or None
        results.append({
            "id": stable_id(link, title), "kind": "lead", "title": title[:400],
            "summary": summary[:800], "summary_zh": "", "title_zh": "", "link": link,
            "publisher": urllib.parse.urlsplit(link).netloc, "source_id": source["id"],
            "published_at": published, "observed_at": observed_at,
            "sector": classify_sector(f"{title} {summary}"), "region": None,
            "stage_hint": classify_stage(f"{title} {summary}"), "tags": [],
            "verification_status": "unverified", "evidence": [{
                "url": link, "source_name": urllib.parse.urlsplit(link).netloc,
                "published_at": published, "observed_at": observed_at,
                "quote_or_fact": title[:400], "supports_fields": ["title"]
            }], "discovered_by": "rss", "ai_generated": False
        })
    return results

def classify_sector(text: str) -> str:
    value = text.lower()
    telecom = ("telecom", "fiber", "fibre", "broadband", "5g", "tower", "ict", "connectivity")
    energy = ("energy", "solar", "wind", "battery", "bess", "power", "grid", "electric", "hydro")
    has_t = any(term in value for term in telecom)
    has_e = any(term in value for term in energy)
    if has_t and has_e:
        return "cross_sector"
    if has_t:
        return "telecommunications"
    if has_e:
        return "energy"
    return "general"

def classify_stage(text: str) -> str:
    value = text.lower()
    for stage, terms in {
        "tender_keyword": ("tender", "procurement", "bid", "bidding"),
        "construction_keyword": ("construction", "groundbreaking", "under construction"),
        "planning_keyword": ("planned", "planning", "proposed", "development"),
    }.items():
        if any(term in value for term in terms):
            return stage
    return "news"

def feed_url(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": "en-PH", "gl": "PH", "ceid": "PH:en"})
    return "https://news.google.com/rss/search?" + params

def fetch_source(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = time.monotonic()
    url = feed_url(source["query"])
    request = urllib.request.Request(url, headers={
        "User-Agent": "PHInfraWatch/1.0 (+https://github.com/)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9,*/*;q=0.5"
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(MAX_FEED_BYTES + 1)
            if len(body) > MAX_FEED_BYTES:
                raise ValueError("feed response exceeded size limit")
        items = parse_feed(body, source)
        return ({"source_id": source["id"], "status": "ok", "item_count": len(items),
                 "checked_at": now_iso(), "duration_ms": int((time.monotonic()-started)*1000)}, items)
    except Exception as exc:  # noqa: BLE001 - source failures are isolated intentionally
        reason = str(exc).replace("\n", " ")[:240] or exc.__class__.__name__
        return ({"source_id": source["id"], "status": "error", "item_count": 0,
                 "checked_at": now_iso(), "duration_ms": int((time.monotonic()-started)*1000),
                 "message": reason}, [])

def merge_items(previous: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in previous + fresh:
        if is_cms_placeholder(item.get("title", "")):
            continue
        item_id = item.get("id") or stable_id(item.get("link", ""), item.get("title", ""))
        if item_id:
            merged[item_id] = {**item, "id": item_id}
    def sort_key(item):
        return timestamp_key(item.get("published_at")) or timestamp_key(item.get("observed_at"))
    return sorted(merged.values(), key=sort_key, reverse=True)[:MAX_ITEMS]

def verified_projects(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in config.get("projects", []) if p.get("verification_status") == "verified"]

def derive_opportunities(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Produce transparent suggestions only from human-verified project records."""
    result = []
    for project in projects:
        if project.get("verification_status") != "verified":
            continue
        sector = project.get("sector", "general")
        if sector not in {"energy", "telecommunications", "cross_sector"}:
            continue
        project_id = project["project_id"]
        evidence = [e for e in project.get("evidence", []) if e.get("url")]
        if not evidence:
            continue
        if sector in {"energy", "cross_sector"}:
            kind, title, rationale = ("equipment_or_epc", f"{project['name']}：核查設備與工程採購窗口",
                "僅根據已核驗的能源項目檔案提出後續核查方向；目前不代表存在已發布採購或供應商需求。")
        else:
            kind, title, rationale = ("network_infrastructure", f"{project['name']}：核查網絡設備與工程合作窗口",
                "僅根據已核驗的通信項目檔案提出後續核查方向；目前不代表存在已發布採購或供應商需求。")
        result.append({
            "opportunity_id": f"suggestion-{project_id}", "title": title,
            "opportunity_type": kind, "project_id": project_id,
            "company_ids": [], "rationale": rationale,
            "evidence_item_ids": [], "evidence_urls": [e["url"] for e in evidence],
            "confidence": "low", "priority": "review",
            "risks": ["尚未確認項目採購計劃、預算、資格或招標狀態"],
            "next_checks": ["查閱最新官方公告", "核實項目階段與採購計劃", "檢查投標資格和期限"],
            "created_by": "rules", "verification_status": "suggested_unverified",
            "created_at": now_iso()
        })
    return result

def load_manual():
    names = {"projects": "manual_projects.json", "companies": "manual_companies.json",
             "relationships": "manual_relationships.json", "opportunities": "manual_opportunities.json"}
    return {key: read_json(CONFIG / name, {key: []}).get(key, []) for key, name in names.items()}

def atomic_write(path: Path, value: dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".tmp-" + path.name)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

def run_collection() -> dict[str, Any]:
    old = read_json(DATA_FILE, {}) or {}
    source_config = read_json(CONFIG / "sources.json", {"sources": [], "official_portals": []})
    enabled = [s for s in source_config.get("sources", []) if s.get("enabled")]
    health, fresh = [], []
    with ThreadPoolExecutor(max_workers=min(5, max(1, len(enabled)))) as pool:
        futures = [pool.submit(fetch_source, source) for source in enabled]
        for future in as_completed(futures):
            status, items = future.result()
            health.append(status); fresh.extend(items)
    manual = load_manual()
    merged_items = merge_items(old.get("items", []), fresh)
    timestamp = now_iso()
    successes = [x for x in health if x["status"] == "ok"]
    run_status = "ok" if len(successes) == len(enabled) else ("partial" if successes else "error")
    opportunities = manual["opportunities"] + derive_opportunities(verified_projects(manual))
    from opportunity_scoring import score_opportunity
    project_by_id = {p.get("project_id"): p for p in manual["projects"]}
    for opportunity in opportunities:
        opportunity["opportunity_score"] = score_opportunity(
            opportunity, project_by_id.get(opportunity.get("project_id")), datetime.now(timezone.utc)
        )
    result = {
        "schema_version": "1.0", "generated_at": timestamp,
        "last_success_at": timestamp if successes else old.get("last_success_at"),
        "run_status": run_status, "source_health": sorted(health, key=lambda x: x["source_id"]),
        "items": merged_items, "projects": manual["projects"],
        "companies": manual["companies"], "relationships": manual["relationships"],
        "opportunities": opportunities,
        "official_portals": source_config.get("official_portals", [])
    }
    try:
        from ai_assist import enrich
        result = enrich(result)
    except Exception as exc:  # optional AI never blocks collection or publication
        result["ai_status"] = {"status": "skipped", "message": str(exc)[:200]}
    atomic_write(DATA_FILE, result)
    return result

if __name__ == "__main__":
    try:
        snapshot = run_collection()
        print(f"Collection complete: {snapshot['run_status']}; {len(snapshot['items'])} lead(s); "
              f"{sum(s['status']=='ok' for s in snapshot['source_health'])}/{len(snapshot['source_health'])} source(s) ok.")
        # Do not let GitHub Actions publish a stale snapshot as a green build
        # when every configured source failed.
        sys.exit(run_status_exit_code(snapshot["run_status"]))
    except Exception as exc:
        # Preserve the last valid JSON if a configuration-level failure occurs.
        print(f"Collection setup failed; previous snapshot preserved: {exc}", file=sys.stderr)
        sys.exit(1)
