"""Synthetic sidecars only; no app imports, network or live persistence roots."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_map_relationship_pilot import build_pilot, import_snapshot
from src.data.relationship_dossier import relationship_preview
from tests.test_map_relationship_pilot import fixture

ACCOUNT = '9007199254740993'


class RelationshipDossierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.db = self.root/'source.json', self.root/'sidecar.db'
        payload = fixture()
        route = payload['dossiers'][0]['contactResearch'][0]['record']['routes'][0]
        route.update(private_note='do-not-return', ego='another-curator')
        self.source.write_text(json.dumps(payload))
        build_pilot(self.source, self.db)

    def preview(self, **kwargs):
        result = relationship_preview(self.db, account_id=ACCOUNT, **kwargs)
        self.assertEqual('available', result.get('status'))
        return result

    def test_exact_account_routes_do_not_merge_shared_inbox_accounts(self):
        result = self.preview()
        self.assertEqual(ACCOUNT, result['accountId'])
        self.assertEqual(2, len(result['contacts']))
        self.assertEqual({'organisation_forwarding','contact_form'}, {r['type'] for r in result['contacts']})
        self.assertIn('Ask to forward to Alice', [r.get('instruction') for r in result['contacts']])
        self.assertNotIn('Ask for Bob', json.dumps(result))

    def test_two_hop_path_retains_edge_provenance(self):
        result = self.preview()
        self.assertEqual(1, len(result['paths']))
        path = result['paths'][0]
        self.assertEqual(ACCOUNT, path['nodes'][0]['key'])
        self.assertEqual('https://bsky.app/profile/alice.example.test', path['nodes'][-1]['key'])
        self.assertEqual(['profile_links_to','page_links_to'], [e['predicate'] for e in path['edges']])
        self.assertTrue(all(e['snapshotId'] and e['sourcePointer'] for e in path['edges']))

    def test_never_returns_source_blob_curator_tags_or_unknown_route_fields(self):
        result = self.preview()
        text = json.dumps(result)
        for marker in ('synthetic-tag','do-not-return','another-curator','payload','source_path'):
            self.assertNotIn(marker, text)

    def test_read_does_not_change_sidecar_or_source(self):
        before = self.db.read_bytes(), self.source.read_bytes()
        self.preview()
        self.assertEqual(before, (self.db.read_bytes(), self.source.read_bytes()))

    def test_missing_or_public_sidecar_is_unavailable_not_empty_success(self):
        missing = self.root/'missing.db'
        self.assertEqual('unavailable', relationship_preview(missing,account_id=ACCOUNT)['status'])
        self.assertFalse(missing.exists())
        self.db.chmod(0o644)
        self.assertEqual('unavailable', relationship_preview(self.db,account_id=ACCOUNT)['status'])
        self.assertEqual('not_configured', relationship_preview(None,account_id=ACCOUNT)['status'])

    def test_unknown_account_does_not_get_another_accounts_contacts(self):
        result = relationship_preview(self.db,account_id='not-this-account')
        self.assertEqual('not_found', result['status'])
        self.assertNotIn('contacts', result)

    def test_bounded_output_reports_truncation(self):
        result = self.preview(limit=1)
        self.assertEqual(1, len(result['contacts']))
        self.assertTrue(result['truncated'])

    def test_unchanged_snapshots_do_not_multiply_cards_or_crowd_out_unique_claims(self):
        payload = json.loads(self.source.read_text())
        payload['createdAt'] = '2026-10-11T12:00:00Z'
        self.source.write_text(json.dumps(payload))
        with sqlite3.connect(self.db) as db:
            import_snapshot(db, self.source)
            self.assertEqual(2, db.execute('SELECT count(*) FROM evidence_snapshot').fetchone()[0])
        result = self.preview(limit=2)
        self.assertEqual(2, len(result['contacts']))
        self.assertEqual(1, len(result['paths']))
        self.assertFalse(result['truncated'])
        refs = [r['evidenceRef'] for r in result['contacts']] + result['paths'][0]['edges']
        self.assertTrue(all(r['observationCount'] == 2 for r in refs))
        self.assertTrue(all(r['capturedAt'] == '2026-10-11T12:00:00.000Z' for r in refs))

    def test_changed_contact_claims_remain_separate_not_latest_truth(self):
        payload = json.loads(self.source.read_text())
        payload['createdAt'] = '2026-10-11T12:00:00Z'
        payload['dossiers'][0]['contactResearch'][0]['record']['routes'][0]['instruction'] = 'Different historical instruction'
        self.source.write_text(json.dumps(payload))
        with sqlite3.connect(self.db) as db:
            import_snapshot(db, self.source)
        self.assertEqual(3, len(self.preview()['contacts']))

    def test_hidden_route_metadata_does_not_create_duplicate_public_claims(self):
        payload = json.loads(self.source.read_text())
        payload['createdAt'] = '2026-10-11T12:00:00Z'
        payload['dossiers'][0]['contactResearch'][0]['record']['routes'][0]['private_note'] = 'changed-hidden'
        self.source.write_text(json.dumps(payload))
        with sqlite3.connect(self.db) as db:
            import_snapshot(db, self.source)
        self.assertEqual(2, len(self.preview()['contacts']))

    def test_capture_order_is_chronological_across_timezone_offsets(self):
        payload = json.loads(self.source.read_text())
        for captured in ('2026-10-11T13:00:00+02:00', '2026-10-11T12:00:00Z'):
            payload['createdAt'] = captured
            self.source.write_text(json.dumps(payload))
            with sqlite3.connect(self.db) as db:
                import_snapshot(db, self.source)
        reference = self.preview()['contacts'][0]['evidenceRef']
        self.assertEqual('2026-10-11T12:00:00.000Z', reference['capturedAt'])
        self.assertEqual('2026-10-11T12:00:00.000Z', reference['lastCapturedAt'])

    def test_explicit_redirect_preserves_a_three_edge_path(self):
        payload = fixture()
        site = payload['dossiers'][0]['websiteEvidence'][0]
        site['source_url'] = site['resolved_url']
        site['resolved_url'] += '/'
        source, database = self.root/'redirect.json', self.root/'redirect.db'
        source.write_text(json.dumps(payload))
        build_pilot(source, database)
        view = relationship_preview(database, account_id=ACCOUNT)
        self.assertEqual(1, len(view['paths']))
        path = view['paths'][0]
        self.assertEqual(['profile_links_to', 'page_resolves_to', 'page_links_to'], [e['predicate'] for e in path['edges']])
        self.assertEqual(4, len(path['nodes']))
        self.assertTrue(all(e['sourcePointer'] and e['snapshotId'] for e in path['edges']))

    def test_shared_public_page_hop_retains_observing_account_without_merging(self):
        payload = fixture()
        second = payload['dossiers'][1]
        second['websiteEvidence'] = [{'account_id':second['accountId'], 'resolved_url':'https://example.test/alice',
            'signal_links_json':'["https://example.test/bob"]'}]
        source, database = self.root/'shared.json', self.root/'shared.db'
        source.write_text(json.dumps(payload))
        build_pilot(source, database)
        paths = relationship_preview(database, account_id=ACCOUNT)['paths']
        foreign = next(p for p in paths if p['nodes'][-1]['key'] == 'https://example.test/bob')
        self.assertEqual(second['accountId'], foreign['edges'][-1]['observingAccountId'])
        self.assertEqual(ACCOUNT, foreign['nodes'][0]['key'])

    def test_malformed_stored_contact_is_explicitly_unavailable(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE relation SET attributes_json='not json' WHERE predicate='has_contact_route'")
        self.assertEqual('unavailable', relationship_preview(self.db,account_id=ACCOUNT)['status'])

    def test_hidden_profile_parent_suppresses_cached_page_paths(self):
        from src.data.published_profile_access import SOURCE_KIND
        before=self.preview()
        self.assertTrue(before['paths'])
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',?,'$.archiveExportId','hidden-export','$.profileFileRef',json('{}')) WHERE subject_id=(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key=?) AND predicate='profile_links_to'",(SOURCE_KIND,ACCOUNT))
        hidden=self.preview()
        self.assertEqual([],hidden['paths'])
        self.assertNotIn('https://bsky.app/profile/alice.example.test',json.dumps(hidden))


if __name__ == '__main__':
    unittest.main()
