"""Test intent: retained API references become explainable paths, not identity guesses.

-1/2-hop typed walks preserve original arrows and exact source/target/post IDs.
- Incoming traversal, cycles, unknown profiles, source/date refs remain explicit.
- Missing coverage refuses; invalid scope cannot become unscoped fallback.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.saved_api_posts import import_api_post_observations
from src.data.saved_api_paths import api_reference_paths, api_reference_sources
from src.data.social_paths import NetworkCoverageError
from tests.test_saved_api_posts import inputs

ALICE = '9007199254740993'


@pytest.fixture
def typed(inputs):
    source, graph = inputs
    with sqlite3.connect(source) as db:
        db.execute("UPDATE api_typed_edges SET target_id='400' WHERE target_id='300'")
        db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)', ('300', 'carol',
            json.dumps({'id':'300','userName':'carol','protected':False,'description':'Marxist design'}), '2026-08-03T10:00:00Z'))
        for src, target, kind, tweet, name in [('200','300','retweet','1007','bob'),
                                             ('300',ALICE,'reply','1008','carol')]:
            db.execute('INSERT INTO api_typed_edges VALUES(?,?,?,?,?,?,?)',
                (src,target,kind,tweet,'Sun Aug 02 19:46:46 +0000 2026','last_tweets_deep','2026-08-03T11:00:00Z'))
            db.execute('INSERT INTO enriched_tweets(tweet_id,account_id,username,text,created_at,fetch_source,fetched_at) VALUES(?,?,?,?,?,?,?)',
                (tweet,src,name,'Tools and Buddhism','Sun Aug 02 19:46:46 +0000 2026','last_tweets_deep','2026-08-03T11:05:00Z'))
    with sqlite3.connect(graph) as db: import_api_post_observations(db,source)
    return graph


def test_typed_two_hops_sources_and_unknown_names_are_exact(typed):
    before = typed.read_bytes()
    with sqlite3.connect(typed) as db:
        db.row_factory = sqlite3.Row
        paths, scope = api_reference_paths(db, ALICE, 2)
        assert '300' in paths
        assert [(e['sourceAccountId'],e['targetAccountId'],e['kind']) for e in paths['300']] == [
            (ALICE,'200','reply'),('200','300','repost')]
        assert all(e['tweetId'] and e['excerpt'] and e['evidenceRef']['sourcePointer']=='/row'
                   and e['postEvidenceRef']['sourcePointer']=='/row/text' for e in paths['300'])
        assert paths['300'][0]['createdAt']=='Sun Aug 02 19:46:46 +0000 2026'
        assert scope['kind']=='saved_api_refs' and scope['direction']=='outgoing'
        assert ALICE not in paths
        assert '300' not in api_reference_paths(db,ALICE,1)[0]
        assert '300' not in api_reference_paths(db,ALICE,2,kinds=['reply'])[0]
        sources=api_reference_sources(db)
        unknown=next(s for s in sources['sources'] if s['accountId']=='400')
        assert unknown['username'] is None
        assert next(s for s in sources['sources'] if s['accountId']==ALICE)['username']=='alice'
    assert typed.read_bytes()==before


def test_incoming_walk_keeps_original_edges_and_missing_direction_coverage_refuses(typed):
    with sqlite3.connect(typed) as db:
        db.row_factory=sqlite3.Row
        paths,scope=api_reference_paths(db,'300',2,direction='incoming')
        assert scope['direction']=='incoming'
        assert [(e['walkFromAccountId'],e['walkToAccountId']) for e in paths[ALICE]]==[('300','200'),('200',ALICE)]
        assert [(e['sourceAccountId'],e['targetAccountId']) for e in paths[ALICE]]==[('200','300'),(ALICE,'200')]
        with pytest.raises(NetworkCoverageError):api_reference_paths(db,'400',1)
        with pytest.raises(NetworkCoverageError):api_reference_paths(db,'555',1)
        for options in [{'max_hops':True},{'direction':'both'},{'kinds':[]},{'kinds':['follow']}]:
            with pytest.raises(ValueError):api_reference_paths(db,ALICE,**options)


def test_combined_search_applies_typed_scope_during_archive_failure(typed):
    from src.data.unified_evidence import search_all_evidence
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        options={'client':client,'from_account_id':ALICE,'network_kind':'saved_api_refs'}
        assert search_all_evidence(typed,None,'Marxist',max_hops=1,**options)['total']==0
        result=search_all_evidence(typed,None,'Marxist',max_hops=2,**options)
    assert result['total']==1 and result['status']=='partial'
    hit=result['results'][0]
    assert hit['accountId']=='300' and hit['networkPath']['kind']=='saved_api_refs'
    assert hit['networkPath']['hopCount']==2
    assert [n['accountId'] for n in hit['networkPath']['nodes']]==[ALICE,'200','300']
    assert str(typed) not in json.dumps(result)


def test_typed_routes_keep_auth_types_direction_missing_coverage_and_private_paths(typed,tmp_path,monkeypatch):
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR'):
        monkeypatch.setenv(key,str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(typed))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as upstream,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        sources='/api/research-notes/network/sources?networkKind=saved_api_refs&types=reply,repost'
        url=f'/api/research-notes/search/all?q=Marxist&networkKind=saved_api_refs&fromAccountId={ALICE}&maxHops=2'
        assert client.get(sources).status_code==401 and client.get(url).status_code==401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        assert client.get(sources).get_json()['coverage']['typedPairs']==4
        result=client.get(url)
        assert result.status_code==200 and result.get_json()['total']==1
        assert str(tmp_path) not in result.get_data(as_text=True)
        assert client.get(url+'&types=follow').status_code==400
        assert client.get(url.replace(ALICE,'400')).status_code==422
        assert client.get(sources.replace('reply,repost','')).status_code==400
        monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(tmp_path/'unavailable'))
        assert client.get(sources).status_code==503 and client.get(url).status_code==422


def test_repeated_post_capture_does_not_multiply_edges_or_reveal_archive_only_labels(typed):
    from src.data.saved_capture_import import CaptureWriter
    from src.data.saved_api_posts import POST
    from src.data.published_profile_access import SOURCE_KIND
    with sqlite3.connect(typed) as db:
        db.row_factory=sqlite3.Row
        w=CaptureWriter(db)
        row=db.execute('SELECT * FROM relation WHERE predicate=? LIMIT 1',(POST,)).fetchone()
        db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)',('synthetic-extra','synthetic',None,b'{}'))
        w.relation(row['subject_id'],POST,row['object_id'],'synthetic-extra',row['source_pointer'],
                   row['observed_at'],json.loads(row['attributes_json']))
        w.relation(w.entity('x_account','400'),'profile_observation',w.entity('x_profile','400'),
                   'synthetic-extra','/profile',None,{'handle':'forbidden_hidden','sourceKind':SOURCE_KIND})
        sources=api_reference_sources(db)
        assert sources['coverage']['typedPairs']==4 and sources['coverage']['postObservations']==4
        assert next(s for s in sources['sources'] if s['accountId']=='400')['username'] is None
        assert 'forbidden_hidden' not in json.dumps(sources)
