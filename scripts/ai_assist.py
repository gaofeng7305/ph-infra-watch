"""Optional server-side OpenAI Responses API enrichment; safe no-op without a key."""
from __future__ import annotations
import json
import os
import urllib.request
import re
import unicodedata
from pathlib import Path

ENDPOINT = "https://api.openai.com/v1/responses"
TRANSLATION_CACHE = Path(__file__).resolve().parent / "data" / "title_translation_cache.json"

def _title_cache_key(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).split()).casefold()

def _load_title_cache(path: Path = TRANSLATION_CACHE) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): v for k, v in value.items() if isinstance(v, str) and v} if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def _write_title_cache(cache: dict[str, str], path: Path = TRANSLATION_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".tmp-" + path.name)
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

EXTRACTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title_zh": {"type": "string"},
        "summary_zh": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "candidate_entities": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "candidate_locations": {"type": "array", "items": {"type": "string"}, "maxItems": 5}
    }, "required": ["title_zh", "summary_zh", "tags", "candidate_entities", "candidate_locations"]
}
OPPORTUNITY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "rationale": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "next_checks": {"type": "array", "items": {"type": "string"}, "maxItems": 4}
    }, "required": ["rationale", "risks", "next_checks"]
}

def _payload_schema(payload: dict, name: str, schema: dict) -> dict:
    return {**payload, "text": {"format": {"type": "json_schema", "name": name,
            "strict": True, "schema": schema}}}

def _safe_list(value, limit: int, max_length: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry[:max_length] for entry in value[:limit] if isinstance(entry, str)]

def _grounded_candidates(values, source_text: str) -> list[str]:
    source = source_text.casefold()
    return [value for value in _safe_list(values, 5, 100) if value.casefold() in source]

def _numbers_are_grounded(text: str, source_text: str) -> bool:
    numbers = set(re.findall(r"(?<![\w])\d[\d,.]*(?:\s?(?:%|mw|gw|kw|km|php|usd|million|billion))?", text, re.I))
    source_numbers = set(re.findall(r"(?<![\w])\d[\d,.]*(?:\s?(?:%|mw|gw|kw|km|php|usd|million|billion))?", source_text, re.I))
    return numbers <= source_numbers

def contains_chinese(text: str) -> bool:
    return any("CJK" in unicodedata.name(char, "") or "IDEOGRAPH" in unicodedata.name(char, "") for char in text)

def validate_title_translation(value, original: str) -> str:
    if not isinstance(value, str):
        return ""
    title = " ".join(value.split()).strip()
    if not title or len(title) > 180 or title.casefold() == (original or "").strip().casefold():
        return ""
    if not contains_chinese(title) or any(unicodedata.category(char).startswith("C") for char in title):
        return ""
    original_numbers = re.findall(r"\d[\d,.]*", original or "")
    translated_numbers = re.findall(r"\d[\d,.]*", title)
    if original_numbers != translated_numbers:
        return ""
    return title

TITLE_TRANSLATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"title_zh": {"type": "string"}}, "required": ["title_zh"]
}

def translate_titles(items: list[dict], limit: int = 10, api_key: str | None = None, model: str | None = None,
                     cache_path: Path = TRANSLATION_CACHE) -> int:
    """Fill missing Chinese titles, preserving originals and failing per-item without raising."""
    cache = _load_title_cache(cache_path)
    for item in items:
        title = item.get("title", "")
        if isinstance(title, str) and title and not item.get("title_zh") and cache.get(_title_cache_key(title)):
            item["title_zh"] = cache[_title_cache_key(title)]
            item["title_zh_ai"] = True
    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        return 0
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    candidates = [item for item in items if isinstance(item.get("title"), str) and item.get("title", "").strip()
                  and not contains_chinese(item["title"]) and not item.get("title_zh")]
    # Reuse successful translations across duplicate headlines and collection runs.
    uncached: dict[str, list[dict]] = {}
    for item in candidates:
        cache_key = _title_cache_key(item["title"])
        cached = cache.get(cache_key)
        if cached:
            item["title_zh"] = cached
            item["title_zh_ai"] = True
            item["title_zh_model"] = model
        else:
            uncached.setdefault(cache_key, []).append(item)
    processed = 0
    for cache_key, duplicates in list(uncached.items())[:max(0, min(50, int(limit)))]:
        item = duplicates[0]
        prompt = {"title": item["title"][:400]}
        payload = {"model": model, "instructions": "Translate this news headline into concise, accurate Simplified Chinese. Return only title_zh. Preserve names and all numbers exactly. Do not add facts, context, or claims. If uncertain, return an empty string.", "input": json.dumps(prompt, ensure_ascii=False), "max_output_tokens": 100}
        try:
            answer = json.loads(_output_text(_request(_payload_schema(payload, "news_title_translation", TITLE_TRANSLATION_SCHEMA), key)))
            translation = validate_title_translation(answer.get("title_zh"), item["title"])
            if translation:
                for duplicate in duplicates:
                    duplicate["title_zh"] = translation
                    duplicate["title_zh_ai"] = True
                    duplicate["title_zh_model"] = model
                cache[cache_key] = translation
                processed += 1
        except Exception:
            # Translation failures are optional and never interrupt collection or backfill.
            continue
    if cache:
        _write_title_cache(cache, cache_path)
    return processed

def _request(payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read(1_000_000).decode("utf-8"))

def _output_text(response: dict) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    pieces = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                pieces.append(content.get("text", ""))
    return "\n".join(pieces)

def enrich(snapshot: dict) -> dict:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    title_cache = _load_title_cache()
    for item in snapshot.get("items", []):
        title = item.get("title", "")
        if isinstance(title, str) and title and not item.get("title_zh") and title_cache.get(_title_cache_key(title)):
            item["title_zh"] = title_cache[_title_cache_key(title)]
            item["title_zh_ai"] = True
    if not key:
        snapshot["ai_status"] = {"status": "disabled", "message": "OPENAI_API_KEY is not configured; core functions remain available."}
        return snapshot
    try:
        limit = max(0, min(10, int(os.environ.get("AI_MAX_RECORDS", "10"))))
    except ValueError:
        limit = 10
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    processed = 0
    for item in snapshot.get("items", [])[:limit]:
        cache_key = _title_cache_key(item.get("title", "")) if item.get("title") else ""
        if cache_key and not item.get("title_zh") and title_cache.get(cache_key):
            item["title_zh"] = title_cache[cache_key]
            item["title_zh_ai"] = True
            item["title_zh_model"] = model
        if item.get("title_zh") or contains_chinese(item.get("title", "")):
            pass
        if item.get("summary_zh"):
            continue
        source = {"title": item.get("title", ""), "summary": item.get("summary", "")[:800]}
        payload = {
            "model": model,
            "instructions": "You assist a public infrastructure intelligence site. Return JSON only with title_zh (a concise accurate Chinese translation of the title, or empty if uncertain), summary_zh (a concise Chinese summary), tags (zero to five topic labels), candidate_entities (zero to five names explicitly present in the text), and candidate_locations (zero to five place names explicitly present in the text). Use only the provided title and short summary. Preserve names and numbers in title translation. All extracted entities/locations are unverified candidates, not facts. Do not infer project truth, amount, capacity, stage, tender status, dates, companies, or locations. If unsupported, return an empty list or empty string.",
            "input": json.dumps(source, ensure_ascii=False),
            "max_output_tokens": 180
        }
        payload = _payload_schema(payload, "news_enrichment", EXTRACTION_SCHEMA)
        try:
            response = _request(payload, key)
            answer = json.loads(_output_text(response))
            summary = answer.get("summary_zh", "")
            title_zh = validate_title_translation(answer.get("title_zh"), source["title"])
            if title_zh and not item.get("title_zh"):
                item["title_zh"] = title_zh
                item["title_zh_ai"] = True
                item["title_zh_model"] = model
            if title_zh and cache_key:
                title_cache[cache_key] = title_zh
            if isinstance(summary, str) and _numbers_are_grounded(summary, f"{source['title']} {source['summary']}"):
                entities = _grounded_candidates(answer.get("candidate_entities"), f"{source['title']} {source['summary']}")
                locations = _grounded_candidates(answer.get("candidate_locations"), f"{source['title']} {source['summary']}")
                item["summary_zh"] = summary[:360]
                item["ai_generated"] = True
                item["ai_model"] = model
                item["tags"] = _safe_list(answer.get("tags"), 5, 40)
                item["ai_extraction"] = {
                    "candidate_entities": entities,
                    "candidate_locations": locations,
                    "evidence": [{
                        "url": item.get("link"), "source_name": item.get("publisher", "RSS source"),
                        "published_at": item.get("published_at"), "observed_at": item.get("observed_at"),
                        "quote_or_fact": f"{source['title']} {source['summary']}".strip()[:800],
                        "supports_fields": ["candidate_entities", "candidate_locations"]
                    }] if (entities or locations) and item.get("link") else [],
                    "verification_status": "unverified"
                }
                processed += 1
        except Exception as exc:  # API/model/JSON failures are deliberately non-fatal
            item["ai_error"] = str(exc).replace("\n", " ")[:160]
    analyzed = 0
    for opportunity in snapshot.get("opportunities", [])[:max(0, limit-processed)]:
        project = next((p for p in snapshot.get("projects", []) if p.get("project_id") == opportunity.get("project_id")), None)
        if not project or project.get("verification_status") != "verified":
            continue
        prompt = {
            "project_name": project.get("name"),
            "sector": project.get("sector"),
            "stage": project.get("stage"),
            "description": (project.get("description") or "")[:500],
            "evidence": [{"url": e.get("url"), "fact": (e.get("quote_or_fact") or "")[:180]}
                         for e in project.get("evidence", [])[:4]]
        }
        payload = {
            "model": model,
            "instructions": "Return JSON only with rationale (short Chinese analysis of possible supplier/EPC/cooperation research direction), risks (up to four), and next_checks (up to four). This is an unverified opportunity hypothesis, not a claim that procurement exists. Use only provided project fields and evidence. Do not invent amounts, capacities, schedules, tenders, counterparties, or facts. Explicitly say when evidence is insufficient.",
            "input": json.dumps(prompt, ensure_ascii=False), "max_output_tokens": 240
        }
        payload = _payload_schema(payload, "opportunity_analysis", OPPORTUNITY_SCHEMA)
        try:
            answer = json.loads(_output_text(_request(payload, key)))
            evidence_text = json.dumps(prompt, ensure_ascii=False)
            rationale = answer.get("rationale", "")
            if not isinstance(rationale, str) or not _numbers_are_grounded(rationale, evidence_text):
                raise ValueError("AI opportunity rationale contains ungrounded numeric claims")
            opportunity["ai_analysis"] = {
                "rationale": rationale[:500],
                "risks": _safe_list(answer.get("risks"), 4, 180),
                "next_checks": _safe_list(answer.get("next_checks"), 4, 180),
                "verification_status": "suggested_unverified", "model": model
            }
            analyzed += 1
        except Exception as exc:
            opportunity["ai_error"] = str(exc).replace("\n", " ")[:160]
    if title_cache:
        _write_title_cache(title_cache)
    snapshot["ai_status"] = {"status": "ok" if processed or analyzed else "no_output", "processed": processed, "analyzed_opportunities": analyzed, "model": model}
    return snapshot
