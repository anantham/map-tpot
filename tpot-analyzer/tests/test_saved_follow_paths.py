"""Test intent: historical directed follows connect evidence, not identities.

- Never ignore a requested graph scope or turn missing coverage into zero follows.
- Preserve direction, shortest paths, cycles, capture dates and source references.
- Keep the candidate boundary; add only explicitly captured source profiles.
- Malformed/unbound/private-source inputs refuse; prior files/tags stay untouched.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.saved_evidence import search_saved_evidence


@pytest.fixture
def inputs(tmp_path):
    tmp_path.chmod(0o700)
    capture, batch, pilot = [tmp_path/name for name in ('capture.json', 'batch-01.json', 'pilot.json')]
    capture.write_text(json.dumps([
        {'account_id': '9007199254740993', 'handle': 'carol', 'bio': 'Research builder'},
        {'account_id': '400', 'handle': 'dan', 'bio': 'Research builder'},
        {'account_id': '500', 'handle': 'unconnected', 'bio': 'Research builder'}]))
    batch.write_text(json.dumps({'cards': [{'account_id': '9007199254740993', 'artifact': {
        'title': 'Neuroscience hardware', 'url': 'https://example.test/work', 'evidence': 'Open research tools'}}]}))
    pilot.write_text(json.dumps({'kind': 'map-tpot-custody-pilot', 'visibility': 'private',
        'dossiers': [{'accountId': '9007199254740993', 'profiles': [{'source': 'synthetic', 'record': {
            'account_id': '9007199254740993', 'handle': 'carol', 'website': 'https://example.test'}}],
            'contactResearch': [{'record': {'account_id': '9007199254740993', 'routes': [{
                'type': 'organisation_forwarding', 'address': 'team@example.test',
                'source_url': 'https://example.test/contact', 'instruction': 'Ask for Carol'}]}}]}]}))
    run = tmp_path/'run'
    run.mkdir(mode=0o700)
    requests = []
    def add(endpoint, handle, body, captured):
        sequence = len(requests)
        filename = f'response-{sequence:03d}.json'
        (run/filename).write_text(json.dumps(body))
        requests.append({'sequence': sequence, 'endpoint': endpoint, 'params': {'userName': handle},
            'status': 'captured', 'http_status': 200, 'file': filename, 'keys': sorted(body), 'received_at': captured})
    for account, handle, following in [('100', 'alice', 3), ('200', 'bob', 2)]:
        add('/twitter/user/info', handle, {'status': 'success', 'data': {'id': account,
            'userName': handle, 'name': handle.title(), 'description': 'Captured source',
            'protected': False, 'following': following, 'followers': 10}}, '2026-10-06T10:00:00+00:00')
    for handle, rows in [('alice', [('200', 'bob'), ('400', 'dan'), ('999', 'excluded')]),
                         ('bob', [('9007199254740993', 'carol'), ('100', 'alice')])]:
        add('/twitter/user/followings', handle, {'status': 'success', 'code': 0,
            'followings': [{'id': account, 'userName': name} for account, name in rows],
            'has_next_page': False, 'next_cursor': ''}, '2026-10-06T11:00:00Z')
    receipt = {'status': 'captured', 'seeds': [{'account_id': '100', 'handle': 'alice'},
        {'account_id': '200', 'handle': 'bob'}], 'requests': requests}
    (run/'receipt.json').write_text(json.dumps(receipt))
    return capture, batch, pilot, run


def client_for(tmp_path, output, monkeypatch):
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(output))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(research_notes_bp)
    client = app.test_client()
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    return client


def test_requested_network_scope_is_not_silently_ignored(inputs, tmp_path, monkeypatch):
    capture, batch, pilot, _ = inputs
    output = tmp_path/'no-graph.db'
    build_saved_capture(capture, [batch], pilot, output)
    client = client_for(tmp_path, output, monkeypatch)
    assert client.get('/api/research-notes/search?q=builder&fromAccountId=100').status_code == 422
    assert client.get('/api/research-notes/search?q=builder').get_json()['total'] == 3
    status = client.get('/api/research-notes/network/sources')
    assert status.status_code == 200
    assert status.get_json()['status'] == 'not_imported'


def test_direction_depth_cycle_and_contact_composition(inputs, tmp_path, monkeypatch):
    capture, batch, pilot, run = inputs
    output = tmp_path/'graph.db'
    result = build_saved_capture(capture, [batch], pilot, output, follow_runs=[run])
    assert result['followSources'] == 2 and result['followObservations'] == 4
    assert result['excludedFollowObservations'] == 1 and result['reimportUnchanged']
    one = search_saved_evidence(output, 'builder', from_account_id='100', max_hops=1)
    assert [hit['username'] for hit in one['results']] == ['dan']
    two = search_saved_evidence(output, 'neuroscience', from_account_id='100', max_hops=2)
    assert two['total'] == 1
    assert two['networkScope']['firstHopAccounts'] == 2
    assert two['networkScope']['firstHopWithOutgoing'] == 1
    hit = two['results'][0]
    assert hit['accountId'] == '9007199254740993'
    assert hit['contactSummary']['routeCount'] == 1
    path = hit['networkPath']
    assert [node['accountId'] for node in path['nodes']] == ['100', '200', '9007199254740993']
    assert len(path['edges']) == 2
    assert all(edge['predicate'] == 'follows_observed' and edge['observedAt'].endswith('+00:00') for edge in path['edges'])
    assert all(edge['receiptRef']['sourcePointer'].startswith('/requests/') for edge in path['edges'])
    assert search_saved_evidence(output, 'alice', from_account_id='100', max_hops=2)['total'] == 0  # No cycle/self result.
    assert search_saved_evidence(output, 'builder', from_account_id='200', max_hops=1)['results'][0]['username'] == 'carol'
    assert search_saved_evidence(output, 'unconnected', from_account_id='100', max_hops=2)['total'] == 0
    client = client_for(tmp_path, output, monkeypatch)
    sources = client.get('/api/research-notes/network/sources').get_json()
    assert sources['coverage']['sourceAccounts'] == 2
    assert {row['username'] for row in sources['sources']} == {'alice', 'bob'}
    api_result = client.get('/api/research-notes/search?q=neuroscience&fromAccountId=100&maxHops=2').get_json()
    assert api_result['total'] == 1
    assert api_result['networkScope'] == {'fromAccountId': '100', 'fromUsername': 'alice',
        'maxHops': 2, 'reachableAccounts': 3, 'firstHopAccounts': 2, 'firstHopWithOutgoing': 1}
    assert client.get('/api/research-notes/search?q=builder&fromAccountId=500').status_code == 422
    assert client.get('/api/research-notes/search?q=builder&fromAccountId=100&maxHops=3').status_code == 400
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get('/api/research-notes/network/sources').status_code == 401


def test_original_follow_and_receipt_pointers_resolve_without_private_paths(inputs, tmp_path):
    capture, batch, pilot, run = inputs
    source_bytes = {p: p.read_bytes() for p in run.glob('*.json')}
    output = tmp_path/'sources.db'
    build_saved_capture(capture, [batch], pilot, output, follow_runs=[run])
    with sqlite3.connect(output) as db:
        raw_by_id = dict(db.execute('SELECT snapshot_id,payload FROM evidence_snapshot'))
        for snapshot, pointer, encoded in db.execute("SELECT snapshot_id,source_pointer,attributes_json FROM relation WHERE predicate='follows_observed'"):
            source = json.loads(raw_by_id[snapshot])
            for token in pointer.lstrip('/').split('/'):
                source = source[int(token)] if isinstance(source, list) else source[token]
            assert source['id'] != '999'
            ref = json.loads(encoded)['receiptRef']
            receipt = json.loads(raw_by_id[ref['snapshotId']])
            for token in ref['sourcePointer'].lstrip('/').split('/'):
                receipt = receipt[int(token)] if isinstance(receipt, list) else receipt[token]
            assert receipt['endpoint'] == '/twitter/user/followings'
        assert not db.execute("SELECT 1 FROM entity WHERE source_key='999'").fetchall()
    payload = search_saved_evidence(output, 'neuroscience', from_account_id='100')
    assert str(tmp_path) not in json.dumps(payload)
    assert all(path.read_bytes() == raw for path, raw in source_bytes.items())


def test_failed_profile_with_declared_id_does_not_restore_an_excluded_target(inputs, tmp_path):
    capture, batch, pilot, run = inputs
    receipt = json.loads((run/'receipt.json').read_bytes())
    receipt['seeds'].append({'account_id': '999', 'handle': 'excluded'})
    body = {'status': 'error', 'msg': 'Profile unavailable', 'data': None}
    (run/'failed-profile.json').write_text(json.dumps(body))
    receipt['requests'].append({'endpoint': '/twitter/user/info', 'params': {'userName': 'excluded'},
        'status': 'captured', 'http_status': 200, 'file': 'failed-profile.json', 'keys': sorted(body),
        'received_at': '2026-10-06T12:00:00Z'})
    (run/'receipt.json').write_text(json.dumps(receipt))
    output = tmp_path/'failed-source.db'
    result = build_saved_capture(capture, [batch], pilot, output, follow_runs=[run])
    assert result['excludedFollowObservations'] == 1
    with sqlite3.connect(output) as db:
        assert db.execute("SELECT count(*) FROM entity WHERE source_key='999'").fetchone()[0] == 0


def test_following_count_uses_receipt_profile_not_newer_general_profile(inputs, tmp_path, monkeypatch):
    capture, batch, pilot, run = inputs
    values = json.loads(capture.read_bytes())
    values.append({'account_id': '100', 'handle': 'alice', 'bio': 'Later general profile',
        'following': 99999, 'captured_at': '2026-10-07T00:00:00Z'})
    capture.write_text(json.dumps(values))
    output = tmp_path/'source-bound.db'
    build_saved_capture(capture, [batch], pilot, output, follow_runs=[run])
    client = client_for(tmp_path, output, monkeypatch)
    sources = client.get('/api/research-notes/network/sources').get_json()['sources']
    alice = next(source for source in sources if source['accountId'] == '100')
    assert alice['reportedFollowingCount'] == 3
    assert alice['profileCapturedAt'] == '2026-10-06T10:00:00+00:00'


@pytest.mark.parametrize('fault', ['source-id', 'source-handle', 'protected', 'naive-date', 'wrong-envelope', 'numeric-target', 'path-escape'])
def test_invalid_follow_capture_refuses_and_removes_only_new_output(inputs, tmp_path, fault):
    capture, batch, pilot, run = inputs
    receipt = json.loads((run/'receipt.json').read_bytes())
    first = run/receipt['requests'][0]['file']
    page = run/receipt['requests'][2]['file']
    body = json.loads(first.read_bytes())
    if fault == 'source-id': body['data']['id'] = '777'
    elif fault == 'source-handle': body['data']['userName'] = 'someone_else'
    elif fault == 'protected': body['data']['protected'] = True
    elif fault == 'naive-date': receipt['requests'][2]['received_at'] = '2026-10-06T10:00:00'
    elif fault == 'path-escape': receipt['requests'][2]['file'] = '../receipt.json'
    elif fault == 'wrong-envelope': page.write_text(json.dumps({'data': []}))
    else:
        values = json.loads(page.read_bytes())
        values['followings'][0]['id'] = 200
        page.write_text(json.dumps(values))
    first.write_text(json.dumps(body))
    (run/'receipt.json').write_text(json.dumps(receipt))
    output = tmp_path/'refused.db'
    with pytest.raises(ValueError):
        build_saved_capture(capture, [batch], pilot, output, follow_runs=[run])
    assert not output.exists()
