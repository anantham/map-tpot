"""Test intent: typed paths with source-shaped synthetic data only.

- Keep reply/quote/repost/mention types, original direction and exact IDs.
- Prove two-hop and incoming paths, cycles, duplicate mentions and missing context.
- Hide ineligible nodes, preserve source evidence and distinguish unbuilt from zero.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.post_index import build_post_index
from src.data.post_interactions import interaction_paths, interaction_sources, explain_interaction_path
from src.data.social_paths import NetworkCoverageError
from tests.test_post_search import ACCOUNT, posts, refresh_manifest, public_client
from tests.test_published_profiles import bundle
from tests.test_archive_refresh import prepared


@pytest.fixture
def network_bundle(posts):
    table = pq.read_table(posts/'profiles.parquet'); rows = table.to_pylist()
    rows.append({**rows[1], 'account_id': '300', 'username': 'Gamma', 'display_name': 'Example C'})
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), posts/'profiles.parquet')
    raw = (posts/'profiles.parquet').read_bytes(); manifest = json.loads((posts/'manifest.json').read_bytes())
    manifest['files']['profiles'].update(rows=3, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest['consent']['eligible_accounts'] = 3
    pointer = json.loads((posts/'latest.json').read_bytes()); pointer['eligible_account_ids'].append('300')
    (posts/'manifest.json').write_text(json.dumps(manifest)); (posts/'latest.json').write_text(json.dumps(pointer))
    table = pq.read_table(posts/'tweets.parquet'); rows = table.to_pylist()
    rows[1]['mentioned_account_ids'] = [ACCOUNT]  # A self-reference is not discovery.
    rows[2]['mentioned_account_ids'] = ['300', '300']  # One post, not two confirmations.
    rows.append({**rows[2], 'tweet_id': '9007199254740993004', 'account_id': '300',
        'full_text': 'Buddhism Marxist volunteer', 'retweeted_tweet_id': None,
        'quoted_tweet_id': '999999', 'mentioned_account_ids': []})
    moment = datetime(2026, 10, 15, 7, 5, tzinfo=timezone.utc)
    rows.append({**rows[0], 'tweet_id': '9007199254740993005', 'created_at': moment,
        'latest_observed_at': moment, 'mentioned_account_ids': []})
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), posts/'tweets.parquet')
    refresh_manifest(posts)
    return posts


@pytest.fixture
def index(network_bundle, tmp_path):
    build_post_index(network_bundle, tmp_path/'index')
    return tmp_path/'index/posts.db'


@contextmanager
def read_index(path):
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True); db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    try: yield db
    finally: db.close()


def test_new_index_contains_a_nonempty_typed_projection(index):
    with read_index(index) as db:
        version = db.execute("SELECT value FROM meta WHERE key='interactionVersion'").fetchone()
        assert version is not None and version[0] == '1'
        rows = db.execute('SELECT * FROM post_interaction').fetchall()
        assert len(rows) == 5
        reply = next(row for row in rows if row['kind'] == 'reply')
        assert reply['source_account_id'] == ACCOUNT and reply['target_account_id'] == '200'
        assert reply['observation_count'] == 2 and reply['sample_tweet_id'] == '9007199254740993005'
        assert reply['sample_source_row'] == 4
        assert not any(row['source_account_id'] == row['target_account_id'] for row in rows)


def test_outgoing_incoming_and_typed_paths_preserve_real_edge_direction(index):
    allowed = {ACCOUNT, '200', '300'}
    with read_index(index) as db:
        paths, scope = interaction_paths(db, ACCOUNT, 2, allowed)
        assert set(paths) == {'200', '300'} and len(paths['300']) == 2
        assert paths['300'][0]['sourceAccountId'] == ACCOUNT
        assert paths['300'][1]['targetAccountId'] == '300'
        assert scope['kind'] == 'post_references' and scope['direction'] == 'outgoing'
        replies, _ = interaction_paths(db, ACCOUNT, 2, allowed, kinds=['reply'])
        assert set(replies) == {'200'}
        incoming, _ = interaction_paths(db, '300', 2, allowed, direction='incoming')
        assert set(incoming) == {'200', ACCOUNT}
        first = incoming[ACCOUNT][0]
        assert first['sourceAccountId'] == '200' and first['targetAccountId'] == '300'
        assert first['walkFromAccountId'] == '300' and first['walkToAccountId'] == '200'
        empty, _ = interaction_paths(db, '300', 2, allowed)
        assert empty == {}  # Unknown quoted-post author is not invented.


def test_coverage_deduplicates_mentions_and_records_unresolved_context(index):
    with read_index(index) as db:
        profiles = json.loads(db.execute("SELECT value FROM meta WHERE key='profiles'").fetchone()[0])
        summary = interaction_sources(db, profiles, set(profiles))
        assert summary['status'] == 'available' and summary['coverage']['typedPairs'] == 5
        assert summary['coverage']['postObservations'] == 6
        audit = json.loads(db.execute("SELECT value FROM meta WHERE key='interactionAudit'").fetchone()[0])
        assert audit['selfReferences']['mention'] == 1
        assert audit['outsideEligibleTargets']['mention'] == 1
        assert audit['unresolvedPostReferences']['quote'] == 1


def test_ineligible_middle_cannot_bridge_a_path_or_leak_a_label(index):
    with read_index(index) as db:
        allowed = {ACCOUNT, '300'}
        paths, _ = interaction_paths(db, ACCOUNT, 2, allowed)
        assert paths == {}
        with pytest.raises(NetworkCoverageError): interaction_paths(db, '200', 2, allowed)
        profiles = json.loads(db.execute("SELECT value FROM meta WHERE key='profiles'").fetchone()[0])
        result = interaction_sources(db, profiles, allowed)
        assert 'beta' not in json.dumps(result).lower()


def test_path_explanation_links_both_original_posts_and_source_rows(index):
    with read_index(index) as db:
        profiles = json.loads(db.execute("SELECT value FROM meta WHERE key='profiles'").fetchone()[0])
        source = json.loads(db.execute("SELECT value FROM meta WHERE key='source'").fetchone()[0])
        paths, _ = interaction_paths(db, ACCOUNT, 1, set(profiles), kinds=['quote'])
        explanation = explain_interaction_path(db, paths['200'], profiles, source)
        edge = explanation['edges'][0]
        assert edge['kind'] == 'quote' and edge['targetTweetId'] == '9007199254740993003'
        assert edge['evidenceRef']['sourceRow'] == 1 and edge['evidenceRef']['targetSourceRow'] == 2
        assert edge['evidenceRef']['fileSha256'] == source['tweetSha256']
        assert edge['excerpt'] == 'Marxist philosophy and institutions'
        assert explanation['nodes'][0]['accountId'] == ACCOUNT and explanation['nodes'][1]['username'] == 'beta'


@pytest.mark.parametrize('options', [{'max_hops': 3}, {'direction': 'either'}, {'kinds': []}, {'kinds': ['friend']}])
def test_bad_graph_requests_refuse(index, options):
    request = {'max_hops': 2, **options}
    with read_index(index) as db, pytest.raises(ValueError):
        interaction_paths(db, ACCOUNT, allowed={ACCOUNT, '200', '300'}, **request)


def test_legacy_projection_upgrade_is_copied_and_preserves_source(index, network_bundle, tmp_path):
    from scripts.verify_current_archive_interactions import build_interaction_copy
    # Disposable fixture only: emulate the actual pre-projection on-disk schema.
    with sqlite3.connect(index) as db:
        db.execute('DROP TABLE post_interaction')
        db.execute("DELETE FROM meta WHERE key IN ('interactionVersion','interactionAudit')")
    before = index.read_bytes()
    result = build_interaction_copy(network_bundle, index, tmp_path/'upgraded')
    assert result['ready'] is True and result['typedPairs'] == 5
    assert index.read_bytes() == before
    with read_index(tmp_path/'upgraded/posts.db') as db:
        paths, _ = interaction_paths(db, ACCOUNT, 2, {ACCOUNT, '200', '300'})
        assert len(paths['300']) == 2
    with pytest.raises(FileExistsError): build_interaction_copy(network_bundle, index, tmp_path/'upgraded')


@pytest.mark.parametrize('fault', ['building', 'legacy', 'bad_audit'])
def test_incomplete_projection_seed_cannot_replace_managed_binding(prepared, tmp_path, fault):
    import os
    import shutil
    from src.data.archive_refresh import refresh_archive
    from tests.test_archive_refresh import adopt, Publisher
    root = tmp_path/'managed'; adopt(root, prepared); old = os.readlink(root/'current')
    bad = tmp_path/'bad-seed.db'; shutil.copy2(prepared[1], bad)
    with sqlite3.connect(bad) as db:
        if fault == 'building': db.execute("UPDATE meta SET value='building' WHERE key='interactionVersion'")
        elif fault == 'legacy': db.execute("DELETE FROM meta WHERE key IN ('interactionVersion','interactionAudit')")
        else: db.execute("UPDATE meta SET value='{}' WHERE key='interactionAudit'")
    with Publisher(prepared[0]).client() as client, pytest.raises((ValueError, RuntimeError)):
        refresh_archive(root, prepared[2], client=client, apply=True, seed_bundle=prepared[0], seed_index=bad)
    assert os.readlink(root/'current') == old


def test_null_reply_account_is_resolved_or_counted_without_other_reference_help(network_bundle, tmp_path):
    table = pq.read_table(network_bundle/'tweets.parquet'); rows = table.to_pylist()
    rows[0]['reply_to_account_id'] = None
    rows[1]['quoted_tweet_id'] = None  # Otherwise quote resolution masks the missing reply-target pass.
    rows[3]['reply_to_tweet_id'] = '999998'; rows[3]['reply_to_account_id'] = None
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), network_bundle/'tweets.parquet')
    refresh_manifest(network_bundle); build_post_index(network_bundle, tmp_path/'new-index')
    with read_index(tmp_path/'new-index/posts.db') as db:
        audit = json.loads(db.execute("SELECT value FROM meta WHERE key='interactionAudit'").fetchone()[0])
        assert audit['references']['reply'] == 3 and audit['unresolvedPostReferences']['reply'] == 1
        assert db.execute("SELECT observation_count FROM post_interaction WHERE kind='reply'").fetchone()[0] == 2


def test_failed_copy_stays_unadoptable_and_partial_input_refuses_before_output(index, network_bundle, tmp_path):
    import os
    from scripts.verify_current_archive_interactions import build_interaction_copy
    from src.data.post_interactions import validate_interaction_projection
    # Only this disposable fixture is downgraded to the previous derived schema.
    with sqlite3.connect(index) as db:
        db.execute('DROP TABLE post_interaction')
        db.execute("DELETE FROM meta WHERE key IN ('interactionVersion','interactionAudit')")
    before = index.stat()
    def concurrent_touch(event):
        if event['stage'] == 'reference_pairs':
            os.utime(index, ns=(before.st_atime_ns, before.st_mtime_ns+1))
    with pytest.raises(ValueError, match='Source changed'):
        build_interaction_copy(network_bundle, index, tmp_path/'failed', progress=concurrent_touch)
    with read_index(tmp_path/'failed/posts.db') as db, pytest.raises(RuntimeError):
        validate_interaction_projection(db)
    with sqlite3.connect(index) as db:
        db.execute("DELETE FROM post WHERE tweet_id='9007199254740993001'")
    with pytest.raises(ValueError, match='physical post rows'):
        build_interaction_copy(network_bundle, index, tmp_path/'partial')
    assert not (tmp_path/'partial').exists()
