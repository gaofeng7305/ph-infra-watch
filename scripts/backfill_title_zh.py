"""Controlled, optional backfill of missing Chinese news headline translations."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from ai_assist import translate_titles

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "site" / "data" / "data.json"

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="Maximum titles to attempt (1–50; default 10)")
    parser.add_argument("--data", type=Path, default=DATA_FILE, help="Snapshot JSON path (defaults to site/data/data.json)")
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("OPENAI_API_KEY is not configured; no translations generated and no file written.")
        return 2
    snapshot = json.loads(args.data.read_text(encoding="utf-8"))
    updated = translate_titles(snapshot.get("items", []), args.limit)
    if updated:
        temporary = args.data.with_name(".tmp-" + args.data.name)
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.data)
    print(f"Added {updated} title translation(s); original titles and verification fields were preserved.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
