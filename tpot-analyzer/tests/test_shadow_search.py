"""Test intent: historical discovery searches more than the dossier preview.

- Search all imported fields without joining Archive/current numeric profiles.
- Explain1–2 directed hops with exact typed IDs, raw dates and source refs.
- Refuse missing coverage; distinguish unavailable/empty; preserve all bytes.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from src.data.shadow_aliases import FOLLOW, PROFILE, SCOPE, shadow_alias_preview
from src.data.shadow_search import search_shadow_evidence
from src.data.social_paths import NetworkCoverageError


@pytest.fixture
def graph(tmp_path):
    path = tmp_path/'graph.db'
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        w = CaptureWriter(db)
        db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)',
                   ('synthetic-source', 'synthetic', None, b'{}'))
        aliases = {}
        for handle, bio, channel in [('alice', 'Meditation tools', 'hybrid_selenium'),
                ('bob', 'Civic design India', 'hybrid_selenium'),
                ('carol', 'Buddhism Marxist India', 'x_api'),
                ('12345', 'Civic design India', 'hybrid_selenium'),
                ('hidden', 'Forbidden archive needle', 'archive_sync')]:
            aliases[handle] = w.entity('unresolved_account', 'shadow:'+handle)
            w.relation(aliases[handle], PROFILE, w.entity('shadow_profile', 'shadow:'+handle),
                'synthetic-source', '/row', '2025-10-06 10:00:00', {
                    'username': handle, 'display_name': handle.title(), 'bio': bio,
                    'location': 'Bengaluru' if handle == 'carol' else None,
                    'sourceChannel': channel, 'fetched_at': '2025-10-06 10:00:00',
                    'captureTimeBasis': 'Stored capture time; timezone unspecified'})
        for handle in ['alice', 'bob']:
            w.relation(aliases[handle], SCOPE, aliases[handle], 'synthetic-source', '/scope', None,
                       {'selectedRows': 22, 'totalRowsAtImport': 22, 'truncated': False})
        for start, end in [('alice', 'bob'), ('bob', 'carol'), ('carol', 'alice'), ('alice', '12345')]:
            w.relation(aliases[start], FOLLOW, aliases[end], 'synthetic-source', '/row',
                '2025-10-06 10:00:00', {'sourceChannel': 'hybrid_selenium',
                'captureDirection': 'inbound' if end == 'carol' else 'outbound',
                'captureTimeBasis': 'Stored capture time; timezone unspecified'})
        # More than the old20-row preview; the last matching endpoint must remain searchable.
        for number in range(24):
            node = w.entity('unresolved_account', f'shadow:extra{number}')
            w.relation(aliases['alice'], FOLLOW, node, 'synthetic-source', '/row',
                '2025-10-06 10:00:00', {'sourceChannel': 'hybrid_selenium',
                    'captureDirection': 'outbound', 'captureTimeBasis': 'timezone unspecified'})
        numeric = w.entity('x_account', '9007199254740993')
        w.relation(numeric, 'profile_observation', w.entity('x_profile', 'current'),
            'synthetic-source', '/profile', None, {'handle': 'alice', 'bio': 'Forbidden numeric needle'})
    path.chmod(0o600)
    return path


def test_global_words_fields_sources_and_numeric_archive_separation(graph):
    before = graph.read_bytes()
    result = search_shadow_evidence(graph, 'buddhism bengaluru')
    assert result['total'] == 1
    row = result['results'][0]
    assert row['alias'] == 'shadow:carol' and 'accountId' not in row
    assert row['profile']['bio'] == 'Buddhism Marxist India'
    assert row['matchedFields'] == {'buddhism': ['bio'], 'bengaluru': ['location']}
    assert row['profile']['evidenceRef']['snapshotId'] == 'synthetic-source'
    assert row['profile']['fetched_at'] == '2025-10-06 10:00:00'
    assert result['coverage']['profileHandles'] == 4
    assert search_shadow_evidence(graph, 'Forbidden')['total'] == 0
    assert search_shadow_evidence(graph, '12345')['results'][0]['alias'] == 'shadow:12345'
    assert str(graph) not in json.dumps(result)
    assert graph.read_bytes() == before


def test_historical_term_coverage_uses_latest_supported_scoped_profiles(graph):
    result=search_shadow_evidence(graph,'Buddhism India',from_handle='alice',limit=1)
    assert result['total']==1 and result['results'][0]['alias']=='shadow:carol'
    assert result['termCoverage']==[
        {'term':'buddhism','matchingHandles':1}, {'term':'india','matchingHandles':3}]
    hidden=search_shadow_evidence(graph,'Forbidden Buddhism')
    assert hidden['total']==0
    assert hidden['termCoverage']==[
        {'term':'forbidden','matchingHandles':0}, {'term':'buddhism','matchingHandles':1}]


def test_historical_term_coverage_is_unknown_without_imported_profiles(graph):
    with sqlite3.connect(graph) as db:
        db.execute('DELETE FROM relation WHERE predicate=?',(PROFILE,))
    result=search_shadow_evidence(graph,'Buddhism India')
    assert result['status']=='not_imported' and result['total']==0
    assert result['termCoverage']==[
        {'term':'buddhism','matchingHandles':None}, {'term':'india','matchingHandles':None}]


def test_two_hops_preserve_directions_sources_and_cycles_do_not_rediscover_root(graph):
    assert search_shadow_evidence(graph, 'Buddhism', from_handle='@ALICE', max_hops=1)['total'] == 0
    result = search_shadow_evidence(graph, 'Buddhism', from_handle='alice', max_hops=2)
    assert result['total'] == 1
    edges = result['results'][0]['networkPath']
    assert [(e['source']['key'], e['target']['key']) for e in edges] == [
        ('shadow:alice', 'shadow:bob'), ('shadow:bob', 'shadow:carol')]
    assert edges[1]['captureDirection'] == 'inbound'  # Stored arrow is not reversed.
    assert all(e['sourcePointer'] == '/row' and e['observedAt'] for e in edges)
    assert result['networkScope']['firstHopNodes'] == 26
    assert result['networkScope']['firstHopWithOutgoing'] == 1
    assert search_shadow_evidence(graph, 'Meditation', from_handle='alice')['total'] == 0


def test_scope_bounds_validation_privacy_and_failure_are_not_empty(graph, tmp_path):
    result = search_shadow_evidence(graph, 'India', limit=1)
    assert result['total'] == 3 and result['truncated'] and len(result['results']) == 1
    with pytest.raises(NetworkCoverageError):
        search_shadow_evidence(graph, 'India', from_handle='missing')
    with pytest.raises(NetworkCoverageError):
        search_shadow_evidence(graph, 'India', from_handle='12345')
    for kwargs in [{'from_handle': '../alice'}, {'max_hops': True}, {'limit': 0}]:
        with pytest.raises(ValueError): search_shadow_evidence(graph, 'India', **kwargs)
    with pytest.raises(ValueError): search_shadow_evidence(graph, 'a')
    with pytest.raises(OSError): search_shadow_evidence(tmp_path/'missing', 'India')
    graph.chmod(0o644)
    with pytest.raises(ValueError): search_shadow_evidence(graph, 'India')


def test_match_beyond_preview_and_exact_numeric_bridge_do_not_bind_current_identity(graph):
    with sqlite3.connect(graph) as db:
        w = CaptureWriter(db)
        alice = w.entity('unresolved_account', 'shadow:alice')
        carol = w.entity('unresolved_account', 'shadow:carol')
        numeric = w.entity('x_account', '9007199254740993')
        attrs = {'sourceChannel': 'hybrid_selenium', 'captureDirection': 'outbound',
                 'captureTimeBasis': 'timezone unspecified'}
        for start, end in [(alice, numeric), (numeric, carol)]:
            w.relation(start, FOLLOW, end, 'synthetic-source', '/row', '2025-10-06', attrs)
        for number in range(24):
            handle = f'extra{number}'
            node = w.entity('unresolved_account', 'shadow:'+handle)
            w.relation(node, PROFILE, w.entity('shadow_profile', 'shadow:'+handle),
                'synthetic-source', '/row', '2025-10-06', {
                    'username': handle, 'bio': 'Beyond the old preview',
                    'sourceChannel': 'hybrid_selenium'})
    shown = {row['target']['key'] for row in shadow_alias_preview(graph, handle='alice')['outgoing']}
    omitted = next(f'extra{n}' for n in range(24) if f'shadow:extra{n}' not in shown)
    result = search_shadow_evidence(graph, omitted, from_handle='alice', max_hops=1)
    assert result['total'] == 1 and result['results'][0]['alias'] == 'shadow:'+omitted
    path = search_shadow_evidence(graph, 'Buddhism', from_handle='alice')['results'][0]['networkPath']
    assert path[0]['target'] == {'kind': 'x_account', 'key': '9007199254740993'}
    assert 'Forbidden numeric needle' not in json.dumps(path)


def test_route_auth_validation_and_unavailable_are_independent_of_archive(graph, tmp_path, monkeypatch):
    for name in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH',
                 'MAP_TPOT_DOSSIER_PATH', 'MAP_TPOT_POST_INDEX', 'MAP_TPOT_ARCHIVE_CACHE_DIR'):
        monkeypatch.setenv(name, str(tmp_path/name))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(graph))
    from flask import Flask
    from src.api.routes.research_notes_shadow import research_notes_shadow_bp
    app = Flask(__name__); app.config['TESTING'] = True
    app.register_blueprint(research_notes_shadow_bp)
    client = app.test_client()
    url = '/api/research-notes/shadow/search?q=Buddhism&fromHandle=alice&maxHops=2'
    assert client.get(url).status_code == 401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    before = graph.read_bytes()
    result = client.get(url)
    assert result.status_code == 200 and result.get_json()['total'] == 1
    assert graph.read_bytes() == before
    assert client.get('/api/research-notes/shadow/search?q=India&fromHandle=missing').status_code == 422
    assert client.get('/api/research-notes/shadow/search?q=India&maxHops=3').status_code == 400
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(tmp_path/'unavailable'))
    result = client.get(url)
    assert result.status_code == 503
    assert 'total' not in result.get_json() and str(tmp_path) not in result.get_data(as_text=True)
