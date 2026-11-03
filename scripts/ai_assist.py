"""Optional server-side OpenAI Responses API enrichment; safe no-op without a key."""
from __future__ import annotations
import json
import os
import urllib.request
import re

ENDPOINT = "https://api.openai.com/v1/responses"

EXTRACTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "summary_zh": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "candidate_entities": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "candidate_locations": {"type": "array", "items": {"type": "string"}, "maxItems": 5}
    }, "required": ["summary_zh", "tags", "candidate_entities", "candidate_locations"]
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
        if item.get("summary_zh"):
            continue
        source = {"title": item.get("title", ""), "summary": item.get("summary", "")[:800]}
        payload = {
            "model": model,
            "instructions": "You assist a public infrastructure intelligence site. Return JSON only with summary_zh (a concise Chinese summary), tags (zero to five topic labels), candidate_entities (zero to five names explicitly present in the text), and candidate_locations (zero to five place names explicitly present in the text). Use only the provided title and short summary. All extracted entities/locations are unverified candidates, not facts. Do not infer project truth, amount, capacity, stage, tender status, dates, companies, or locations. If unsupported, return an empty list or empty string.",
            "input": json.dumps(source, ensure_ascii=False),
            "max_output_tokens": 180
        }
        payload = _payload_schema(payload, "news_enrichment", EXTRACTION_SCHEMA)
        try:
            response = _request(payload, key)
            answer = json.loads(_output_text(response))
            summary = answer.get("summary_zh", "")
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
    snapshot["ai_status"] = {"status": "ok" if processed or analyzed else "no_output", "processed": processed, "analyzed_opportunities": analyzed, "model": model}
    return snapshot
