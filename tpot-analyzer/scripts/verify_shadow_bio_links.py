#!/usr/bin/env python3
"""Copy/backfill already-saved historical bio-link claims. No fetching/adoption.

Original graph, sources, tags and rollback stay untouched. The caller explicitly
adopts only after source/synthetic review and real source inspection.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.data.local_graph_batch import build_local_graph_batch
from src.data.shadow_aliases import project_shadow_bio_links


def build_shadow_bio_link_batch(source_graph, output):
    """Derive URL mentions from retained profile fields, never current identity."""
    result=build_local_graph_batch(source_graph,output,[],project_shadow_bio_links)
    if not result['bioLinkObservations']:
        raise ValueError('No new historical bio URL mentions; prior graph unchanged')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-graph',type=Path,required=True)
    parser.add_argument('--output-db',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=build_shadow_bio_link_batch(args.source_graph,args.output_db)
        fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    except (OSError,ValueError,sqlite3.Error) as error:
        print(f'✗ Historical bio-link batch refused: {type(error).__name__}: {error}')
        return 1
    print(f"✓ Stored historical profile observations={result['historicalProfileObservations']}; new bio URL mentions={result['bioLinkObservations']}")
    print(f"✓ Graph before={result['before']}; after={result['after']}")
    print('✓ Prior rows retained; repeated projection unchanged; integrity/foreign keys pass; source identities unchanged')
    print('✓ Literal text, assumed HTTPS, original capture time and source field retained; no identity/contact promotion')
    print('Next: review code/synthetic tests, inspect added source claims, then explicitly adopt this private graph. No live switch occurred.')
    return 0


if __name__=='__main__':raise SystemExit(main())
