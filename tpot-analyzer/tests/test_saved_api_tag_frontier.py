"""Saved API references inform working-tag discovery without current Archive access."""
import json
import sqlite3
from contextlib import closing

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.account_tags import AccountTagStore
from src.data import post_tag_frontier
from src.data.published_profile_access import SOURCE_KIND as ARCHIVE_KIND
from src.data.saved_api_posts import PREDICATES, SOURCE_KIND, append_api_post_row
from src.data.saved_capture_import import CaptureWriter


def _build(graph, tags, **options):
    builder=getattr(post_tag_frontier,'build_saved_api_tag_frontier',None)
    assert callable(builder), 'saved API reference frontier reader is not available'
    ego=options.pop('ego','curator');tag=options.pop('tag','Builders')
    return builder(graph,tags,ego=ego,tag=tag,**options)


@pytest.fixture
def frontier(tmp_path):
    tmp_path.chmod(0o700)
    graph=tmp_path/'relationships.db'; tags=tmp_path/'account_tags.db'
    raw=tmp_path/'source.json'; raw.write_text('{"kind":"synthetic-reference-source"}')
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        writer=CaptureWriter(db); snapshot,_=writer.source(raw)
        def add(source,target,kind,tweet,copy=0):
            fetched=f'2026-10-01T10:{copy:02d}:00+00:00'
            post={'account_id':source,'tweet_id':tweet,'text':'Synthetic saved post',
                'created_at':'2026-09-01T00:00:00+00:00','fetch_source':'last_tweets',
                'fetched_at':fetched}
            actor=append_api_post_row(writer,raw,post)
            attrs={'sourceKind':SOURCE_KIND,'tweetId':tweet,'type':kind,
                'createdAt':post['created_at'],'fetchSource':'last_tweets'}
            predicate_kind='retweet' if kind=='repost' else kind
            writer.relation(actor,PREDICATES[predicate_kind],writer.entity('x_account',target),snapshot,
                f'/typed/{source}/{tweet}/{copy}',fetched,attrs)
        rows=[('100','500','reply','1001',0),('100','500','reply','1001',1),
            ('100','500','reply','1002',0),('100','500','quote','1003',0),
            ('200','500','mention','2001',0),('400','500','repost','4001',0),
            ('600','500','reply','6001',0),('300','500','quote','3001',0),
            ('100','800','reply','1004',0),('900','100','reply','9001',0)]
        for row in rows:add(*row)
        writer.relation(writer.entity('x_account','500'),'profile_observation',
            writer.entity('x_profile','archive-only'),snapshot,'/archive-profile',None,
            {'sourceKind':ARCHIVE_KIND,'handle':'must_not_leak','name':'Hidden label'})
        writer.relation(writer.entity('x_account','800'),'profile_observation',
            writer.entity('x_profile','independent'),snapshot,'/independent-profile',None,
            {'handle':'known_synthetic','name':'Known Synthetic'})
    graph.chmod(0o600)
    store=AccountTagStore(tags)
    for account,polarity in [('100',1),('200',1),('400',1),('600',1),('300',-1)]:
        store.upsert_tag(ego='curator',account_id=account,tag='Builders',polarity=polarity)
    store.upsert_tag(ego='another-curator',account_id='500',tag='Builders',polarity=1)
    store.upsert_tag(ego='curator',account_id='800',tag='Other',polarity=1)
    with closing(sqlite3.connect(tags)) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    tags.chmod(0o600)
    return graph,tags,store


def test_frontier_uses_distinct_tagged_anchors_caps_paths_and_keeps_unknown_names(frontier):
    graph,tags,_=frontier; before=(graph.read_bytes(),tags.read_bytes())
    result=_build(graph,tags,min_support=2,limit=1)
    assert result['status']=='provisional'
    assert result['target']=={'ego':'curator','tag':'Builders','tagKey':'builders'}
    assert result['source']=={'kind':'saved_api_post_row','status':'available',
        'coverage':{'typedPairs':8,'postObservations':9,'sourceAccounts':6}}
    assert result['anchors']['positive']=={'count':4,'matchingReferenceCount':4}
    assert result['anchors']['negative']=={'count':1,'matchingReferenceCount':1}
    assert result['diagnostics']=={'referenceCandidateCount':2,'candidateCount':1,'returnedCount':1}
    candidate=result['candidates'][0]
    assert candidate['accountId']=='500' and candidate['username'] is None
    assert candidate['displayName'] is None and candidate['posts']==[]
    assert candidate['positiveRawSupport']==4 and candidate['negativeRawSupport']==1
    assert candidate['positiveSupportingAnchors']==['100','200','400','600']
    assert candidate['negativeSupportingAnchors']==['300']
    assert candidate['shownSupportingPaths']==3 and len(candidate['supportingPaths'])==3
    for path in candidate['supportingPaths']:
        assert [node['accountId'] for node in path['nodes']][1]=='500'
        assert path['edges'][0]['walkFromAccountId']==path['nodes'][0]['accountId']
        assert path['edges'][0]['sourceAccountId']==path['nodes'][0]['accountId']
    assert 'must_not_leak' not in json.dumps(result) and 'Hidden label' not in json.dumps(result)
    assert result['semantics']['channel']=='saved_api_refs'
    assert result['semantics']['calibrated'] is False
    assert result['semantics']['recencyMeaning'].startswith('Historical/all-time')
    assert (graph.read_bytes(),tags.read_bytes())==before


def test_direction_type_limits_and_curator_mutations_are_applied_each_call(frontier):
    graph,tags,store=frontier
    incoming=_build(graph,tags,direction='incoming',kinds=['reply'],limit=1)
    assert [candidate['accountId'] for candidate in incoming['candidates']]==['900']
    path=incoming['candidates'][0]['supportingPaths'][0]
    assert [node['accountId'] for node in path['nodes']]==['100','900']
    edge=path['edges'][0]
    assert (edge['sourceAccountId'],edge['targetAccountId'])==('900','100')
    assert (edge['walkFromAccountId'],edge['walkToAccountId'])==('100','900')
    limited=_build(graph,tags,min_support=1,limit=1)
    assert limited['diagnostics']['candidateCount']==2
    assert limited['diagnostics']['returnedCount']==1
    store.upsert_tag(ego='curator',account_id='200',tag='Builders',polarity=-1)
    assert _build(graph,tags,min_support=4)['candidates']==[]
    store.delete_tag(ego='curator',account_id='200',tag='Builders')
    assert _build(graph,tags,min_support=4)['candidates']==[]
    store.upsert_tag(ego='curator',account_id='200',tag='Builders',polarity=1)
    assert _build(graph,tags,min_support=4)['candidates'][0]['accountId']=='500'
    store.upsert_tag(ego='curator',account_id='500',tag='Builders',polarity=-1)
    assert all(row['accountId']!='500' for row in _build(graph,tags,min_support=1)['candidates'])


def test_missing_references_and_validation_are_not_empty_success(frontier,tmp_path):
    graph,tags,_=frontier
    none=_build(graph,tags,tag='Unstarted')
    assert none['reason']=='no_positive_anchors' and none['status']=='insufficient'
    empty=tmp_path/'empty.db'
    with sqlite3.connect(empty) as db:db.executescript(SCHEMA)
    empty.chmod(0o600)
    no_refs=_build(empty,tags)
    assert no_refs['reason']=='no_saved_api_references'
    assert no_refs['source']['status']=='not_imported'
    assert no_refs['diagnostics']['candidateCount'] is None
    assert no_refs['anchors']['positive']['matchingReferenceCount'] is None
    assert no_refs['anchors']['negative']['matchingReferenceCount'] is None
    with pytest.raises((OSError,sqlite3.Error)):
        _build(tmp_path/'missing.db',tags)
    for options in ({'direction':'both'},{'kinds':[]},{'min_support':True},{'limit':0}):
        with pytest.raises(ValueError):_build(graph,tags,**options)
