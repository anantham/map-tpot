#!/usr/bin/env python3
"""Build/verify a private saved-thread batch; no network calls or auto-adoption."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.data.local_graph_batch import build_local_graph_batch
from src.data.saved_thread_posts import import_saved_thread_observations


def build_thread_post_batch(source_graph, archive, output, *, limit=500):
    return build_local_graph_batch(source_graph, output, [archive],
        lambda db: import_saved_thread_observations(db, archive, limit=limit))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-graph', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output-db', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=500)
    args = parser.parse_args()
    try:
        report = build_thread_post_batch(args.source_graph, args.archive, args.output_db, limit=args.limit)
        fd = os.open(args.report, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream: json.dump(report, stream, indent=2)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f'✗ Saved thread batch refused: {type(error).__name__}: {error}'); return 1
    print(f"✓ Selected {report['selectedRows']}/{report['totalRowsAtImport']} cached threads; truncated={report['truncated']}")
    print(f"✓ Qualified posts={report['apiPosts']}; observations={report['postObservations']}; authors={report['providerAccounts']}")
    print(f"✓ Structured references={report['referenceTypes']}; self references={report['selfReferences']}")
    print(f"✓ Excluded posts={report['excludedPosts']}; restricted references={report['excludedReferences']}; unresolved mentions={report['unresolvedMentions']}; unresolved quotes={report['unresolvedQuotes']}")
    print(f"✓ Graph before={report['before']}; after={report['after']}")
    print('✓ Prior rows retained; repeat unchanged; integrity/FKs pass; raw source identities unchanged')
    print('Next: review a real new query and quote/mention evidence, independently review, then adopt. No live switch occurred.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
