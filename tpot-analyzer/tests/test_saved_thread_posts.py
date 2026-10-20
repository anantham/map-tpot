"""Test intent: stored threads add source-backed posts and typed references.

- Exact quote/mention IDs, raw cache JSON, pointers and dates survive projection.
- Unknown/private/flagged authors and restricted targets never gain visible text.
- Repeated captures do not multiply path counts; copied adoption preserves originals.
- Quotes are references, not attribution of the nested quoted text to the source.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.saved_thread_posts import import_saved_thread_observations
from src.data.saved_api_posts import api_post_fragments
from src.data.saved_api_paths import api_reference_paths, api_reference_sources
from src.data.unified_evidence import search_all_evidence
from tests.test_saved_api_posts import inputs

ALICE = '9007199254740993'


def post(tid, aid, handle, text, **extra):
    return {'type': 'tweet', 'id': tid, 'text': text,
        'createdAt': 'Wed Feb 25 01:02:03 +0000 2026',
        'author': {'id': aid, 'userName': handle, 'protected': False,
            'name': handle.title(), 'description': 'Marxist design' if aid == '200' else 'India tools',
            'location': 'India', 'url': '', 'entities': {}},
        'entities': {'user_mentions': []}, 'quoted_tweet': None,
        'retweeted_tweet': None, 'isReply': False, 'inReplyToUserId': None,
        'inReplyToId': None, **extra}


@pytest.fixture
def threads(inputs):
    source, graph = inputs
    bob = post('5002', '200', 'bob', 'Nested quoted secretword')
    alice = post('5001', ALICE, 'alice', 'Meditation interface notes', quoted_tweet=bob,
        entities={'user_mentions': [{'id_str': '300', 'screen_name': 'carol', 'name': 'Carol', 'indices': [0, 6]},
            {'id_str': '999', 'screen_name': 'private'}, {'id_str': '700', 'screen_name': 'hidden'},
            {'id_str': '600', 'screen_name': 'flagged'}, {'screen_name': 'unresolved'}]})
    carol = post('5003', '300', 'carol', 'Buddhism tools', isReply=True,
        inReplyToUserId=ALICE, inReplyToId='5001')
    hidden = post('5004', '700', 'hidden', 'Forbidden hidden text')
    hidden['author']['protected'] = True
    unknown = post('5005', '800', 'unknown', 'Forbidden unknown text')
    unknown['author'].pop('protected')
    flagged = post('5006', '600', 'flagged', 'Forbidden flagged text')
    payload = json.dumps([alice, bob, carol, hidden, unknown, flagged])
    with sqlite3.connect(source) as db:
        db.executescript('CREATE TABLE thread_context_cache(tweet_id TEXT PRIMARY KEY,raw_json TEXT NOT NULL,fetched_at TEXT);')
        db.execute('INSERT INTO protected_accounts VALUES(?)', ('600',))
        for tid, date in [('5001', '2026-02-25T02:31:26+00:00'), ('5003', '2026-02-26T02:31:26+00:00')]:
            db.execute('INSERT INTO thread_context_cache VALUES(?,?,?)', (tid, payload, date))
    return source, graph


def test_thread_projection_preserves_cache_and_typed_sources(threads):
    source, graph = threads
    original = source.read_bytes()
    with sqlite3.connect(graph) as db:
        report = import_saved_thread_observations(db, source)
        assert report['apiPosts'] == 3
        assert report['referenceTypes'] == {'quote': 2, 'mention': 2, 'reply': 2}
        assert report['excludedPosts'] == 6
        assert report['unresolvedMentions'] == 2
        db.row_factory = sqlite3.Row
        posts, coverage = api_post_fragments(db)
        assert coverage['apiPostAccounts'] == 3
        assert coverage['apiPostObservations'] == 6 and coverage['apiTypedReferences'] == 6
        assert len(posts[ALICE]) == 1 and posts[ALICE][0]['captureCount'] == 2
        alice = posts[ALICE][0]
        assert alice['text'] == 'Meditation interface notes'
        assert 'secretword' not in alice['text']
        assert alice['evidenceRef']['sourcePointer'] == '/tweets/0/text'
        assert alice['createdAt'] == 'Wed Feb 25 01:02:03 +0000 2026'
        quote = next(r for r in alice['references'] if r['type'] == 'quote')
        assert quote['targetAccountId'] == '200' and quote['targetTweetId'] == '5002'
        assert quote['evidenceRef']['sourcePointer'] == '/tweets/0/quoted_tweet/author/id'
        assert {r['targetAccountId'] for r in alice['references']} == {'200', '300'}
        assert len(alice['references']) == 2
        raw = db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',
                         (alice['evidenceRef']['snapshotId'],)).fetchone()[0]
        saved = json.loads(raw)
        with sqlite3.connect(source) as archive:
            expected_raw = archive.execute('SELECT raw_json FROM thread_context_cache WHERE tweet_id=?',
                                            (saved['row']['tweet_id'],)).fetchone()[0]
        assert saved['row']['raw_json'] == expected_raw
        assert json.loads(expected_raw) == saved['tweets']
        counts = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('entity', 'relation', 'evidence_snapshot')]
        import_saved_thread_observations(db, source)
        assert counts == [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                          for t in ('entity', 'relation', 'evidence_snapshot')]
        paths, _ = api_reference_paths(db, ALICE, 1, kinds=['quote', 'mention'])
        assert paths['200'][0]['observationCount'] == 1
        assert paths['300'][0]['kind'] == 'mention'
        assert not {'999', '600', '700'} & paths.keys()
        assert not {'600', '700', '800'} & posts.keys()
        assert api_reference_sources(db, kinds=['quote'])['coverage']['typedPairs'] == 1
    assert source.read_bytes() == original


def test_thread_search_and_quote_scope_work_when_archive_unavailable(threads):
    source, graph = threads
    with sqlite3.connect(graph) as db: import_saved_thread_observations(db, source)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        result = search_all_evidence(graph, None, 'Marxist', from_account_id=ALICE,
            network_kind='saved_api_refs', interaction_types=['quote'], max_hops=1, client=client)
        mixed = search_all_evidence(graph, None, 'India Meditation', client=client)
    assert result['total'] == 1 and result['results'][0]['accountId'] == '200'
    assert result['results'][0]['networkPath']['edges'][0]['targetTweetId'] == '5002'
    assert mixed['total'] == 1 and mixed['results'][0]['ranking']['savedWords'] == ['india']
    assert str(source) not in json.dumps(result)


def test_empty_quote_placeholder_keeps_outer_post_without_guessing_target(threads):
    source, graph = threads
    with sqlite3.connect(source) as db:
        for tid, raw in db.execute('SELECT tweet_id,raw_json FROM thread_context_cache').fetchall():
            data = json.loads(raw)
            data[0]['quoted_tweet'] = {'id': '', 'author': {}, 'text': '', 'type': 'tweet'}
            db.execute('UPDATE thread_context_cache SET raw_json=? WHERE tweet_id=?', (json.dumps(data), tid))
    with sqlite3.connect(graph) as db:
        report = import_saved_thread_observations(db, source)
        assert report['apiPosts'] == 3 and report['unresolvedQuotes'] == 2
        db.row_factory = sqlite3.Row
        posts, _ = api_post_fragments(db)
        assert all(r['type'] != 'quote' for p in posts[ALICE] for r in p['references'])
        assert posts[ALICE][0]['text'] == 'Meditation interface notes'


def test_thread_copy_rejects_malformed_identity_and_preserves_sources(threads, tmp_path):
    from scripts.verify_thread_post_batch import build_thread_post_batch
    source, graph = threads
    with sqlite3.connect(source) as db:
        row = db.execute('SELECT raw_json FROM thread_context_cache LIMIT 1').fetchone()[0]
        data = json.loads(row); data[0]['id'] = 5001
        db.execute('UPDATE thread_context_cache SET raw_json=?', (json.dumps(data),))
    original, baseline = source.read_bytes(), graph.read_bytes()
    output = tmp_path/'rejected.db'
    with pytest.raises(ValueError, match='numeric'):
        build_thread_post_batch(graph, source, output)
    assert not output.exists() and source.read_bytes() == original and graph.read_bytes() == baseline


def test_thread_copy_retains_prior_rows_and_adopts_without_replacing_package(threads, tmp_path):
    from scripts.verify_thread_post_batch import build_thread_post_batch
    from src.data.local_graph_batch import adopt_graph
    source, graph = threads
    root = tmp_path/'managed'; prior = root/'releases/old'
    for name in ('graph', 'index', 'package'): (prior/name).mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    baseline = prior/'graph/relationships.db'; graph.rename(baseline)
    (prior/'index/posts.db').write_bytes(b'unchanged synthetic index')
    (root/'current').symlink_to(prior, target_is_directory=True)
    output = tmp_path/'accepted.db'
    raw, old = source.read_bytes(), baseline.read_bytes()
    report = build_thread_post_batch(baseline, source, output)
    assert report['apiPosts'] == 3 and report['priorRowsRetained'] and report['reimportUnchanged']
    adopt_graph(root, baseline, output, report)
    assert (root/'current/graph/relationships.db').resolve() == output
    assert (root/'current/index/posts.db').read_bytes() == b'unchanged synthetic index'
    assert baseline.read_bytes() == old and source.read_bytes() == raw


def test_conflicting_authors_for_same_quoted_post_refuse_copy(threads, tmp_path):
    from scripts.verify_thread_post_batch import build_thread_post_batch
    source, graph = threads
    with sqlite3.connect(source) as db:
        data = json.loads(db.execute('SELECT raw_json FROM thread_context_cache LIMIT 1').fetchone()[0])
        data[0]['quoted_tweet']['author']['id'] = '1234'
        db.execute('UPDATE thread_context_cache SET raw_json=?', (json.dumps(data),))
    output = tmp_path/'conflicted.db'
    with pytest.raises(ValueError, match='conflicting author'):
        build_thread_post_batch(graph, source, output)
    assert not output.exists()
