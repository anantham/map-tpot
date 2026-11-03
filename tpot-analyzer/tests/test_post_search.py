"""Nonempty source-shaped post discovery; all state and network are synthetic."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.post_index import build_post_index
from src.data.post_search import search_posts
from tests.test_published_profiles import bundle, legacy_graph, rewrite_usernames
from tests.test_published_profile_access import graph

ACCOUNT = '9007199254740993'


@pytest.fixture
def posts(bundle):
    moment = datetime(2026, 10, 15, 7, tzinfo=timezone.utc)
    ids = ['9007199254740993001', '9007199254740993002', '9007199254740993003']
    media = pa.list_(pa.struct([pa.field('1', pa.string(), False), pa.field('2', pa.string(), False),
        pa.field('3', pa.string(), False), pa.field('4', pa.uint32()), pa.field('5', pa.uint32())]))
    urls = pa.list_(pa.struct([pa.field('1', pa.string(), False), pa.field('2', pa.string()), pa.field('3', pa.string(), False)]))
    data = {'tweet_id': ids, 'account_id': [ACCOUNT, ACCOUNT, '200'],
        'created_at': pa.array([moment]*3, type=pa.timestamp('ms', tz='UTC')),
        'full_text': ['Buddhism and practice', 'Marxist philosophy and institutions', 'Buddhism only'],
        'favorite_count': pa.array([1, 2, 3], type=pa.uint64()),
        'retweet_count': pa.array([0, 1, 0], type=pa.uint64()),
        'reply_to_tweet_id': [ids[2], None, None], 'reply_to_account_id': ['200', None, None],
        'quoted_tweet_id': [None, ids[2], None], 'retweeted_tweet_id': [None, None, ids[0]],
        'conversation_id': [ids[2], ids[1], ids[0]], 'media': pa.array([[], [], []], type=media),
        'urls': pa.array([[], [], []], type=urls),
        'mentioned_account_ids': pa.array([['200', '999'], [], []], type=pa.list_(pa.string())),
        'archive_upload_ids': pa.array([['17'], ['17'], ['18']], type=pa.list_(pa.string())),
        'latest_observed_at': pa.array([moment]*3, type=pa.timestamp('ms', tz='UTC'))}
    table = pa.table(data)
    pq.write_table(table, bundle/'tweets.parquet')
    refresh_manifest(bundle)
    return bundle


def refresh_manifest(folder):
    table = pq.read_table(folder/'tweets.parquet'); raw = (folder/'tweets.parquet').read_bytes()
    manifest = json.loads((folder/'manifest.json').read_bytes())
    manifest['files']['tweets'] = {'path': 'tweets.parquet', 'columns': table.column_names,
        'rows': len(table), 'distinct_accounts': len(set(table['account_id'].to_pylist())),
        'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    manifest['publication']['urls']['tweets'] = manifest['publication']['urls']['profiles'].replace('profiles.parquet', 'tweets.parquet')
    (folder/'manifest.json').write_text(json.dumps(manifest))


def public_client(folder, fault=None):
    pointer = json.loads((folder/'latest.json').read_bytes())
    manifest = json.loads((folder/'manifest.json').read_bytes())
    if fault == 'withdrawn': manifest['publication']['status'] = 'withdrawn'
    if fault == 'checksum': manifest['files']['tweets']['sha256'] = '0'*64
    if fault == 'subject': pointer['eligible_account_ids'][0] = '999'
    def respond(request):
        assert request.method == 'GET' and not request.url.query
        if fault == 'http': return httpx.Response(503)
        return httpx.Response(200, json=pointer if request.url.path.endswith('/latest.json') else manifest)
    return httpx.Client(transport=httpx.MockTransport(respond))


def test_ready_index_preserves_sources_and_refuses_overwrite(posts, tmp_path):
    before = {p.name: p.read_bytes() for p in posts.iterdir()}
    target = tmp_path/'index'
    report = build_post_index(posts, target)
    assert report['ready'] and report['rows'] == 3 and report['authors'] == 2
    database = target/'posts.db'
    assert database.stat().st_mode & 0o077 == 0
    assert all((posts/name).read_bytes() == raw for name, raw in before.items())
    with pytest.raises(FileExistsError): build_post_index(posts, target)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT count(*) FROM post').fetchone()[0] == 3


def test_words_can_match_different_posts_and_context_stays_typed(posts, tmp_path):
    build_post_index(posts, tmp_path/'index')
    with public_client(posts) as client:
        result = search_posts(tmp_path/'index'/'posts.db', 'Buddhism Marxist', client=client)
    assert result['status'] == 'available' and result['total'] == 1
    hit = result['results'][0]
    assert hit['accountId'] == ACCOUNT and hit['username'] == 'Alpha'
    assert {match['term'] for match in hit['posts']} == {'buddhism', 'marxist'}
    first = next(match for match in hit['posts'] if match['term'] == 'buddhism')
    assert first['tweetId'] == '9007199254740993001'
    assert first['context']['replyToAccountId'] == '200'
    assert first['context']['replyToTweetId'] == '9007199254740993003'
    assert first['context']['mentionedAccountIds'] == ['200', '999']
    assert first['evidenceRef']['sourceRow'] == 0
    assert first['evidenceRef']['fileSha256'] == result['source']['tweetSha256']


def test_missing_handle_keeps_source_qualified_search_and_reference_evidence(posts,tmp_path):
    """Retain evidence and counts by exact ID; no fabricated username or stale access."""
    from scripts.verify_current_archive_profiles import build_profile_copy
    from src.data.post_search import post_network_sources
    from src.data.saved_evidence import search_saved_evidence
    from src.data.unified_evidence import search_all_evidence
    from src.data.published_profile_access import current_publication
    rewrite_usernames(posts,['','beta'])
    build_post_index(posts,tmp_path/'index')
    build_profile_copy(posts,legacy_graph(tmp_path),tmp_path/'copy')
    index=tmp_path/'index/posts.db';graph=tmp_path/'copy/relationships.db'
    with public_client(posts) as client:
        access=current_publication(client=client)
        profiles=search_saved_evidence(graph,'Contemplative',published_access=access)
        current=search_posts(index,'Buddhism Marxist',client=client)
        combined=search_all_evidence(graph,index,'Buddhism Marxist',client=client)
        network=post_network_sources(index,client=client)
    for result in (profiles,current,combined):
        assert result['status']=='available' and result['total']==1
        assert result['results'][0]['accountId']==ACCOUNT
        assert result['results'][0]['username']==''
    assert {post['term'] for post in current['results'][0]['posts']}=={'buddhism','marxist'}
    source=next(row for row in network['sources'] if row['accountId']==ACCOUNT)
    assert source['username']==''
    with public_client(posts,'withdrawn') as client:
        hidden=search_posts(index,'Buddhism Marxist',client=client)
    assert hidden['status']=='source_hidden' and hidden['total'] is None


@pytest.mark.parametrize('fault', ['withdrawn', 'checksum', 'http'])
def test_unverified_source_is_not_a_zero_match(posts, tmp_path, fault):
    build_post_index(posts, tmp_path/'index')
    with public_client(posts, fault) as client:
        result = search_posts(tmp_path/'index'/'posts.db', 'Buddhism', client=client)
    assert result['status'] == 'source_hidden' and result['total'] is None and result['results'] == []


def test_partial_eligibility_never_returns_an_ineligible_author(posts, tmp_path):
    build_post_index(posts, tmp_path/'index')
    with public_client(posts, 'subject') as client:
        result = search_posts(tmp_path/'index'/'posts.db', 'Buddhism', client=client)
    assert [hit['accountId'] for hit in result['results']] == ['200']


def test_follow_scope_and_missing_independent_supplement(posts, graph, tmp_path):
    build_post_index(posts, tmp_path/'index')
    with public_client(posts) as client:
        scoped = search_posts(tmp_path/'index'/'posts.db', 'Buddhism', client=client,
            relationship_path=graph[0], from_account_id=ACCOUNT)
        independent = search_posts(tmp_path/'index'/'posts.db', 'Buddhism', client=client,
            relationship_path=tmp_path/'absent.db')
    assert [hit['accountId'] for hit in scoped['results']] == ['200']
    assert scoped['results'][0]['networkPath']['hopCount'] == 1
    assert independent['total'] == 2 and independent['relationshipStatus'] == 'unavailable'


def test_unicode_words_and_late_accented_match_are_explained(posts, tmp_path):
    table = pq.read_table(posts/'tweets.parquet')
    text = 'intro '*160+'Straße and café'
    table = table.set_column(table.schema.get_field_index('full_text'), 'full_text', pa.array([text, 'other', 'nothing']))
    pq.write_table(table, posts/'tweets.parquet'); refresh_manifest(posts)
    build_post_index(posts, tmp_path/'index')
    with public_client(posts) as client:
        street = search_posts(tmp_path/'index'/'posts.db', 'Straße', client=client)
        coffee = search_posts(tmp_path/'index'/'posts.db', 'cafe', client=client)
    assert street['total'] == 1
    assert 'café' in coffee['results'][0]['posts'][0]['excerpt']


def test_true_zero_hidden_path_names_and_bad_scope_are_distinct(posts, graph, tmp_path):
    build_post_index(posts, tmp_path/'index')
    with public_client(posts) as client:
        zero = search_posts(tmp_path/'index'/'posts.db', 'nonexistentword', client=client)
        assert zero['status'] == 'available' and zero['total'] == 0
        with pytest.raises(ValueError, match='fromAccountId'):
            search_posts(tmp_path/'index'/'posts.db', 'Buddhism', client=client, relationship_path=graph[0], from_account_id='abc')
    with public_client(posts, 'subject') as client:
        hidden = search_posts(tmp_path/'index'/'posts.db', 'Buddhism', client=client,
            relationship_path=graph[0], from_account_id=ACCOUNT)
    path = hidden['results'][0]['networkPath']
    assert path['nodes'][0]['username'] is None and 'Alpha' not in json.dumps(path)


def test_missing_columns_is_a_refusal_before_output_creation(posts, tmp_path):
    manifest = json.loads((posts/'manifest.json').read_bytes()); del manifest['files']['tweets']['columns']
    (posts/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError): build_post_index(posts, tmp_path/'missing-columns')
    assert not (tmp_path/'missing-columns').exists()


def test_post_search_route_auth_source_refusal_and_validation(posts, tmp_path, monkeypatch):
    build_post_index(posts, tmp_path/'index')
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX', str(tmp_path/'index'/'posts.db'))
    monkeypatch.delenv('MAP_TPOT_RELATIONSHIP_DB', raising=False)
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__); app.config['TESTING'] = True; app.register_blueprint(research_notes_bp)
    with public_client(posts) as public, app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        assert client.get('/api/research-notes/posts/search?q=Buddhism').status_code == 401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
        response = client.get('/api/research-notes/posts/search?q=Buddhism%20Marxist')
        assert response.status_code == 200 and response.get_json()['total'] == 1
        assert str(tmp_path) not in response.get_data(as_text=True)
        assert client.get('/api/research-notes/posts/search?q=%22').status_code == 400
        with public_client(posts, 'withdrawn') as withdrawn:
            app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = withdrawn
            data = client.get('/api/research-notes/posts/search?q=Buddhism').get_json()
            assert data['status'] == 'source_hidden' and data['total'] is None


@pytest.mark.parametrize('fault', ['checksum', 'ineligible-author', 'duplicate-post', 'numeric-id', 'naive-date'])
def test_invalid_source_never_becomes_ready(posts, tmp_path, fault):
    table = pq.read_table(posts/'tweets.parquet')
    if fault == 'checksum':
        manifest = json.loads((posts/'manifest.json').read_bytes()); manifest['files']['tweets']['sha256'] = '0'*64
        (posts/'manifest.json').write_text(json.dumps(manifest))
    else:
        field, values = {
            'ineligible-author': ('account_id', pa.array(['999', ACCOUNT, '200'])),
            'duplicate-post': ('tweet_id', pa.array(['100', '100', '200'])),
            'numeric-id': ('tweet_id', pa.array([100, 101, 102])),
            'naive-date': ('created_at', pa.array([datetime(2026, 10, 15)]*3, type=pa.timestamp('ms'))),
        }[fault]
        table = table.set_column(table.schema.get_field_index(field), field, values)
        pq.write_table(table, posts/'tweets.parquet'); refresh_manifest(posts)
    with pytest.raises(ValueError): build_post_index(posts, tmp_path/'invalid')
    database = tmp_path/'invalid'/'posts.db'
    if database.exists():
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT value FROM meta WHERE key='ready'").fetchone() != ('true',)
