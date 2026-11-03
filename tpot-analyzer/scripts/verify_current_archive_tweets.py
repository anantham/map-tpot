#!/usr/bin/env python3
"""Build or query a private current-package post index without changing the graph."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.data.post_index import build_post_index
from src.data.post_search import search_posts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--bundle', type=Path, help='verified paired profiles/tweets package to index')
    mode.add_argument('--index', type=Path, help='existing private index to query with a fresh public metadata check')
    parser.add_argument('--output-dir', type=Path, help='new exclusive directory for a build')
    parser.add_argument('--query', help='one to eight words for an existing index')
    args = parser.parse_args()
    if (args.bundle and (not args.output_dir or args.query)) or (args.index and (not args.query or args.output_dir)):
        parser.error('Build requires --bundle/--output-dir; query requires --index/--query')
    try:
        if args.bundle:
            last = [0]
            def progress(event):
                if event['stage'] != 'posts' or event['rows']-last[0] >= 500000:
                    print('✓ Build progress: '+json.dumps(event), flush=True); last[0] = event['rows']
            result = build_post_index(args.bundle, args.output_dir, progress=progress)
            print('✓ Verified source and ready copied index: '+json.dumps(result))
            print('Next: independently review the consumer and verify search in Review before changing its binding.')
        else:
            result = search_posts(args.index, args.query)
            if result['status'] != 'available':
                print('✗ Source hidden, not zero matches: '+json.dumps(result['source'])); return 1
            print('✓ Current-source search: '+json.dumps({'total': result['total'],
                'shown': len(result['results']), 'coverage': result['coverage'], 'seconds': result['seconds'],
                'sampleAccountIds': [row['accountId'] for row in result['results'][:3]]}))
            print('Next: inspect supporting posts and contact routes in Review; word matches are not membership.')
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(f'✗ Post index refused: {type(error).__name__}: {error}')
        print('Next: inspect the failed input; preserve incomplete outputs and use a fresh output directory for a repaired build.')
        return 1
    print('Boundary: no original graph/tag writes, no paid acquisition or outreach. Query mode checks fixed public metadata only.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
