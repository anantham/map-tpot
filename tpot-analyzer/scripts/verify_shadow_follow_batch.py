#!/usr/bin/env python3
"""Build/verify a private additive batch; optionally adopt only its graph.

No fetching, raw-source/tag mutation or Archive visibility override. Previous
release/package/index remain intact. Adoption is explicit, never the default.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.data.shadow_follow_import import import_shadow_follows
from src.data.shadow_aliases import import_shadow_aliases

from src.data.local_graph_batch import build_local_graph_batch, adopt_graph as adopt_graph


def build_shadow_batch(source_graph, shadow, archive, output, *, offset=0, limit=2000, handles=None,alias_rows=False):
    """Compatibility entry point using the shared copied-batch transaction."""
    def importer(db):
        if alias_rows:return import_shadow_aliases(db,shadow,None,offset=offset,limit=limit)
        return (import_shadow_aliases(db, shadow, handles, limit=limit) if handles is not None
                else import_shadow_follows(db, shadow, archive, offset=offset, limit=limit))
    if alias_rows and handles is not None:raise ValueError('Alias-row mode cannot select handles')
    if not alias_rows and archive is None:raise ValueError('Existing shadow mode requires --archive')
    if alias_rows:
        with Path(shadow).open('rb') as stream:source_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    result=build_local_graph_batch(source_graph, output, [shadow] if alias_rows else [shadow,archive], importer)
    if alias_rows:
        with Path(shadow).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=source_sha:raise ValueError('Shadow source changed during row batch')
        result['shadowSourceSha256']=source_sha
    if alias_rows and not result['followObservations']:raise ValueError('No new historical follow observations; prior graph unchanged')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-graph', type=Path, required=True)
    parser.add_argument('--shadow', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--alias-rows',action='store_true',help='offline alias-involving source-row window, not a complete neighborhood')
    parser.add_argument('--output-db', type=Path, required=True)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=2000)
    parser.add_argument('--handle', action='append', help='unresolved handle-only neighborhood; repeat for a bounded batch')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_shadow_batch(args.source_graph, args.shadow, args.archive, args.output_db,
            offset=args.offset, limit=args.limit, handles=args.handle,alias_rows=args.alias_rows)
        fd = os.open(args.report, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(result, stream, indent=2)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f'✗ Shadow batch refused: {type(error).__name__}: {error}')
        return 1
    if args.alias_rows:
        print(f"✓ Selected alias rows={result['selectedRows']}; qualified={result['qualifiedFollowRows']}; new follow observations={result['followObservations']}; profiles={result['aliasProfiles']}")
        print(f"✓ Domain={result['eligibleAliasRowsAtImport']}; self-loops excluded from domain={result['selfRowsExcludedFromDomain']}; next offset={result['nextOffset']}; more={result['hasMore']}")
        print(f"✓ Source version SHA256={result['shadowSourceSha256']}; offsets apply only to this saved store")
        print(f"✓ Source exclusions={result['excludedSourceRows']}; blocked profiles={result['excludedProfileRows']}; missing profiles={result['missingProfileRows']}; partial historical coverage")
    elif args.handle:
        print(f"✓ Selected handle-only rows={result['selectedRows']}; separate shadow observations={result['followObservations']}; alias profiles={result['aliasProfiles']}")
        print(f"✓ Scope={result['scopes']}; source-channel exclusions={result['excludedSourceRows']}; no numeric identity merge")
    else:
        print(f"✓ Selected numeric shadow rows={result['selectedRows']}; qualifying follow observations={result['followObservations']}")
        print(f"✓ Explicit public provider profile observations={result['providerProfiles']}; unprofiled edge exclusions={result['excludedUnprofiledRows']}")
        print(f"✓ Handle-only rows deferred={result['deferredAliasRows']}; no alias merges")
    print(f"✓ Graph before={result['before']}; after={result['after']}")
    if 'bioLinkObservations' in result:
        print(f"✓ New source-backed bio URL mentions={result['bioLinkObservations']}; not identity or checked contact routes")
    print('✓ Prior rows retained; repeat unchanged; integrity/foreign keys pass; source identities unchanged')
    print('Next: independently review changed code, inspect new search paths, then explicitly adopt this graph. No live switch occurred.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
