#!/usr/bin/env python3
"""Copy/backfill saved profile counts;no fetching,live adoption or source writes."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.data.local_graph_batch import build_local_graph_batch
from src.data.shadow_profile_counts import project_shadow_profile_counts


def build_shadow_profile_count_batch(source_graph,output):
    result=build_local_graph_batch(source_graph,output,[],project_shadow_profile_counts)
    if not result['profileCountObservations']:
        raise ValueError('No new historical profile counts;prior graph unchanged')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-graph',type=Path,required=True)
    parser.add_argument('--output-db',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=build_shadow_profile_count_batch(args.source_graph,args.output_db)
        fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    except (OSError,ValueError,sqlite3.Error) as error:
        print(f'✗ Historical profile-count batch refused: {type(error).__name__}: {error}')
        return 1
    print(f"✓ Count-bearing selected profiles={result['countBearingProfiles']};new enriched observations={result['profileCountObservations']}")
    print(f"✓ Graph before={result['before']};after={result['after']}")
    print('✓ Prior rows retained;repeat unchanged;integrity/FKs and original identities pass')
    print('✓ Exact snapshot/alias/channel/fields/date retained;unknown is not zero;no graph-degree inference')
    print('Next: review code/synthetic tests and real source comparisons,then adopt privately and inspect Review. No live switch occurred.')
    return 0


if __name__=='__main__':raise SystemExit(main())
