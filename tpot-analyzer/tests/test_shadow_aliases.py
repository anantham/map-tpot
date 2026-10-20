"""Test intent: unresolved historical neighborhoods are evidence, not identity.

- Preserve alias/numeric separation, arrows, source fields and naive dates.
- Bound neighborhoods with explicit scope, retaining raw/profile provenance.
- Exclude Archive-derived profile copies; repeat imports change no prior rows.
- Missing/unavailable/refused observations never masquerade as zero follows.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from src.data.shadow_aliases import import_shadow_aliases, shadow_alias_preview


@pytest.fixture
def stores(tmp_path):
    tmp_path.chmod(0o700)
    cache, graph = tmp_path/'cache.db', tmp_path/'graph.db'
    with sqlite3.connect(cache) as db:
        db.execute('CREATE TABLE shadow_edge(source_id TEXT,target_id TEXT,direction TEXT,source_channel TEXT,fetched_at TEXT,metadata TEXT,PRIMARY KEY(source_id,target_id,direction))')
        db.execute('CREATE TABLE shadow_account(account_id TEXT PRIMARY KEY,username TEXT,display_name TEXT,bio TEXT,source_channel TEXT,fetched_at TEXT)')
        for aid, name, channel in [('shadow:alice', 'Alice', 'hybrid_selenium'),
                                   ('shadow:bob', 'Bob', 'hybrid_selenium'),
                                   ('shadow:carol', 'Carol', 'archive_sync')]:
            db.execute('INSERT INTO shadow_account VALUES(?,?,?,?,?,?)',
                (aid, name, name+' Example', 'Meditation research', channel, '2025-10-06 10:00:00'))
        for src, dst, direction in [('shadow:alice', 'shadow:bob', 'outbound'),
                                    ('shadow:carol', 'shadow:alice', 'inbound'),
                                    ('9007199254740993', 'shadow:alice', 'inbound')]:
            db.execute('INSERT INTO shadow_edge VALUES(?,?,?,?,?,?)',
                (src, dst, direction, 'hybrid_selenium', '2025-10-06 10:00:00', json.dumps({'resolution': 'selenium'})))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        w=CaptureWriter(db)
        w.entity('x_account','100')  # A same-handle current account remains separate.
    graph.chmod(0o600)
    return cache, graph


def test_separate_neighborhood_preserves_sources_direction_dates_and_identity(stores):
    cache, graph = stores
    raw = cache.read_bytes()
    with sqlite3.connect(graph) as db:
        result = import_shadow_aliases(db, cache, ['Alice'])
        assert result['followObservations'] == 3
        counts = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('entity', 'relation', 'evidence_snapshot')]
        import_shadow_aliases(db, cache, ['Alice'])
        assert counts == [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                          for t in ('entity', 'relation', 'evidence_snapshot')]
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='follows_observed'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE e.source_key='100'").fetchone()[0] == 0
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        snapshots=dict(db.execute('SELECT snapshot_id,payload FROM evidence_snapshot'))
    evidence=shadow_alias_preview(graph,handle='ALICE')
    assert evidence['status']=='available'
    assert evidence['bindingStatus']=='unresolved_handle_only'
    assert evidence['alias']=='shadow:alice'
    assert evidence['outgoingCount']==1 and evidence['incomingCount']==2
    assert evidence['scope']['totalRowsAtImport']==3
    outgoing=evidence['outgoing'][0]
    assert outgoing['target']['key']=='shadow:bob'
    assert outgoing['target']['profile']['bio']=='Meditation research'
    assert outgoing['source']['key']=='shadow:alice'
    assert outgoing['observedAt']=='2025-10-06 10:00:00'
    assert outgoing['captureTimeBasis']=='Stored capture time; timezone unspecified'
    source=json.loads(snapshots[outgoing['snapshotId']])
    assert source['row']['source_id']=='shadow:alice'
    carol=next(edge for edge in evidence['incoming'] if edge['source']['key']=='shadow:carol')
    assert carol['captureDirection']=='inbound'
    assert carol['source']['profile'] is None  # No archive_sync profile leakage.
    assert 'Carol Example' not in json.dumps(evidence)
    assert str(cache) not in json.dumps(evidence)
    assert cache.read_bytes()==raw


def test_scope_and_view_truncation_are_explicit(stores):
    cache, graph=stores
    with sqlite3.connect(graph) as db:
        result=import_shadow_aliases(db,cache,['alice'],limit=2)
        assert result['followObservations']==2
    evidence=shadow_alias_preview(graph,handle='alice',limit=1)
    assert evidence['scope']['selectedRows']==2
    assert evidence['scope']['totalRowsAtImport']==3
    assert evidence['scope']['truncated'] is True
    assert evidence['truncated'] is True
    assert len(evidence['incoming'])+len(evidence['outgoing']) <= 2


def test_not_imported_unconfigured_unavailable_are_distinct(stores,tmp_path):
    _,graph=stores
    assert shadow_alias_preview(None,handle='alice')['status']=='not_configured'
    assert shadow_alias_preview(graph,handle='alice')['status']=='not_imported'
    assert shadow_alias_preview(tmp_path/'missing.db',handle='alice')['status']=='unavailable'
    with pytest.raises(ValueError):shadow_alias_preview(graph,handle='../alice')


def test_bad_source_aborts_without_merging_or_writing(stores):
    cache,graph=stores
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE shadow_edge SET metadata='[]'")
    with sqlite3.connect(graph) as db:
        with pytest.raises(ValueError),db:import_shadow_aliases(db,cache,['alice'])
        assert db.execute('SELECT count(*) FROM relation').fetchone()[0]==0


def test_alias_copy_keeps_numeric_discovery_unchanged(stores,tmp_path):
    from scripts.verify_shadow_follow_batch import build_shadow_batch
    cache,graph=stores
    unused=tmp_path/'unused-archive.db'
    with sqlite3.connect(unused):pass
    report=build_shadow_batch(graph,cache,unused,tmp_path/'copy.db',handles=['alice'],limit=500)
    assert report['followObservations']==3
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    with sqlite3.connect(tmp_path/'copy.db') as db:
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='follows_observed'").fetchone()[0]==0
