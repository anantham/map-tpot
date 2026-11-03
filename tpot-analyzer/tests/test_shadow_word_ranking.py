"""Behavior: word support ranks before fragment collisions, without losing recall.

Use the existing public reader, real three-table synthetic graph and source paths.
No live data, inferred identity, opaque relevance score or membership label.
"""
import json
import sqlite3

import pytest

from src.data.saved_capture_import import CaptureWriter
from src.data.shadow_aliases import PROFILE
from src.data.shadow_search import search_shadow_evidence
from tests.test_shadow_search import graph


def add_profile(path, handle, bio):
    with sqlite3.connect(path) as db:
        writer=CaptureWriter(db)
        alias=writer.entity('unresolved_account','shadow:'+handle)
        writer.relation(alias,PROFILE,writer.entity('shadow_profile','shadow:'+handle),
            'synthetic-source','/row','2025-10-06 10:00:00',{
                'username':handle,'display_name':handle,'bio':bio,
                'sourceChannel':'hybrid_selenium','fetched_at':'2025-10-06 10:00:00',
                'captureTimeBasis':'Stored capture time; timezone unspecified'})


def test_whole_words_rank_before_inside_word_collision_and_limit_is_applied_last(graph):
    add_profile(graph,'aaa_aid','Open Aid helps with resources')
    add_profile(graph,'zzz_builder','Open-source tools')
    before=graph.read_bytes()
    first=search_shadow_evidence(graph,'open source',limit=1)
    assert first['results'][0]['alias']=='shadow:zzz_builder'
    assert first['total']==2 and first['truncated']
    assert first['matchCounts']=={'wholeWords':1,'partialText':1}
    all_rows=search_shadow_evidence(graph,'open source')['results']
    assert {row['alias'] for row in all_rows}=={'shadow:aaa_aid','shadow:zzz_builder'}
    assert all_rows[0]['ranking']=={'matchKind':'whole_words',
        'wholeWordFields':{'open':['bio'],'source':['bio']},'partialTerms':[]}
    assert all_rows[1]['ranking']=={'matchKind':'partial_text',
        'wholeWordFields':{'open':['bio'],'source':[]},'partialTerms':['source']}
    assert all_rows[1]['matchedFields']=={'open':['bio'],'source':['bio']}
    assert all_rows[1]['profile']['evidenceRef']['snapshotId']=='synthetic-source'
    assert graph.read_bytes()==before


def test_word_tier_precedes_hop_distance_but_paths_and_within_tier_hops_stay_exact(graph):
    add_profile(graph,'bob','Open help for resources')
    add_profile(graph,'carol','Open source tools')
    result=search_shadow_evidence(graph,'open source',from_handle='alice',max_hops=2)
    assert [row['alias'] for row in result['results']]==['shadow:carol','shadow:bob']
    assert [len(row['networkPath']) for row in result['results']]==[2,1]
    edges=result['results'][0]['networkPath']
    assert [(e['source']['key'],e['target']['key']) for e in edges]==[
        ('shadow:alice','shadow:bob'),('shadow:bob','shadow:carol')]
    assert edges[-1]['captureDirection']=='inbound'
    assert all(e['snapshotId']=='synthetic-source' and e['sourcePointer']=='/row' for e in edges)
    add_profile(graph,'bob','Open-source design')
    tied=search_shadow_evidence(graph,'open source',from_handle='alice',max_hops=2)
    assert [row['alias'] for row in tied['results']]==['shadow:bob','shadow:carol']


@pytest.mark.parametrize('query,bio,kind',[
    ('open source','OPEN-SOURCE community','whole_words'),
    ('open source','open_source community','whole_words'),
    ('open source','Open support from resources','partial_text'),
    ('open source','Open projects and published sources','whole_words'),
    ('ai','Available resources','partial_text'),
    ('ai','AIs and agents','whole_words'),
    ('c++','C++ systems engineer','whole_words'),
    ('c++','C++17 systems engineer','partial_text'),
    ('a.*','Literal a.* here','whole_words'),
    ('café','Café design','whole_words'),
    ('café','Caféteria design','partial_text'),
    ('禅定','禅定 practice','whole_words'),
    ('禅定','禅定会 practice','partial_text'),
])
def test_visible_boundary_convention_preserves_literal_candidates(graph,query,bio,kind):
    add_profile(graph,'querycase',bio)
    result=search_shadow_evidence(graph,query)
    row=next(row for row in result['results'] if row['alias']=='shadow:querycase')
    assert row['ranking']['matchKind']==kind
    assert result['matchCounts']['wholeWords']+result['matchCounts']['partialText']==result['total']
    assert row['profile']['bio']==bio and row['bindingStatus']=='unresolved_handle_only'
    assert 'accountId' not in row and 'score' not in row['ranking']


def test_partial_prefixes_and_cross_field_word_support_stay_available(graph):
    prefix=search_shadow_evidence(graph,'meditat')
    assert prefix['total']==1 and prefix['results'][0]['alias']=='shadow:alice'
    assert prefix['matchCounts']=={'wholeWords':0,'partialText':1}
    assert prefix['results'][0]['ranking']['partialTerms']==['meditat']
    cross=search_shadow_evidence(graph,'buddhism bengaluru')['results'][0]
    assert cross['ranking']['wholeWordFields']=={'buddhism':['bio'],'bengaluru':['location']}
    assert cross['ranking']['matchKind']=='whole_words'
    assert search_shadow_evidence(graph,'12345')['results'][0]['alias']=='shadow:12345'


def test_api_exposes_tiers_without_weakening_auth_or_mutating_the_graph(graph,tmp_path,monkeypatch):
    for name in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                 'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR',
                 'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(name,str(tmp_path/name))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    from flask import Flask
    from src.api.routes.research_notes_shadow import research_notes_shadow_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_shadow_bp)
    client=app.test_client();url='/api/research-notes/shadow/search?q=meditat'
    assert client.get(url).status_code==401
    before=graph.read_bytes()
    response=client.get(url,headers={'X-TPOT-Curator-Token':'synthetic-token'})
    assert response.status_code==200
    result=response.get_json()
    assert result['matchCounts']=={'wholeWords':0,'partialText':1}
    assert result['results'][0]['ranking']['matchKind']=='partial_text'
    assert str(tmp_path) not in json.dumps(result) and graph.read_bytes()==before
