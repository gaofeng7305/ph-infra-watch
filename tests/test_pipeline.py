import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai_assist
import collect
import validate_data
import import_data
from opportunity_scoring import score_opportunity
from check_snapshot import check


class PipelineTests(unittest.TestCase):
    def test_canonical_url_removes_tracking_and_requires_https(self):
        self.assertEqual(collect.canonical_url("https://Example.org/story?utm_source=x&id=2#top"), "https://example.org/story?id=2")
        self.assertEqual(collect.canonical_url("http://example.org/story"), "")

    def test_stable_id_is_repeatable(self):
        self.assertEqual(collect.stable_id("https://news.example/a", "Headline"), collect.stable_id("https://news.example/a", "Different"))

    def test_rss_parse_creates_unverified_lead_with_evidence(self):
        xml = b'''<?xml version="1.0"?><rss version="2.0"><channel><item><title>Solar project report</title><link>https://news.example/solar</link><description>Short report</description><pubDate>Tue, 03 Nov 2026 01:00:00 GMT</pubDate></item></channel></rss>'''
        records = collect.parse_feed(xml, {"id": "test-source"}, "2026-11-03T02:00:00Z")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "lead")
        self.assertEqual(records[0]["verification_status"], "unverified")
        self.assertEqual(records[0]["evidence"][0]["url"], "https://news.example/solar")

    def test_rss_parser_drops_cms_untitled_placeholders(self):
        xml = b'''<rss><channel><item><title>Untitled - PPP Center</title><link>https://news.example/cms-page</link></item></channel></rss>'''
        self.assertEqual(collect.parse_feed(xml, {"id": "test-source"}), [])

    def test_atom_feed_supports_link_href(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fiber project</title><link href="https://news.example/fiber"/><summary>Broadband update</summary><updated>2026-11-03T00:00:00Z</updated></entry></feed>'''
        records = collect.parse_feed(xml, {"id": "atom-source"})
        self.assertEqual(records[0]["link"], "https://news.example/fiber")

    def test_merge_deduplicates_by_id_and_preserves_history(self):
        old = [{"id": "same", "title": "old"}, {"id": "keep", "title": "historical"},
               {"id": "cms", "title": "Untitled - Legacy placeholder"}]
        fresh = [{"id": "same", "title": "new"}]
        merged = collect.merge_items(old, fresh)
        self.assertEqual(len(merged), 2)
        self.assertEqual(next(x for x in merged if x["id"] == "same")["title"], "new")
        self.assertIn("keep", {x["id"] for x in merged})
        self.assertNotIn("cms", {x["id"] for x in merged})

    def test_merge_sorts_rfc822_and_iso_publication_times_chronologically(self):
        rows = [
            {"id": "later", "published_at": "Tue, 03 Nov 2026 02:00:00 GMT"},
            {"id": "earlier", "published_at": "Mon, 02 Nov 2026 20:00:00 GMT"},
            {"id": "fallback", "published_at": "not a date", "observed_at": "2026-11-03T01:30:00Z"},
        ]
        self.assertEqual([x["id"] for x in collect.merge_items([], rows)], ["later", "fallback", "earlier"])

    def test_all_source_failure_fails_ci_but_partial_collection_does_not(self):
        self.assertEqual(collect.run_status_exit_code("error"), 1)
        self.assertEqual(collect.run_status_exit_code("partial"), 0)
        self.assertEqual(collect.run_status_exit_code("ok"), 0)

    def test_tender_keyword_is_not_verified_status(self):
        self.assertEqual(collect.classify_stage("Tender announcement"), "tender_keyword")

    def test_rule_opportunity_only_uses_verified_project_and_evidence(self):
        base = {"project_id": "prj-1", "name": "Project", "sector": "energy", "stage": "planning",
                "verification_status": "verified", "evidence": [{"url": "https://official.example/doc"}]}
        pending = {**base, "project_id": "prj-2", "verification_status": "pending_review"}
        self.assertEqual([x["project_id"] for x in collect.derive_opportunities([base, pending])], ["prj-1"])

    def test_ai_is_safe_noop_without_key(self):
        snapshot = {"items": [], "opportunities": [], "projects": []}
        with patch.dict(os.environ, {}, clear=True):
            result = ai_assist.enrich(snapshot)
        self.assertEqual(result["ai_status"]["status"], "disabled")

    def test_ai_schemas_and_grounding_guards(self):
        self.assertTrue(ai_assist.EXTRACTION_SCHEMA["required"])
        self.assertFalse(ai_assist.EXTRACTION_SCHEMA["additionalProperties"])
        for unsupported in ("budget", "capacity", "procurement_demand"):
            self.assertNotIn(unsupported, ai_assist.EXTRACTION_SCHEMA["properties"])
        self.assertTrue(ai_assist._numbers_are_grounded("500 MW", "A 500 MW plan"))
        self.assertFalse(ai_assist._numbers_are_grounded("500 MW", "A project plan"))
        self.assertEqual(ai_assist._grounded_candidates(["DOE", "Invented Corp"], "DOE report"), ["DOE"])

    def test_ai_enrichment_keeps_only_grounded_candidates_and_source(self):
        item = {"id": "lead-1", "title": "DOE solar project", "summary": "DOE plans solar equipment", "link": "https://news.example/a", "publisher": "news.example", "observed_at": "2026-11-03T00:00:00Z", "evidence": [], "verification_status": "unverified"}
        snapshot = {"items": [item], "opportunities": [], "projects": []}
        answer = {"summary_zh": "DOE 计划太阳能设备项目", "tags": ["energy"], "candidate_entities": ["DOE", "Invented Corp"],
                  "candidate_locations": [], "budget": {"value": 999}, "capacity": "999 MW", "verification_status": "verified"}
        response = {"output_text": json.dumps(answer)}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(ai_assist, "_request", return_value=response):
            result = ai_assist.enrich(snapshot)
        self.assertEqual(result["items"][0]["ai_extraction"]["candidate_entities"], ["DOE"])
        self.assertEqual(result["items"][0]["ai_extraction"]["verification_status"], "unverified")
        self.assertEqual(result["items"][0]["ai_extraction"]["evidence"][0]["url"], item["link"])
        self.assertNotIn("budget", result["items"][0])
        self.assertNotIn("capacity", result["items"][0])
        self.assertEqual(result["items"][0]["verification_status"], "unverified")

    def test_all_source_failure_preserves_history_and_last_success(self):
        previous = {"items": [{"id": "historic", "title": "Historic lead"}],
                    "last_success_at": "2026-11-02T10:00:00Z"}
        source_config = {"sources": [{"id": "test-feed", "enabled": True}], "official_portals": []}
        def fake_read(path, default=None):
            return previous if Path(path).name == "data.json" else source_config
        failed = ({"source_id": "test-feed", "status": "error", "item_count": 0,
                   "checked_at": "2026-11-03T10:00:00Z", "message": "offline"}, [])
        with patch.object(collect, "read_json", side_effect=fake_read), \
             patch.object(collect, "fetch_source", return_value=failed), \
             patch.object(collect, "load_manual", return_value={"projects": [], "companies": [], "relationships": [], "opportunities": []}), \
             patch.object(collect, "atomic_write") as write:
            result = collect.run_collection()
        self.assertEqual(result["run_status"], "error")
        self.assertEqual(result["items"], previous["items"])
        self.assertEqual(result["last_success_at"], previous["last_success_at"])
        write.assert_called_once()

    def test_snapshot_rejects_verified_rss_lead(self):
        snapshot = {k: [] for k in ("items", "projects", "companies", "relationships", "opportunities", "source_health", "official_portals")}
        snapshot["items"] = [{"kind": "lead", "verification_status": "verified", "link": "https://news.example"}]
        self.assertTrue(any("cannot be marked verified" in error for error in check(snapshot)))

    def test_snapshot_rejects_unsupported_ai_extracted_fact_fields(self):
        snapshot = {k: [] for k in ("items", "projects", "companies", "relationships", "opportunities", "source_health", "official_portals")}
        snapshot["items"] = [{"kind": "lead", "verification_status": "unverified", "link": "https://news.example/a",
            "title": "DOE news", "summary": "Public source", "ai_extraction": {"candidate_entities": ["DOE"],
            "candidate_locations": [], "verification_status": "unverified", "evidence": [{"url": "https://news.example/a",
            "quote_or_fact": "DOE news", "supports_fields": ["candidate_entities", "candidate_locations"]}], "capacity": "500 MW"}}]
        self.assertTrue(any("unsupported factual fields" in error for error in check(snapshot)))

    def test_manual_data_empty_config_is_valid(self):
        payloads = {
            "manual_projects.json": {"projects": []},
            "manual_companies.json": {"companies": []},
            "manual_relationships.json": {"relationships": []},
            "manual_opportunities.json": {"opportunities": []}
        }
        with patch.object(validate_data, "read_json", side_effect=lambda path: payloads[Path(path).name]):
            self.assertEqual(validate_data.validate_records(), [])

    def test_verified_project_requires_review_evidence_and_metadata(self):
        payloads = {
            "manual_projects.json": {"projects": [{"project_id": "p-1", "name": "Project", "verification_status": "verified", "evidence": []}]},
            "manual_companies.json": {"companies": []}, "manual_relationships.json": {"relationships": []}, "manual_opportunities.json": {"opportunities": []}
        }
        with patch.object(validate_data, "read_json", side_effect=lambda path: payloads[Path(path).name]):
            errors = validate_data.validate_records()
            self.assertTrue(any("timezone-aware ISO 8601 verified_at" in error for error in errors))
            self.assertTrue(any("evidence" in error for error in errors))

    def test_manual_validation_checks_relationship_identity_status_and_review_time(self):
        evidence = [{"url": "https://agency.example/source", "observed_at": "2026-11-03T00:00:00Z",
                     "supports_fields": ["name"], "quote_or_fact": "Source note"}]
        payloads = {
            "manual_projects.json": {"projects": [{"project_id": "p-1", "name": "P", "verification_status": "verified",
                "verified_by": "reviewer", "verified_at": "yesterday", "evidence": evidence}]},
            "manual_companies.json": {"companies": [{"company_id": "c-1", "name": "C", "verification_status": "pending_review", "evidence": evidence}]},
            "manual_relationships.json": {"relationships": [{"relationship_id": "r-1", "company_id": "c-1", "project_id": "p-1",
                "role": "epc", "verification_status": "maybe", "evidence": evidence},
                {"relationship_id": "r-1", "company_id": "c-1", "project_id": "p-1", "role": "epc", "evidence": evidence}]},
            "manual_opportunities.json": {"opportunities": []}
        }
        with patch.object(validate_data, "read_json", side_effect=lambda path: payloads[Path(path).name]):
            errors = validate_data.validate_records()
        self.assertTrue(any("timezone-aware ISO 8601 verified_at" in error for error in errors))
        self.assertTrue(any("relationship_id" in error for error in errors))
        self.assertTrue(any("invalid verification_status" in error for error in errors))

    def test_opportunity_score_dimensions_caps_and_unverified_news(self):
        now = collect.datetime(2026, 11, 3, tzinfo=collect.timezone.utc)
        fields = list(__import__("opportunity_scoring").SUPPORTED_FIELDS)
        evidence = [{"url": "https://agency.example/tender", "quote_or_fact": "Open tender for equipment supply", "published_at": "2026-10-20T00:00:00Z", "supports_fields": fields},
                    {"url": "https://company.example/project", "quote_or_fact": "Solar procurement and bidding", "published_at": "2026-10-21T00:00:00Z", "supports_fields": fields},
                    {"url": "https://regulator.example/approval", "quote_or_fact": "Project record confirmed", "published_at": "2026-10-22T00:00:00Z", "supports_fields": fields}]
        project = {"verification_status": "verified", "stage": "tender", "evidence": evidence}
        score = score_opportunity({"verification_status": "suggested_unverified"}, project, now)
        self.assertEqual(score["total"], 100)
        self.assertEqual(sum(x["max"] for x in score["dimensions"].values()), 100)
        self.assertEqual(score["updated_at"], "2026-11-03T00:00:00Z")
        one_source = score_opportunity({}, {**project, "evidence": evidence[:1]}, now)
        self.assertLessEqual(one_source["total"], 45)
        news_score = score_opportunity({"evidence": evidence}, None, now)
        self.assertLessEqual(news_score["total"], 30)
        negative = score_opportunity({}, {**project, "stage": "planning", "evidence": [{**evidence[0], "quote_or_fact": "No confirmed procurement; this is not yet tendered."}]}, now)
        self.assertEqual(negative["dimensions"]["demand_clarity"]["score"], 0)
        self.assertEqual(negative["dimensions"]["stage_procurement"]["score"], 7)

    def test_import_appends_pending_records_and_rejects_bad_evidence_atomically(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            root = Path(temp)
            for filename, key in (("manual_projects.json", "projects"), ("manual_companies.json", "companies"),
                                  ("manual_relationships.json", "relationships"), ("manual_opportunities.json", "opportunities")):
                (root / filename).write_text(json.dumps({key: []}), encoding="utf-8")
            row = {"project_id": "source-supplied-id", "name": "Human-provided title", "sector": "energy",
                   "verification_status": "verified", "verified_by": "Importer should remove this",
                   "evidence": [{"url": "https://agency.example/item", "observed_at": "2026-11-03T00:00:00Z",
                                 "quote_or_fact": "Source excerpt", "supports_fields": ["name", "sector"]}]}
            count, errors = import_data.import_records("projects", [row], root)
            self.assertEqual((count, errors), (1, []))
            saved = json.loads((root / "manual_projects.json").read_text(encoding="utf-8"))["projects"][0]
            self.assertEqual(saved["verification_status"], "pending_review")
            self.assertNotIn("verified_by", saved)
            bad = {**row, "project_id": "bad-project", "evidence": [{**row["evidence"][0], "url": "http://bad.example"}]}
            before = (root / "manual_projects.json").read_text(encoding="utf-8")
            count, errors = import_data.import_records("projects", [bad], root)
            self.assertEqual(count, 0)
            self.assertTrue(any("HTTPS" in error for error in errors))
            self.assertEqual((root / "manual_projects.json").read_text(encoding="utf-8"), before)

    def test_import_supported_record_types_default_to_pending_review(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            root = Path(temp)
            for filename, key in (("manual_projects.json", "projects"), ("manual_companies.json", "companies"),
                                  ("manual_relationships.json", "relationships"), ("manual_opportunities.json", "opportunities")):
                (root / filename).write_text(json.dumps({key: []}), encoding="utf-8")
            def source(field):
                return [{"url": f"https://source.example/{field}", "observed_at": "2026-11-03T00:00:00Z",
                         "quote_or_fact": "Human-supplied source note", "supports_fields": [field]}]
            rows = {
                "projects": [{"project_id": "p-1", "name": "Provided project", "evidence": source("name")}],
                "companies": [{"company_id": "c-1", "name": "Provided company", "evidence": source("name")}],
                "relationships": [{"relationship_id": "r-1", "company_id": "c-1", "project_id": "p-1", "role": "epc", "evidence": source("role")}],
                "opportunities": [{"opportunity_id": "o-1", "title": "Provided research lead", "project_id": "p-1", "evidence": source("title")}],
            }
            for kind, items in rows.items():
                count, errors = import_data.import_records(kind, items, root)
                self.assertEqual((count, errors), (1, []), kind)
                filename, key = import_data.FILES[kind]
                record = json.loads((root / filename).read_text(encoding="utf-8"))[key][0]
                self.assertEqual(record["verification_status"], "pending_review", kind)

    def test_csv_import_parser_reads_nested_evidence_json(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            path = Path(temp) / "records.csv"
            path.write_text('project_id,name,evidence\np-1,Provided,"[{""url"":""https://example.org/s"",""observed_at"":""2026-11-03T00:00:00Z"",""quote_or_fact"":""source"",""supports_fields"":[""name""]}]"\n', encoding="utf-8")
            rows = import_data.read_records(path, "projects")
            self.assertEqual(rows[0]["evidence"][0]["url"], "https://example.org/s")


if __name__ == "__main__":
    unittest.main()
