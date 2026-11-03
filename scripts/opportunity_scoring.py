"""Transparent, evidence-aware 0–100 follow-up priority score."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

MAXIMA = {
    "evidence_completeness": 35,
    "demand_clarity": 30,
    "stage_procurement": 20,
    "information_freshness": 15,
}
SUPPORTED_FIELDS = ("name", "sector", "stage", "region", "coordinates", "capacity", "budget", "owner", "developer", "contractors")


def _date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None


def score_opportunity(opportunity: dict, project: dict | None, now: datetime | None = None) -> dict:
    """Score only declared source/project evidence; preserve all verification states."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    evidence_source = (project or {}).get("evidence", []) if project else opportunity.get("evidence", [])
    evidence = [e for e in evidence_source if isinstance(e, dict)]
    evidence = [e for e in evidence if urlparse(e.get("url", "")).scheme == "https" and e.get("quote_or_fact")]
    source_domains = {urlparse(e["url"]).netloc.lower() for e in evidence}
    covered = {field for e in evidence for field in e.get("supports_fields", [])}
    evidence_score = min(15, 5 * len(source_domains)) + min(20, 2 * sum(field in covered for field in SUPPORTED_FIELDS))
    evidence_reason = f"{len(source_domains)} 个不同来源域名，支持 {sum(field in covered for field in SUPPORTED_FIELDS)} 个核心字段。"

    original_text = " ".join(str(e.get("quote_or_fact") or "") for e in evidence).casefold()
    tender_terms = ("open tender", "tender notice", "procurement", "request for proposal", "request for quotation", "rfp", "bidding", "bid submission", "supply contract", "purchase contract", "招标", "采购", "投标", "供货合同")
    equipment_terms = ("equipment requirement", "supply and installation", "equipment supply", "supply of", "采购需求", "设备需求", "设备采购", "供货")
    negated_demand = any(term in original_text for term in ("no tender", "no procurement", "not yet tender", "not yet procured", "without tender", "no confirmed procurement", "尚未确认采购", "未发布招标", "暂无招标", "没有采购", "不代表存在采购"))
    if negated_demand:
        demand_score, demand_reason = 0, "原始证据未确认或明确否定采购；不计商业需求分。"
    elif any(term in original_text for term in tender_terms):
        demand_score, demand_reason = 30, "原始证据明确出现招标、采购、投标或供货合同信息。"
    elif any(term in original_text for term in equipment_terms):
        demand_score, demand_reason = 18, "原始证据提及设备/供货需求，但未确认正式招标。"
    else:
        demand_score, demand_reason = 0, "现有原始证据没有明确采购或设备需求；不得从 AI 推测补分。"

    stage = str((project or {}).get("stage") or "").casefold().replace(" ", "_")
    if not negated_demand and (any(term in original_text for term in tender_terms) or stage in {"tender", "procurement", "bidding", "招标", "采购"}):
        stage_score, stage_reason = 20, "项目阶段或原始证据与招标采购直接相关。"
    elif stage in {"construction", "under_construction", "建设中", "施工"}:
        stage_score, stage_reason = 14, "已进入建设阶段，存在跟进工程采购窗口的理由。"
    elif stage in {"approved", "approved_development", "核准", "已批准"}:
        stage_score, stage_reason = 11, "项目已获批，但现有资料未证明已进入采购。"
    elif stage in {"planning", "planned", "规划", "计划"}:
        stage_score, stage_reason = 7, "仍处于规划阶段，采购时间和执行情况未确定。"
    else:
        stage_score, stage_reason = 0, "没有可用的人工核验项目阶段信息。"

    dated = [_date(e.get("published_at")) or _date(e.get("observed_at")) for e in evidence]
    dated = [d for d in dated if d]
    latest = max(dated) if dated else None
    if latest and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age_days = max(0, (now.astimezone(timezone.utc) - latest.astimezone(timezone.utc)).days) if latest else None
    if age_days is None:
        freshness_score, freshness_reason = 0, "来源没有可解析的发布时间或核查时间。"
    elif age_days <= 30:
        freshness_score, freshness_reason = 15, f"最新证据约 {age_days} 天。"
    elif age_days <= 90:
        freshness_score, freshness_reason = 11, f"最新证据约 {age_days} 天。"
    elif age_days <= 180:
        freshness_score, freshness_reason = 7, f"最新证据约 {age_days} 天，时效性下降。"
    elif age_days <= 365:
        freshness_score, freshness_reason = 3, f"最新证据约 {age_days} 天，需重新核实。"
    else:
        freshness_score, freshness_reason = 0, f"最新证据约 {age_days} 天，已较陈旧。"

    dimensions = {
        "evidence_completeness": {"score": evidence_score, "max": MAXIMA["evidence_completeness"], "reason": evidence_reason},
        "demand_clarity": {"score": demand_score, "max": MAXIMA["demand_clarity"], "reason": demand_reason},
        "stage_procurement": {"score": stage_score, "max": MAXIMA["stage_procurement"], "reason": stage_reason},
        "information_freshness": {"score": freshness_score, "max": MAXIMA["information_freshness"], "reason": freshness_reason},
    }
    total = sum(d["score"] for d in dimensions.values())
    caps = []
    # One source cannot establish a well-supported commercial lead.
    if len(source_domains) < 2 and total > 45:
        total = 45
        caps.append("少于两条独立来源，总分上限 45 分。")
    # A news lead or a project awaiting review cannot receive a high priority score.
    if not project or project.get("verification_status") != "verified":
        if total > 30:
            total = 30
        caps.append("没有已核验项目档案，总分上限 30 分。")
    return {
        "total": total,
        "dimensions": dimensions,
        "reasons": [d["reason"] for d in dimensions.values()] + caps,
        "caps": caps,
        "updated_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "note": "该分数仅用于情报跟进优先级，不代表项目真实性或成交概率。",
    }
