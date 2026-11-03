"""Older admitted passages remain discoverable,not current person traits.

Real retained provider objects through public search;keep current display,
ranking,exact identity,source gates and raw bytes unchanged.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.saved_evidence import search_saved_evidence
from src.data.saved_provider_profiles import import_saved_provider_profiles
from src.data.unified_evidence import search_all_evidence
from src.data.published_profile_access import PublishedProfileAccess,load_published_profile_access
from scripts.verify_current_archive_profiles import build_profile_copy
from tests.test_saved_evidence import saved
from tests.test_saved_api_posts import inputs
from tests.test_published_profiles import bundle
from tests.test_post_search import public_client

ACCOUNT='9007199254740993'


def add_prior_profile(graph,source,*,observed='2025-01-01T00:00:00Z',bio='Ceramics community research'):
    profile={'id':ACCOUNT,'userName':'earlier_alice','protected':False,
        'description':bio,'name':'Older Alice'}
    with sqlite3.connect(source) as db:
        db.execute('UPDATE user_profile_cache SET username=?,raw_json=?,fetched_at=? WHERE account_id=?',
            ('earlier_alice',json.dumps(profile),observed,ACCOUNT))
    with sqlite3.connect(graph) as db:
        assert import_saved_provider_profiles(db,source,[ACCOUNT])['profiles']==1


@pytest.fixture
def history(saved,inputs):
    graph=saved[0];source=inputs[0]
    add_prior_profile(graph,source)
    return graph,source


def test_older_bio_search_keeps_current_display_and_original_source(history):
    graph,source=history;before={p:p.read_bytes() for p in history}
    result=search_saved_evidence(graph,'ceramics')
    assert result['total']==1
    hit=result['results'][0]
    assert hit['accountId']==ACCOUNT and hit['username']=='alice'
    assert hit['bio']=='Neuroscience tools'
    match=next(m for m in hit['matches'] if 'Ceramics' in m['excerpt'])
    assert match['evidenceRef']['observedAt']=='2025-01-01T00:00:00Z'
    assert match['evidenceRef']['sourcePointer']=='/raw'
    assert match['storedText']=='Ceramics community research'
    assert match['sourceKind']=='saved_twitterapi_profile'
    assert 'not a transport receipt' in match['sourceBoundary']
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_repeated_history_is_one_account_and_not_current_bio_support(history):
    graph,source=history
    add_prior_profile(graph,source,observed='2024-01-01T00:00:00Z')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        result=search_all_evidence(graph,None,'ceramics tools',client=client)
    assert result['total']==1 and result['termCoverage']==[
        {'term':'ceramics','matchingAccounts':1},{'term':'tools','matchingAccounts':1}]
    hit=result['results'][0]
    assert hit['ranking']['bioWords']==['tools']
    assert hit['ranking']['savedWords']==['ceramics','tools']
    old=[m for m in hit['matches'] if m['label']=='Profile bio' and 'ceramics' in m['matchedWords']]
    assert len(old)==1 and old[0]['evidenceRef']['observedAt']=='2025-01-01T00:00:00Z'
    assert search_saved_evidence(graph,'ceramics London')['total']==0


def test_unknown_capture_time_is_not_imputed(history):
    graph,source=history
    add_prior_profile(graph,source,observed=None,bio='Zither community research')
    result=search_saved_evidence(graph,'zither')
    assert result['total']==1
    assert result['results'][0]['matches'][0]['evidenceRef']['observedAt'] is None


def test_hidden_archive_history_cannot_complete_a_match(history,bundle,tmp_path):
    graph,_=history;copied=tmp_path/'published-copy'
    assert search_saved_evidence(graph,'Alpha')['total']==0
    build_profile_copy(bundle,graph,copied);graph=copied/'relationships.db'
    before=graph.read_bytes()
    hidden=search_saved_evidence(graph,'ceramics Alpha',published_access=PublishedProfileAccess())
    assert hidden['total']==0 and hidden['publishedProfiles']['hiddenProfileObservations']>0
    with public_client(bundle) as client:access=load_published_profile_access(graph,client=client)
    assert access.status=='available'
    visible=search_saved_evidence(graph,'ceramics Alpha',published_access=access)
    assert visible['total']==1 and visible['results'][0]['accountId']==ACCOUNT
    assert graph.read_bytes()==before
