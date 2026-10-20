#!/usr/bin/env python3
"""Check or explicitly refresh the local current Archive pair; no paid calls."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.data.archive_refresh import refresh_archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='private managed releases root')
    parser.add_argument('--refresh', action='store_true', help='explicitly allow download/build and managed binding replacement')
    parser.add_argument('--source-db', type=Path, help='existing private graph to copy, required with --refresh')
    parser.add_argument('--seed-bundle', type=Path, help='first adoption only: existing verified paired package')
    parser.add_argument('--seed-index', type=Path, help='first adoption only: matching ready posts.db')
    parser.add_argument('--max-bytes', type=int, default=2_000_000_000, help='total package transfer ceiling')
    parser.add_argument('--website-cache',type=Path,help='optional local cache to reproject after a downloaded publication refresh')
    parser.add_argument('--website-accounts-json',type=Path,help='explicit fixed account selection for cache reprojection; current publication stays a no-op')
    args = parser.parse_args(argv)
    if args.refresh and not args.source_db: parser.error('--refresh requires --source-db')
    if bool(args.seed_bundle) != bool(args.seed_index) or ((args.seed_bundle or args.seed_index) and not args.refresh):
        parser.error('Seed adoption requires both seed paths and --refresh')
    if bool(args.website_cache)!=bool(args.website_accounts_json):
        parser.error('Website reprojection requires both --website-cache and --website-accounts-json')
    last = [0]
    def progress(event):
        if event['stage'] != 'posts' or event['rows']-last[0] >= 500000:
            print('✓ Progress: '+json.dumps(event), flush=True)
            if 'rows' in event: last[0] = event['rows']
    print('Current Archive pair refresh: '+('APPLY' if args.refresh else 'CHECK ONLY'), flush=True)
    try:
        website_accounts=None
        if args.website_accounts_json:
            selection=json.loads(args.website_accounts_json.read_bytes())
            if not isinstance(selection,list) or not selection:raise ValueError('Website account selection must be nonempty')
            website_accounts=[row['accountId'] for row in selection]
        with httpx.Client(timeout=httpx.Timeout(300, connect=10), follow_redirects=False) as client:
            result = refresh_archive(args.root, args.source_db, client=client, apply=args.refresh,
                seed_bundle=args.seed_bundle, seed_index=args.seed_index,
                max_bytes=args.max_bytes, progress=progress,website_cache=args.website_cache,website_accounts=website_accounts)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, sqlite3.Error, httpx.HTTPError) as error:
        print(f'✗ Refresh refused: {type(error).__name__}: {error}')
        print('Next: inspect the failure and private incomplete release; the prior binding and source-visibility checks remain in force. No automatic retry.')
        return 1
    print(('✗' if result['status'] == 'needs_refresh' else '✓')+' '+json.dumps(result, sort_keys=True))
    print('✓ Boundary: original stores/tags/outreach unchanged; prior releases retained; no paid request or background schedule.')
    if result['status'] == 'needs_refresh':
        print('Next: rerun with --refresh --source-db PATH after checking free disk space. First adoption can use --seed-bundle/--seed-index.')
    else:
        print('Next: Review should use ROOT/current/index/posts.db and ROOT/current/graph/relationships.db; verify search and exact dossier. A runtime needs that one-time binding configuration.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
