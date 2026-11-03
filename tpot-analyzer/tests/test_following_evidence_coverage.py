"""Test intent: exact-person coverage, not identity or completeness scores.

- Public HTTP reads count admitted observations without duplicate inflation.
- Privacy, source eligibility, owner scope and unavailable channels stay explicit.
- Reads preserve raw/tag/candidate/journal bytes and never initialize decisions.
"""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from tests.test_following_roster_routes import roster_client
from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_api_posts import append_api_post_row, SOURCE_KIND
from tests.test_post_search import posts,public_client
from tests.test_published_profiles import bundle

AID='9007199254740993'


@pytest.fixture
def covered(roster_client,tmp_path,monkeypatch):
    client,cache,tags=roster_client
    for key in ('MAP_TPOT_FOLLOWING_COVERAGE','MAP_TPOT_POST_INDEX'):
        monkeypatch.delenv(key,raising=False)
    graph=tmp_path/'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO evidence_snapshot VALUES ('fixture','synthetic',NULL,'{}')")
        w=CaptureWriter(db)
        actors={aid:w.entity('x_account',aid) for aid in (AID,'100','200','999')}
        for aid,handle in ((AID,'first'),('200','second'),('999','outsider')):
            w.relation(actors[aid],'profile_observation',w.entity('x_profile',aid),'fixture',
                '/profile', '2025-01-01',{'handle':handle,'sourceKind':'saved_twitterapi_profile'})
        for when in ('2025-01-01','2025-02-01'):
            w.relation(actors[AID],'follows_observed',actors['200'],'fixture','/follow',when,{})
        w.relation(actors['200'],'follows_observed',actors[AID],'fixture','/reverse','2025-01-01',{})
        w.relation(actors[AID],'shadow_follows_observed',w.entity('unresolved_account','shadow:invented'),
            'fixture','/shadow','2025-01-01',{'sourceKind':'shadow_follow_observation'})
        for when in ('2025-01-01','2025-02-01'):
            append_api_post_row(w,Path('synthetic.db'),{'account_id':AID,'tweet_id':'555',
                'text':'SYNTHETIC_POST_CANARY','created_at':'2024-12-01T00:00:00+00:00',
                'fetch_source':'last_tweets','fetched_at':when})
        w.relation(actors[AID],'replied_to_account_observed',actors['200'],'fixture','/ref',
            '2025-01-01',{'sourceKind':SOURCE_KIND,'tweetId':'555','type':'reply',
                'createdAt':'2024-12-01T00:00:00+00:00','fetchSource':'last_tweets'})
        w.relation(actors[AID],'research_associates_with',w.entity('web_resource','https://work.example.test/'),
            'fixture','/work','2025-01-01',{'title':'Synthetic work','url':'https://work.example.test/'})
    graph.chmod(0o600)
    cat=tmp_path/'candidates.json'
    candidates=[{'accountId':aid,'kind':'profile','scope':'unknown','platform':platform,
        'value':f'https://{platform.lower()}.example.test/{aid}',
        'evidence':[{'url':'https://source.example.test/','note':'Synthetic',
            'sourceType':'public_research','observedAt':'2025-01-01'}]}
        for aid,platform in ((AID,'GitHub'),(AID,'LinkedIn'),('999','PRIVATE_PLATFORM_CANARY'))]
    cat.write_text(json.dumps({'schemaVersion':1,'candidates':candidates}));cat.chmod(0o600)
    journal=tmp_path/'person_card_reviews.db'
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('MAP_TPOT_CONTACT_CANDIDATES',str(cat))
    monkeypatch.setenv('MAP_TPOT_CONTACT_MATCH_DB',str(journal))
    return client,graph,cat,journal,cache,tags


def response(covered):
    result=covered[0].get('/api/research-notes/following?ego=synthetic&coverage=1')
    assert result.status_code==200
    return result,result.get_json()


def test_coverage_counts_exact_people_and_deduplicates_saved_evidence(covered):
    _,graph,cat,journal,cache,tags=covered
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (graph,cat,cache,tags)}
    result,body=response(covered)
    assert body.get('evidenceCoverage',{}).get('graph',{}).get('status')=='available'
    rows={r['accountId']:r for r in body['accounts']}
    cov=rows[AID]['evidenceCoverage']
    assert cov['follows']['outgoing']==cov['follows']['incoming']==1
    assert cov['shadowFollows']['outgoing']==1 and cov['shadowFollows']['incoming']==0
    assert cov['apiPosts']['count']==1 and cov['apiPosts']['firstAt']=='2024-12-01T00:00:00+00:00'
    assert cov['references']['reply']=={'outgoing':1,'incoming':0}
    assert rows['200']['evidenceCoverage']['references']['reply']['incoming']==1
    assert cov['works']['count']==1 and cov['pages']['count']==0
    assert cov['platforms']=={'status':'available','confirmed':[],
        'possible':['GitHub','LinkedIn'],'rejected':[]}
    assert cov['archivePosts']['status']=='not_configured'
    assert cov['websitePass']['status']=='not_configured'
    assert rows[AID]['tags']==[{'tag':'Makers','polarity':1}]
    assert '999' not in rows
    assert all(token not in result.text for token in ('SYNTHETIC_POST_CANARY',
        'PRIVATE_PLATFORM_CANARY','source.example.test','synthetic.db'))
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
    assert not journal.exists()


def test_coverage_distinguishes_curator_confirmation_from_possible_profiles(covered):
    from src.data.contact_matches import load_candidates,record_contact_match
    _,_,cat,journal,_,_=covered
    candidates=load_candidates(cat)
    github=next(c for c in candidates.values() if c['accountId']==AID and c['platform']=='GitHub')
    record_contact_match(cat,journal,account_id=AID,ego='other',candidate_id=github['candidateId'],
        state='confirmed',source='human_curator_api')
    assert response(covered)[1]['accounts'][0]['evidenceCoverage']['platforms']['confirmed']==[]
    record_contact_match(cat,journal,account_id=AID,ego='synthetic',candidate_id=github['candidateId'],
        state='confirmed',source='human_curator_api')
    before=journal.read_bytes()
    row=next(r for r in response(covered)[1]['accounts'] if r['accountId']==AID)
    assert row['evidenceCoverage']['platforms']['confirmed']==['GitHub']
    assert row['evidenceCoverage']['platforms']['possible']==['LinkedIn']
    assert journal.read_bytes()==before


def test_coverage_channel_failure_does_not_erase_list_or_tags(covered,monkeypatch,tmp_path):
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(tmp_path/'missing.db'))
    _,body=response(covered)
    assert body['total']==2 and body['tagStatus']=='available'
    assert body['evidenceCoverage']['graph']['status']=='unavailable'
    for row in body['accounts']:
        cov=row['evidenceCoverage']
        assert cov['follows'] is None and cov['apiPosts'] is None and cov['pages'] is None
        assert cov['platforms']['status']=='not_admitted'
    assert not (tmp_path/'missing.db').exists()


@pytest.mark.parametrize('flag',['true','0','maybe'])
def test_coverage_flag_is_explicit_and_auth_precedes_reads(covered,flag):
    client=covered[0]
    assert client.get('/api/research-notes/following?ego=synthetic&coverage='+flag).status_code==400
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get('/api/research-notes/following?ego=synthetic&coverage=1').status_code==401


@pytest.fixture
def saved_pass(covered,tmp_path,monkeypatch):
    capture=tmp_path/'capture';capture.mkdir()
    receipt={'status':'captured','seeds':[{'handle':'synthetic','account_id':'100',
        'complete':True,'api_terminal_page':True,'following_claim':2,'following_claim_after':2}]}
    roster={'accountId':'100','completeByProviderCount':True,
        'capturedFrom':'2026-01-02T00:00:00+00:00','capturedTo':'2026-01-02T00:01:00+00:00',
        'accounts':[{'id':AID},{'id':'200'}]}
    (capture/'receipt.json').write_text(json.dumps(receipt))
    (capture/'roster.json').write_text(json.dumps(roster))
    folder=tmp_path/'pass';folder.mkdir()
    cohort={'sourceCapture':str(capture),'createdAt':'2026-10-22T00:00:00+00:00',
        'accounts':[{'accountId':AID},{'accountId':'200'}]}
    ledger=[{'accountId':aid,'status':status,'retainedPageObservations':0,
        'connectedPages':0,'remainingAdmittedRootUrls':0} for aid,status in
        ((AID,'privacy_hold'),('200','no_saved_bio_website'))]
    for name,value in (('cohort.json',cohort),('coverage-ledger.json',ledger)):
        path=folder/name;path.write_text(json.dumps(value));path.chmod(0o600)
    monkeypatch.setenv('MAP_TPOT_FOLLOWING_CAPTURE',str(capture))
    monkeypatch.setenv('MAP_TPOT_FOLLOWING_COVERAGE',str(folder))
    return folder


def test_saved_pass_holds_suppress_counts_without_deleting_tags_or_evidence(covered,saved_pass):
    _,body=response(covered)
    rows={r['accountId']:r for r in body['accounts']}
    assert body['evidenceCoverage']['websitePass']['status']=='available'
    assert rows[AID]['evidenceCoverage']=={'status':'privacy_held'}
    assert rows[AID]['tags']==[{'tag':'Makers','polarity':1}]
    assert rows['200']['evidenceCoverage']['websitePass']['status']=='no_saved_bio_website'
    result=covered[0].get('/api/research-notes/following?ego=synthetic&coverage=1&source=historical').get_json()
    assert result['evidenceCoverage']['websitePass']['status']=='outside_capture'


@pytest.mark.parametrize('fault',['different_capture','duplicate','unknown_outcome','bad_count'])
def test_invalid_ledger_is_unknown_not_a_negative_finding(covered,saved_pass,fault):
    file=saved_pass/('cohort.json' if fault=='different_capture' else 'coverage-ledger.json')
    value=json.loads(file.read_bytes())
    if fault=='different_capture':value['sourceCapture']=str(saved_pass/'different')
    if fault=='duplicate':value.append(dict(value[0]))
    if fault=='unknown_outcome':value[0]['status']='complete_no_contacts'
    if fault=='bad_count':value[0]['connectedPages']=True
    file.write_text(json.dumps(value))
    _,body=response(covered)
    assert body['evidenceCoverage']['websitePass']['status']=='unavailable'
    assert all(r['evidenceCoverage']['websitePass']['status']=='unavailable' for r in body['accounts'])


@pytest.mark.parametrize('fault,expected',[(None,'available'),('checksum','superseded'),
    ('http','unavailable'),('withdrawn','withdrawn')])
def test_archive_coverage_obeys_current_publication_and_keeps_sources_independent(
        covered,posts,tmp_path,monkeypatch,fault,expected):
    from src.data.post_index import build_post_index
    build_post_index(posts,tmp_path/'index')
    monkeypatch.setenv('MAP_TPOT_POST_INDEX',str(tmp_path/'index/posts.db'))
    with public_client(posts,fault) as upstream:
        covered[0].application.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        result,body=response(covered)
    assert body['evidenceCoverage']['archive']['status']==expected
    row=next(r for r in body['accounts'] if r['accountId']==AID)['evidenceCoverage']
    assert row['apiPosts']['count']==1
    assert row['archivePosts']['status']==expected
    if expected=='available':assert row['archivePosts']['count']==2
    else:assert 'count' not in row['archivePosts']
    assert 'Buddhism' not in result.text and 'Marxist' not in result.text


def test_post_text_variants_are_not_multiple_posts(covered):
    with sqlite3.connect(covered[1]) as db:
        append_api_post_row(CaptureWriter(db),Path('synthetic.db'),{'account_id':AID,'tweet_id':'555',
            'text':'Different retained rendering','created_at':'2024-12-01T00:00:00+00:00',
            'fetch_source':'last_tweets','fetched_at':'2025-03-01'})
    row=next(r for r in response(covered)[1]['accounts'] if r['accountId']==AID)
    assert row['evidenceCoverage']['apiPosts']['count']==1
