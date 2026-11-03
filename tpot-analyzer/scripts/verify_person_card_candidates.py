#!/usr/bin/env python3
"""Read-only acceptance for an additive, saved-source person-card candidate batch.

Checks exact account admission, original candidates, retained source values and
dates. Literal profile destinations can remain websites, not identity or contact
affordance assertions. This does not verify delivery or the human's decisions.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
import tempfile


def _pointer(payload,pointer):
    if not isinstance(pointer,str) or not pointer.startswith('/'):
        raise ValueError('Profile source requires a retained JSON pointer')
    try:
        for token in pointer[1:].split('/'):
            token=token.replace('~1','/').replace('~0','~')
            if isinstance(payload,list):
                if not token.isascii() or not token.isdigit():raise ValueError('Invalid source array index')
                payload=payload[int(token)]
            elif isinstance(payload,dict):payload=payload[token]
            else:raise ValueError('Profile source pointer crosses an unsupported value')
    except (KeyError,IndexError,TypeError) as error:
        raise ValueError('Profile source pointer does not exist') from error
    return payload


def profile_destination_source(db,account_id,link,*,bio_email=False):
    """Exact raw profile URL or bio-email witness, never an identity match."""
    from src.enrichment.bio_url_mentions import bio_url_mentions
    from src.data.profile_contact_clues import bio_contact_mentions
    from src.data.saved_provider_profiles import SOURCE_KIND,decode_provider_profile
    sid=link['snapshotId'];pointer=link['sourcePointer']
    row=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(sid,)).fetchone()
    if row is None or not isinstance(row[0],bytes) or hashlib.sha256(row[0]).hexdigest()!=sid:
        raise ValueError('Retained profile source is missing or has a different digest')
    payload=json.loads(row[0]);value=_pointer(payload,pointer)
    if not isinstance(value,str):
        raise ValueError('Profile source field must be literal text')
    if bio_email:
        mention=next((item for item in bio_contact_mentions(value)
                      if item['platform']=='email' and item['value']==link['url']),None)
        matching=mention is not None
    else:
        matching=value==link['url'] or any(item['url']==link['url'] for item in bio_url_mentions(value))
    if not matching:
        raise ValueError('Profile destination disagrees with its literal source field')
    anchors=db.execute("""SELECT r.source_pointer,r.attributes_json,r.observed_at FROM relation r
      JOIN entity a ON a.entity_id=r.subject_id WHERE a.kind='x_account' AND a.source_key=?
      AND r.predicate='profile_observation' AND r.snapshot_id=?""",(account_id,sid))
    for anchor in anchors:
        if not pointer.startswith(anchor['source_pointer']+'/') or anchor['observed_at']!=link['observedAt']:continue
        profile=_pointer(payload,anchor['source_pointer']);attrs=json.loads(anchor['attributes_json'])
        if not isinstance(profile,dict):continue
        kind=attrs.get('sourceKind')
        if kind==SOURCE_KIND:
            valid=(profile.get('id')==account_id and profile.get('protected') is False
                   and profile.get('unavailable') is not True and profile.get('userName')==attrs.get('handle'))
            if bio_email:
                valid=valid and pointer==anchor['source_pointer']+'/description' and attrs.get('bio')==value
                if payload.get('kind')=='saved-provider-profile-row':
                    try:
                        decoded,reason=decode_provider_profile(payload['row'])
                    except (KeyError,TypeError) as error:
                        raise ValueError('Stored bio profile row is malformed') from error
                    valid=(valid and not reason and decoded==profile
                           and payload['row'].get('fetched_at')==link['observedAt']
                           and attrs.get('captured_at')==link['observedAt'])
            handle=profile.get('userName')
        elif kind is None:
            if bio_email:continue
            valid=profile.get('account_id')==account_id and profile.get('handle')==attrs.get('handle')
            handle=profile.get('handle')
        else:continue
        if valid and isinstance(handle,str) and re.fullmatch('[A-Za-z0-9_]{1,15}',handle):
            field=' '.join(mention['context'].split()) if bio_email else value
            return {'url':f'https://x.com/{handle}',
                'sourceType':'saved_bio_mention' if bio_email else 'saved_destination',
                'observedAt':link['observedAt'],'sourcePointer':pointer,'sourceDigest':sid,
                'note':('Literal email mention in a saved provider bio' if bio_email else
                        'Literal destination in a saved X profile field')+', not verified ownership or contactability. '
                       'It may refer to another person or organisation. '+
                       (f"Bio characters {mention['start']}-{mention['end']}: " if bio_email else 'Original field: ')+field[:1800]}
    raise ValueError('Profile destination has no matching raw exact-account profile witness')


def verify_batch(catalogue, previous, cohort, graph, expected_added_accounts):
    from src.data.contact_matches import load_candidates
    from src.data.published_profile_access import PublishedProfileAccess
    from src.data.saved_evidence import saved_profile_locators
    from src.data.website_evidence import projected_website_pages
    from src.data.website_evidence import profile_link_preview

    old=load_candidates(previous);new=load_candidates(catalogue)
    if any(key not in new or new[key]!=value for key,value in old.items()):
        raise ValueError('Prior candidates or their evidence changed')
    rows=json.loads(Path(cohort).read_bytes())['accounts']
    allowed={row['accountId'] for row in rows if row['status']!='privacy_hold'}
    ids={item['accountId'] for item in new.values()}
    if not ids<=allowed:raise ValueError('Candidate is outside the public frozen cohort')
    if not ids<=set(saved_profile_locators(graph,sorted(ids))):
        raise ValueError('Candidate has no admitted independent exact-ID profile')
    added={key:value for key,value in new.items() if key not in old}
    if not added:raise ValueError('No added candidate observations; catalogue is unchanged')
    added_ids={item['accountId'] for item in added.values()}-{item['accountId'] for item in old.values()}
    if len(added_ids)!=expected_added_accounts:
        raise ValueError('Added account count does not match the declared batch')
    source=Path(graph).resolve(strict=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
        pages=projected_website_pages(db,published_access=PublishedProfileAccess())
        snapshots={}
        for digest in {ref.get('sourceDigest') for item in added.values() for ref in item['evidence']}:
            row=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(digest,)).fetchone()
            if row is None or not isinstance(row[0],bytes) or hashlib.sha256(row[0]).hexdigest()!=digest:
                raise ValueError('Retained page source is missing or has a different digest')
            snapshots[digest]=json.loads(row[0])
        witnesses={(aid,p['graphEvidenceRef']['snapshotId']):p for aid,items in pages.items() for p in items}
        profile_links={}
        for item in added.values():
          for ref in item['evidence']:
            if ref['sourceType']=='saved_bio_mention':
                if (item['kind']!='email' or item['platform']!='email'
                        or item['scope'] not in ('unknown','organisation')):
                    raise ValueError('Bio mentions must remain uncertain email associations')
                link={'url':item['value'],'snapshotId':ref.get('sourceDigest'),
                      'sourcePointer':ref.get('sourcePointer'),'observedAt':ref['observedAt']}
                source_ref=profile_destination_source(db,item['accountId'],link,bio_email=True)
                if ref['url']!=source_ref['url']:
                    raise ValueError('Bio mention source URL disagrees with the captured profile handle')
                continue
            if ref['sourceType']=='saved_destination':
                if item['scope'] not in ('unknown','organisation') or item['kind'] not in ('profile','website'):
                    raise ValueError('Direct profile candidates must remain possible profile or website associations')
                aid=item['accountId']
                if aid not in profile_links:
                    profile_links[aid]=profile_link_preview(graph,account_id=aid,limit=100)['items']
                matching=[link for link in profile_links[aid] if link['url']==item['value']
                    and link['snapshotId']==ref.get('sourceDigest')
                    and link['sourcePointer']==ref.get('sourcePointer') and link['observedAt']==ref['observedAt']]
                if not matching:raise ValueError('Direct candidate has no admitted exact profile field/date witness')
                source_ref=profile_destination_source(db,aid,matching[0])
                if ref['url']!=source_ref['url']:raise ValueError('Direct candidate source URL disagrees with the captured profile handle')
                continue
            page=witnesses.get((item['accountId'],ref.get('sourceDigest')))
            if (page is None or ref['sourceType']!='historical_cache'
                    or ref['url']!=page['url'] or ref['observedAt']!=page.get('capturedAt')):
                raise ValueError('Added candidate has no exact admitted page/date witness')
            parts=ref.get('sourcePointer','').split('/')
            if len(parts)!=4 or parts[:2]!=['','derived'] or not parts[3].isdigit():
                raise ValueError('Added candidate source pointer is not a retained clue')
            field=parts[2];index=int(parts[3]);items=page.get(field)
            if field not in ('links','emailClues','messageForms') or not isinstance(items,list) or index>=len(items):
                raise ValueError('Added candidate source pointer does not exist')
            clue=items[index]
            if snapshots[ref['sourceDigest']].get('derived',{}).get(field,[])[index]!=clue:
                raise ValueError('Projected clue disagrees with its original retained source')
            expected=(clue.get('address') if field=='emailClues' else
                      page['url'] if field=='messageForms' else clue.get('url'))
            if item['value']!=expected:
                raise ValueError('Added value disagrees with the retained source')
            if item['scope'] not in ('unknown','organisation'):
                raise ValueError('Saved-page batch must not assert personal ownership')
            if field=='messageForms' and (item['kind']!='contact_form' or clue.get('tested') is not False):
                raise ValueError('Form must remain an untested page affordance')
            if field=='emailClues' and item['kind']!='email':
                raise ValueError('Email clue kind disagrees with the retained source')
    return {'accounts':len(ids),'values':len(new),'addedAccounts':len(added_ids),
            'addedValues':len(added),'priorValuesRetained':len(old)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('catalogue','previous','cohort','graph'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-added-accounts',type=int,required=True)
    args=parser.parse_args()
    if not 0<=args.expected_added_accounts<=1650:
        parser.error('Expected new account count must be between 0 and 1650; added values are still required')
    # No live persistence/lease destination is inherited before application imports.
    state=Path(tempfile.mkdtemp(prefix='tpot-candidate-batch-check-'))
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','ARCHIVE_DB_PATH','CACHE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR',
                'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT','RESEARCH_NOTES_SOURCE_PATH',
                'RESEARCH_NOTES_PROPOSALS_PATH','MAP_TPOT_CONTACT_MATCH_DB'):
        os.environ[key]=str(state/key)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    try:
        result=verify_batch(args.catalogue,args.previous,args.cohort,args.graph,args.expected_added_accounts)
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error) as error:
        print(f'✗ Candidate batch refused ({type(error).__name__}); no source or decision writes')
        if isinstance(error,ValueError):print(str(error))
        print('Next: inspect source/account/pointer mismatch locally; do not activate the batch.')
        return 1
    print(f"✓ Accounts={result['accounts']}; values={result['values']}; "
          f"new cards={result['addedAccounts']}; new values={result['addedValues']}")
    print(f"✓ Prior candidates/evidence retained={result['priorValuesRetained']}; exact independent identities admitted")
    print('✓ Every added value/date matches an admitted saved page or profile field; no graph or decision writes')
    print('Next: verify authenticated Review reads and source visibility, preserving the existing decision journal.')
    return 0


if __name__=='__main__':raise SystemExit(main())
