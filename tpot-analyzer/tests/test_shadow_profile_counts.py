"""Test intent: saved counts are exact-capture evidence, not current degree.

- Direct imports preserve optional integer counts; missing stays unknown,zero valid.
- Copy-backfill appends from immutable snapshots,retains old rows/links and repeats.
- Reject wrong types,source identity/date/hash and no borrowing from older profiles.
"""
import json
import sqlite3

import pytest

from src.data.shadow_aliases import import_shadow_aliases
from src.data.shadow_search import search_shadow_evidence
from src.data.saved_capture_import import CaptureWriter
from tests.test_shadow_aliases import stores


def add_counts(cache,following=700,followers=0):
    with sqlite3.connect(cache) as db:
        db.execute('ALTER TABLE shadow_account ADD COLUMN following_count')
        db.execute('ALTER TABLE shadow_account ADD COLUMN followers_count')
        db.execute('UPDATE shadow_account SET following_count=?,followers_count=? WHERE account_id=?',
                   (following,followers,'shadow:alice'))


def test_direct_import_preserves_counts_with_same_source_and_keeps_unknown_unknown(stores):
    cache,graph=stores;add_counts(cache)
    before=cache.read_bytes()
    with sqlite3.connect(graph) as db:import_shadow_aliases(db,cache,['alice'])
    row=search_shadow_evidence(graph,'alice')['results'][0]
    assert row['profile'].get('following_count')==700
    assert row['profile'].get('followers_count')==0
    assert row['profile']['evidenceRef']['sourcePointer']=='/row'
    assert row['profile']['fetched_at']=='2025-10-06 10:00:00'
    assert row['bindingStatus']=='unresolved_handle_only' and 'accountId' not in row
    unknown=search_shadow_evidence(graph,'bob')['results'][0]['profile']
    assert unknown.get('following_count') is None
    assert unknown.get('followers_count') is None
    assert cache.read_bytes()==before


def old_graph(cache,graph):
    add_counts(cache)
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE shadow_account SET bio='Research alice.example.org' WHERE account_id='shadow:alice'")
    with sqlite3.connect(graph) as db:
        import_shadow_aliases(db,cache,['alice'])
        db.row_factory=sqlite3.Row
        rows=db.execute("SELECT * FROM relation WHERE predicate='shadow_profile_observation'").fetchall()
        for row in rows:
            attrs=json.loads(row['attributes_json'])
            if not any(key in attrs for key in ('following_count','followers_count')):continue
            for key in ('following_count','followers_count'):attrs.pop(key,None)
            # Disposable fixture:recreate the real predecessor serializer and ID.
            db.execute('DELETE FROM relation WHERE relation_id=?',(row['relation_id'],))
            CaptureWriter(db).relation(row['subject_id'],row['predicate'],row['object_id'],
                row['snapshot_id'],row['source_pointer'],row['observed_at'],attrs)


def test_copy_backfill_retains_sources_links_counts_identity_and_repeats(stores,tmp_path):
    from scripts.verify_shadow_profile_counts import build_shadow_profile_count_batch
    cache,graph=stores;old_graph(cache,graph)
    raw=cache.read_bytes();prior=graph.read_bytes()
    old=search_shadow_evidence(graph,'alice')['results'][0]
    target=tmp_path/'copy.db';report=build_shadow_profile_count_batch(graph,target)
    new=search_shadow_evidence(target,'alice')['results'][0]
    assert report['profileCountObservations']==1 and report['countBearingProfiles']==1
    assert report['after']['relation']==report['before']['relation']+1
    assert report['after']['entity']==report['before']['entity']
    assert report['after']['evidence_snapshot']==report['before']['evidence_snapshot']
    assert report['reimportUnchanged'] and report['priorRowsRetained']
    assert new['profile']['following_count']==700 and new['profile']['followers_count']==0
    assert new['profile']['evidenceRef']==old['profile']['evidenceRef']
    assert new['profile']['bioLinks']==old['profile']['bioLinks']
    assert new['matchedFields']==old['matchedFields'] and new['networkPath']==old['networkPath']
    assert new['bindingStatus']=='unresolved_handle_only' and 'accountId' not in new
    assert cache.read_bytes()==raw and graph.read_bytes()==prior
    with pytest.raises(ValueError,match='No new historical profile counts'):
        build_shadow_profile_count_batch(target,tmp_path/'no-new.db')


@pytest.mark.parametrize('value',[-1,True,700.0,'700',9007199254740992])
def test_public_count_projection_refuses_lossy_coercion(value):
    from src.data.shadow_profile_counts import captured_profile_counts
    with pytest.raises(ValueError,match='safe integers'):
        captured_profile_counts({'following_count':value})
    assert captured_profile_counts({'following_count':None,'followers_count':0})=={'followers_count':0}


@pytest.mark.parametrize('field,value',[('username','different'),('fetched_at','2024-01-01'),
                                       ('following_count',999)])
def test_copy_refuses_disagreeing_profile_without_mutating_original(stores,tmp_path,field,value):
    from scripts.verify_shadow_profile_counts import build_shadow_profile_count_batch
    cache,graph=stores;old_graph(cache,graph)
    with sqlite3.connect(graph) as db:
        rid,encoded=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='shadow_profile_observation' AND json_extract(attributes_json,'$.username')='Alice'").fetchone()
        attrs=json.loads(encoded);attrs[field]=value
        db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
    before=graph.read_bytes();target=tmp_path/'refused.db'
    with pytest.raises(ValueError,match='disagree'):
        build_shadow_profile_count_batch(graph,target)
    assert graph.read_bytes()==before and not target.exists()


def test_copy_refuses_snapshot_hash_mismatch(stores,tmp_path):
    from scripts.verify_shadow_profile_counts import build_shadow_profile_count_batch
    cache,graph=stores;old_graph(cache,graph)
    with sqlite3.connect(graph) as db:
        key,payload=db.execute("SELECT s.snapshot_id,s.payload FROM evidence_snapshot s JOIN relation r USING(snapshot_id) WHERE r.predicate='shadow_profile_observation' AND json_extract(r.attributes_json,'$.username')='Alice'").fetchone()
        obj=json.loads(payload);obj['row']['following_count']=12
        db.execute('UPDATE evidence_snapshot SET payload=? WHERE snapshot_id=?',(json.dumps(obj).encode(),key))
    before=graph.read_bytes();target=tmp_path/'refused.db'
    with pytest.raises(ValueError,match='hash disagrees'):
        build_shadow_profile_count_batch(graph,target)
    assert graph.read_bytes()==before and not target.exists()


def test_latest_countless_capture_does_not_borrow_old_counts(stores,tmp_path):
    from scripts.verify_shadow_profile_counts import build_shadow_profile_count_batch
    cache,graph=stores;old_graph(cache,graph)
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE shadow_account SET following_count=NULL,followers_count=NULL,fetched_at='2026-03-01' WHERE account_id='shadow:alice'")
    with sqlite3.connect(graph) as db:import_shadow_aliases(db,cache,['alice'])
    with pytest.raises(ValueError,match='No new historical profile counts'):
        build_shadow_profile_count_batch(graph,tmp_path/'no-new.db')
    profile=search_shadow_evidence(graph,'alice')['results'][0]['profile']
    assert profile.get('following_count') is None and profile['fetched_at']=='2026-03-01'


def test_count_batch_adopts_with_prior_graph_package_and_index_retained(stores,tmp_path):
    from scripts.verify_shadow_profile_counts import build_shadow_profile_count_batch
    from src.data.local_graph_batch import adopt_graph
    cache,graph=stores;old_graph(cache,graph)
    target=tmp_path/'copy.db';report=build_shadow_profile_count_batch(graph,target)
    root=tmp_path/'managed';root.mkdir(mode=0o700)
    prior=root/'releases'/'prior';prior.mkdir(parents=True,mode=0o700)
    (prior/'graph').mkdir();(prior/'graph/relationships.db').symlink_to(graph)
    (prior/'package').mkdir();(prior/'index').mkdir();(prior/'index/posts.db').touch()
    (root/'current').symlink_to(prior)
    before=graph.read_bytes();receipt=adopt_graph(root,graph,target,report)
    current=(root/'current').resolve()
    assert current==tmp_path/receipt['release']
    assert (current/'graph/relationships.db').resolve()==target
    assert (current/'package').resolve()==prior/'package'
    assert (current/'index/posts.db').resolve()==prior/'index/posts.db'
    assert prior.exists() and graph.read_bytes()==before
