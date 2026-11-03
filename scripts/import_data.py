#!/usr/bin/env python3
"""Append evidence-backed JSON/CSV records as pending review; never invent records."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from validate_data import validate_records

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
FILES = {
    "projects": ("manual_projects.json", "projects"),
    "companies": ("manual_companies.json", "companies"),
    "relationships": ("manual_relationships.json", "relationships"),
    "opportunities": ("manual_opportunities.json", "opportunities"),
}
ALLOWED = {
    "projects": {"project_id", "name", "sector", "description", "stage", "province", "region", "island_group", "coordinates", "capacity", "budget", "owner", "developer", "contractors", "evidence", "verification_status", "verified_by", "verified_at"},
    "companies": {"company_id", "name", "aliases", "entity_type", "country", "website", "description", "evidence", "verification_status", "verified_by", "verified_at"},
    "relationships": {"relationship_id", "company_id", "project_id", "role", "evidence", "verification_status", "verified_by", "verified_at"},
    "opportunities": {"opportunity_id", "title", "opportunity_type", "project_id", "company_ids", "rationale", "risks", "next_checks", "evidence", "verification_status", "verified_by", "verified_at"},
}
JSON_COLUMNS = {"coordinates", "capacity", "budget", "contractors", "aliases", "company_ids", "risks", "next_checks", "evidence"}


def read_records(path: Path, kind: str, file_format: str = "auto") -> list[dict]:
    fmt = path.suffix.lower().lstrip(".") if file_format == "auto" else file_format
    if fmt == "json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload.get(kind, []) if isinstance(payload, dict) else payload
    elif fmt == "csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        converted = []
        for row in rows:
            record = {}
            for key, value in row.items():
                if value is None or value == "":
                    continue
                if key in JSON_COLUMNS:
                    try:
                        record[key] = json.loads(value)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"CSV field {key} must contain valid JSON: {exc}") from exc
                else:
                    record[key] = value
            converted.append(record)
        rows = converted
    else:
        raise ValueError("Input must be .json or .csv")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Input must contain a non-empty list of {kind} objects")
    return rows


def import_records(kind: str, rows: list[dict], config_dir: Path = CONFIG) -> tuple[int, list[str]]:
    if kind not in FILES:
        return 0, [f"Unsupported record type: {kind}"]
    filename, key = FILES[kind]
    target = config_dir / filename
    payloads = {}
    for record_kind, (name, list_key) in FILES.items():
        source_path = config_dir / name
        payloads[name] = json.loads(source_path.read_text(encoding="utf-8")) if source_path.exists() else {list_key: []}
    existing = payloads[filename].get(key, [])
    prepared = []
    errors = []
    for index, raw in enumerate(rows):
        extra = set(raw) - ALLOWED[kind]
        if extra:
            errors.append(f"row[{index}]: unsupported fields: {', '.join(sorted(extra))}")
            continue
        item = dict(raw)
        # Imported records are never trusted as verified, regardless of input status.
        item["verification_status"] = "pending_review"
        item.pop("verified_by", None)
        item.pop("verified_at", None)
        prepared.append(item)
    id_field = {"projects": "project_id", "companies": "company_id", "relationships": "relationship_id", "opportunities": "opportunity_id"}[kind]
    existing_ids = {item.get(id_field) for item in existing}
    seen = set()
    for index, item in enumerate(prepared):
        value = item.get(id_field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"row[{index}]: {id_field} is required; IDs are never generated")
        elif value in existing_ids or value in seen:
            errors.append(f"row[{index}]: duplicate {id_field}: {value}")
        if isinstance(value, str):
            seen.add(value)
        required_name = "name" if kind in {"projects", "companies"} else "title" if kind == "opportunities" else "role"
        if not isinstance(item.get(required_name), str) or not item[required_name].strip():
            errors.append(f"row[{index}]: {required_name} is required")
    if errors:
        return 0, errors
    payloads[filename][key] = existing + prepared
    errors = validate_records(payloads)
    if errors:
        return 0, errors
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(".tmp-" + target.name)
    temp.write_text(json.dumps(payloads[filename], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return len(prepared), []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import evidence-backed records as pending review.")
    parser.add_argument("--type", choices=FILES, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--format", choices=("auto", "json", "csv"), default="auto")
    args = parser.parse_args(argv)
    try:
        rows = read_records(args.input, args.type, args.format)
        count, errors = import_records(args.type, rows)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Import rejected: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Import rejected; no records were written:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Imported {count} {args.type} record(s) as pending_review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
