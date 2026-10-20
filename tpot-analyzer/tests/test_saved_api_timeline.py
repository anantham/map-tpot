"""Test intent: already-saved independent text is useful without invented edges.

- Source/public-profile qualification, exact raw rows/dates and no handle joins.
- Existing post-author conflicts remain excluded, originals and prior rows retained.
- Repeated imports preserve old typed-row snapshots and exact-account search.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.saved_api_posts import import_api_post_observations, import_api_timeline_posts, api_post_fragments
from src.data.unified_evidence import search_all_evidence
from tests.test_saved_api_posts import inputs

ALICE='9007199254740993'


@pytest.fixture
def timeline(inputs):
    source,graph=inputs
    with sqlite3.connect(source) as db:
        db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)',('88','unknown',
            json.dumps({'id':'88','userName':'unknown','description':'Jhana'}),'2026-08-03T10:00:00Z'))
        rows=[('1007',ALICE,'alice','Jhana open-source research','advanced_search'),
              ('1008','42','missing','Do not surface missing profile','last_tweets'),
              ('1009',ALICE,'alice','Interpretability tools','topic_seed'),
              ('1010','88','unknown','Do not surface unknown privacy','last_tweets')]
        for tid,aid,handle,text,kind in rows:
            db.execute('INSERT INTO enriched_tweets(tweet_id,account_id,username,text,created_at,fetch_source,fetched_at,mentions_json,in_reply_to_user) VALUES(?,?,?,?,?,?,?,?,?)',
                (tid,aid,handle,text,'Wed Feb 25 01:02:03 +0000 2026',kind,'2026-08-03T12:00:00Z',
                 '["bob"]','bob'))
    return source,graph


def test_standalone_text_qualifies_without_typed_edge_and_keeps_originals(timeline):
    source,graph=timeline;original=source.read_bytes()
    with sqlite3.connect(graph) as db:
        report=import_api_timeline_posts(db,source)
        assert report['apiPosts']==6 and report['postObservationsAdded']==6
        assert report['selectedRows']==9 and report['typedReferences']==0
        assert len(report['exclusions'])==3 and report['excludedSourceCounts']=={'archive':1}
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN('mentioned_account_observed','replied_to_account_observed')").fetchone()[0]==0
        db.row_factory=sqlite3.Row
        posts,coverage=api_post_fragments(db)
        assert coverage=={'apiPostObservations':6,'apiPostAccounts':2,'apiTypedReferences':0}
        post=next(p for p in posts[ALICE] if p['tweetId']=='1007')
        assert post['text']=='Jhana open-source research' and post['references']==[]
        assert post['createdAt']=='Wed Feb 25 01:02:03 +0000 2026'
        saved=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',
            (post['evidenceRef']['snapshotId'],)).fetchone()[0])
        assert saved['row']['mentions_json']=='["bob"]' and saved['row']['fetch_source']=='advanced_search'
        assert post['evidenceRef']['sourcePointer']=='/row/text'
        assert import_api_timeline_posts(db,source)['postObservationsAdded']==0
    assert source.read_bytes()==original
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        result=search_all_evidence(graph,None,'India Jhana',client=client)
    assert result['total']==1 and result['results'][0]['accountId']==ALICE
    assert result['results'][0]['ranking']['savedWords']==['india']
    assert any(m['kind']=='api_post' and 'Jhana' in m['excerpt'] for m in result['results'][0]['matches'])
    assert str(source) not in json.dumps(result)


def test_previously_imported_typed_post_is_not_added_again(timeline):
    source,graph=timeline
    with sqlite3.connect(graph) as db:
        import_api_post_observations(db,source)
        prior=db.execute('SELECT * FROM relation').fetchall()
        report=import_api_timeline_posts(db,source)
        assert report['apiPosts']==6 and report['postObservationsAdded']==4
        assert all(row in db.execute('SELECT * FROM relation').fetchall() for row in prior)
        assert import_api_timeline_posts(db,source)['postObservationsAdded']==0


def test_existing_graph_post_author_conflict_is_explicit_not_new_attribution(timeline):
    source,graph=timeline
    with sqlite3.connect(graph) as db:import_api_post_observations(db,source)
    with sqlite3.connect(source) as db:db.execute("UPDATE enriched_tweets SET account_id='200' WHERE tweet_id='1001'")
    with sqlite3.connect(graph) as db:
        report=import_api_timeline_posts(db,source)
        assert {'tweetId':'1001','reason':'existing_post_author_conflict'} in report['exclusions']
        authors=db.execute("SELECT a.source_key FROM relation r JOIN entity a ON a.entity_id=r.subject_id JOIN entity p ON p.entity_id=r.object_id WHERE r.predicate='api_post_observation' AND p.source_key='1001'").fetchall()
        assert authors==[(ALICE,)]


def test_missing_raw_profile_cannot_be_rescued_by_old_graph_profile(timeline):
    source,graph=timeline
    with sqlite3.connect(graph) as db:import_api_post_observations(db,source)
    with sqlite3.connect(source) as db:db.execute('UPDATE user_profile_cache SET raw_json=NULL')
    with sqlite3.connect(graph) as db:
        report=import_api_timeline_posts(db,source)
        assert report['apiPosts']==0 and report['postObservationsAdded']==0


def test_timeline_copy_is_additive_and_malformed_ids_leave_no_derivative(timeline,tmp_path):
    from scripts.verify_api_post_batch import build_api_post_batch
    source,graph=timeline
    with sqlite3.connect(graph) as db:import_api_post_observations(db,source)
    raw,baseline=source.read_bytes(),graph.read_bytes()
    output=tmp_path/'copy.db'
    report=build_api_post_batch(graph,source,output,source_mode='timeline')
    assert report['postObservationsAdded']==4 and report['priorRowsRetained'] and report['reimportUnchanged']
    assert source.read_bytes()==raw and graph.read_bytes()==baseline
    with pytest.raises(ValueError,match='mode'):
        build_api_post_batch(graph,source,tmp_path/'bad-mode.db',source_mode='guess')
    with sqlite3.connect(source) as db:db.execute("UPDATE enriched_tweets SET tweet_id='not_numeric' WHERE tweet_id='1007'")
    with pytest.raises(ValueError,match='numeric'):
        build_api_post_batch(graph,source,tmp_path/'bad-id.db',source_mode='timeline')
    assert not (tmp_path/'bad-id.db').exists()
