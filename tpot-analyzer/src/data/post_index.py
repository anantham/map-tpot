"""Rebuildable local post index; raw package and relationship stores stay intact."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.archive.snapshot import utc_iso
from src.data.published_profiles import BASE, read_profile_bundle
from src.data.post_interactions import build_post_interactions

POST_FIELDS = ('tweet_id', 'account_id', 'created_at', 'full_text', 'favorite_count',
    'retweet_count', 'reply_to_tweet_id', 'reply_to_account_id', 'quoted_tweet_id',
    'retweeted_tweet_id', 'conversation_id', 'media', 'urls', 'mentioned_account_ids',
    'archive_upload_ids', 'latest_observed_at')
CONTEXT = {'replyToTweetId': 'reply_to_tweet_id', 'replyToAccountId': 'reply_to_account_id',
    'quotedTweetId': 'quoted_tweet_id', 'repostedTweetId': 'retweeted_tweet_id',
    'conversationId': 'conversation_id'}
INDEX_FIELDS = [key for key in POST_FIELDS if key not in ('media', 'urls', 'archive_upload_ids')]


def verified_post_package(folder):
    """Validate publisher-bound bytes and physical types before output creation."""
    folder = Path(folder)
    profiles = read_profile_bundle(folder)
    raw = (folder/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != profiles['rawSource']['manifestSha256']:
        raise ValueError('Post package metadata changed during validation')
    manifest = json.loads(raw)
    try:
        info = manifest['files']['tweets']; export = profiles['exportId']
        if (info['path'] != 'tweets.parquet' or manifest['publication']['urls']['tweets'] != BASE+'v1/'+export+'/tweets.parquet'
            or any(type(info[key]) is not int or info[key] <= 0 for key in ('bytes', 'rows', 'distinct_accounts'))
            or info['bytes'] > 8*1024**3 or info['rows'] > 50000000
            or not isinstance(info['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', info['sha256'])):
            raise ValueError('Post package manifest fields are invalid')
    except (KeyError, TypeError) as error:
        raise ValueError('Post package manifest is incomplete') from error
    path = folder/'tweets.parquet'; before = path.stat()
    if before.st_size != info['bytes']:
        raise ValueError('Post package size differs from manifest')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != info['sha256']:
        raise ValueError('Post package checksum differs from manifest')
    source = pq.ParquetFile(path); schema = source.schema_arrow
    if schema.names != info.get('columns') or not set(POST_FIELDS) <= set(schema.names) or source.metadata.num_rows != info['rows']:
        raise ValueError('Post physical schema/rows differ from manifest')
    for field in ('tweet_id', 'account_id', 'full_text', *CONTEXT.values()):
        if not pa.types.is_string(schema.field(field).type):
            raise ValueError('Post text and identities must be strings')
    for field in ('created_at', 'latest_observed_at'):
        kind = schema.field(field).type
        if not pa.types.is_timestamp(kind) or kind.tz is None or kind.unit != 'ms':
            raise ValueError('Post timestamps must be timezone-aware milliseconds')
    for field in ('favorite_count', 'retweet_count'):
        if not pa.types.is_unsigned_integer(schema.field(field).type):
            raise ValueError('Post counts must be unsigned integers')
    mentions = schema.field('mentioned_account_ids').type
    if not pa.types.is_list(mentions) or not pa.types.is_string(mentions.value_type):
        raise ValueError('Mention identities must be a list of strings')
    return profiles, info, source, (before.st_ino, before.st_size, before.st_mtime_ns)


def _validate_batch(batch, eligible):
    for field in ('tweet_id', 'account_id', 'created_at', 'full_text', 'favorite_count', 'retweet_count', 'latest_observed_at'):
        if batch.column(field).null_count:
            raise ValueError('Required post field contains null: '+field)
    for field in ('tweet_id', 'account_id', *CONTEXT.values(), 'mentioned_account_ids'):
        values = batch.column(field)
        if field == 'mentioned_account_ids':
            if values.null_count:
                raise ValueError('Post mention list is null')
            values = pc.list_flatten(values)
        if field in ('tweet_id', 'account_id') and values.null_count:
            raise ValueError('Post identity is null')
        values = pc.drop_null(values)
        if pc.any(pc.invert(pc.match_substring_regex(values, '^[0-9]+$'))).as_py():
            raise ValueError('Post/reference identity is not an exact numeric string')
    if not pc.all(pc.is_in(batch.column('account_id'), value_set=eligible)).as_py():
        raise ValueError('Post author is outside the published eligible set')


def build_post_index(bundle, output_dir, *, progress=None):
    started = time.monotonic()
    profiles, info, parquet, identity = verified_post_package(bundle)
    target = Path(output_dir); target.mkdir(mode=0o700)
    if target.stat().st_mode & 0o077:
        raise ValueError('Post index directory must be private')
    path = target/'posts.db'
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(descriptor)
    eligible = pa.array([row['account_id'] for row in profiles['profiles']])
    authors, total = set(), 0
    with sqlite3.connect(path) as db:
        db.executescript("""PRAGMA journal_mode=DELETE;
          CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          INSERT INTO meta VALUES('ready','false');
          CREATE TABLE post(tweet_id TEXT UNIQUE NOT NULL,account_id TEXT NOT NULL,
            created_at TEXT NOT NULL,full_text TEXT NOT NULL,context_json TEXT NOT NULL,source_row INTEGER UNIQUE NOT NULL);
          CREATE INDEX post_account ON post(account_id,created_at DESC);
          CREATE VIRTUAL TABLE post_fts USING fts5(full_text,account_id,content='post',content_rowid='rowid',tokenize='unicode61');""")
        try:
            for batch in parquet.iter_batches(batch_size=32768, columns=INDEX_FIELDS):
                _validate_batch(batch, eligible)
                columns = {name: batch.column(name).to_pylist() for name in INDEX_FIELDS}
                rows = []
                for offset in range(len(batch)):
                    context = {name: columns[field][offset] for name, field in CONTEXT.items()}
                    context.update(mentionedAccountIds=columns['mentioned_account_ids'][offset],
                        favoriteCount=columns['favorite_count'][offset],retweetCount=columns['retweet_count'][offset],
                        observedAt=utc_iso(columns['latest_observed_at'][offset]))
                    rows.append((columns['tweet_id'][offset], columns['account_id'][offset],
                        utc_iso(columns['created_at'][offset]), columns['full_text'][offset],
                        json.dumps(context, separators=(',', ':')), total+offset))
                db.executemany('INSERT INTO post VALUES(?,?,?,?,?,?)', rows)
                authors.update(columns['account_id']); total += len(batch)
                if progress: progress({'stage': 'posts', 'rows': total, 'expectedRows': info['rows']})
            if total != info['rows'] or len(authors) != info['distinct_accounts']:
                raise ValueError('Post row/author counts differ from manifest')
            if progress: progress({'stage': 'full_text_index', 'rows': total})
            db.execute("INSERT INTO post_fts(post_fts) VALUES('rebuild')")
            build_post_interactions(db, parquet, eligible.to_pylist(), progress=progress)
            current = (Path(bundle)/'tweets.parquet').stat()
            if identity != (current.st_ino, current.st_size, current.st_mtime_ns):
                raise ValueError('Post source identity changed during build')
            source = {'kind': 'community_archive_published_posts', 'exportId': profiles['exportId'],
                'tweetSha256': info['sha256'], 'profileSha256': profiles['rawSource']['profileSha256'],
                'manifestSha256': profiles['rawSource']['manifestSha256'],
                'rows': total, 'authors': len(authors), 'sourcePath': str((Path(bundle)/'tweets.parquet').resolve())}
            db.executemany('INSERT INTO meta VALUES(?,?)', [('source', json.dumps(source)),
                ('profiles', json.dumps({row['account_id']: row for row in profiles['profiles']}))])
            db.execute("UPDATE meta SET value='true' WHERE key='ready'")
            db.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError('Post identities/source rows are duplicated; index not ready') from error
    report = {'ready': True, 'rows': total, 'authors': len(authors), 'exportId': profiles['exportId'],
        'bytes': path.stat().st_size, 'seconds': round(time.monotonic()-started, 3),
        'operationalStatus': 'copied_index_not_active'}
    descriptor = os.open(target/'report.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as output: json.dump(report, output, indent=2)
    return report
