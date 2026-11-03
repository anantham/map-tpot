"""Test intent: historical bio mentions are source-backed links, not identity.

- Existing import/search surfaces recover explicit and bare bio URLs.
- Preserve literal text, assumed scheme, source field/date and exact alias.
- Repeat imports are stable; blocked sources/unsafe URLs never become links.
- No numeric identity, reviewed contact route or credential is inferred.
"""
import json
import sqlite3

import pytest

from scripts.verify_shadow_bio_links import build_shadow_bio_link_batch
from src.data.saved_capture_import import CaptureWriter
from src.data.shadow_aliases import import_shadow_aliases
from src.data.shadow_search import search_shadow_evidence
from tests.test_shadow_aliases import stores


def test_import_and_search_expose_literal_bio_links_without_identity_or_contact_promotion(stores):
    cache, graph = stores
    bio = 'Research https://research.example.org/paper?a=1&amp;b=2 and alice.example.org/contact.'
    with sqlite3.connect(cache) as db:
        db.execute('UPDATE shadow_account SET bio=? WHERE account_id=?', (bio, 'shadow:alice'))
        db.execute('UPDATE shadow_account SET bio=? WHERE account_id=?',
                   ('bob@example.org https://user:secret@example.org/ https://x.com/bob', 'shadow:bob'))
        db.execute('UPDATE shadow_account SET bio=? WHERE account_id=?', ('hidden.example.org', 'shadow:carol'))
    raw = cache.read_bytes()
    with sqlite3.connect(graph) as db:
        report = import_shadow_aliases(db, cache, ['alice'])
        rows = db.execute("SELECT e.kind,e.source_key,t.source_key,r.source_pointer,r.observed_at,s.payload,r.attributes_json "
            'FROM relation r JOIN entity e ON e.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id '
            "JOIN evidence_snapshot s USING(snapshot_id) WHERE r.predicate='profile_links_to'").fetchall()
        assert {r[2] for r in rows} == {
            'https://research.example.org/paper?a=1&b=2', 'https://alice.example.org/contact'}
        assert all(r[0:2] == ('unresolved_account', 'shadow:alice') for r in rows)
        assert all(r[3:5] == ('/row/bio', '2025-10-06 10:00:00') for r in rows)
        assert all(json.loads(r[5])['row']['bio'] == bio for r in rows)
        assert report['bioLinkObservations'] == 2
        before = db.execute('SELECT count(*) FROM relation').fetchone()[0]
        assert import_shadow_aliases(db, cache, ['alice'])['bioLinkObservations'] == 0
        assert db.execute('SELECT count(*) FROM relation').fetchone()[0] == before
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','has_contact_route','works_at')").fetchone()[0] == 0
    row = search_shadow_evidence(graph, 'alice')['results'][0]
    links = row['profile'].get('bioLinks', [])
    assert {link['url'] for link in links} == {r[2] for r in rows}
    bare = next(link for link in links if link['url'] == 'https://alice.example.org/contact')
    assert bare['literal'] == 'alice.example.org/contact' and bare['schemeAssumed'] is True
    assert bare['evidenceRef']['sourcePointer'] == '/row/bio'
    assert bare['sourceChannel'] == 'hybrid_selenium'
    assert 'accountId' not in row and cache.read_bytes() == raw


def test_copied_backfill_preserves_old_rows_sources_and_repeat_behavior(stores,tmp_path):
    cache,graph=stores
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE shadow_account SET bio='alice.example.org' WHERE account_id='shadow:alice'")
    with sqlite3.connect(graph) as db:
        import_shadow_aliases(db,cache,['alice'])
        # Isolated fixture: simulate an older graph before bio-link projection existed.
        db.execute("DELETE FROM relation WHERE predicate='profile_links_to'")
        source=tmp_path/'blocked.json';source.write_text(json.dumps({'bio':'hidden.example.org'}))
        w=CaptureWriter(db);snapshot,_=w.source(source);blocked=w.entity('unresolved_account','shadow:hidden')
        w.relation(blocked,'shadow_profile_observation',w.entity('shadow_profile','shadow:hidden'),
            snapshot,'/row','2025-10-06 10:00:00',{'username':'hidden','bio':'hidden.example.org',
            'sourceChannel':'archive_sync','fetched_at':'2025-10-06 10:00:00'})
        snapshots=db.execute('SELECT count(*) FROM evidence_snapshot').fetchone()[0]
    before=graph.read_bytes();raw=cache.read_bytes();target=tmp_path/'copy.db'
    report=build_shadow_bio_link_batch(graph,target)
    assert report['bioLinkObservations']==1 and report['historicalProfileObservations']==2
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    assert report['after']['evidence_snapshot']==snapshots
    assert search_shadow_evidence(target,'alice')['results'][0]['profile']['bioLinks'][0]['url']=='https://alice.example.org'
    assert graph.read_bytes()==before and cache.read_bytes()==raw
    with pytest.raises(ValueError,match='No new historical bio URL'):
        build_shadow_bio_link_batch(target,tmp_path/'no-new-links.db')
    assert graph.read_bytes()==before


@pytest.mark.parametrize('field,value',[('username','different'),('fetched_at','2024-01-01')])
def test_copied_backfill_refuses_wrong_identity_or_date_without_mutating_source(stores,tmp_path,field,value):
    cache,graph=stores
    with sqlite3.connect(graph) as db:
        import_shadow_aliases(db,cache,['alice'])
        row=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='shadow_profile_observation' LIMIT 1").fetchone()
        attrs=json.loads(row[1]);attrs[field]=value
        db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),row[0]))
    before=graph.read_bytes();target=tmp_path/'refused.db'
    with pytest.raises(ValueError,match='disagree'):
        build_shadow_bio_link_batch(graph,target)
    assert graph.read_bytes()==before and not target.exists()


def test_latest_profile_does_not_borrow_links_from_older_capture(stores,tmp_path):
    cache,graph=stores
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE shadow_account SET bio='alice.example.org' WHERE account_id='shadow:alice'")
    with sqlite3.connect(graph) as db:
        import_shadow_aliases(db,cache,['alice'])
        w=CaptureWriter(db);source=tmp_path/'newer.json'
        source.write_text(json.dumps({'bio':'New research, no link stated here'}))
        snapshot,_=w.source(source);alias=w.entity('unresolved_account','shadow:alice')
        w.relation(alias,'shadow_profile_observation',w.entity('shadow_profile','shadow:alice'),
            snapshot,'/row','2026-03-01T00:00:00Z',{'username':'alice','bio':'New research, no link stated here',
            'fetched_at':'2026-03-01T00:00:00Z','sourceChannel':'hybrid_selenium',
            'captureTimeBasis':'Stored timezone-aware capture time'})
    row=search_shadow_evidence(graph,'alice')['results'][0]
    assert row['profile']['bioLinks']==[]
    with sqlite3.connect(graph) as db:
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='profile_links_to'").fetchone()[0]==1


def test_damaged_link_target_refuses_instead_of_becoming_a_contact(stores):
    cache,graph=stores
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE shadow_account SET bio='alice.example.org' WHERE account_id='shadow:alice'")
    with sqlite3.connect(graph) as db:
        import_shadow_aliases(db,cache,['alice'])
        wrong=CaptureWriter(db).entity('web_resource','https://different.example.org/')
        db.execute("UPDATE relation SET object_id=? WHERE predicate='profile_links_to'",(wrong,))
    with pytest.raises(ValueError,match='disagrees with its source profile'):
        search_shadow_evidence(graph,'alice')
