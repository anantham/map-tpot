"""Test intent: real temporary index/tag state, never live stores or network.

- Distinct exact-tag IN examples, not posts/types, determine support.
- Latest-date and lifetime repetition stay separate; no missing-source false zero.
- Set, NOT IN and retract refresh candidates; hidden examples cannot leak paths.
"""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.post_index import build_post_index
from src.data.post_tag_frontier import build_post_tag_frontier
from tests.test_post_search import ACCOUNT, posts, refresh_manifest, public_client
from tests.test_published_profiles import bundle

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def pilot(posts, tmp_path, monkeypatch):
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    from src.data.account_tags import AccountTagStore
    table = pq.read_table(posts/'profiles.parquet'); profiles = table.to_pylist()
    profiles += [{**profiles[1], 'account_id': account, 'username': name, 'display_name': name}
        for account, name in [('300', 'Gamma'), ('400', 'Delta'), ('500', 'Epsilon')]]
    pq.write_table(pa.Table.from_pylist(profiles, schema=table.schema), posts/'profiles.parquet')
    raw = (posts/'profiles.parquet').read_bytes(); manifest = json.loads((posts/'manifest.json').read_bytes())
    manifest['files']['profiles'].update(rows=5, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest['consent']['eligible_accounts'] = 5
    pointer = json.loads((posts/'latest.json').read_bytes()); pointer['eligible_account_ids'] += ['300','400','500']
    (posts/'manifest.json').write_text(json.dumps(manifest)); (posts/'latest.json').write_text(json.dumps(pointer))
    table = pq.read_table(posts/'tweets.parquet'); base = table.to_pylist()[0]; rows = []
    def add(source, target, dates, *, mentions=False):
        for date in dates:
            moment = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
            rows.append({**base, 'tweet_id': str(9007199254740993100+len(rows)), 'account_id': source,
                'created_at': moment, 'latest_observed_at': moment, 'full_text': 'Synthetic linked evidence',
                'reply_to_account_id': target, 'reply_to_tweet_id': None,
                'quoted_tweet_id': None, 'retweeted_tweet_id': None,
                'mentioned_account_ids': [target, target] if mentions else []})
    add(ACCOUNT, '300', ['2025-01-01', '2025-02-01', '2026-10-01'], mentions=True)
    add('200', '300', ['2026-09-18', '2026-09-19', '2026-09-20'])
    add(ACCOUNT, '400', ['2025-01-01']*3)
    add('200', '400', ['2026-10-01'])
    add('500', '300', ['2026-10-01']*3)
    add('300', ACCOUNT, ['2026-10-01']*3)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), posts/'tweets.parquet'); refresh_manifest(posts)
    build_post_index(posts, tmp_path/'index')
    tag_path = tmp_path/'account_tags.db'; store = AccountTagStore(tag_path)
    for account, polarity in [(ACCOUNT,1),('200',1),('9999',1),('500',-1)]:
        store.upsert_tag(ego='curator',account_id=account,tag='Builders',polarity=polarity)
    store.upsert_tag(ego='other',account_id='500',tag='Builders',polarity=1)
    store.upsert_tag(ego='curator',account_id='500',tag='Unrelated',polarity=1)
    # Byte-preservation checks require setup writes settled out of WAL first.
    # sqlite3's transaction context does not close its connection on exit.
    with closing(sqlite3.connect(tag_path)) as settled:
        assert settled.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone() == (0,0,0)
    return tmp_path/'index/posts.db', tag_path, store, posts


def run(pilot, **options):
    index, tags, _, folder = pilot
    with public_client(folder) as client:
        return build_post_tag_frontier(index, tags, ego='curator', tag='bUiLdErS', client=client,
            as_of=NOW, **options)


def test_distinct_support_provenance_and_missing_example_coverage(pilot):
    before = pilot[1].read_bytes(); result = run(pilot, min_support=2)
    assert result.get('status') == 'provisional'
    assert result['diagnostics']['candidateCount'] == 1
    hit = result['candidates'][0]
    assert hit['accountId'] == '300' and hit['positiveRawSupport'] == 2
    assert hit['negativeRawSupport'] == 1  # Not subtracted or relabeled negative.
    assert hit['positiveSupportingAnchors'] == ['200', ACCOUNT]
    assert result['anchors']['positive']['count'] == 3
    assert result['anchors']['positive']['eligibleCount'] == 2
    assert result['anchors']['positive']['unavailableCount'] == 1
    assert len(hit['supportingPaths']) == 2
    edge = next(path for path in hit['supportingPaths'] if path['nodes'][0]['accountId'] == ACCOUNT)['edges'][0]
    assert edge['observationCount'] == 3 and edge['firstAt'].startswith('2025-01-01')
    assert edge['lastAt'].startswith('2026-10-01') and edge['excerpt'] == 'Synthetic linked evidence'
    assert edge['evidenceRef']['fileSha256'] == result['source']['tweetSha256']
    assert result['filters']['minimumLifetimePostsPerType'] == 3
    assert result['semantics']['calibrated'] is False
    assert pilot[1].read_bytes() == before


def test_lifetime_repetition_latest_date_and_type_selection_are_separate(pilot):
    all_time = run(pilot, latest_within_days=0)
    assert {hit['accountId'] for hit in all_time['candidates']} == {'300','400'}
    recent = run(pilot)
    assert [hit['accountId'] for hit in recent['candidates']] == ['300']
    mentioned = run(pilot, kinds=['mention'])
    assert mentioned['candidates'][0]['positiveRawSupport'] == 1
    assert run(pilot, kinds=['mention'], min_support=2)['candidates'] == []
    assert {hit['accountId'] for hit in run(pilot,min_posts=1)['candidates']} == {'300','400'}


def test_actual_tag_mutations_change_candidates_without_changing_index(pilot):
    index, _, store, _ = pilot; before = index.read_bytes()
    assert run(pilot,min_support=2)['candidates']
    store.upsert_tag(ego='curator',account_id='200',tag='Builders',polarity=-1)
    assert run(pilot,min_support=2)['candidates'] == []
    store.delete_tag(ego='curator',account_id='200',tag='Builders')
    assert run(pilot,min_support=2)['candidates'] == []
    store.upsert_tag(ego='curator',account_id='200',tag='Builders',polarity=1)
    assert run(pilot,min_support=2)['candidates']
    store.upsert_tag(ego='curator',account_id='300',tag='Builders',polarity=-1)
    assert run(pilot,min_support=2)['candidates'] == []
    store.delete_tag(ego='curator',account_id='300',tag='Builders')
    assert run(pilot,min_support=2)['candidates'][0]['accountId'] == '300'
    assert index.read_bytes() == before


def test_incoming_explanation_preserves_actor_and_hidden_examples_never_leak(pilot):
    incoming = run(pilot,direction='incoming')
    edge = incoming['candidates'][0]['supportingPaths'][0]['edges'][0]
    assert edge['sourceAccountId'] == '300' and edge['targetAccountId'] == ACCOUNT
    with public_client(pilot[3], 'subject') as client:
        partial = build_post_tag_frontier(pilot[0],pilot[1],ego='curator',tag='Builders',client=client,as_of=NOW)
    assert partial['anchors']['positive']['eligibleCount'] == 1
    assert partial['candidates'][0]['positiveRawSupport'] == 1
    assert 'Alpha' not in json.dumps(partial)


@pytest.mark.parametrize('fault',['withdrawn','checksum','http'])
def test_hidden_source_is_not_empty_candidates(pilot,fault):
    with public_client(pilot[3], fault) as client:
        result = build_post_tag_frontier(pilot[0],pilot[1],ego='curator',tag='Builders',client=client,as_of=NOW)
    assert result['status'] == 'source_hidden' and result['diagnostics']['candidateCount'] is None
    assert result['candidates'] == []


@pytest.mark.parametrize('options',[{'min_posts':0},{'min_posts':True},{'latest_within_days':-1},
    {'min_support':0},{'kinds':[]},{'direction':'both'},{'limit':101}])
def test_bad_filter_inputs_refuse(pilot,options):
    with pytest.raises(ValueError): run(pilot,**options)


@pytest.fixture
def api(pilot,monkeypatch):
    monkeypatch.setenv('MAP_TPOT_POST_INDEX',str(pilot[0]))
    monkeypatch.setenv('SNAPSHOT_DIR',str(pilot[1].parent))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__); app.register_blueprint(research_notes_bp)
    app.config['DISCOVERY_AS_OF'] = NOW
    with public_client(pilot[3]) as public, app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        yield client,app


def test_api_auth_validation_and_real_tag_refresh(api,pilot):
    client,_ = api
    url = '/api/research-notes/posts/frontier?ego=curator&tag=Builders&minSupport=2'
    assert client.get(url).status_code == 401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    response = client.get(url)
    assert response.status_code == 200 and response.get_json()['candidates'][0]['accountId'] == '300'
    assert str(pilot[1].parent) not in response.get_data(as_text=True)
    pilot[2].upsert_tag(ego='curator',account_id='300',tag='Builders',polarity=1)
    assert client.get(url).get_json()['candidates'] == []
    for suffix in ('minSupport=0','minPosts=bad','types=','direction=both','latestWithinDays=-1'):
        assert client.get('/api/research-notes/posts/frontier?ego=curator&tag=Builders&'+suffix).status_code == 400


def test_api_source_refusal_and_missing_projection_are_not_zero(api,pilot):
    client,app = api; client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    url = '/api/research-notes/posts/frontier?ego=curator&tag=Builders'
    with public_client(pilot[3],'withdrawn') as public:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        hidden = client.get(url)
        assert hidden.status_code == 200 and hidden.get_json()['status'] == 'source_hidden'
    with public_client(pilot[3]) as public:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        with sqlite3.connect(pilot[0]) as db:
            db.execute("UPDATE meta SET value='building' WHERE key='interactionVersion'")
        assert client.get(url).status_code == 503


@pytest.mark.parametrize('hidden,label',[(ACCOUNT,'Alpha'),('300','Gamma'),('500','Epsilon')])
def test_all_reference_roles_are_gated_by_one_current_eligibility_snapshot(pilot,hidden,label):
    pointer = json.loads((pilot[3]/'latest.json').read_bytes())
    pointer['eligible_account_ids'] = ['999' if account == hidden else account for account in pointer['eligible_account_ids']]
    manifest = json.loads((pilot[3]/'manifest.json').read_bytes())
    def respond(request):
        assert request.method == 'GET' and not request.url.query
        return httpx.Response(200,json=pointer if request.url.path.endswith('/latest.json') else manifest)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = build_post_tag_frontier(pilot[0],pilot[1],ego='curator',tag='Builders',client=client,as_of=NOW)
    assert result['source']['status'] == 'available'
    assert label not in json.dumps(result)
    if hidden == '300': assert result['candidates'] == []
    if hidden == '500': assert result['candidates'][0]['negativeRawSupport'] == 0
