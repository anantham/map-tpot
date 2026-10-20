#!/usr/bin/env python3
"""Copy/verify source-bound saved page clues;no fetching or live adoption."""
import argparse,json,os,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.data.local_graph_batch import build_local_graph_batch
from src.data.page_contact_clues import project_page_contact_clues


def build_page_contact_batch(source_graph,output):
    result=build_local_graph_batch(source_graph,output,[],project_page_contact_clues)
    if not result['pageContactObservations']:raise ValueError('No new saved page contact clues;prior graph unchanged')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-graph',type=Path,required=True)
    parser.add_argument('--output-db',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=build_page_contact_batch(args.source_graph,args.output_db)
        fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    except (OSError,ValueError,sqlite3.Error) as error:
        print(f'✗ Page contact batch refused: {type(error).__name__}: {error}');return 1
    print(f"✓ Qualified page bindings={result['qualifiedPageBindings']};captured pages={result['capturedPages']};legacy bindings deferred={result['legacyBindingsDeferred']}")
    print(f"✓ New literal page-contact observations={result['pageContactObservations']};not reviewed personal routes")
    print(f"✓ Graph before={result['before']};after={result['after']}")
    print('✓ Prior rows/repeat/FKs/integrity/source identities pass;raw sources and tags untouched')
    print('Next: review source/synthetic code,compare added source pointers,then adopt privately and inspect Review. No live switch occurred.')
    return 0


if __name__=='__main__':raise SystemExit(main())
