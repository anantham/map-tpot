#!/usr/bin/env python3
"""Upgrade only a new private copy of a qualified post index; no network."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import shutil
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.data.post_index import verified_post_package
from src.data.post_interactions import build_post_interactions
from src.data.post_search import open_post_index, read_post_metadata


def build_interaction_copy(bundle, index, output_dir, *, progress=None):
    started = time.monotonic()
    package, info, parquet, raw_identity = verified_post_package(bundle)
    source_path = Path(index).resolve(strict=True); before = source_path.stat()
    with open_post_index(source_path) as original:
        source, _ = read_post_metadata(original)
        expected = {'exportId': package['exportId'], 'tweetSha256': info['sha256'],
            'profileSha256': package['rawSource']['profileSha256'],
            'manifestSha256': package['rawSource']['manifestSha256'],
            'rows': info['rows'], 'authors': info['distinct_accounts']}
        if any(source.get(key) != value for key, value in expected.items()):
            raise ValueError('Index and verified source package are not the same pair')
        if original.execute("SELECT 1 FROM meta WHERE key='interactionVersion' AND value='1'").fetchone():
            raise ValueError('This index already has reference paths; use it without rebuilding')
        if original.execute('SELECT count(*) FROM post').fetchone()[0] != info['rows']:
            raise ValueError('Index physical post rows differ from the verified package')
        target = Path(output_dir)
        if shutil.disk_usage(target.parent).free < before.st_size*2:
            raise ValueError('Insufficient free space for a full copied index and projection margin')
        target.mkdir(mode=0o700)
        if target.stat().st_mode & 0o077: raise ValueError('Interaction-copy directory must be private')
        output = target/'posts.db'; descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(descriptor)
        with closing(sqlite3.connect(output)) as db:
            if progress: progress({'stage': 'copying_qualified_index', 'bytes': before.st_size})
            original.backup(db)
            db.execute("INSERT OR REPLACE INTO meta VALUES('interactionVersion','building')"); db.commit()
            with db:
                audit = build_post_interactions(db, parquet, {row['account_id'] for row in package['profiles']}, progress=progress)
                raw_after = (Path(bundle)/'tweets.parquet').stat()
                after = source_path.stat()
                if (raw_identity != (raw_after.st_ino, raw_after.st_size, raw_after.st_mtime_ns)
                        or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns)):
                    raise ValueError('Source changed during projection; copied index must not be adopted')
    report = {'ready': True, 'interactionVersion': 1, **audit, 'rows': info['rows'],
        'authors': info['distinct_accounts'], 'bytes': output.stat().st_size,
        'seconds': round(time.monotonic()-started, 3), 'originalIndexUnchanged': True,
        'operationalStatus': 'copied_index_not_active'}
    descriptor = os.open(target/'interaction-report.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream: json.dump(report, stream, indent=2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='new private output; never overwritten')
    args = parser.parse_args(); last = {}
    def progress(event):
        stage = event['stage']; rows = event.get('rows', 0)
        if not rows or rows-last.get(stage, 0) >= 500000:
            print('✓ Progress: '+json.dumps(event), flush=True); last[stage] = rows
    try: result = build_interaction_copy(args.bundle, args.index, args.output_dir, progress=progress)
    except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error) as error:
        print(f'✗ Reference projection refused: {type(error).__name__}: {error}')
        print('Next: preserve the incomplete copy and investigate; do not adopt it. Original index/tags unchanged.')
        return 1
    print('✓ Qualified copied reference index: '+json.dumps(result, sort_keys=True))
    print('Next: independently review and verify typed paths, then explicitly adopt this seed via the managed refresh command.')
    print('Boundary: local source only; no original-store/tag writes, paid request or outreach.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
