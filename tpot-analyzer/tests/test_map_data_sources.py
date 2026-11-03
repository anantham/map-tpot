"""Test intent:
- Exact-ID joins retain contacts/work/tags without same-handle merges.
- Missing/corrupt/duplicate-ID sources remain explicit, not healthy emptiness.
- Read-only joins leave sources byte-for-byte unchanged, including tag events.
- Existing output files are never overwritten.

All sources are synthetic, isolated before import. No application is imported.
"""
import csv
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_map_data_sources.py"
spec = importlib.util.spec_from_file_location("map_sources", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MapSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive, self.shadow, self.tags = [self.root / (name + ".db") for name in ("archive", "shadow", "tags")]
        with sqlite3.connect(self.archive) as conn:
            conn.executescript("""
                CREATE TABLE profiles(account_id TEXT PRIMARY KEY, username TEXT, bio TEXT, website TEXT);
                INSERT INTO profiles VALUES ('1234567890123456789','example','public bio','https://example.org');
                CREATE TABLE tweets(tweet_id TEXT, account_id TEXT);
                INSERT INTO tweets VALUES ('post1','1234567890123456789');
                CREATE TABLE bio_link_profile(account_id TEXT, signal_links_json TEXT, html_gz BLOB);
                INSERT INTO bio_link_profile VALUES ('1234567890123456789','["https://bsky.app/profile/example.org"]',X'0102');
            """)
        with sqlite3.connect(self.shadow) as conn:
            conn.executescript("""
                CREATE TABLE shadow_account(account_id TEXT PRIMARY KEY, username TEXT, bio TEXT);
                INSERT INTO shadow_account VALUES ('shadow:example','example','unresolved alias');
                CREATE TABLE shadow_edge(source_id TEXT, target_id TEXT);
            """)
        with sqlite3.connect(self.tags) as conn:
            conn.executescript("""
                CREATE TABLE account_tags(ego TEXT, account_id TEXT, tag_key TEXT, polarity INTEGER);
                INSERT INTO account_tags VALUES ('curator','1234567890123456789','topic',-1);
                CREATE TABLE account_tag_events(event_id INTEGER, account_id TEXT, action TEXT);
                INSERT INTO account_tag_events VALUES (1,'1234567890123456789','remove');
            """)
        self.research = self.root / "research"
        self.research.mkdir()
        self.captures = self.root / "captures.json"
        self.captures.write_text(json.dumps([{"account_id": "1234567890123456789", "handle": "example", "bio": "October bio"}, {"account_id": "2", "handle": "other"}]))
        with (self.research / "outreach-master.csv").open("w") as target:
            writer = csv.DictWriter(target, fieldnames=["account_id", "contact_email", "draft_message"])
            writer.writeheader()
            writer.writerow({"account_id": "1234567890123456789", "contact_email": "public@example.org", "draft_message": "event text must not become a person fact"})
        (self.research / "batch-01.json").write_text(json.dumps({"cards": [{"account_id": "1234567890123456789", "artifact": {"url": "https://example.org/paper", "evidence": "public paper"}, "invitation_message": "excluded event draft"}]}))
        (self.research / "contact-route-reviews-test-batch01.json").write_text(json.dumps({"reviews": [{"account_id": "1234567890123456789", "routes": [{"type": "organisation_email", "address": "team@example.org", "instruction": "ask for author"}]}], "checks": [{"account_id": "2", "reason": "site unavailable"}]}))
        self.arguments = {key: getattr(self, key) for key in ("archive", "shadow", "tags", "captures", "research")}

    def report(self):
        return module.build_report(**self.arguments)

    def test_exact_identity_and_source_preservation(self):
        paths = [self.archive, self.shadow, self.tags, self.captures, *self.research.iterdir()]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        report = self.report()
        dossier = next(row for row in report["dossiers"] if row["accountId"] == "1234567890123456789")
        self.assertEqual(len(dossier["profiles"]), 2)
        self.assertEqual(dossier["workingJudgments"][0]["polarity"], -1)
        self.assertEqual(dossier["unresolvedHandleMatches"], [{"accountId": "shadow:example", "username": "example", "status": "not-merged"}])
        self.assertEqual(dossier["contactResearch"][0]["record"]["routes"][0]["type"], "organisation_email")
        self.assertEqual(dossier["coverage"]["tweets"], 1)
        self.assertIsNone(dossier["coverage"]["enriched_tweets"])
        self.assertNotIn("invitation_message", json.dumps(dossier))
        self.assertNotIn("event text must", json.dumps(dossier))
        self.assertNotIn("html_gz", dossier["websiteEvidence"][0])
        capture_only = next(row for row in report["dossiers"] if row["accountId"] == "2")
        self.assertEqual(capture_only["contactChecks"][0]["record"]["reason"], "site unavailable")
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})

    def test_missing_source_is_not_empty_success(self):
        self.arguments["shadow"] = self.root / "missing.db"
        report = self.report()
        self.assertEqual(report["sources"]["shadow"]["status"], "unavailable")
        self.assertNotIn("tables", report["sources"]["shadow"])
        self.assertTrue(report["dossiers"])

    def test_duplicate_ids_and_invalid_research_are_visible(self):
        self.captures.write_text('[{"account_id":"2"},{"account_id":"2"}]')
        (self.research / "batch-02.json").write_text('{"cards":[{"account_id":2}]}')
        report = self.report()
        self.assertEqual(report["sources"]["captures"]["status"], "unavailable")
        self.assertEqual(len(report["researchErrors"]), 1)
        self.assertEqual(report["researchErrors"][0]["errorType"], "ValueError")

    def test_existing_output_is_preserved(self):
        target = self.root / "existing.json"
        target.write_text("do not overwrite")
        args = [sys.executable, str(SCRIPT)]
        for key, value in {**self.arguments, "output": target}.items():
            args += ["--" + key, str(value)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "do not overwrite")

    def test_new_directory_and_backup_recovery(self):
        target = self.root / "new-private-directory" / "pilot.json"
        backup = target.parent / "tags.db"
        args = [sys.executable, str(SCRIPT)]
        for key, value in {**self.arguments, "output": target, "tag-backup": backup}.items():
            args += ["--" + key, str(value)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertTrue(target.exists(), result.stderr)
        report = json.loads(target.read_text())
        self.assertTrue(report["tagBackup"]["matchesSourceReport"])
        with module.readonly(backup) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_tag_events").fetchone()[0], 1)
            self.assertEqual(module.tag_digest(conn), report["sources"]["tags"]["logicalDigest"])
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
