#!/usr/bin/env python3
"""Build a fresh private October profile/work sidecar; no network or live writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.verify_map_relationship_pilot import SCHEMA, import_snapshot
from src.data.saved_capture_import import import_saved_capture, import_saved_contacts, CaptureWriter, project_work_attributes, WORK_TEXT, public_url
from src.data.saved_follow_import import import_saved_follows
from src.data.local_graph_batch import build_local_graph_batch
from src.data.contact_catalog import import_contact_catalog
from src.data.published_profile_access import SOURCE_KIND
from src.data.research_source_links import project_research_sources


def build_saved_capture(capture, batches, pilot, output, *, contact_paths=None, follow_runs=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.stat().st_mode & 0o077:
        raise ValueError('Output directory must be private (mode0700)')
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(output)) as db:
            db.executescript(SCHEMA)
            import_snapshot(db, pilot)  # Keep the reviewed website/contact evidence.
            with db:
                result = import_saved_capture(db, capture, batches)
                if contact_paths is not None:
                    if not contact_paths:
                        raise ValueError('Requested contact import has no source files')
                    result.update(import_saved_contacts(db, contact_paths))
                if follow_runs is not None:
                    result.update(import_saved_follows(db, follow_runs))
            counts = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                      for table in ('entity', 'relation', 'evidence_snapshot')}
            with db:
                import_saved_capture(db, capture, batches)
                if contact_paths is not None:
                    import_saved_contacts(db, contact_paths)
                if follow_runs is not None:
                    import_saved_follows(db, follow_runs)
            after = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                     for table in counts}
            if counts != after or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Repeat-import/provenance check failed')
            profiled = db.execute("SELECT count(DISTINCT subject_id) FROM relation WHERE predicate='profile_observation'").fetchone()[0]
            return {**result, 'profileAccounts': profiled, 'counts': counts, 'ready': True, 'reimportUnchanged': True}
    except BaseException:
        output.unlink(missing_ok=True)  # Only the fresh file created above.
        raise


def build_work_repair_batch(source,output):
    """Append complete projections of already-retained source records on a copy."""
    def repair(db):
        db.row_factory=sqlite3.Row
        rows=db.execute("SELECT r.*,e.kind,e.source_key account_id,t.kind target_kind,t.source_key url,s.payload FROM relation r "
            "JOIN entity e ON e.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id "
            "JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id WHERE r.predicate='research_associates_with' "
            "ORDER BY CASE WHEN json_extract(r.attributes_json,'$.workProjectionVersion')=2 THEN 1 ELSE 0 END DESC,r.relation_id").fetchall()
        seen=set();before=len(rows);recovered=0;w=CaptureWriter(db)
        for row in rows:
            key=(row['snapshot_id'],row['source_pointer'])
            if key in seen:continue
            seen.add(key)
            pointer=re.fullmatch(r'/cards/(0|[1-9][0-9]*)/artifact',row['source_pointer'])
            if not pointer:raise ValueError('Retained work pointer is outside the supported card contract')
            payload=json.loads(row['payload'])
            try:card=payload['cards'][int(pointer[1])]
            except (KeyError,IndexError,TypeError) as error:raise ValueError('Retained work source record cannot be resolved') from error
            if not isinstance(card,dict) or row['kind']!='x_account' or card.get('account_id')!=row['account_id']:
                raise ValueError('Retained work account identity disagrees with its source record')
            attrs=project_work_attributes(card.get('artifact'));old=json.loads(row['attributes_json'])
            if (attrs['title']!=old.get('title') or attrs['url']!=old.get('url')
                    or row['target_kind']!='web_resource' or public_url(attrs['url'])!=row['url']):
                raise ValueError('Retained work title or URL disagrees with its source record')
            if {k:v for k,v in attrs.items() if k!='workProjectionVersion'}=={k:v for k,v in old.items() if k!='workProjectionVersion'}:continue
            has=lambda value:any(isinstance(value.get(k),str) and value[k].strip() for k in WORK_TEXT)
            recovered+=not has(old) and has(attrs)
            w.relation(row['subject_id'],'research_associates_with',row['object_id'],
                row['snapshot_id'],row['source_pointer'],row['observed_at'],attrs)
        after=db.execute("SELECT count(*) FROM relation WHERE predicate='research_associates_with'").fetchone()[0]
        return {'sourceRecords':len(seen),'workObservations':after-before,'recoveredBodies':recovered}
    result=build_local_graph_batch(source,output,[],repair)
    if not result['workObservations']:raise ValueError('No incomplete retained work projections remain; source unchanged')
    return result


def build_contact_catalog_batch(source,catalog,witness,output):
    result=build_local_graph_batch(source,output,[catalog],lambda db:import_contact_catalog(db,catalog,witness))
    if not result['channelMentions']:raise ValueError('No new channel mentions; empty exports cannot establish readiness')
    return result


def build_saved_work_batch(source,capture,work_sources,output):
    """Explicit original cards,with a retained frozen numeric-ID/handle witness."""
    def append(db):
        db.row_factory=sqlite3.Row
        raw=Path(capture).read_bytes();sid=hashlib.sha256(raw).hexdigest()
        retained=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(sid,)).fetchone()
        if retained is None or retained[0]!=raw:raise ValueError('Work import requires the exact already-retained profile capture')
        profiles=json.loads(raw)
        if not isinstance(profiles,list) or not profiles:raise ValueError('Frozen profile capture must be nonempty')
        known={}
        for n,profile in enumerate(profiles):
            if (not isinstance(profile,dict) or not isinstance(profile.get('account_id'),str)
                    or not re.fullmatch('[0-9]+',profile['account_id']) or profile['account_id'] in known
                    or not isinstance(profile.get('handle'),str)):
                raise ValueError('Frozen work profile identity is invalid')
            known[profile['account_id']]=(profile['handle'],f'/{n}')
        bindings={}
        for row in db.execute("""SELECT r.*,e.source_key account_id FROM relation r
          JOIN entity e ON e.entity_id=r.subject_id WHERE r.snapshot_id=?
          AND r.predicate='profile_observation' AND e.kind='x_account'""",(sid,)):
            attrs=json.loads(row['attributes_json']);aid=row['account_id']
            if (aid in known and attrs.get('sourceKind')!=SOURCE_KIND
                    and known[aid]==(attrs.get('handle'),row['source_pointer'])):
                if aid in bindings:raise ValueError('Frozen work profile witness is ambiguous')
                bindings[aid]=row['subject_id']
        writer=CaptureWriter(db);before=db.execute("SELECT count(*) FROM relation WHERE predicate='research_associates_with'").fetchone()[0]
        processed=0
        for path in work_sources:
            snapshot,payload=writer.source(path);cards=payload.get('cards') if isinstance(payload,dict) else None
            if not isinstance(cards,list) or not cards:raise ValueError('Explicit work source requires nonempty cards')
            for n,card in enumerate(cards):
                aid=card.get('account_id') if isinstance(card,dict) else None
                if (aid not in bindings or not isinstance(card.get('handle'),str)
                        or card['handle'].casefold()!=known[aid][0].casefold()):
                    raise ValueError('Work card numeric identity/handle disagrees with frozen capture')
                if card.get('artifact') is None:continue
                attrs=project_work_attributes(card['artifact'])
                if not any(isinstance(attrs.get(k),str) and attrs[k].strip() for k in WORK_TEXT):
                    raise ValueError('Work card has no substantive saved passage')
                caveats=card.get('caveats',[])
                if not isinstance(caveats,list) or any(not isinstance(v,str) for v in caveats):
                    raise ValueError('Work card caveats must be a list of text qualifications')
                if 'caveats' in card:attrs.update(caveats=caveats,caveats_source=f'/cards/{n}/caveats')
                writer.relation(bindings[aid],'research_associates_with',writer.entity('web_resource',public_url(attrs['url'])),
                    snapshot,f'/cards/{n}/artifact',None,attrs)
                processed+=1
        after=db.execute("SELECT count(*) FROM relation WHERE predicate='research_associates_with'").fetchone()[0]
        return {'workObservations':after-before,'processedWorkCards':processed,'profileWitnessSnapshotId':sid}
    result=build_local_graph_batch(source,output,[capture,*work_sources],append)
    if not result['workObservations']:raise ValueError('No new explicit saved work observations; source unchanged')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--batch-dir', type=Path)
    parser.add_argument('--pilot', type=Path)
    parser.add_argument('--output-db', type=Path, required=True)
    parser.add_argument('--contact-dir', type=Path, help='optional saved public route reviews; includes the first non-batch file')
    parser.add_argument('--follow-run', type=Path, action='append', help='saved public follow capture root; repeat for continuations')
    parser.add_argument('--repair-work-from-snapshots',action='store_true',help='append corrected retained work projections on a graph copy')
    parser.add_argument('--source-graph',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--contact-catalog',type=Path,help='offline unverified saved-channel catalogue; no private lookup fields projected')
    parser.add_argument('--profile-witness',help='exact retained original profile-capture snapshot ID')
    parser.add_argument('--work-source',type=Path,action='append',help='explicit saved cards file(s),including cards.json;copied graph only')
    parser.add_argument('--research-source-snapshot',action='append',help='retained work snapshot whose cited URLs should be connected;repeat for one atomic copied batch')
    args = parser.parse_args()
    try:
        if args.research_source_snapshot:
            if (args.work_source or args.capture or args.batch_dir or args.pilot or args.contact_dir or args.follow_run
                    or args.repair_work_from_snapshots or args.contact_catalog or args.profile_witness):
                raise ValueError('Research-source mode cannot be mixed with other import modes')
            if not args.source_graph or not args.report:raise ValueError('Research sources require source graph and report')
            if args.report.parent.resolve()!=args.output_db.parent.resolve():raise ValueError('Report must share private output directory')
            if len(set(args.research_source_snapshot))!=len(args.research_source_snapshot):
                raise ValueError('Duplicate research source snapshot selection')
            def append_citations(db):
                reports=[project_research_sources(db,sid) for sid in args.research_source_snapshot]
                return reports[0] if len(reports)==1 else {
                    'researchSourceObservations':sum(r['researchSourceObservations'] for r in reports),
                    'sourceReports':reports}
            result=build_local_graph_batch(args.source_graph,args.output_db,[],append_citations)
            if not result['researchSourceObservations']:raise ValueError('No new research source citations;source unchanged')
            fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
            print(f"✓ Research citations={result['researchSourceObservations']};selected snapshots={len(args.research_source_snapshot)};per-source counts retained in report")
            print(f"✓ Before={result['before']};after={result['after']};prior rows/raw identity/repeat/FKs/integrity pass")
            print('✓ Cited sources,not verified identities,owned profiles,employment,contacts or new fetching')
            print('Next:source-check all added links,review,then verify exact-URL lookup and the account citation disclosure.')
            return 0
        if args.work_source:
            if (args.repair_work_from_snapshots or args.contact_catalog or args.profile_witness
                    or args.batch_dir or args.pilot or args.contact_dir or args.follow_run):
                raise ValueError('Explicit work-source mode cannot be mixed with other import modes')
            if not args.source_graph or not args.capture or not args.report:
                raise ValueError('Explicit work source requires source graph,retained profile capture and report')
            if args.report.parent.resolve()!=args.output_db.parent.resolve():raise ValueError('Work report must share private output directory')
            result=build_saved_work_batch(args.source_graph,args.capture,args.work_source,args.output_db)
            fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
            print(f"✓ Explicit cards={result['processedWorkCards']};new saved work observations={result['workObservations']}")
            print(f"✓ Before={result['before']};after={result['after']};prior rows/raw identities retained;repeat/FKs/integrity pass")
            print('✓ Saved research associations only;card caveats/evidence URL retained;no profiles,identity merge,tags,fetching or outreach')
            print('Next:reconcile added source paths,review,then verify search and account work evidence in private Review.')
            return 0
        if args.contact_catalog:
            if (args.repair_work_from_snapshots or args.capture or args.batch_dir or args.pilot
                    or args.contact_dir or args.follow_run):raise ValueError('Channel catalogue mode cannot be combined with other import modes')
            if not args.source_graph or not args.profile_witness or not args.report:
                raise ValueError('Channel catalogue requires source graph,profile witness and private report')
            if args.report.parent.resolve()!=args.output_db.parent.resolve():raise ValueError('Catalogue report must share the private output directory')
            result=build_contact_catalog_batch(args.source_graph,args.contact_catalog,args.profile_witness,args.output_db)
            fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
            print(f"✓ Bound catalogue entries={result['catalogEntries']}; new entry observations={result['newCatalogEntries']}; new literal mentions={result['channelMentions']}")
            print(f"✓ Graph before={result['before']}; after={result['after']}; prior rows/raw identities retained; repeat/integrity/FKs pass")
            print('✓ Unverified historical mentions; no current identity/ownership/contact validation,private lookup projection,fetching,tags or outreach')
            print('Next: source-check every added path,review,then inspect the bounded catalogue disclosure in private Review before adoption is delivered.')
            return 0
        if args.profile_witness:raise ValueError('Profile witness is only valid with channel catalogue mode')
        if args.repair_work_from_snapshots:
            if not args.source_graph or not args.report:raise ValueError('Work repair requires --source-graph and --report')
            if args.report.parent.resolve()!=args.output_db.parent.resolve():raise ValueError('Repair report must share the private output directory')
            result=build_work_repair_batch(args.source_graph,args.output_db)
            fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
            print(f"✓ Retained source records={result['sourceRecords']}; corrected projections={result['workObservations']}; recovered empty bodies={result['recoveredBodies']}")
            print(f"✓ Graph before={result['before']}; after={result['after']}; original rows retained; repeat/integrity/FKs pass")
            print('✓ No new works claimed, raw/source/tag mutation, fetching or live adoption')
            print('Next: review corrected search/dossier passages and source context before graph-only adoption.')
            return 0
        if not all((args.capture,args.batch_dir,args.pilot)):raise ValueError('Capture build requires --capture, --batch-dir and --pilot')
        contact_paths = list(args.contact_dir.glob('contact-route-reviews-*.json')) if args.contact_dir else None
        result = build_saved_capture(args.capture, list(args.batch_dir.glob('batch-*.json')), args.pilot, args.output_db, contact_paths=contact_paths, follow_runs=args.follow_run)
    except (OSError, ValueError, TypeError, sqlite3.Error) as error:
        detail = str(error) if type(error) is ValueError else type(error).__name__
        print(f'✗ Saved evidence build refused: {detail}. Existing files preserved.')
        return 1
    print(f"✓ Profile accounts={result['profileAccounts']}; saved work observations={result['workObservations']}")
    if args.contact_dir:
        print(f"✓ Sourced contact routes={result['contactRoutes']} across{result['contactReviews']} reviews; incomplete checks={result['incompleteChecks']}")
    print(f"✓ Source-backed counts={result['counts']}; repeat import unchanged; foreign keys valid")
    if args.follow_run:
        print(f"✓ Directed follow observations={result['followObservations']} from{result['followSources']} sources; out-of-scope rows excluded={result['excludedFollowObservations']}")
    print('✓ Fresh owner-only file; raw bytes retained; no network, tags or outreach writes')
    print('Next: verify local search → exact-account dossier before private runtime adoption.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
