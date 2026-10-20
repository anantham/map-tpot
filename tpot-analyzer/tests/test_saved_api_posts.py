"""Test intent: independent stored API posts join existing evidence, not identities.

- Exact post/source IDs, reported typed targets, text and date/source refs survive.
- Private/flagged sources and Archive fallback text cannot qualify independently.
- Missing target profiles stay exact numeric references; repeat imports append no duplicates.
- Mixed-source queries remain useful during Archive failure without a ranking bonus.
"""
import json
import sqlite3

import httpx
import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_api_posts import import_api_post_observations, api_post_fragments
from src.data.saved_evidence import search_saved_evidence


@pytest.fixture
def inputs(tmp_path):
    tmp_path.chmod(0o700)
    source, graph = tmp_path/'source.db', tmp_path/'graph.db'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE user_profile_cache(account_id TEXT PRIMARY KEY,
          username TEXT,raw_json TEXT,fetched_at TEXT);
          CREATE TABLE protected_accounts(account_id TEXT);
          CREATE TABLE api_typed_edges(source_id TEXT,target_id TEXT,edge_type TEXT,
            tweet_id TEXT,created_at TEXT,fetch_source TEXT,fetched_at TEXT,
            PRIMARY KEY(source_id,target_id,edge_type,tweet_id));
          CREATE TABLE enriched_tweets(tweet_id TEXT PRIMARY KEY,account_id TEXT NOT NULL,
            username TEXT NOT NULL,text TEXT NOT NULL,like_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0,reply_count INTEGER DEFAULT 0,view_count INTEGER DEFAULT 0,
            created_at TEXT,lang TEXT,is_reply INTEGER DEFAULT 0,in_reply_to_user TEXT,
            has_media INTEGER DEFAULT 0,mentions_json TEXT DEFAULT '[]',fetch_source TEXT NOT NULL,
            fetch_query TEXT,fetched_at TEXT NOT NULL);''')
        for aid, handle, private in [('9007199254740993', 'alice', False), ('200', 'bob', False),
                                     ('999', 'private', True)]:
            db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)', (aid, handle,
                json.dumps({'id': aid, 'userName': handle, 'protected': private,
                            'description': 'Neuroscience tools', 'location': 'India'}), '2026-08-03T10:00:00Z'))
        rows = [('9007199254740993', '200', 'reply', '1001', '9007199254740993', 'last_tweets_deep'),
                ('9007199254740993', '300', 'retweet', '1002', '9007199254740993', 'last_tweets'),
                ('9007199254740993', '999', 'reply', '1003', '9007199254740993', 'last_tweets'),
                ('999', '200', 'reply', '1004', '999', 'last_tweets'),
                ('9007199254740993', '200', 'reply', '1005', '200', 'last_tweets'),
                ('9007199254740993', '200', 'reply', '1006', '9007199254740993', 'archive')]
        for src, target, kind, tweet, author, fetch in rows:
            db.execute('INSERT INTO api_typed_edges VALUES(?,?,?,?,?,?,?)',
                (src, target, kind, tweet, 'Sun Aug 02 19:46:46 +0000 2026', 'last_tweets_dump', '2026-08-03T11:00:00Z'))
            db.execute('INSERT INTO enriched_tweets(tweet_id,account_id,username,text,created_at,fetch_source,fetched_at) VALUES(?,?,?,?,?,?,?)',
                (tweet, author, 'alice' if author != '999' else 'private',
                 'Buddhism Marxist tools '+tweet, 'Sun Aug 02 19:46:46 +0000 2026', fetch, '2026-08-03T11:05:00Z'))
    with sqlite3.connect(graph) as db: db.executescript(SCHEMA)
    graph.chmod(0o600)
    return source, graph


def test_projection_preserves_raw_rows_typed_ids_unknown_target_and_exclusions(inputs):
    source, graph = inputs
    before = source.read_bytes()
    with sqlite3.connect(graph) as db:
        report = import_api_post_observations(db, source)
        assert report['apiPosts'] == 2 and report['typedReferences'] == 2
        assert len(report['exclusions']) == 4
        counts = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('entity', 'relation', 'evidence_snapshot')]
        import_api_post_observations(db, source)
        assert counts == [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                          for t in ('entity', 'relation', 'evidence_snapshot')]
        db.row_factory = sqlite3.Row
        fragments, coverage = api_post_fragments(db)
        assert coverage == {'apiPostObservations': 2, 'apiPostAccounts': 1, 'apiTypedReferences': 2}
        posts = fragments['9007199254740993']
        assert {p['kind'] for p in posts} == {'api_post'}
        assert {r['targetAccountId'] for p in posts for r in p['references']} == {'200', '300'}
        assert posts[0]['evidenceRef']['sourcePointer'] == '/row/text'
        assert all(p['createdAt'] == 'Sun Aug 02 19:46:46 +0000 2026' for p in posts)
        snapshots = dict(db.execute('SELECT snapshot_id,payload FROM evidence_snapshot'))
        assert any(json.loads(raw).get('sourceTable') == 'api_typed_edges' for raw in snapshots.values())
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert source.read_bytes() == before
    result = search_saved_evidence(graph, 'India Buddhism')
    assert result['total'] == 1 and result['results'][0]['accountId'] == '9007199254740993'
    assert any(m['kind'] == 'api_post' and m['references'] for m in result['results'][0]['matches'])
    assert str(source) not in json.dumps(result)


def test_missing_public_author_is_not_rescued_by_legacy_profile(inputs):
    source, graph = inputs
    with sqlite3.connect(source) as db: db.execute('DELETE FROM user_profile_cache')
    with sqlite3.connect(graph) as db:
        assert import_api_post_observations(db, source)['apiPosts'] == 0
        assert db.execute('SELECT count(*) FROM relation').fetchone()[0] == 0


@pytest.mark.parametrize('kind', ['quote', 'mention'])
def test_supported_typed_row_keeps_its_actual_reference_type(inputs, kind):
    source, graph = inputs
    with sqlite3.connect(source) as db:
        db.execute('UPDATE api_typed_edges SET edge_type=? WHERE tweet_id=?', (kind, '1001'))
    with sqlite3.connect(graph) as db:
        import_api_post_observations(db, source)
        db.row_factory = sqlite3.Row
        posts, _ = api_post_fragments(db)
        post = next(p for p in posts['9007199254740993'] if p['tweetId'] == '1001')
        assert post['references'][0]['type'] == kind


def test_combined_search_uses_independent_post_words_during_archive_failure_without_bonus(inputs):
    from src.data.unified_evidence import search_all_evidence
    source, graph = inputs
    with sqlite3.connect(graph) as db: import_api_post_observations(db, source)
    before = {p: p.read_bytes() for p in inputs}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        result = search_all_evidence(graph, None, 'India Buddhism', client=client)
        posts_only = search_all_evidence(graph, None, 'Buddhism Marxist', client=client)
    assert result['status'] == 'partial' and result['total'] == 1
    hit = result['results'][0]
    assert hit['posts'] == [] and hit['accountId'] == '9007199254740993'
    assert hit['ranking']['savedWords'] == ['india']
    assert posts_only['results'][0]['ranking']['savedWords'] == []
    assert result['sources']['saved']['coverage']['apiTypedReferences'] == 2
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_api_copy_and_adoption_keep_prior_release_and_raw_sources(inputs, tmp_path):
    from scripts.verify_api_post_batch import build_api_post_batch
    from src.data.local_graph_batch import adopt_graph
    source, graph = inputs
    root = tmp_path/'managed'
    prior = root/'releases'/'old'
    for name in ('graph', 'index', 'package'): (prior/name).mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    baseline = prior/'graph'/'relationships.db'; graph.rename(baseline)
    (prior/'index/posts.db').write_bytes(b'synthetic unchanged index')
    (prior/'package/meta').write_bytes(b'synthetic unchanged package')
    (root/'current').symlink_to(prior, target_is_directory=True)
    output = tmp_path/'copy.db'
    raw, old = source.read_bytes(), baseline.read_bytes()
    report = build_api_post_batch(baseline, source, output)
    assert report['apiPosts'] == 2 and report['priorRowsRetained'] and report['reimportUnchanged']
    assert 'followObservations' not in report
    adopt_graph(root, baseline, output, report)
    assert (root/'current/graph/relationships.db').resolve() == output
    assert (root/'current/index/posts.db').read_bytes() == b'synthetic unchanged index'
    assert (root/'current/package/meta').read_bytes() == b'synthetic unchanged package'
    assert baseline.read_bytes() == old and source.read_bytes() == raw
