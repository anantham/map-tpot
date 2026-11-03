#!/usr/bin/env python3
"""Build a copied profile-bridge graph; no network, tags or live binding."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.verify_map_data_sources import readonly
from src.data.published_profiles import import_published_profiles, read_profile_bundle


def build_profile_copy(bundle,source_db,output_dir):
    package=read_profile_bundle(bundle)  # Refuse bad source before creating output.
    source_db=Path(source_db).resolve(strict=True); output_dir=Path(output_dir)
    before=hashlib.sha256(source_db.read_bytes()).hexdigest()
    output_dir.mkdir(parents=True,mode=0o700)  # Never reuse an output directory.
    if output_dir.stat().st_mode & 0o077:
        raise ValueError('Profile-copy directory must be private mode0700')
    target=output_dir/'relationships.db'
    descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    with closing(readonly(source_db)) as original, closing(sqlite3.connect(target)) as db:
        original.backup(db); db.execute('PRAGMA foreign_keys=ON')
        journal_mode=original.execute('PRAGMA journal_mode').fetchone()[0]
        original_ids={row[0] for row in original.execute('SELECT relation_id FROM relation')}
        old_profiles={row[0] for row in original.execute("SELECT DISTINCT e.source_key FROM entity e JOIN relation r ON r.subject_id=e.entity_id WHERE r.predicate='profile_observation' AND e.kind='x_account'")}
        with db:result=import_published_profiles(db,bundle,output_dir/'decoded-profiles.json')
        ids={row[0] for row in db.execute("SELECT DISTINCT e.source_key FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE r.snapshot_id=? AND r.predicate='profile_observation' AND e.kind='x_account'",(result['projectionSnapshotId'],))}
        counts={table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('entity','relation','evidence_snapshot')}
        with db:import_published_profiles(db,bundle,output_dir/'decoded-profiles.json')
        after={table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in counts}
        retained={row[0] for row in db.execute('SELECT relation_id FROM relation')}
        if counts!=after or not original_ids<=retained or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Profile-copy repeat-import/retention/foreign-key check failed')
    if hashlib.sha256(source_db.read_bytes()).hexdigest()!=before:
        raise ValueError('Source graph changed during copied import; no live adoption')
    report={**result,'newProfileAccounts':len(ids-old_profiles),'overlappingProfileAccounts':len(ids&old_profiles),
        'profileAccounts':len(ids|old_profiles),'counts':counts,'originalRelationsRetained':len(original_ids),
        'reimportUnchanged':True,'sourceSha256':before,'sourceUnchanged':True,
        'sourceJournalMode':journal_mode,'hashBoundary':'Source main-file bytes; not a WAL-inclusive cryptographic identity.',
        'candidateSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'operationalStatus':'copied_only_not_active',
        'boundary':'Publication-time consent snapshot, not current display eligibility. Live graph/tags unchanged.'}
    with (output_dir/'report.json').open('x') as stream:
        os.chmod(output_dir/'report.json',0o600);json.dump(report,stream,indent=2)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    try:report=build_profile_copy(args.bundle,args.source_db,args.output_dir)
    except (OSError,ValueError,TypeError,sqlite3.Error) as error:
        print(f'✗ Copied profile bridge refused: {type(error).__name__}: {error}. No live binding changed.')
        return 1
    print(f"✓ Published profiles={report['profiles']}; website links={report['websiteLinks']}; export={report['exportId']}")
    print(f"✓ New account IDs={report['newProfileAccounts']}; overlap={report['overlappingProfileAccounts']}; copied universe={report['profileAccounts']}")
    print(f"✓ Counts={report['counts']}; original relations retained={report['originalRelationsRetained']}; repeat import unchanged/FKs valid")
    print('✓ Source graph bytes unchanged; new owner-only copy; no network, tags or live-state writes')
    print('Next: current-source eligibility gate and source-aware Review consumer BEFORE active binding; copied_only_not_active.')
    return 0


if __name__=='__main__':raise SystemExit(main())
