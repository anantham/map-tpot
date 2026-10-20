#!/usr/bin/env python3
"""Build/verify a private saved-API batch; never fetch or auto-adopt."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.data.local_graph_batch import build_local_graph_batch
from src.data.saved_api_posts import import_api_post_observations, import_api_timeline_posts


def build_api_post_batch(source_graph, archive, output, *, limit=1000, source_mode='typed'):
    if source_mode not in ('typed', 'timeline'): raise ValueError('API batch source mode must be typed or timeline')
    importer = import_api_timeline_posts if source_mode == 'timeline' else import_api_post_observations
    return build_local_graph_batch(source_graph, output, [archive],
        lambda db: {**importer(db, archive, limit=limit), 'sourceMode': source_mode})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-graph', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output-db', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--source-mode', choices=('typed', 'timeline'), default='typed',
        help='typed requires saved edges; timeline admits independently saved text without inferring edges')
    args = parser.parse_args()
    try:
        report = build_api_post_batch(args.source_graph, args.archive, args.output_db, limit=args.limit, source_mode=args.source_mode)
        fd = os.open(args.report, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream: json.dump(report, stream, indent=2)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f'✗ API post batch refused: {type(error).__name__}: {error}')
        return 1
    print(f"✓ Selected {report['selectedRows']}/{report['totalRowsAtImport']} rows; truncated={report['truncated']}")
    print(f"✓ Saved API posts={report['apiPosts']}; typed references={report['typedReferences']}; self references={report['selfReferences']}")
    print(f"✓ Explicit-public provider observations={report.get('providerProfiles',0)}; excluded rows={len(report['exclusions'])}")
    if report['sourceMode'] == 'timeline':
        print(f"✓ Newly added post observations={report['postObservationsAdded']}; source counts={report['selectedSourceCounts']}")
        print(f"✓ Other origins remain separate={report['excludedSourceCounts']}; handle-only references are not new edges")
    print(f"✓ Graph before={report['before']}; after={report['after']}")
    print('✓ Prior rows retained; repeat unchanged; integrity/FKs pass; raw source identities unchanged')
    print('Next: inspect real combined search/post/reference evidence; independently review, then adopt. No live switch occurred.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
