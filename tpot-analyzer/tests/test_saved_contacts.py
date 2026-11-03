"""Test intent: sourced routes survive general-purpose graph reuse.

- Import all reviewed route files, not only filenames containing batch.
- Keep organisation forwarding, forms and incomplete checks distinct.
- Search exposes route availability, never contact contents or outreach text.
- Exact identities, retained source pointers, no-overwrite and idempotence hold.
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import httpx

import pytest

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.relationship_dossier import relationship_preview
from src.data.saved_evidence import search_saved_evidence


@pytest.fixture
def inputs(tmp_path):
    tmp_path.chmod(0o700)
    capture, batch, pilot, contacts = [tmp_path/name for name in
        ('capture.json', 'batch-01.json', 'pilot.json', 'contact-route-reviews-20261013.json')]
    ids = ('9007199254740993', '200', '300')
    capture.write_text(json.dumps([{'account_id': account, 'handle': handle, 'bio': 'Research builder'}
        for account, handle in zip(ids, ('alice', 'bob', 'carol'))]))
    batch.write_text(json.dumps({'cards': [{'account_id': ids[0], 'artifact': {
        'title': 'Useful hardware', 'url': 'https://example.test/work', 'evidence': 'Collaborative tools'}}]}))
    route = {'type': 'organisation_forwarding', 'address': 'team@example.test',
        'source_url': 'https://example.test/contact', 'verified_on': '2026-10-13',
        'evidence': 'Public team page names Alice', 'instruction': 'Ask for Alice; forwarding unconfirmed'}
    pilot.write_text(json.dumps({'kind': 'map-tpot-custody-pilot', 'visibility': 'private',
        'dossiers': [{'accountId': ids[0], 'profiles': [{'source': 'synthetic',
            'record': {'account_id': ids[0], 'handle': 'alice'}}], 'contactResearch': [
            {'record': {'account_id': ids[0], 'routes': [route]}}]}]}))
    payload = {'reviews': [{'account_id': ids[0], 'handle': 'alice', 'primary_email': None, 'routes': [route]},
        {'account_id': ids[1], 'handle': 'bob', 'primary_email': 'team@example.test', 'routes': [
            {**route, 'instruction': 'Ask for Bob', 'evidence': 'Team page names Bob'},
            {'type': 'contact_form', 'address': 'https://example.test/form',
             'source_url': 'https://example.test/form', 'verified_on': '2026-10-14',
             'instruction': 'General enquiry form; not submitted', 'evidence': 'Public form exists'}]}],
        'checks': [{'account_id': ids[2], 'handle': 'carol', 'checked_on': '2026-10-14',
            'source_urls': ['https://example.test/carol', 'https://example.test/carol/contact'],
            'reason': 'Partial inspection; no public route verified, other sources not exhaustively checked'}],
        'selection': {'event_fit': 'forbidden-ranking'}, 'send_history': 'forbidden-history'}
    contacts.write_text(json.dumps(payload))
    return capture, batch, pilot, contacts, payload


def test_search_counts_existing_routes_without_exposing_contact_details(inputs, tmp_path):
    capture, batch, pilot, _, _ = inputs
    output = tmp_path/'existing.db'
    build_saved_capture(capture, [batch], pilot, output)
    hit = search_saved_evidence(output, 'alice')['results'][0]
    assert hit.get('contactSummary', {}).get('routeCount') == 1
    assert hit['contactSummary']['types'] == ['organisation_forwarding']
    assert 'team@example.test' not in json.dumps(hit)


def test_full_routes_checks_and_original_sources_are_preserved(inputs, tmp_path):
    capture, batch, pilot, contacts, _ = inputs
    before = {path: path.read_bytes() for path in (capture, batch, pilot, contacts)}
    output = tmp_path/'contacts.db'
    result = build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts])
    assert result['contactRoutes'] == 3 and result['contactReviews'] == 2 and result['incompleteChecks'] == 1
    assert result['reimportUnchanged']
    hit = search_saved_evidence(output, 'alice')['results'][0]
    assert hit['contactSummary']['routeCount'] == 1  # Identical pilot copy is not a new route.
    assert hit['contactSummary']['status'] == 'routes_saved'
    bob = relationship_preview(output, account_id='200')
    assert {r['type'] for r in bob['contacts']} == {'organisation_forwarding', 'contact_form'}
    assert next(r for r in bob['contacts'] if r['type']=='organisation_forwarding')['instruction'] == 'Ask for Bob'
    carol = relationship_preview(output, account_id='300')
    assert carol['contacts'] == []
    assert len(carol['contactChecks']) == 1
    assert len(carol['contactChecks'][0]['sourceUrls']) == 2
    assert 'not exhaustively checked' in carol['contactChecks'][0]['reason']
    carol_hit = search_saved_evidence(output, 'carol')['results'][0]
    assert carol_hit['contactSummary']['status'] == 'incomplete_check'
    assert 'forbidden-' not in json.dumps(search_saved_evidence(output, 'builder'))
    with sqlite3.connect(output) as db:
        assert db.execute("SELECT count(*) FROM entity WHERE kind='x_account'").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','personal_email')").fetchone()[0] == 0
        for snapshot, raw in db.execute('SELECT snapshot_id,payload FROM evidence_snapshot'):
            source = json.loads(raw)
            for (pointer,) in db.execute('SELECT source_pointer FROM relation WHERE snapshot_id=?', (snapshot,)):
                value = source
                for token in pointer.lstrip('/').split('/'):
                    value = value[int(token)] if isinstance(value, list) else value[token]
                assert value is not None
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize('fault', ['wrong-id', 'wrong-handle', 'empty-routes', 'unknown-type', 'bad-date', 'unsafe-source'])
def test_malformed_review_refuses_without_touching_existing_sources(inputs, tmp_path, fault):
    capture, batch, pilot, contacts, payload = inputs
    review = payload['reviews'][0]
    if fault == 'wrong-id': review['account_id'] = '999'
    elif fault == 'wrong-handle': review['handle'] = 'someone_else'
    elif fault == 'empty-routes': review['routes'] = []
    elif fault == 'unknown-type': review['routes'][0]['type'] = 'guessed_email'
    elif fault == 'bad-date': review['routes'][0]['verified_on'] = '2026-13-50'
    else: review['routes'][0]['source_url'] = 'javascript:alert(1)'
    contacts.write_text(json.dumps(payload))
    raw = contacts.read_bytes()
    output = tmp_path/'refused.db'
    with pytest.raises(ValueError):
        build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts])
    assert not output.exists()
    assert contacts.read_bytes() == raw


def test_requested_empty_contacts_cannot_manufacture_readiness(inputs, tmp_path):
    capture, batch, pilot, contacts, _ = inputs
    contacts.write_text(json.dumps({'reviews': [], 'checks': []}))
    output = tmp_path/'empty.db'
    with pytest.raises(ValueError, match='No projectable contact'):
        build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts])
    assert not output.exists()


def test_private_api_search_to_routes_and_incomplete_checks(inputs, tmp_path, monkeypatch):
    capture, batch, pilot, contacts, _ = inputs
    output = tmp_path/'api.db'
    build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts])
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(output))
    monkeypatch.delenv('MAP_TPOT_DOSSIER_PATH', raising=False)
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE', 'community_archive_rest')
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(research_notes_bp)
    with app.test_client() as client, httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=[]))) as upstream:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = upstream
        assert client.get('/api/research-notes/search?q=builder').status_code == 401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
        response = client.get('/api/research-notes/search?q=builder')
        assert response.status_code == 200
        assert 'team@example.test' not in response.get_data(as_text=True)
        assert response.get_json()['coverage']['contactRouteAccounts'] == 2
        assert response.get_json()['coverage']['incompleteCheckAccounts'] == 1
        dossier = client.get('/api/research-notes/dossiers/bob?accountId=200')
        assert dossier.status_code == 200
        assert dossier.get_json()['relationshipEvidence']['contacts'][0]['address']
        checks = client.get('/api/research-notes/dossiers/carol?accountId=300')
        assert checks.status_code == 200
        check = checks.get_json()['relationshipEvidence']['contactChecks'][0]
        assert check['outcome'] == 'incomplete' and len(check['sourceUrls']) == 2
        assert check['evidenceRefs'][0]['sourcePointer'].startswith('/checks/0/source_urls/')
        assert 'forbidden-' not in dossier.get_data(as_text=True) + checks.get_data(as_text=True)
        assert str(tmp_path) not in dossier.get_data(as_text=True) + checks.get_data(as_text=True)


def test_reverification_is_one_route_with_two_qualified_observations(inputs, tmp_path):
    capture, batch, pilot, contacts, payload = inputs
    payload['reviews'][0]['routes'][0]['verified_on'] = '2026-10-14'
    contacts.write_text(json.dumps(payload))
    output = tmp_path/'reverified.db'
    build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts])
    hit = search_saved_evidence(output, 'alice')['results'][0]
    assert hit['contactSummary']['routeCount'] == 1
    routes = relationship_preview(output, account_id='9007199254740993')['contacts']
    assert {route['verified_on'] for route in routes} == {'2026-10-13', '2026-10-14'}


def test_coverage_is_within_searchable_profiles_not_all_pilot_entities(inputs, tmp_path):
    capture, batch, pilot, _, _ = inputs
    payload = json.loads(pilot.read_bytes())
    route = payload['dossiers'][0]['contactResearch'][0]['record']['routes'][0]
    payload['dossiers'].append({'accountId': '999', 'profiles': [{'source': 'synthetic', 'record': {
        'account_id': '999', 'handle': 'outsider'}}],
        'contactResearch': [{'record': {'account_id': '999', 'routes': [route]}}]})
    pilot.write_text(json.dumps(payload))
    output = tmp_path/'scoped.db'
    build_saved_capture(capture, [batch], pilot, output)
    result = search_saved_evidence(output, 'builder')
    assert result['coverage']['profileAccounts'] == 3
    assert result['coverage']['contactRouteAccounts'] == 1


def test_distinct_check_records_are_not_merged_by_same_day_and_reason(inputs, tmp_path):
    capture, batch, pilot, contacts, payload = inputs
    payload['checks'].append({**payload['checks'][0], 'source_urls': ['https://example.test/carol']})
    contacts.write_text(json.dumps(payload))
    output = tmp_path/'two-checks.db'
    build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts])
    view = relationship_preview(output, account_id='300')
    assert len(view['contactChecks']) == 2
    assert {reference['sourcePointer'].split('/source_urls/')[0]
            for check in view['contactChecks'] for reference in check['evidenceRefs']} == {'/checks/0', '/checks/1'}
    assert search_saved_evidence(output, 'carol')['results'][0]['contactSummary']['incompleteCheckCount'] == 2


def test_carried_forward_check_is_two_source_records_not_new_inspections(inputs, tmp_path):
    capture, batch, pilot, contacts, payload = inputs
    copied = tmp_path/'contact-route-reviews-20261014.json'
    payload['selection'] = {'note': 'A changed file can retain the same unresolved check'}
    copied.write_text(json.dumps(payload))
    output = tmp_path/'carried-forward.db'
    build_saved_capture(capture, [batch], pilot, output, contact_paths=[contacts, copied])
    records = relationship_preview(output, account_id='300')['contactChecks']
    assert len(records) == 2
    assert len({reference['snapshotId'] for record in records for reference in record['evidenceRefs']}) == 2
    assert {record['checked_on'] for record in records} == {'2026-10-14'}
    assert search_saved_evidence(output, 'carol')['results'][0]['contactSummary']['incompleteCheckCount'] == 2


def test_cli_includes_actual_first_non_batch_contact_filename(inputs, tmp_path):
    capture, batch, pilot, _, _ = inputs
    output = tmp_path/'cli.db'
    result = subprocess.run([sys.executable, 'scripts/verify_map_saved_capture.py',
        '--capture', str(capture), '--batch-dir', str(tmp_path), '--pilot', str(pilot),
        '--contact-dir', str(tmp_path), '--output-db', str(output)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert relationship_preview(output, account_id='200')['contacts']
