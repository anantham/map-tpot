#!/usr/bin/env python3
"""Read-only typed-edge inventory, not current eligibility or graph activation.

One-shot diagnostic: instrument real schemas/counts, not a new graph pipeline.
Missing/expired queries are unavailable, never zero. No application imports.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.verify_map_data_sources import file_identity, readonly

ARCHIVE = {
    'posts': """SELECT count(*) records,count(DISTINCT account_id) sourceAccounts,
      sum(reply_to_tweet_id IS NOT NULL AND reply_to_tweet_id!='') replyPostRefs,
      sum(reply_to_username IS NOT NULL AND reply_to_username!='') replyHandleRefs FROM tweets""",
    'likes': 'SELECT count(*) records,count(DISTINCT liker_account_id) sourceAccounts FROM likes',
    'likedAuthorLookup': """SELECT count(*) matchedRecords FROM likes l WHERE EXISTS
      (SELECT 1 FROM tweets t WHERE t.tweet_id=l.tweet_id AND t.account_id IS NOT NULL AND t.account_id!='')""",
    'retweets': """SELECT count(*) records,count(DISTINCT account_id) sourceAccounts,
      count(DISTINCT rt_of_username) targetHandles FROM retweets""",
    'retweetHandleLookup': """SELECT count(*) candidateRecords FROM retweets
      WHERE lower(rt_of_username) IN (SELECT lower(username) FROM profiles WHERE username IS NOT NULL)""",
    'apiTyped': """SELECT edge_type type,fetch_source source,count(*) records,
      count(DISTINCT source_id) sourceAccounts,count(DISTINCT target_id) targetAccounts,
      min(fetched_at) rawCaptureMin,max(fetched_at) rawCaptureMax
      FROM api_typed_edges GROUP BY edge_type,fetch_source ORDER BY edge_type,fetch_source""",
    'derivedPairs': """SELECT 'account_engagement_agg' source,count(*) records FROM account_engagement_agg
      UNION ALL SELECT 'quote_graph',count(*) FROM quote_graph
      UNION ALL SELECT 'mention_graph',count(*) FROM mention_graph
      UNION ALL SELECT 'signed_reply',count(*) FROM signed_reply""",
}
SHADOW = {
    'profiles': """SELECT count(*) records,sum(account_id LIKE 'shadow:%') handleAliasRecords,
      sum(bio IS NOT NULL AND bio!='') withBio FROM shadow_account""",
    'edges': """SELECT direction,source_channel source,count(*) records FROM shadow_edge
      GROUP BY direction,source_channel ORDER BY direction,source_channel""",
}


def _metric(db, sql, budget):
    start = time.monotonic()
    db.set_progress_handler(lambda: time.monotonic()-start > budget, 10000)
    try:
        values = [dict(row) for row in db.execute(sql)]
        return {'status': 'available', 'rows': values, 'seconds': round(time.monotonic()-start, 3)}
    except sqlite3.Error as error:
        return {'status': 'unavailable', 'error': str(error), 'seconds': round(time.monotonic()-start, 3)}
    finally:
        db.set_progress_handler(None, 0)


def inventory(archive, shadow, *, sidecar=None, query_seconds=60):
    if not math.isfinite(query_seconds) or not 0 < query_seconds <= 300:
        raise ValueError('Query budget must be finite and between0 and300 seconds')
    report = {'observedAt': datetime.now(timezone.utc).isoformat(), 'sources': {},
        'boundary': ['Private historical custody, not current consent, completeness or active graph.',
          'Liked-author lookup uses exact post IDs; unmatched likes remain unresolved.',
          'Retweet handle candidates are not verified account identities; no alias merge.',
          'Derived-pair rows are not raw events or independent confirmations.',
          'Raw capture bounds are strings, not a parsed event-date range. No like event time is stored.',
          'Each store uses a read snapshot; stat identity cannot prove quiescence or detect WAL-only changes.']}
    for name, path, queries in (('archive', archive, ARCHIVE), ('shadow', shadow, SHADOW)):
        before = file_identity(path)
        with closing(readonly(path)) as db:
            metrics, reference, side_before = {}, None, None
            if name == 'archive' and sidecar:
                try:
                    side_before = file_identity(sidecar)
                    candidate = Path(side_before['path'])
                    db.execute('ATTACH DATABASE ? AS saved', (candidate.as_uri()+'?mode=ro',))
                    reference = candidate
                except (OSError, ValueError, sqlite3.Error) as error:
                    metrics['apiProfileOverlap'] = {'status': 'unavailable', 'error': type(error).__name__}
            db.execute('BEGIN')  # Keep totals and lookups on the same read snapshot.
            metrics.update({key: _metric(db, sql, query_seconds) for key, sql in queries.items()})
            if reference is not None:
                metrics['apiProfileOverlap'] = _metric(db, """WITH p AS (
                  SELECT DISTINCT e.source_key id FROM saved.entity e JOIN saved.relation r ON r.subject_id=e.entity_id
                  WHERE e.kind='x_account' AND r.predicate='profile_observation')
                  SELECT edge_type type,count(*) records,
                   sum(source_id IN (SELECT id FROM p)) withSourceProfile,
                   sum(target_id IN (SELECT id FROM p)) withTargetProfile,
                   sum(source_id IN (SELECT id FROM p) AND target_id IN (SELECT id FROM p)) withBothProfiles
                  FROM api_typed_edges GROUP BY edge_type ORDER BY edge_type""", query_seconds)
                side_stable = side_before == file_identity(reference)
                report['sidecar'] = {**side_before, 'stableIdentity': side_stable}
                if not side_stable:
                    metrics['apiProfileOverlap']['status'] = 'unavailable'
                    metrics['apiProfileOverlap']['error'] = 'Sidecar file identity changed during read'
        report['sources'][name] = {**before, 'stableIdentity': before == file_identity(path), 'metrics': metrics}
    metrics = report['sources']['archive']['metrics']
    for total, lookup, key in (('likes','likedAuthorLookup','unresolvedAuthorRecords'),
                                ('retweets','retweetHandleLookup','withoutHandleCandidateRecords')):
        if metrics[total]['status'] == metrics[lookup]['status'] == 'available':
            count = metrics[total]['rows'][0]['records']
            matched = next(iter(metrics[lookup]['rows'][0].values()))
            metrics[lookup][key] = count-matched
    report['complete'] = all(source['stableIdentity'] and all(metric['status']=='available'
        for metric in source['metrics'].values()) for source in report['sources'].values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--shadow', type=Path, required=True)
    parser.add_argument('--sidecar', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--query-seconds', type=float, default=60)
    args = parser.parse_args()
    try:
        report = inventory(args.archive, args.shadow, sidecar=args.sidecar, query_seconds=args.query_seconds)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if args.output.parent.stat().st_mode & 0o077:
                raise ValueError('Report directory must be private mode0700')
            descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, 'w') as output:
                json.dump(report, output, indent=2)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f'✗ Inventory refused: {type(error).__name__}: {error}')
        return 1
    for source, content in report['sources'].items():
        print(f"{'✓' if content['stableIdentity'] else '✗'} {source} file identity stable; {content['bytes']:,} bytes")
        for name, metric in content['metrics'].items():
            print(f"{'✓' if metric['status']=='available' else '✗'} {source}.{name}: {json.dumps(metric)}")
    print('Boundary: historical custody only; no active eligibility, identity merge, tags, network or source writes.')
    print('Next: map current source eligibility before interaction backfill; keep Review context links usable now.')
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
