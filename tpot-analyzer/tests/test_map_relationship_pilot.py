"""Public pilot behavior with synthetic accounts and isolated temporary state."""
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_map_relationship_pilot import build_pilot, import_snapshot


def fixture():
    return {"kind": "map-tpot-custody-pilot", "visibility": "private",
            "createdAt": "2026-10-10T12:00:00Z", "dossiers": [
        {"accountId": "9007199254740993", "profiles": [{"source": "synthetic",
         "record": {"account_id": "9007199254740993", "username": "same_handle",
                    "website": "https://example.test/alice", "bio": "Former staff at Example"}}],
         "websiteEvidence": [{"account_id": "9007199254740993",
             "resolved_url": "https://example.test/alice", "fetched_at": "2026-10-09",
             "signal_links_json": '["https://bsky.app/profile/alice.example.test"]'}],
         "contactResearch": [{"record": {"account_id": "9007199254740993", "routes": [
             {"type": "organisation_forwarding", "address": "hello@example.test",
              "source_url": "https://example.test/contact", "verified_on": "2026-10-08",
              "instruction": "Ask to forward to Alice", "evidence": "Synthetic contact page"},
             {"type": "contact_form", "address": "https://example.test/form",
              "source_url": "https://example.test/form", "verified_on": "2026-10-08"}]}}],
         "workingJudgments": [{"tag": "synthetic-tag", "polarity": 1}]},
        {"accountId": "9007199254740994", "profiles": [{"source": "synthetic",
         "record": {"account_id": "9007199254740994", "username": "same_handle"}}],
         "contactResearch": [{"record": {"account_id": "9007199254740994", "routes": [
             {"type": "organisation_forwarding", "address": "hello@example.test",
              "source_url": "https://example.test/contact", "instruction": "Ask for Bob"}]}}]}]}


class RelationshipPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.output = self.root / "pilot.db"
        self.payload = fixture()
        self.save()

    def save(self):
        self.source.write_text(json.dumps(self.payload))

    def build(self):
        result = build_pilot(self.source, self.output)
        self.assertTrue(result.get("ready"), "Pilot must create queryable relations")
        return result

    def test_typed_contacts_and_two_hop_source_path(self):
        self.build()
        with sqlite3.connect(self.output) as db:
            routes = db.execute("SELECT attributes_json FROM relation WHERE predicate='has_contact_route'").fetchall()
            self.assertEqual(3, len(routes))
            self.assertEqual(2, sum(json.loads(r[0])["type"] == "organisation_forwarding" for r in routes))
            paths = db.execute("SELECT count(*) FROM relation a JOIN relation b ON a.object_id=b.subject_id WHERE a.predicate='profile_links_to' AND b.predicate='page_links_to'").fetchone()[0]
            self.assertEqual(1, paths)
            self.assertEqual(0, db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','works_at','member_of')").fetchone()[0])

    def test_source_bytes_dates_and_all_fields_survive(self):
        before = self.source.read_bytes()
        self.build()
        with sqlite3.connect(self.output) as db:
            saved = db.execute("SELECT payload FROM evidence_snapshot").fetchone()[0]
            self.assertEqual(before, saved)
            dates = db.execute("SELECT observed_at FROM relation WHERE predicate='has_contact_route'").fetchall()
            self.assertEqual([None, '2026-10-08', '2026-10-08'], sorted((r[0] for r in dates), key=lambda v: v or ''))
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(0o600, self.output.stat().st_mode & 0o777)

    def test_reimport_is_idempotent_and_accounts_do_not_merge(self):
        self.build()
        with sqlite3.connect(self.output) as db:
            before = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('entity','relation','evidence_snapshot')]
            import_snapshot(db, self.source)
            after = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('entity','relation','evidence_snapshot')]
            self.assertEqual(before, after)
            self.assertEqual(2, db.execute("SELECT count(*) FROM entity WHERE kind='x_account'").fetchone()[0])

    def test_refuses_mismatched_profile_identity(self):
        self.payload['dossiers'][0]['profiles'][0]['record']['account_id'] = 'different'
        self.save()
        with self.assertRaises(ValueError):
            build_pilot(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_refuses_duplicate_or_numeric_account_identity(self):
        for bad in ('9007199254740993', 9007199254740994):
            with self.subTest(bad=bad):
                self.payload = fixture()
                self.payload['dossiers'][1]['accountId'] = bad
                self.save()
                with self.assertRaises(ValueError):
                    build_pilot(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_never_overwrites_existing_output(self):
        self.output.write_bytes(b'preserve this existing file')
        with self.assertRaises(FileExistsError):
            build_pilot(self.source, self.output)
        self.assertEqual(b'preserve this existing file', self.output.read_bytes())

    def test_no_evidence_cannot_manufacture_a_success(self):
        self.payload['dossiers'] = [self.payload['dossiers'][1]]
        self.payload['dossiers'][0].pop('contactResearch')
        self.save()
        with self.assertRaisesRegex(ValueError, 'No projectable'):
            build_pilot(self.source, self.output)
        self.assertFalse(self.output.exists(), 'A refused fresh output must not remain')

    def test_nested_malformed_records_refuse_before_creating_output(self):
        for field, bad in [('websiteEvidence', [None]), ('websiteEvidence', None),
                           ('contactResearch', [None]), ('contactResearch', [{'record': None}])]:
            with self.subTest(field=field, bad=bad):
                self.payload = fixture()
                self.payload['dossiers'][0][field] = bad
                self.save()
                with self.assertRaises(ValueError):
                    build_pilot(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_invalid_capture_time_refuses_without_an_output(self):
        for captured in (123, 'not-a-time', '2026-10-15T12:00:00'):
            self.payload['createdAt'] = captured
            self.save()
            with self.assertRaises(ValueError):
                build_pilot(self.source, self.output)
            self.assertFalse(self.output.exists())

    def test_every_source_pointer_resolves_in_retained_snapshot(self):
        self.build()
        with sqlite3.connect(self.output) as db:
            for pointer, payload in db.execute('SELECT r.source_pointer,s.payload FROM relation r JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id'):
                value = json.loads(payload)
                try:
                    for token in pointer.lstrip('/').split('/'):
                        value = value[int(token)] if isinstance(value, list) else value[token]
                except (TypeError, KeyError, ValueError, IndexError):
                    self.fail('Every source pointer must resolve in original JSON')
                self.assertIsNotNone(value)

    def test_changed_observation_retains_both_versions(self):
        self.build()
        changed = copy.deepcopy(self.payload)
        changed['createdAt'] = '2026-10-11T12:00:00Z'
        changed['dossiers'][0]['contactResearch'][0]['record']['routes'][0]['instruction'] = 'Historical forwarding route'
        self.source.write_text(json.dumps(changed))
        with sqlite3.connect(self.output) as db:
            import_snapshot(db, self.source)
            self.assertEqual(2, db.execute('SELECT count(*) FROM evidence_snapshot').fetchone()[0])
            self.assertEqual(2, db.execute("SELECT count(DISTINCT r.attributes_json) FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE r.predicate='has_contact_route' AND r.attributes_json LIKE '%hello@example.test%' AND e.source_key='9007199254740993'").fetchone()[0])


if __name__ == '__main__':
    unittest.main()
