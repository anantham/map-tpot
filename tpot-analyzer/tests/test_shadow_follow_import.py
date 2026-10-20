"""Test intent: source-shaped shadow rows become inspectable directed paths.

- Append exact numeric observations, preserving inbound source→target direction.
- Keep raw rows/dates and sources unchanged; repeats append nothing twice.
- Recover only explicit public provider profiles, never handle/Archive fallbacks.
- Unknown endpoints, malformed metadata and bad batch bounds remain explicit.
- New follow paths and source coverage are visible through existing read APIs.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import saved_social_sources, search_saved_evidence
from src.data.shadow_follow_import import import_shadow_follows


@pytest.fixture
def stores(tmp_path):
    tmp_path.chmod(0o700)
    shadow, archive, graph = [tmp_path/name for name in ('shadow.db', 'archive.db', 'graph.db')]
    with sqlite3.connect(shadow) as db:
        db.execute('CREATE TABLE shadow_edge(source_id TEXT,target_id TEXT,direction TEXT,source_channel TEXT,fetched_at TEXT,checked_at TEXT,weight INTEGER,metadata TEXT,PRIMARY KEY(source_id,target_id,direction))')
        rows = [('100', '200', 'outbound'), ('200', '9007199254740993', 'inbound'),
                ('200', '100', 'outbound'), ('100', '999', 'outbound'),
                ('shadow:carol', '100', 'inbound')]
        db.executemany('INSERT INTO shadow_edge VALUES(?,?,?,?,?,?,?,?)', [
            (*row, 'hybrid_selenium', '2025-10-06 10:00:00', None, 1,
             json.dumps({'list_type': 'following' if row[2] == 'outbound' else 'followers',
                         'resolution': 'selenium'})) for row in rows])
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT PRIMARY KEY,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
        for aid, handle, private in [('100', 'alice', False), ('200', 'bob', False),
                                     ('9007199254740993', 'carol', False), ('999', 'private', True)]:
            db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)', (aid, handle,
                json.dumps({'id': aid, 'userName': handle, 'name': handle.title(),
                            'description': 'Research builder', 'protected': private,
                            'following': 5, 'followers': 8}), '2026-07-30T10:00:00Z'))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
    graph.chmod(0o600)
    return shadow, archive, graph


def test_shadow_rows_connect_existing_search_with_direction_and_source(stores):
    shadow, archive, graph = stores
    protected = {path: path.read_bytes() for path in (shadow, archive)}
    with sqlite3.connect(graph) as db:
        result = import_shadow_follows(db, shadow, archive)
        assert result['followObservations'] == 3
        assert result['deferredAliasRows'] == 1
        assert result['excludedUnprofiledRows'] == 1
        counts = [db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('entity', 'relation', 'evidence_snapshot')]
        import_shadow_follows(db, shadow, archive)
        assert counts == [db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                          for table in ('entity', 'relation', 'evidence_snapshot')]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        snapshots = dict(db.execute('SELECT snapshot_id,payload FROM evidence_snapshot'))
        rows = db.execute("SELECT snapshot_id,attributes_json,observed_at FROM relation WHERE predicate='follows_observed'").fetchall()
        assert len(rows) == 3
        for snapshot, encoded, observed in rows:
            attrs = json.loads(encoded)
            raw = json.loads(snapshots[snapshot])['row']
            assert observed == raw['fetched_at'] == '2025-10-06 10:00:00'
            assert attrs['captureTimeBasis'] == 'Stored capture time; timezone unspecified'
            assert attrs['sourceRef'] == {'snapshotId': snapshot, 'sourcePointer': '/row'}
            assert raw['source_channel'] == 'hybrid_selenium'
    result = search_saved_evidence(graph, 'carol', from_account_id='100', max_hops=2)
    assert result['total'] == 1
    path = result['results'][0]['networkPath']
    assert [node['accountId'] for node in path['nodes']] == ['100', '200', '9007199254740993']
    assert path['edges'][1]['captureDirection'] == 'inbound'
    assert path['edges'][1]['sourceRef']['sourcePointer'] == '/row'
    sources = saved_social_sources(graph)
    assert sources['coverage']['sourceAccounts'] == 2
    assert {row['username'] for row in sources['sources']} == {'alice', 'bob'}
    assert all(path.read_bytes() == raw for path, raw in protected.items())
    assert search_saved_evidence(graph, 'private')['total'] == 0


def test_unknown_and_flagged_profiles_cannot_be_recovered(stores):
    shadow, archive, graph = stores
    with sqlite3.connect(archive) as db:
        db.execute("INSERT INTO protected_accounts VALUES('200')")
        db.execute("UPDATE user_profile_cache SET raw_json=json_remove(raw_json,'$.protected') WHERE account_id='100'")
    with sqlite3.connect(graph) as db:
        report = import_shadow_follows(db, shadow, archive)
        assert report['followObservations'] == 0
        assert report['excludedUnprofiledRows'] == 4
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='follows_observed'").fetchone()[0] == 0


def test_archive_only_profiles_do_not_qualify_missing_endpoints(stores):
    shadow, archive, graph = stores
    with sqlite3.connect(archive) as db:
        db.execute('DELETE FROM user_profile_cache')
    with sqlite3.connect(graph) as db:
        w = CaptureWriter(db)
        for aid, name in [('100', 'alice'), ('200', 'bob')]:
            db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)', (aid, 'synthetic', None, b'{}'))
            w.relation(w.entity('x_account', aid), 'profile_observation', w.entity('x_profile', aid),
                aid, '/', None, {'handle': name, 'sourceKind': 'community_archive_published_profile'})
        assert import_shadow_follows(db, shadow, archive)['followObservations'] == 0


@pytest.mark.parametrize('offset,limit', [(-1, 10), (0, 0), (0, 20001), (True, 10)])
def test_invalid_bounds_do_not_write(stores, offset, limit):
    shadow, archive, graph = stores
    with sqlite3.connect(graph) as db:
        with pytest.raises(ValueError):
            import_shadow_follows(db, shadow, archive, offset=offset, limit=limit)
        assert db.execute('SELECT count(*) FROM relation').fetchone()[0] == 0


def test_bad_metadata_refuses_transaction_and_preserves_sources(stores):
    shadow, archive, graph = stores
    with sqlite3.connect(shadow) as db:
        db.execute("UPDATE shadow_edge SET metadata='[]' WHERE source_id='200'")
    before = shadow.read_bytes()
    with sqlite3.connect(graph) as db:
        with pytest.raises(ValueError), db:
            import_shadow_follows(db, shadow, archive)
        assert db.execute('SELECT count(*) FROM relation').fetchone()[0] == 0
    assert shadow.read_bytes() == before


def test_copied_batch_retains_prior_rows_with_space_in_source_path(stores, tmp_path):
    from scripts.verify_shadow_follow_batch import build_shadow_batch
    shadow, archive, graph = stores
    folder = tmp_path/'source graph'
    folder.mkdir(mode=0o700)
    prior = folder/'prior.db'
    graph.rename(prior)
    output = tmp_path/'copy.db'
    report = build_shadow_batch(prior, shadow, archive, output)
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    assert report['after']['relation'] > report['before']['relation']
    assert report['followObservations'] == 3


def test_adoption_keeps_old_release_index_package_and_refuses_changed_graph(stores, tmp_path):
    from scripts.verify_shadow_follow_batch import adopt_graph, build_shadow_batch
    shadow, archive, graph = stores
    root = tmp_path/'managed'
    prior = root/'releases'/'old'
    for name in ('graph', 'index', 'package'):
        (prior/name).mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    baseline = prior/'graph'/'relationships.db'
    graph.rename(baseline)
    (prior/'index'/'posts.db').write_bytes(b'synthetic unchanged index')
    (prior/'package'/'latest.json').write_bytes(b'synthetic unchanged metadata')
    (root/'current').symlink_to(prior, target_is_directory=True)
    output = tmp_path/'derived.db'
    report = build_shadow_batch(baseline, shadow, archive, output)
    before = baseline.read_bytes()
    wrong = {**report, 'outputGraphSha256': 'changed'}
    with pytest.raises(ValueError):
        adopt_graph(root, baseline, output, wrong)
    assert (root/'current').resolve() == prior
    result = adopt_graph(root, baseline, output, report)
    assert (root/'current'/'graph'/'relationships.db').resolve() == output
    assert (root/'current'/'index'/'posts.db').read_bytes() == b'synthetic unchanged index'
    assert (root/'current'/'package'/'latest.json').read_bytes() == b'synthetic unchanged metadata'
    assert baseline.read_bytes() == before
    assert result['previousRelease'] == str(prior)


def test_archive_only_source_does_not_disable_all_sources_or_expose_hidden_name(stores):
    _, _, graph = stores
    with sqlite3.connect(graph) as db:
        w = CaptureWriter(db)
        db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)', ('source', 'synthetic', None, b'{}'))
        account = w.entity('x_account', '300')
        w.relation(account, 'profile_observation', w.entity('x_profile', '300'), 'source', '/', None,
            {'handle': 'hidden_name', 'sourceKind': 'community_archive_published_profile'})
        w.relation(account, 'follows_observed', w.entity('x_account', '100'), 'source', '/', None,
            {'receiptRef': {'snapshotId': 'source', 'sourcePointer': '/'}})
    payload = saved_social_sources(graph)
    assert payload['status'] == 'available'
    assert payload['sources'][0]['accountId'] == '300'
    assert payload['sources'][0]['username'] is None
    assert 'hidden_name' not in json.dumps(payload)
