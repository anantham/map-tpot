"""Offline projection of captured API thread observations."""
import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

from src.data.saved_api_posts import SOURCE_KIND, POST, PREDICATES, BOUNDARY
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_provider_profiles import decode_provider_profile, append_provider_profile


def _numeric(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9]+', value):
        raise ValueError('Saved thread identities must be exact numeric strings')
    return value


def _references(tweet, pointer, report):
    """Only structured provider IDs, never screen-name or text inference."""
    if tweet.get('isReply') is True and tweet.get('inReplyToUserId'):
        yield 'reply', _numeric(tweet['inReplyToUserId']), pointer+'/inReplyToUserId', tweet.get('inReplyToId')
    quoted = tweet.get('quoted_tweet')
    if quoted is not None:
        if not isinstance(quoted, dict): raise ValueError('Saved quoted post must be an object')
        author = quoted.get('author')
        if not quoted.get('id') or not isinstance(author, dict) or not author.get('id'):
            report['unresolvedQuotes'] += 1
        elif author.get('protected') is False and author.get('unavailable') is not True:
            yield 'quote', _numeric(author.get('id')), pointer+'/quoted_tweet/author/id', _numeric(quoted.get('id'))
        else: report['excludedReferences'] += 1
    entities = tweet.get('entities') or {}
    if not isinstance(entities, dict): raise ValueError('Saved post entities must be an object')
    mentions = entities.get('user_mentions', [])
    if not isinstance(mentions, list): raise ValueError('Saved mention entities must be an array')
    for index, mention in enumerate(mentions):
        if not isinstance(mention, dict): raise ValueError('Saved mention must be an object')
        if not mention.get('id_str'):
            report['unresolvedMentions'] += 1; continue
        yield 'mention', _numeric(mention['id_str']), f'{pointer}/entities/user_mentions/{index}/id_str', None


def import_saved_thread_observations(db, archive_path, *, limit=500):
    """Append source-qualified outer posts on the caller's private graph copy.

    Preserve the raw cache row and decoded array for exact field pointers. Nested
    quoted text is not imported as the quoting author's text. Original stores are
    opened read-only; this module never imports the fetching client.
    """
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Thread batch limit must be1–1000 cache rows')
    path = Path(archive_path).resolve(strict=True)
    report = {'apiPosts': 0, 'postObservations': 0, 'typedReferences': 0, 'referenceTypes': {},
        'excludedPosts': 0, 'excludedReferences': 0, 'unresolvedMentions': 0, 'unresolvedQuotes': 0, 'selfReferences': 0}
    writer, posts, profiles, types = CaptureWriter(db), set(), set(), Counter()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('PRAGMA query_only=ON'); source.execute('BEGIN')
        blocked = {r[0] for r in source.execute('SELECT account_id FROM protected_accounts')}
        for row in source.execute('SELECT account_id,raw_json FROM user_profile_cache'):
            try: profile = json.loads(row['raw_json'])
            except (TypeError, ValueError): continue
            if isinstance(profile, dict) and (profile.get('protected') is True or profile.get('unavailable') is True):
                blocked.add(row['account_id'])
        total = source.execute('SELECT count(*) FROM thread_context_cache').fetchone()[0]
        rows = [dict(row) for row in source.execute('SELECT * FROM thread_context_cache ORDER BY tweet_id LIMIT ?', (limit,))]
        report.update(selectedRows=len(rows), totalRowsAtImport=total, truncated=total > len(rows))
        decoded = []
        identities = {}
        for row in rows:
            _numeric(row['tweet_id'])
            tweets = json.loads(row['raw_json'])
            if not isinstance(tweets, list): raise ValueError('Saved thread cache must contain a tweet array')
            if not isinstance(row['fetched_at'], str): raise ValueError('Saved thread capture time is missing')
            datetime.fromisoformat(row['fetched_at'])
            decoded.append((row, tweets))
            for tweet in tweets:
                if not isinstance(tweet, dict): raise ValueError('Saved thread post must be an object')
                for item in (tweet, tweet.get('quoted_tweet')):
                    if not isinstance(item, dict): continue
                    author = item.get('author')
                    if item is not tweet and (not item.get('id') or not isinstance(author, dict) or not author.get('id')):
                        continue  # Empty/unavailable quoted targets remain unresolved, not new identities.
                    tid = _numeric(item.get('id'))
                    if not isinstance(author, dict): raise ValueError('Saved thread post lacks a structured author')
                    aid = _numeric(author.get('id'))
                    if tid in identities and identities[tid] != aid:
                        raise ValueError('Saved thread post has conflicting author identities')
                    identities[tid] = aid
                    if author.get('protected') is True or author.get('unavailable') is True: blocked.add(aid)
        for row, tweets in decoded:
            payload = {'producer': 'saved-api-threads-v1', 'visibility': 'private',
                'sourceTable': 'thread_context_cache', 'row': row, 'tweets': tweets}
            raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
            snapshot = hashlib.sha256(raw).hexdigest()
            written = False
            for index, tweet in enumerate(tweets):
                if not isinstance(tweet, dict): raise ValueError('Saved thread post must be an object')
                tid = _numeric(tweet.get('id'))
                author = tweet.get('author')
                if not isinstance(author, dict): raise ValueError('Saved thread post lacks a structured author')
                aid = _numeric(author.get('id'))
                profile, reason = decode_provider_profile({'raw_json': json.dumps(author),
                    'account_id': aid, 'username': author.get('userName'), 'fetched_at': row['fetched_at']})
                if reason or aid in blocked:
                    report['excludedPosts'] += 1; continue
                if not isinstance(tweet.get('text'), str) or not tweet['text'].strip():
                    raise ValueError('Saved thread post text is missing')
                if not isinstance(tweet.get('createdAt'), str): raise ValueError('Saved thread post date is missing')
                pointer = f'/tweets/{index}'
                if not written:
                    db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES(?,?,?,?)',
                        (snapshot, str(path)+'#thread_context_cache', row['fetched_at'], raw))
                    written = True
                append_provider_profile(writer, profile, snapshot, pointer+'/author', row['fetched_at'],
                    observed_field='thread_context_cache.fetched_at')
                actor = writer.entity('x_account', aid)
                attrs = {'sourceKind': SOURCE_KIND, 'tweetId': tid, 'text': tweet['text'],
                    'createdAt': tweet['createdAt'], 'fetchSource': 'thread_context_cache', 'boundary': BOUNDARY}
                writer.relation(actor, POST, writer.entity('x_post', tid), snapshot, pointer+'/text', row['fetched_at'], attrs)
                for kind, target, field, target_post in _references(tweet, pointer, report):
                    if target in blocked:
                        report['excludedReferences'] += 1; continue
                    if target_post is not None: target_post = _numeric(target_post)
                    reference = {**{key: value for key, value in attrs.items() if key != 'text'}, 'type': kind}
                    if target_post: reference['targetTweetId'] = target_post
                    writer.relation(actor, PREDICATES[kind], writer.entity('x_account', target),
                        snapshot, field, row['fetched_at'], reference)
                    types[kind] += 1; report['selfReferences'] += aid == target
                posts.add((aid, tid)); profiles.add(aid); report['postObservations'] += 1
    report.update(apiPosts=len(posts), providerAccounts=len(profiles), referenceTypes=dict(types), typedReferences=sum(types.values()))
    return report
