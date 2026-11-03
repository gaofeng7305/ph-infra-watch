#!/usr/bin/env python3
"""Check the publish snapshot's shape and traceability before deployment."""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "site" / "data" / "data.json"

def check(snapshot: dict) -> list[str]:
    errors = []
    for key in ("items", "projects", "companies", "relationships", "opportunities", "source_health", "official_portals"):
        if not isinstance(snapshot.get(key), list):
            errors.append(f"{key} must be an array")
    for index, item in enumerate(snapshot.get("items", [])):
        if item.get("kind") != "lead":
            errors.append(f"items[{index}] must be kind=lead")
        if item.get("verification_status") == "verified":
            errors.append(f"items[{index}] RSS discoveries cannot be marked verified")
        if not str(item.get("link", "")).startswith("https://"):
            errors.append(f"items[{index}] link must use HTTPS")
        extraction = item.get("ai_extraction")
        if extraction:
            allowed = {"candidate_entities", "candidate_locations", "evidence", "verification_status"}
            if set(extraction) - allowed:
                errors.append(f"items[{index}] AI extraction contains unsupported factual fields")
            if extraction.get("verification_status") != "unverified":
                errors.append(f"items[{index}] AI extraction must remain unverified")
            source_text = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
            candidates = list(extraction.get("candidate_entities", [])) + list(extraction.get("candidate_locations", []))
            for candidate in candidates:
                if not isinstance(candidate, str) or candidate.casefold() not in source_text:
                    errors.append(f"items[{index}] AI candidate is not present in source text")
            if candidates and not any(e.get("url") == item.get("link") and e.get("quote_or_fact") and
                                      {"candidate_entities", "candidate_locations"}.issubset(set(e.get("supports_fields", [])))
                                      and all(c.casefold() in e.get("quote_or_fact", "").casefold() for c in candidates if isinstance(c, str))
                                      for e in extraction.get("evidence", [])):
                errors.append(f"items[{index}] AI candidates lack source evidence")
    for index, project in enumerate(snapshot.get("projects", [])):
        if project.get("verification_status") == "verified" and (not project.get("evidence") or not project.get("verified_by") or not project.get("verified_at")):
            errors.append(f"projects[{index}] verified record lacks evidence or reviewer metadata")
    maxima = {"evidence_completeness": 35, "demand_clarity": 30,
              "stage_procurement": 20, "information_freshness": 15}
    for index, opportunity in enumerate(snapshot.get("opportunities", [])):
        score = opportunity.get("opportunity_score") or {}
        if not isinstance(score.get("total"), int) or not 0 <= score["total"] <= 100:
            errors.append(f"opportunities[{index}] score total must be an integer from 0 to 100")
            continue
        dimensions = score.get("dimensions", {})
        for key, maximum in maxima.items():
            dimension = dimensions.get(key, {})
            value = dimension.get("score")
            if dimension.get("max") != maximum or not isinstance(value, int) or not 0 <= value <= maximum:
                errors.append(f"opportunities[{index}] invalid score dimension {key}")
        if not score.get("updated_at"):
            errors.append(f"opportunities[{index}] score updated_at is required")
        analysis = opportunity.get("ai_analysis")
        if analysis:
            allowed = {"rationale", "risks", "next_checks", "verification_status", "model"}
            if set(analysis) - allowed:
                errors.append(f"opportunities[{index}] AI analysis contains unsupported factual fields")
            if analysis.get("verification_status") != "suggested_unverified":
                errors.append(f"opportunities[{index}] AI analysis must remain suggested_unverified")
    return errors

def main() -> int:
    try:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Snapshot is not valid JSON: {exc}")
        return 1
    errors = check(snapshot)
    if errors:
        for error in errors:
            print(f"- {error}")
        return 1
    print("Publish snapshot check passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
