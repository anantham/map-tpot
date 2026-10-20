#!/usr/bin/env python3
"""Build a fresh copied cached-website graph; originals and active binding stay intact."""
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
from src.data.cached_website_import import project_cached_websites, project_stored_profile_bio_links, project_stored_publisher_links
from src.data.published_profile_access import load_published_profile_access
from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_provider_profiles import import_saved_provider_profiles,project_stored_provider_links
from src.data.local_graph_batch import build_local_graph_batch
from scripts.verify_map_data_sources import readonly


def build_website_copy(source_db,archive,account_ids,output_dir,*,published_access,provider_account_ids=None):
    source_db=Path(source_db).resolve(strict=True)
    if source_db.stat().st_mode & 0o077:raise ValueError('Source graph must be private')
    archive=Path(archive).resolve(strict=True)
    if not isinstance(account_ids,list) or not 1<=len(account_ids)<=20000:
        raise ValueError('Copied website build requires1–20000 exact accounts')
    before=hashlib.sha256(source_db.read_bytes()).hexdigest()
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,mode=0o700)
    if output_dir.stat().st_mode & 0o077:raise ValueError('Output directory must be private')
    target=output_dir/'relationships.db'
    descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    with closing(readonly(source_db)) as original,closing(sqlite3.connect(target)) as db:
        original.backup(db);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        old_ids={r[0] for r in db.execute('SELECT relation_id FROM relation')}
        with db:
            provider=import_saved_provider_profiles(db,archive,provider_account_ids) if provider_account_ids is not None else None
            if provider is not None and provider['profiles']==0:raise ValueError('No source-qualified provider profiles; old pages cannot satisfy this pilot')
            selected=sorted(set(account_ids)|set(provider['projectedAccountIds'] if provider else []))
            bio_projection=project_stored_profile_bio_links(db,published_access=published_access)
            result=project_cached_websites(db,archive,selected,published_access=published_access)
        if result['pages']==0:raise ValueError('No projectable pages; copied pilot is not ready')
        counts={t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('entity','relation','evidence_snapshot')}
        with db:
            if provider_account_ids is not None:import_saved_provider_profiles(db,archive,provider_account_ids)
            project_stored_profile_bio_links(db,published_access=published_access)
            project_cached_websites(db,archive,selected,published_access=published_access)
        if counts!={t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in counts}:
            raise ValueError('Repeat import changed copied counts')
        if not old_ids<={r[0] for r in db.execute('SELECT relation_id FROM relation')} or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Source retention or foreign-key check failed')
    if hashlib.sha256(source_db.read_bytes()).hexdigest()!=before:raise RuntimeError('Source graph changed during copy')
    result.update(counts=counts,bioLinkProjection=bio_projection,sourceSha256=before,sourceUnchanged=True,reimportUnchanged=True,
                  operationalStatus='copied_only_not_active',ready=True)
    if provider is not None:result['providerProfiles']=provider
    descriptor=os.open(output_dir/'report.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w') as stream:json.dump(result,stream,indent=2)
    return result


def build_provider_evidence_batch(source_db,archive,account_ids,output_dir):
    """Offline copied batch: existing independent provider/page contracts only."""
    output_dir=Path(output_dir)
    def project(db):
        def count(predicate):
            return db.execute('SELECT count(*) FROM relation WHERE predicate=?',(predicate,)).fetchone()[0]
        profiles_before,pages_before=count('profile_observation'),count('website_observed_for')
        provider=import_saved_provider_profiles(db,archive,account_ids)
        if provider['profiles']==0:raise ValueError('No source-qualified provider profiles; prior pages cannot satisfy this batch')
        pages=project_cached_websites(db,archive,provider['projectedAccountIds'],
            published_access=PublishedProfileAccess('unchecked'))
        return {'providerProfiles':provider,'websiteProjection':pages,
            'providerProfileObservations':count('profile_observation')-profiles_before,
            'websiteObservations':count('website_observed_for')-pages_before,
            'sourcePolicy':'independent_provider_only_archive_unchecked'}
    result=build_local_graph_batch(source_db,output_dir/'relationships.db',[archive],project)
    if not (result['providerProfileObservations'] or result['websiteObservations']):
        raise ValueError('No new provider profile or website observations; existing evidence is unchanged')
    descriptor=os.open(output_dir/'report.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w') as stream:json.dump(result,stream,indent=2)
    return result


def build_cached_page_batch(source_db,archive,account_ids,output_dir):
    """Re-extract existing independent pages offline,without profile import."""
    def project(db):
        before=db.execute("SELECT count(*) FROM relation WHERE predicate='website_observed_for'").fetchone()[0]
        access=PublishedProfileAccess('unchecked')
        pages=project_cached_websites(db,archive,account_ids,published_access=access)
        if not pages['pages']:raise ValueError('No source-qualified cached pages; this is not a contact-negative result')
        publisher=project_stored_publisher_links(db,account_ids,published_access=access)
        return {'websiteProjection':pages,'publisherLinkProjection':publisher,
            'websiteObservations':db.execute("SELECT count(*) FROM relation WHERE predicate='website_observed_for'").fetchone()[0]-before,
            'pageContactObservations':pages['pageContactObservations'],
            'publisherLinkObservations':publisher['publisherLinkObservations'],
            'sourcePolicy':'independent_cached_pages_only_archive_unchecked'}
    output_dir=Path(output_dir)
    result=build_local_graph_batch(source_db,output_dir/'relationships.db',[archive],project)
    if not any(result[k] for k in ('websiteObservations','pageContactObservations','publisherLinkObservations')):
        raise ValueError('No new cached page evidence; existing observations cannot satisfy this batch')
    fd=os.open(output_dir/'report.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('source-db','output-dir'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--accounts-json',type=Path)
    parser.add_argument('--stored-provider-links',action='store_true',help='offline copied projection of retained public-provider URL fields only')
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--stored-publisher-links',action='store_true',help='offline copied projection of retained publisher URL claims')
    parser.add_argument('--saved-provider-accounts-json',type=Path,help='opt-in exact saved provider-profile selection, no legacy fallback')
    parser.add_argument('--independent-provider-only',action='store_true',help='offline provider/page batch; no Archive publication read or fallback')
    parser.add_argument('--independent-cached-pages',action='store_true',help='offline saved-page extraction only; no profile import or publication request')
    args=parser.parse_args()
    try:
        if args.stored_provider_links:
            if any((args.archive,args.accounts_json,args.stored_publisher_links,args.independent_provider_only,
                    args.saved_provider_accounts_json,args.independent_cached_pages)):
                raise ValueError('Stored provider links cannot be combined with selections, caches or other import modes')
            result=build_stored_provider_link_batch(args.source_db,args.output_dir)
            print(f"✓ Retained provider profiles={result['profiles']}; new literal URL observations={result['bioLinkObservations']}")
            print(f"✓ Graph before={result['before']}; after={result['after']}; old rows/snapshots retained; repeat/integrity/FKs pass")
            print('✓ Copied offline only; no cache/publication reads, new profiles, identity/contact promotion, tags, fetching or outreach')
            print('Next: reconcile original URL fields,review,then inspect exact lookup and source dates before graph-only adoption.')
            return 0
        if not args.accounts_json:raise ValueError('This import mode requires --accounts-json')
        selection=json.loads(args.accounts_json.read_bytes())
        if not isinstance(selection,list) or any(not isinstance(r,dict) for r in selection):
            raise ValueError('Selection must be a fixed account list')
        if args.stored_publisher_links:
            if args.independent_provider_only or args.saved_provider_accounts_json or args.independent_cached_pages:
                raise ValueError('Stored publisher links cannot be combined with acquisition/import modes')
            result=build_publisher_link_batch(args.source_db,[r['accountId'] for r in selection],args.output_dir)
            print(f"✓ New publisher link observations={result['publisherLinkObservations']}; pages={result['pagesWithClaims']}; name-only organisation claims retained as notes={result['nameOnlyOrganisationClaims']}")
            print(f"✓ Graph before={result['before']}; after={result['after']}; old rows/source bytes retained; repeat/integrity/FKs pass")
            print('✓ Offline independent sources; no identity/job/contact promotion, fetching, tags, outreach or active switch')
            print('Next: inspect typed path meaning and original page/script fields before graph-only adoption.')
            return 0
        if not args.archive:raise ValueError('Website/provider import requires --archive')
        if args.independent_cached_pages:
            if args.independent_provider_only or args.saved_provider_accounts_json:
                raise ValueError('Independent cached pages cannot import provider profiles')
            result=build_cached_page_batch(args.source_db,args.archive,[r['accountId'] for r in selection],args.output_dir)
            pages=result['websiteProjection']
            print(f"✓ Re-extracted qualified pages={pages['pages']}; new website observations={result['websiteObservations']}; new page-contact observations={result['pageContactObservations']}")
            print(f"✓ New publisher URL-claim observations={result['publisherLinkObservations']}; not verified identity or employment")
            print(f"✓ Unmatched cache rows={pages['unmatchedCacheRows']}; missing HTML={pages['missingHtmlPages']}; these are coverage gaps")
            print(f"✓ Graph before={result['before']}; after={result['after']}; prior rows/source identities retained; repeat/integrity/FKs pass")
            print('✓ Offline copy only; no profile import, publication request, source/tag mutation, fetching or outreach')
            print('Next: compare all additions to retained HTML/dates,review,then adopt privately and inspect Review. Old binding unchanged.')
            return 0
        if args.independent_provider_only:
            if args.saved_provider_accounts_json:
                raise ValueError('Independent mode uses --accounts-json for its provider selection')
            result=build_provider_evidence_batch(args.source_db,args.archive,
                [r['accountId'] for r in selection],args.output_dir)
            provider,pages=result['providerProfiles'],result['websiteProjection']
            print(f"✓ Saved public provider profiles={provider['profiles']}; source exclusions={len(provider['exclusions'])}")
            print(f"✓ New profile observations={result['providerProfileObservations']}; website associations={result['websiteObservations']}")
            print(f"✓ Qualified cache pages={pages['pages']}; links={pages['linkObservations']}; email clues={pages['emailClues']}; form markup={pages['messageForms']}")
            print(f"✓ Unmatched cache rows={pages['unmatchedCacheRows']}; missing HTML={pages['missingHtmlPages']}; not negative contact findings")
            print(f"✓ Graph before={result['before']}; after={result['after']}; prior rows/source identities retained; repeat/integrity/FKs pass")
            print('✓ No publication request, Archive promotion, raw/tag mutation, fetching or outreach; independent sources only')
            print('Next: review source-qualified new search/dossier evidence before explicit graph-only adoption.')
            return 0
        access=load_published_profile_access(args.source_db)
        if access.status not in ('available','not_present'):
            raise RuntimeError('Current source eligibility is unavailable; do not infer empty coverage')
        provider_ids=None
        if args.saved_provider_accounts_json:
            rows=json.loads(args.saved_provider_accounts_json.read_bytes())
            if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Provider selection must be an account list')
            provider_ids=[r['accountId'] for r in rows]
        result=build_website_copy(args.source_db,args.archive,[r['accountId'] for r in selection],
                                  args.output_dir,published_access=access,provider_account_ids=provider_ids)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error) as error:
        detail=str(error) if type(error) in (ValueError,RuntimeError) else type(error).__name__
        print(f'✗ Copied website graph refused: {detail}. Prior stores/binding unchanged; incomplete copy retained.')
        return 1
    print(f"✓ Selected accounts={result['selectionAccounts']}; cache page observations={result['pages']}; qualifying associations={result['associations']}")
    print(f"✓ Source-visible profile observations={result['bioLinkProjection']['visibleProfileObservations']}; literal bio URL observations={result['bioLinkProjection']['bioLinkObservations']}")
    if 'providerProfiles' in result:
        provider=result['providerProfiles'];print(f"✓ Saved provider profiles={provider['profiles']}; excluded={len(provider['exclusions'])}; reasons retained privately, not contact negatives")
    print(f"✓ Link observations={result['linkObservations']}; redirects={result['redirects']}; listed email clues={result['emailClues']}; form markup={result['messageForms']}")
    print(f"✓ Publisher self-links={result['publicSelfLinkClues']}; page-subject claims={result['pageSubjectClaims']}; reported employer clues={result['employmentClues']}; not verified people/current jobs")
    print(f"✓ Unmatched cache rows={result['unmatchedCacheRows']}; missing page bytes={result['missingHtmlPages']}; these are coverage gaps")
    print(f"✓ Counts={result['counts']}; source retained; repeat import unchanged; foreign keys valid")
    print('✓ Owner-only copy; no tag/outreach/source mutation or live binding adoption; no paid call')
    print('Next: verify website-only query → exact account and source paths before managed private adoption.')
    return 0


def build_publisher_link_batch(source_db,account_ids,output_dir):
    """Materialize already-retained independent claims; leave old binding intact."""
    output_dir=Path(output_dir)
    result=build_local_graph_batch(source_db,output_dir/'relationships.db',[],
        lambda db:project_stored_publisher_links(db,account_ids,published_access=PublishedProfileAccess('unchecked')))
    if not result['publisherLinkObservations']:raise ValueError('No new publisher link observations; source unchanged')
    fd=os.open(output_dir/'report.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    return result


def build_stored_provider_link_batch(source_db,output_dir):
    """Only append URL mentions from already-qualified retained profile rows."""
    output_dir=Path(output_dir)
    result=build_local_graph_batch(source_db,output_dir/'relationships.db',[],project_stored_provider_links)
    if not result['bioLinkObservations']:raise ValueError('No new retained provider links; this is not another batch')
    fd=os.open(output_dir/'report.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    return result


if __name__=='__main__':raise SystemExit(main())
