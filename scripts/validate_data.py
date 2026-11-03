#!/usr/bin/env python3
"""Validate human maintained PH Infra Watch JSON without external packages."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"

def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

def valid_https(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc)

def valid_iso_datetime(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None
    except ValueError:
        return False

def validate_records(overrides=None):
    overrides = overrides or {}
    def records(filename, key):
        payload = overrides.get(filename)
        return (payload if payload is not None else read_json(CONFIG / filename)).get(key, [])
    errors = []
    projects = records("manual_projects.json", "projects")
    companies = records("manual_companies.json", "companies")
    relationships = records("manual_relationships.json", "relationships")
    opportunities = records("manual_opportunities.json", "opportunities")
    project_ids = set()
    company_ids = set()

    def evidence_ok(record, label):
        evidence = record.get("evidence", [])
        if not evidence:
            errors.append(f"{label}: at least one evidence record is required")
        for entry in evidence:
            if not valid_https(entry.get("url", "")):
                errors.append(f"{label}: evidence URL must use HTTPS")
            if not entry.get("observed_at"):
                errors.append(f"{label}: evidence observed_at is required")
            if not isinstance(entry.get("supports_fields"), list) or not entry.get("supports_fields"):
                errors.append(f"{label}: evidence supports_fields is required")
            if not entry.get("quote_or_fact"):
                errors.append(f"{label}: evidence quote_or_fact is required")

    for idx, item in enumerate(projects):
        label = f"project[{idx}]"
        pid = item.get("project_id")
        if not pid or pid in project_ids:
            errors.append(f"{label}: project_id is required and must be unique")
        project_ids.add(pid)
        if not item.get("name"):
            errors.append(f"{label}: name is required")
        status = item.get("verification_status", "pending_review")
        if status not in {"pending_review", "verified", "needs_review"}:
            errors.append(f"{label}: invalid verification_status")
        evidence_ok(item, label)
        if status == "verified" and (not item.get("verified_by") or not valid_iso_datetime(item.get("verified_at"))):
            errors.append(f"{label}: verified records require verified_by and timezone-aware ISO 8601 verified_at")
        if item.get("sector") and item["sector"] not in {"energy", "telecommunications", "cross_sector", "general", "infrastructure"}:
            errors.append(f"{label}: invalid sector")
        if item.get("island_group") and item["island_group"] not in {"Luzon", "Visayas", "Mindanao"}:
            errors.append(f"{label}: island_group must be Luzon, Visayas or Mindanao")
        if item.get("island_group") and not any("island_group" in entry.get("supports_fields", []) for entry in item.get("evidence", [])):
            errors.append(f"{label}: island_group requires supporting evidence")
        if status == "verified":
            supported = {field for entry in item.get("evidence", []) for field in entry.get("supports_fields", [])}
            for field in ("name", "sector", "stage", "province", "region", "island_group", "coordinates", "capacity", "budget", "owner", "developer", "contractors"):
                if item.get(field) is not None and field not in supported:
                    errors.append(f"{label}: verified field {field} is not linked to evidence supports_fields")
        coords = item.get("coordinates")
        if coords is not None:
            try:
                lat, lon = float(coords["lat"]), float(coords["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors.append(f"{label}: coordinates must contain valid lat/lon values")
            else:
                if not any("coordinates" in entry.get("supports_fields", []) for entry in item.get("evidence", [])):
                    errors.append(f"{label}: coordinates require evidence that supports coordinates")

    for idx, item in enumerate(companies):
        label = f"company[{idx}]"
        cid = item.get("company_id")
        if not cid or cid in company_ids:
            errors.append(f"{label}: company_id is required and must be unique")
        company_ids.add(cid)
        if not item.get("name"):
            errors.append(f"{label}: name is required")
        evidence_ok(item, label)
        status = item.get("verification_status", "pending_review")
        if status not in {"pending_review", "verified", "needs_review"}:
            errors.append(f"{label}: invalid verification_status")
        if status == "verified" and (not item.get("verified_by") or not valid_iso_datetime(item.get("verified_at"))):
            errors.append(f"{label}: verified records require verified_by and timezone-aware ISO 8601 verified_at")
        if status == "verified":
            supported = {field for entry in item.get("evidence", []) for field in entry.get("supports_fields", [])}
            for field in ("name", "entity_type", "country", "website", "aliases"):
                if item.get(field) is not None and field not in supported:
                    errors.append(f"{label}: verified field {field} is not linked to evidence supports_fields")
        if item.get("website") and not valid_https(item["website"]):
            errors.append(f"{label}: website must use HTTPS")

    relationship_ids = set()
    for idx, rel in enumerate(relationships):
        label = f"relationship[{idx}]"
        rid = rel.get("relationship_id")
        if not rid or rid in relationship_ids:
            errors.append(f"{label}: relationship_id is required and must be unique")
        relationship_ids.add(rid)
        if rel.get("company_id") not in company_ids:
            errors.append(f"{label}: company_id does not exist")
        if rel.get("project_id") not in project_ids:
            errors.append(f"{label}: project_id does not exist")
        if not rel.get("role"):
            errors.append(f"{label}: role is required")
        if rel.get("role") not in {"owner", "developer", "epc", "operator", "supplier", "investor", "unknown"}:
            errors.append(f"{label}: invalid role")
        rel_status = rel.get("verification_status", "pending_review")
        if rel_status not in {"pending_review", "verified", "needs_review"}:
            errors.append(f"{label}: invalid verification_status")
        evidence_ok(rel, label)
        if rel_status == "verified":
            if not rel.get("verified_by") or not valid_iso_datetime(rel.get("verified_at")):
                errors.append(f"{label}: verified relationship requires reviewer and timezone-aware ISO 8601 verified_at")
            supported = {field for entry in rel.get("evidence", []) for field in entry.get("supports_fields", [])}
            for field in ("company_id", "project_id", "role"):
                if field not in supported:
                    errors.append(f"{label}: verified field {field} is not linked to evidence supports_fields")

    for idx, item in enumerate(opportunities):
        label = f"opportunity[{idx}]"
        if not item.get("opportunity_id") or not item.get("title"):
            errors.append(f"{label}: opportunity_id and title are required")
        evidence_ok(item, label)
        if item.get("project_id") and item.get("project_id") not in project_ids:
            errors.append(f"{label}: project_id does not exist")
        for company_id in item.get("company_ids", []):
            if company_id not in company_ids:
                errors.append(f"{label}: company_id {company_id} does not exist")
        if item.get("verification_status", "suggested_unverified") not in {"pending_review", "verified", "needs_review", "suggested_unverified"}:
            errors.append(f"{label}: invalid verification_status")
        if item.get("verification_status") == "verified" and (not item.get("verified_by") or not valid_iso_datetime(item.get("verified_at"))):
            errors.append(f"{label}: verified opportunity requires reviewer and timezone-aware ISO 8601 verified_at")
        if item.get("verification_status") == "verified":
            supported = {field for entry in item.get("evidence", []) for field in entry.get("supports_fields", [])}
            for field in ("title", "opportunity_type", "project_id", "company_ids", "rationale"):
                if item.get(field) is not None and field not in supported:
                    errors.append(f"{label}: verified field {field} is not linked to evidence supports_fields")
    return errors

def main() -> int:
    errors = validate_records()
    if errors:
        print("Data validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Manual data validation passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
