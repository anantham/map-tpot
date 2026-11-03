"""Test intent: combine full reference pool with sourced own-post evidence.

- Filter before truncation; all words can occur in separate candidate posts.
- Own-post time window, missing coverage and source refusal remain distinct.
- Preserve source rows, Unicode text, tags and independent default post search.
"""
import json
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.post_index import build_post_index
from src.data.post_tag_frontier import build_post_tag_frontier
from tests.test_post_tag_frontier import pilot, run, api, NOW
from tests.test_post_search import posts, refresh_manifest, public_client
from tests.test_published_profiles import bundle


@pytest.fixture
def content_pilot(pilot,tmp_path):
    table=pq.read_table(pilot[3]/'tweets.parquet'); rows=table.to_pylist(); base=rows[0]
    for offset,(text,date) in enumerate([('Buddhism and café','2026-10-01'),
            ('Marxist critique, not endorsement.','2026-09-20'),('Archaeology reference','2020-01-01'),
            ('Futurism reference','2026-11-01')]):
        moment=datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        rows.append({**base,'tweet_id':str(9007199254740993990+offset),'account_id':'400',
            'full_text':text,'created_at':moment,'latest_observed_at':moment,
            'reply_to_account_id':None,'reply_to_tweet_id':None,'quoted_tweet_id':None,
            'retweeted_tweet_id':None,'mentioned_account_ids':[]})
    pq.write_table(pa.Table.from_pylist(rows,schema=table.schema),pilot[3]/'tweets.parquet')
    refresh_manifest(pilot[3]); build_post_index(pilot[3],tmp_path/'content-index')
    return tmp_path/'content-index/posts.db',*pilot[1:]


def test_content_filter_precedes_limit_and_explains_each_word(content_pilot):
    plain=run(content_pilot,latest_within_days=0,min_posts=1,limit=1)
    assert plain['candidates'][0]['accountId']=='300'  # The matching account is below this page.
    before=content_pilot[1].read_bytes()
    result=run(content_pilot,latest_within_days=0,min_posts=1,limit=1,query='Buddhism Marxist')
    assert [row['accountId'] for row in result['candidates']]==['400']
    assert result['diagnostics']['referenceCandidateCount']==2 and result['diagnostics']['candidateCount']==1
    hit=result['candidates'][0]
    assert {word for post in hit['posts'] for word in post['matchedWords']}=={'buddhism','marxist'}
    assert len(hit['posts'])==2 and all(post['createdAt']>=result['contentFilter']['since'] for post in hit['posts'])
    assert all(post['evidenceRef']['fileSha256']==result['source']['tweetSha256'] for post in hit['posts'])
    assert all(post['tweetId'].startswith('900719925474099399') for post in hit['posts'])
    assert content_pilot[1].read_bytes()==before


def test_word_window_and_supporting_evidence_agree_and_unicode_survives(content_pilot):
    options={'latest_within_days':0,'min_posts':1}
    recent=run(content_pilot,query='Archaeology',**options)
    assert recent['candidates']==[] and recent['diagnostics']['referenceCandidateCount']==2
    historical=run(content_pilot,query='Archaeology',post_within_days=0,**options)
    assert historical['candidates'][0]['posts'][0]['createdAt'].startswith('2020-01-01')
    assert historical['contentFilter']['since'] is None
    coffee=run(content_pilot,query='cafe',**options)
    assert 'café' in coffee['candidates'][0]['posts'][0]['excerpt']


def test_missing_candidate_posts_are_not_negative_topic_evidence(pilot):
    result=run(pilot,query='Synthetic',latest_within_days=0,min_posts=1)
    assert result['contentFilter']['referenceCandidates']==2
    assert result['contentFilter']['accountsWithPostsInWindow']==1
    assert result['contentFilter']['unsearchedAccounts']==1
    assert [row['accountId'] for row in result['candidates']]==['300']
    assert run(pilot,query='   ')['contentFilter'] is None


def test_recent_window_does_not_count_reported_future_dates(content_pilot):
    options={'latest_within_days':0,'min_posts':1,'query':'Futurism'}
    assert run(content_pilot,**options)['candidates']==[]
    assert run(content_pilot,post_within_days=0,**options)['candidates'][0]['posts'][0]['createdAt'].startswith('2026-11-01')


@pytest.mark.parametrize('options',[{'query':'"'},{'query':'a'},{'query':'word '*35},
    {'query':None},{'query':'one two three four five six seven eight nine'},
    {'post_within_days':-1},{'post_within_days':True}])
def test_bad_content_filters_refuse(pilot,options):
    with pytest.raises(ValueError):run(pilot,**options)


def test_content_source_withdrawal_is_not_zero(pilot):
    with public_client(pilot[3],'withdrawn') as client:
        result=build_post_tag_frontier(pilot[0],pilot[1],ego='curator',tag='Builders',query='Synthetic',as_of=NOW,client=client)
    assert result['status']=='source_hidden' and result['diagnostics']['candidateCount'] is None


def test_api_applies_query_and_rejects_bad_content_options(api):
    client,_=api; client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
    url='/api/research-notes/posts/frontier?ego=curator&tag=Builders'
    assert client.get(url).get_json()['candidates']
    result=client.get(url+'&q=nonexistentword').get_json()
    assert result['candidates']==[] and result['contentFilter']['query']=='nonexistentword'
    for suffix in ('q=%22','q=a','postWithinDays=-1','postWithinDays=bad'):
        assert client.get(url+'&'+suffix).status_code==400
