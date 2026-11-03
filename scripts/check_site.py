#!/usr/bin/env python3
"""Offline structural checks for the static page set and local assets."""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = ("index.html", "intelligence.html", "projects.html", "map.html", "companies.html", "opportunities.html")

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.refs=[]; self.pages=[]; self.external=[]; self.main_count=0; self.has_status=False
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag == "main" and values.get("data-page"):
            self.pages.append(values["data-page"]); self.main_count+=1
        if values.get("id") == "load-status": self.has_status=True
        for key in ("href", "src"):
            ref=values.get(key, "")
            if ref: self.refs.append(ref)
        href=values.get("href", "")
        if href.startswith("https://") and values.get("target") == "_blank":
            self.external.append((href, values.get("rel", "")))

def inspect_page(path: Path) -> list[str]:
    errors=[]; parser=PageParser()
    try: parser.feed(path.read_text(encoding="utf-8"))
    except Exception as exc: return [f"{path.name}: HTML parse error: {exc}"]
    if parser.main_count != 1: errors.append(f"{path.name}: expected exactly one main[data-page]")
    if not parser.has_status: errors.append(f"{path.name}: missing data load status element")
    for ref in parser.refs:
        if ref.startswith("./"):
            local=ref[2:].split("#",1)[0].split("?",1)[0]
            if local and not (SITE / local).is_file(): errors.append(f"{path.name}: missing local asset/page {ref}")
    for href, rel in parser.external:
        if not {"noopener", "noreferrer"}.issubset(set(rel.split())):
            errors.append(f"{path.name}: external new-tab link lacks safe rel: {href}")
    return errors

def main() -> int:
    errors=[]
    for page in PAGES:
        path=SITE/page
        if not path.is_file(): errors.append(f"missing required page {page}")
        else: errors.extend(inspect_page(path))
    if errors:
        print("Static site check failed:")
        for error in errors: print(f"- {error}")
        return 1
    print(f"Static site check passed ({len(PAGES)} pages).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
