"""Test intent: explicit OR wording within interests, AND across one exact account.

Use real source-shaped stores. Preserve plain-query behavior, source refusal,
complete candidate pools, scope and ranking without counting synonyms twice.
"""
import json
import sqlite3

import pytest

from src.data.saved_capture_import import CaptureWriter
from tests.test_unified_evidence import joined, ranked, posts, saved, bundle, run, public_client, ACCOUNT


def test_alternative_words_span_same_account_sources_without_guessing_synonyms(joined):
    before={path:path.read_bytes() for path in joined[:2]}
    result=run(joined,'dharma|Buddhism India meditation|practice')
    assert result['total']==1
    hit=result['results'][0]
    assert hit['accountId']==ACCOUNT
    assert hit['interestMatches']==[
        {'alternatives':['dharma','buddhism'],'matchedWords':['buddhism']},
        {'alternatives':['india'],'matchedWords':['india']},
        {'alternatives':['meditation','practice'],'matchedWords':['meditation','practice']}]
    assert result['historical']['status']=='not_searched'
    assert all(path.read_bytes()==raw for path,raw in before.items())
    assert run(joined,'dharma India')['total']==0  # No automatic synonym expansion.


def test_alternative_groups_never_join_different_accounts_or_escape_scope(joined):
    assert run(joined,'India|Mumbai backend|engineering')['total']==0
    with sqlite3.connect(joined[0]) as db:
        writer=CaptureWriter(db)
        for source,target in [('200','300'),('300',ACCOUNT)]:
            writer.relation(writer.entity('x_account',source),'follows_observed',
                writer.entity('x_account',target),'synthetic','/follows','2026-01-01',
                {'receiptRef':{'snapshotId':'synthetic','sourcePointer':'/follows'}})
    assert run(joined,'Buddhism|dharma India',from_account_id='200',max_hops=1)['total']==0
    found=run(joined,'Buddhism|dharma India',from_account_id='200',max_hops=2)
    assert found['total']==1 and found['results'][0]['networkPath']['hopCount']==2


def test_plain_query_order_and_support_stay_unchanged_and_variants_count_once(joined,tmp_path):
    result=run(joined,'India meditation')
    repeated=run(joined,'India|India meditation|meditation')
    assert [hit['accountId'] for hit in result['results']]==[hit['accountId'] for hit in repeated['results']]
    assert result['results'][0]['matches']==repeated['results'][0]['matches']
    capture=tmp_path/'alternatives.json'
    capture.write_text(json.dumps([
        {'account_id':'1001','handle':'a_variant','bio':'dharma Buddhism','location':'India'},
        {'account_id':'1002','handle':'z_distinct','bio':'dharma India'}]))
    with sqlite3.connect(joined[0]) as db:
        writer=CaptureWriter(db);sid,rows=writer.source(capture)
        for index,row in enumerate(rows):
            account=writer.entity('x_account',row['account_id'])
            writer.relation(account,'profile_observation',account,sid,f'/{index}','2026-01-01',row)
    result=run(joined,'dharma|Buddhism India',limit=1)
    assert result['total']==3 and result['results'][0]['accountId']=='1002'
    assert result['results'][0]['ranking']['bioGroups']==[0,1]
    assert {tuple(row['alternatives']):row['matchingAccounts'] for row in result['interestCoverage']}=={
        ('dharma','buddhism'):4,('india',):3}  # Includes a post-only account lacking India.


@pytest.mark.parametrize('fault',['withdrawn','checksum','http'])
def test_hidden_post_branch_cannot_qualify_an_interest(joined,fault):
    missing=run(joined,'Buddhism|dharma India',fault)
    assert missing['status']=='partial' and missing['total']==0
    assert missing['interestCoverage'][0]['matchingAccounts']==0
    independent=run(joined,'Buddhism|meditation India',fault)
    assert independent['total']==1 and independent['results'][0]['posts']==[]


@pytest.mark.parametrize('query',['dharma| India','|dharma India','dharma||Buddhism',
    'dharma | Buddhism','dharma|open-source India'])
def test_malformed_alternatives_are_refused_before_reading_sources(joined,query):
    with pytest.raises(ValueError,match='Alternative'):run(joined,query)


def test_no_sources_keeps_group_coverage_unknown(joined):
    with public_client(joined[2]) as client:
        from src.data.unified_evidence import search_all_evidence
        result=search_all_evidence(None,None,'dharma|Buddhism India',client=client)
    assert result['total'] is None and result['status']=='unavailable'
    assert all(group['matchingAccounts'] is None for group in result['interestCoverage'])


def test_one_post_bonus_cites_only_the_alternatives_actually_in_that_post(ranked):
    result=run(ranked,'dharma|Buddhism Mumbai|India')
    passage=result['results'][0]['posts'][0]
    assert passage['rankingEvidence'] and passage['rankingInterestEvidence']
    assert passage['matchedWords']==['buddhism','india']
    assert 'dharma' not in passage['storedText'].casefold()
    assert 'mumbai' not in passage['storedText'].casefold()


def test_alternative_query_uses_existing_authenticated_route(joined,monkeypatch):
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(joined[0]))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX',str(joined[1]))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    with public_client(joined[2]) as upstream,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        url='/api/research-notes/search/all'
        assert client.get(url,query_string={'q':'dharma|Buddhism India'}).status_code==401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        response=client.get(url,query_string={'q':'dharma|Buddhism India'})
        assert response.status_code==200 and response.get_json()['total']==1
        assert client.get(url,query_string={'q':'dharma| India'}).status_code==400
