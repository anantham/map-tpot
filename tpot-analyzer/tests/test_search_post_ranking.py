"""Test intent: improve post-only ties without changing qualification or privacy.

- Rank the complete candidate pool before limiting; cite the exact ranked post.
- One all-word passage is a tie-break, not summed post volume or membership.
- Preserve source refusal, raw text, exact identities and deterministic ties.
"""
import json
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.post_index import build_post_index
from src.data.unified_evidence import search_all_evidence
from tests.test_post_search import posts, public_client, refresh_manifest, ACCOUNT
from tests.test_published_profiles import bundle


@pytest.fixture
def passage_index(posts, tmp_path):
    table = pq.read_table(posts/'tweets.parquet')
    text = ['Buddhism '+('unrelated words '*200), 'Marxist on another topic',
            'Buddhism Marxist practice']
    table = table.set_column(table.schema.get_field_index('full_text'),'full_text',pa.array(text))
    pq.write_table(table,posts/'tweets.parquet');refresh_manifest(posts)
    build_post_index(posts,tmp_path/'ranked')
    return tmp_path/'ranked/posts.db',posts


def run(pair, fault=None, **options):
    with public_client(pair[1],fault) as client:
        return search_all_evidence(None,pair[0],'Buddhism Marxist',client=client,**options)


def test_coherent_passage_breaks_alphabetic_tie_before_limit_and_explains_source(passage_index):
    before=passage_index[0].read_bytes()
    full=run(passage_index)
    one=run(passage_index,limit=1)
    assert full['total']==one['total']==2
    assert {hit['accountId'] for hit in full['results']}=={ACCOUNT,'200'}
    hit=one['results'][0]
    assert hit['accountId']=='200'  # beta, not alphabetical Alpha
    evidence=next(post for post in hit['posts'] if post.get('rankingEvidence'))
    assert evidence['storedText']=='Buddhism Marxist practice'
    assert evidence['evidenceRef']['sourceRow']==2
    assert evidence['evidenceRef']['fileSha256']==one['sources']['posts']['tweetSha256']
    assert set(evidence['matchedWords'])=={'buddhism','marxist'}
    assert hit['ranking']['postTweetId']==evidence['tweetId']
    assert 'together in one retained post' in hit['ranking']['explanation']
    assert 'confidence' in one['method']
    assert passage_index[0].read_bytes()==before


def test_repeated_passages_do_not_sum_into_a_volume_bonus(passage_index):
    table=pq.read_table(passage_index[1]/'tweets.parquet')
    duplicate=table.slice(0,1)
    copies=[]
    for n in range(12):
        copies.append(duplicate.set_column(0,'tweet_id',pa.array([str(1000+n)])))
    pq.write_table(pa.concat_tables([table,*copies]),passage_index[1]/'tweets.parquet')
    refresh_manifest(passage_index[1])
    output=passage_index[0].parent.parent/'duplicate-index'
    build_post_index(passage_index[1],output)
    result=run((output/'posts.db',passage_index[1]))
    assert result['results'][0]['accountId']=='200'
    assert result['total']==2
    assert sum(bool(post.get('rankingEvidence')) for post in result['results'][0]['posts'])==1
    assert not any(post.get('rankingEvidence') for post in result['results'][1]['posts'])


@pytest.mark.parametrize('fault',['withdrawn','checksum','http'])
def test_hidden_source_cannot_contribute_rank_or_passage(passage_index,fault):
    result=run(passage_index,fault)
    assert result['total'] is None and result['results']==[]
    assert result['sources']['posts']['status']!='available'


def test_ties_keep_stable_exact_id_order_and_no_duplicate_support_card(passage_index):
    with sqlite3.connect(passage_index[0]) as db:
        db.execute("UPDATE post SET full_text='Buddhism Marxist practice'")
        db.execute("INSERT INTO post_fts(post_fts) VALUES('rebuild')")
    result=run(passage_index)
    assert [hit['accountId'] for hit in result['results']]==[ACCOUNT,'200']
    for hit in result['results']:
        assert len({post['tweetId'] for post in hit['posts']})==len(hit['posts'])


def test_single_word_retains_prior_order_without_a_cooccurrence_claim(passage_index):
    with public_client(passage_index[1]) as client:
        result=search_all_evidence(None,passage_index[0],'Buddhism',client=client)
    assert [hit['accountId'] for hit in result['results']]==[ACCOUNT,'200']
    assert not any(post.get('rankingEvidence') for hit in result['results'] for post in hit['posts'])
