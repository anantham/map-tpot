"""Independent historical API post/reference observations, not HTTP receipts."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from collections import Counter

from src.data.saved_capture_import import CaptureWriter
from src.data.saved_provider_profiles import import_saved_provider_profiles

SOURCE_KIND = 'saved_api_post_row'
POST = 'api_post_observation'
PREDICATES = {'reply': 'replied_to_account_observed', 'retweet': 'reposted_account_observed',
              'quote': 'quoted_account_observed', 'mention': 'mentioned_account_observed'}
BOUNDARY = ('Historical saved API table observations, not original transport receipts, '
            'current availability, agreement, endorsement, expertise or membership.')
TIMELINE_SOURCES = ('last_tweets', 'last_tweets_deep', 'advanced_search', 'topic_seed')


def _numeric(value):
    return isinstance(value, str) and re.fullmatch('[0-9]+', value) is not None


def _snapshot(db, path, table, row):
    payload = {'producer': 'saved-api-posts-v1', 'visibility': 'private', 'sourceTable': table, 'row': row}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    key = hashlib.sha256(raw).hexdigest()
    db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES(?,?,?,?)',
               (key, str(path)+'#'+table, row['fetched_at'], raw))
    return key


def append_api_post_row(writer, path, post):
    """Use identical snapshots/attributes for typed and standalone stored rows."""
    if any(not _numeric(post[key]) for key in ('account_id', 'tweet_id')):
        raise ValueError('Saved API posts require exact numeric identities')
    if not isinstance(post['text'], str) or not post['text'].strip():
        raise ValueError('Saved API post has no usable text')
    if not isinstance(post['fetched_at'], str): raise ValueError('Saved API capture time is missing')
    datetime.fromisoformat(post['fetched_at'])
    actor = writer.entity('x_account', post['account_id'])
    snapshot = _snapshot(writer.db, path, 'enriched_tweets', post)
    writer.relation(actor, POST, writer.entity('x_post', post['tweet_id']), snapshot, '/row/text', post['fetched_at'],
        {'sourceKind': SOURCE_KIND, 'tweetId': post['tweet_id'], 'text': post['text'],
         'createdAt': post['created_at'], 'fetchSource': post['fetch_source'], 'boundary': BOUNDARY})
    return actor


def import_api_timeline_posts(db, archive_path, *, limit=5000):
    """Standalone saved timeline/search text, no inferred numeric references."""
    if type(limit) is not int or not 1 <= limit <= 5000:
        raise ValueError('API timeline batch limit must be1–5000')
    path = Path(archive_path).resolve(strict=True)
    report = {'apiPosts': 0, 'typedReferences': 0, 'selfReferences': 0, 'exclusions': [],
              'postObservationsAdded': 0, 'selectedSourceCounts': {}, 'excludedSourceCounts': {}}
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('PRAGMA query_only=ON'); source.execute('BEGIN')
        totals = dict(source.execute('SELECT fetch_source,count(*) FROM enriched_tweets GROUP BY fetch_source'))
        total = sum(n for kind, n in totals.items() if kind in TIMELINE_SOURCES)
        rows = [dict(row) for row in source.execute('''SELECT * FROM enriched_tweets
            WHERE fetch_source IN (?,?,?,?) ORDER BY account_id,tweet_id LIMIT ?''', (*TIMELINE_SOURCES, limit))]
        report.update(selectedRows=len(rows), totalRowsAtImport=total, truncated=total > len(rows),
            selectedSourceCounts=dict(Counter(row['fetch_source'] for row in rows)),
            excludedSourceCounts={kind: n for kind, n in totals.items() if kind not in TIMELINE_SOURCES})
        if not rows: return report
        if any(not _numeric(row[key]) for row in rows for key in ('account_id', 'tweet_id')):
            raise ValueError('Saved API posts require exact numeric identities')
        recovery = import_saved_provider_profiles(db, path, sorted({row['account_id'] for row in rows}))
        allowed = set(recovery['projectedAccountIds'])
        report.update(providerProfiles=recovery['profiles'], profileExclusions=recovery['exclusions'])
        authors = {}
        for tid, aid in db.execute('''SELECT p.source_key,a.source_key FROM relation r
            JOIN entity a ON a.entity_id=r.subject_id JOIN entity p ON p.entity_id=r.object_id
            WHERE r.predicate=? AND a.kind='x_account' AND p.kind='x_post' ''', (POST,)):
            authors.setdefault(tid, set()).add(aid)
        before = db.execute('SELECT count(*) FROM relation WHERE predicate=?', (POST,)).fetchone()[0]
        writer = CaptureWriter(db)
        for post in rows:
            reason = ('source_not_explicit_public' if post['account_id'] not in allowed else
                      'existing_post_author_conflict' if post['tweet_id'] in authors
                        and authors[post['tweet_id']] != {post['account_id']} else None)
            if reason:
                report['exclusions'].append({'tweetId': post['tweet_id'], 'reason': reason}); continue
            append_api_post_row(writer, path, post)
            report['apiPosts'] += 1
        report['postObservationsAdded'] = db.execute('SELECT count(*) FROM relation WHERE predicate=?', (POST,)).fetchone()[0] - before
    return report


def import_api_post_observations(db, archive_path, *, limit=1000):
    """Caller owns the copied graph/transaction; all source reads are offline."""
    if type(limit) is not int or not 1 <= limit <= 5000:
        raise ValueError('API post batch limit must be1–5000')
    path = Path(archive_path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('PRAGMA query_only=ON'); source.execute('BEGIN')
        total = source.execute('SELECT count(*) FROM api_typed_edges').fetchone()[0]
        rows = [dict(row) for row in source.execute('SELECT * FROM api_typed_edges ORDER BY source_id,target_id,edge_type,tweet_id LIMIT ?', (limit,))]
        report = {'apiPosts': 0, 'typedReferences': 0, 'exclusions': [], 'selfReferences': 0,
                  'selectedRows': len(rows), 'totalRowsAtImport': total, 'truncated': total > len(rows)}
        if not rows:
            return report
        if any(not _numeric(row[key]) for row in rows for key in ('source_id', 'target_id', 'tweet_id')):
            raise ValueError('Saved API reference requires exact numeric identities')
        ids = sorted({row[key] for row in rows for key in ('source_id', 'target_id')})
        recovery = import_saved_provider_profiles(db, path, ids)
        allowed = set(recovery['projectedAccountIds'])
        blocked = {row['accountId'] for row in recovery['exclusions']
                   if row['reason'] in ('flagged_account', 'protected_at_capture', 'unavailable_at_capture')}
        report['providerProfiles'] = recovery['profiles']; report['profileExclusions'] = recovery['exclusions']
        writer, posts = CaptureWriter(db), set()
        for row in rows:
            post = source.execute('SELECT * FROM enriched_tweets WHERE tweet_id=?', (row['tweet_id'],)).fetchone()
            reason = ('source_not_explicit_public' if row['source_id'] not in allowed else
                      'target_restricted_at_capture' if row['target_id'] in blocked else
                      'unsupported_reference_source' if row['edge_type'] not in PREDICATES or row['fetch_source'] not in ('last_tweets_dump', 'last_tweets_deep') else
                      'post_missing_or_author_conflict' if post is None or post['account_id'] != row['source_id'] else
                      'post_not_independent_api_text' if post['fetch_source'] not in ('last_tweets', 'last_tweets_deep') else None)
            if reason:
                report['exclusions'].append({'tweetId': row['tweet_id'], 'reason': reason}); continue
            post = dict(post)
            if not isinstance(row['fetched_at'], str): raise ValueError('Saved API capture time is missing')
            datetime.fromisoformat(row['fetched_at'])
            actor = append_api_post_row(writer, path, post)
            snapshot = _snapshot(db, path, 'api_typed_edges', row)
            writer.relation(actor, PREDICATES[row['edge_type']], writer.entity('x_account', row['target_id']),
                snapshot, '/row', row['fetched_at'], {'sourceKind': SOURCE_KIND,
                'tweetId': row['tweet_id'], 'type': 'repost' if row['edge_type'] == 'retweet' else row['edge_type'],
                'createdAt': row['created_at'], 'fetchSource': row['fetch_source'], 'boundary': BOUNDARY})
            posts.add((row['source_id'], row['tweet_id'])); report['typedReferences'] += 1
            report['selfReferences'] += row['source_id'] == row['target_id']
        report['apiPosts'] = len(posts)
        return report


def api_post_fragments(db):
    """Allowlisted search fragments and reported references, never raw payloads."""
    def ref(row):
        return {'snapshotId': row['snapshot_id'], 'sourcePointer': row['source_pointer'],
                'observedAt': row['observed_at']}
    references, fragments, unique = {}, {}, {}
    reference_observations = post_observations = 0
    for row in db.execute('''SELECT a.source_key source_id,b.source_key target_id,r.* FROM relation r
            JOIN entity a ON a.entity_id=r.subject_id JOIN entity b ON b.entity_id=r.object_id
            WHERE r.predicate IN (?,?,?,?) AND a.kind='x_account' AND b.kind='x_account' ORDER BY r.relation_id''', tuple(PREDICATES.values())):
        attrs = json.loads(row['attributes_json'])
        if attrs.get('sourceKind') != SOURCE_KIND: continue
        reference_observations += 1
        key = (row['target_id'], attrs['type'], attrs.get('targetTweetId'))
        references.setdefault((row['source_id'], attrs['tweetId']), {}).setdefault(key, {
            'sourceAccountId': row['source_id'], 'targetAccountId': row['target_id'],
            'type': attrs['type'], 'createdAt': attrs.get('createdAt'),
            **({'targetTweetId': attrs['targetTweetId']} if attrs.get('targetTweetId') else {}),
            'fetchSource': attrs['fetchSource'], 'evidenceRef': ref(row), 'boundary': BOUNDARY})
    for row in db.execute('''SELECT a.source_key account_id,p.source_key tweet_id,r.* FROM relation r
            JOIN entity a ON a.entity_id=r.subject_id JOIN entity p ON p.entity_id=r.object_id
            WHERE r.predicate=? AND a.kind='x_account' AND p.kind='x_post' ORDER BY r.relation_id''', (POST,)):
        attrs = json.loads(row['attributes_json'])
        if (attrs.get('sourceKind') != SOURCE_KIND or attrs.get('tweetId') != row['tweet_id']
                or not _numeric(row['tweet_id']) or not isinstance(attrs.get('text'), str)):
            raise ValueError('Saved API post projection is invalid')
        post_observations += 1
        key = (row['account_id'], row['tweet_id'], attrs['text'])
        if key in unique:
            unique[key]['captureCount'] += 1
            continue
        fragment = {'kind': 'api_post', 'label': 'Post '+row['tweet_id'], 'captureCount': 1,
            'tweetId': row['tweet_id'],
            'text': attrs['text'], 'url': 'https://x.com/i/status/'+row['tweet_id'],
            'createdAt': attrs.get('createdAt'), 'evidenceRef': ref(row), 'association': BOUNDARY,
            'sourceContext': [{'field': 'stored_post_date', 'value': attrs.get('createdAt')},
                              {'field': 'fetch_source', 'value': attrs.get('fetchSource')}],
            'references': list(references.get((row['account_id'], row['tweet_id']), {}).values())}
        unique[key] = fragment
        fragments.setdefault(row['account_id'], []).append(fragment)
    return fragments, {'apiPostObservations': post_observations,
                       'apiPostAccounts': len(fragments), 'apiTypedReferences': reference_observations}
