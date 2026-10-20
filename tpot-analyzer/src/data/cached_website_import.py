"""Append cached public-page observations using the existing sidecar predicates."""
import base64
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from src.data.cached_websites import describe_cached_page
from src.data.saved_capture_import import CaptureWriter, public_url, append_profile_bio_links, PROFILE_POLICY_FIELDS
from src.data.website_evidence import PRODUCER, projected_website_pages
from src.data.page_contact_clues import append_page_contact_clues

POLICY_FIELDS = ('sourceKind','archiveExportId','profileFileRef','packageRef','eligibilityRef','boundary')


def _encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()


def _association(row):
    return {'relationId':row['relation_id'],'snapshotId':row['snapshot_id'],
            'sourcePointer':row['source_pointer'],'observedAt':row['observed_at'],'url':row['url']}


def project_stored_profile_bio_links(db, *, published_access):
    """Backfill already-retained profile fields on a caller-owned graph copy."""
    db.row_factory=sqlite3.Row
    writer=CaptureWriter(db);counts={'visibleProfileObservations':0,'bioLinkObservations':0}
    rows=db.execute("SELECT e.source_key account_id,r.* FROM relation r JOIN entity e ON e.entity_id=r.subject_id "
                    "WHERE e.kind='x_account' AND r.predicate='profile_observation' ORDER BY r.relation_id").fetchall()
    for row in rows:
        if not published_access.allows(row['attributes_json'],row['account_id']):continue
        attrs=json.loads(row['attributes_json'])
        if not re.fullmatch('[0-9]+',row['account_id']):raise ValueError('Stored profile has no exact numeric identity')
        counts['visibleProfileObservations']+=1
        counts['bioLinkObservations']+=append_profile_bio_links(writer,row['subject_id'],row['snapshot_id'],
            row['source_pointer'],row['observed_at'],attrs.get('bio'),
            {key:attrs[key] for key in PROFILE_POLICY_FIELDS if key in attrs},field=attrs.get('bioSourceField','bio'))
    return counts


def project_cached_websites(db, archive_path, account_ids, *, published_access):
    """Caller owns a copied DB and transaction. Never modify archive/tag state.

    Multiple associations qualify one original cache observation; they are not
    independent page confirmations. Do not create reviewed contact/identity edges.
    """
    if (not isinstance(account_ids,(list,tuple)) or not 1<=len(account_ids)<=20000
            or any(not isinstance(a,str) or not re.fullmatch('[0-9]+',a) for a in account_ids)
            or len(set(account_ids))!=len(account_ids)):
        raise ValueError('Website projection requires nonempty unique exact numeric account IDs')
    db.row_factory=sqlite3.Row
    for aid in account_ids:
        if db.execute("SELECT 1 FROM relation r JOIN entity e ON e.entity_id=r.subject_id "
            "WHERE e.kind='x_account' AND e.source_key=? AND r.predicate='profile_observation' LIMIT 1",(aid,)).fetchone() is None:
            raise ValueError('Website selection has no exact captured profile identity')
    archive=Path(archive_path).resolve(strict=True)
    counts={'selectionAccounts':len(account_ids),'pages':0,'associations':0,
            'linkObservations':0,'redirects':0,'missingHtmlPages':0,'unmatchedCacheRows':0,
            'emailClues':0,'messageForms':0,'publicSelfLinkClues':0,
            'pageSubjectClaims':0,'employmentClues':0,'pageContactObservations':0}
    writer=CaptureWriter(db)
    with closing(sqlite3.connect(archive.as_uri()+'?mode=ro',uri=True)) as arc:
        arc.row_factory=sqlite3.Row;arc.execute('PRAGMA query_only=ON')
        arc.execute('SELECT account_id,source_url,resolved_url,title,fetched_at,error,html_gz FROM bio_link_profile LIMIT 0')
        for aid in sorted(account_ids):
            roots=list(db.execute('SELECT r.*,target.source_key url FROM relation r '
                'JOIN entity account ON account.entity_id=r.subject_id JOIN entity target ON target.entity_id=r.object_id '
                "WHERE account.kind='x_account' AND account.source_key=? AND r.predicate='profile_links_to' ORDER BY r.relation_id",(aid,)))
            roots=[r for r in roots if published_access.allows(r['attributes_json'],aid) and public_url(r['url'])]
            for row in arc.execute('SELECT account_id,source_url,resolved_url,title,fetched_at,error,html_gz '
                                   'FROM bio_link_profile WHERE account_id=? ORDER BY source_url',(aid,)):
                urls={u for raw in (row['source_url'],row['resolved_url']) if (u:=public_url(raw))}
                matches=[r for r in roots if public_url(r['url']) in urls]
                if not matches:
                    counts['unmatchedCacheRows']+=1
                    continue
                page=describe_cached_page(row,{})
                page.pop('association')
                if page['status']=='not_cached':
                    counts['missingHtmlPages']+=1
                    continue
                if page['status']!='available':
                    raise ValueError('Selected cached page is damaged; projection is incomplete')
                source={key:row[key] for key in ('account_id','source_url','resolved_url','title','fetched_at','error')}
                source['htmlGzipBase64']=base64.b64encode(row['html_gz']).decode('ascii')
                payload={'kind':'cached-public-website-observation','visibility':'private',
                         'producer':PRODUCER,'source':source,'derived':page}
                raw=_encoded(payload);snapshot=hashlib.sha256(raw).hexdigest()
                db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES (?,?,?,?)',
                    (snapshot,str(archive)+'#bio_link_profile',row['fetched_at'],raw))
                observation=hashlib.sha256(_encoded([aid,row['source_url'],row['fetched_at'],page['evidenceRef']['gzipSha256']])).hexdigest()
                account=writer.entity('x_account',aid)
                target=writer.entity('web_resource',page['url'])
                for root in matches:
                    policy=json.loads(root['attributes_json'])
                    attrs={key:policy[key] for key in POLICY_FIELDS if key in policy}
                    attrs.update(producer=PRODUCER,observingAccountId=aid,cacheObservationId=observation,
                        associationRef=_association(root),cacheRef={'snapshotId':snapshot,'sourcePointer':'/source'})
                    writer.relation(account,'website_observed_for',target,snapshot,'/source',row['fetched_at'],
                                    {**attrs,'page':page})
                    counts['pageContactObservations']+=append_page_contact_clues(writer,page,snapshot,row['fetched_at'],attrs)
                    counts['associations']+=1
                    start=public_url(row['source_url']);end=public_url(row['resolved_url'])
                    if start and end and start!=end:
                        writer.relation(writer.entity('web_resource',start),'page_resolves_to',target,
                            snapshot,'/source/resolved_url',row['fetched_at'],attrs)
                        counts['redirects']+=1
                    for index,link in enumerate(page['links']):
                        writer.relation(target,'page_links_to',writer.entity('web_resource',link['url']),
                            snapshot,f'/derived/links/{index}',row['fetched_at'],
                            {**attrs,'decodedIndex':index,'linkLabel':link['label'],'linkContext':link['context']})
                        counts['linkObservations']+=1
                counts['pages']+=1
                counts['emailClues']+=page['emailClueCount'];counts['messageForms']+=page['formCount']
                claims=page.get('publicClaims',{})
                counts['publicSelfLinkClues']+=len(claims.get('selfLinks',[]))
                counts['pageSubjectClaims']+=len(claims.get('people',[]))
                counts['employmentClues']+=sum(len(person.get('worksFor',[])) for person in claims.get('people',[]))
    return counts


def project_stored_publisher_links(db,account_ids,*,published_access):
    """Append marked URL claims, not verified identity/employment/contact edges."""
    if (not isinstance(account_ids,list) or not 1<=len(account_ids)<=20000
            or len(set(account_ids))!=len(account_ids)
            or any(not isinstance(a,str) or not re.fullmatch('[0-9]+',a) for a in account_ids)):
        raise ValueError('Publisher links require unique exact numeric account IDs')
    db.row_factory=sqlite3.Row;writer=CaptureWriter(db)
    for aid in account_ids:
        if not db.execute("SELECT 1 FROM entity e JOIN relation r ON r.subject_id=e.entity_id "
            "WHERE e.kind='x_account' AND e.source_key=? AND r.predicate='profile_observation'",(aid,)).fetchone():
            raise ValueError('Publisher-link selection has no exact captured profile')
    before=db.execute('SELECT count(*) FROM relation').fetchone()[0]
    report={'publisherLinkObservations':0,'pagesWithClaims':0,'nameOnlyOrganisationClaims':0}
    for aid in sorted(account_ids):
        for page in projected_website_pages(db,published_access=published_access,account_id=aid).get(aid,[]):
            ref=page['graphEvidenceRef'];claims=page.get('publicClaims',{})
            raw=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(ref['snapshotId'],)).fetchone()
            if raw is None or json.loads(raw[0]).get('derived',{}).get('publicClaims',{})!=claims:
                raise ValueError('Publisher claims disagree with the retained page source')
            parent=db.execute('SELECT attributes_json FROM relation WHERE relation_id=?',
                (ref['associationRef']['relationId'],)).fetchone()
            policy=json.loads(parent[0]);items=[]
            for n,claim in enumerate(claims.get('selfLinks',[])):
                items.append(('rel_me',claim,f'/derived/publicClaims/selfLinks/{n}',None))
            for n,person in enumerate(claims.get('people',[])):
                for kind in ('sameAs','worksFor','affiliation','alumniOf'):
                    for m,claim in enumerate(person.get(kind,[])):
                        if not claim.get('url'):
                            report['nameOnlyOrganisationClaims']+=kind!='sameAs';continue
                        items.append((kind,claim,f'/derived/publicClaims/people/{n}/{kind}/{m}',person))
            if items:report['pagesWithClaims']+=1
            for kind,claim,pointer,person in items:
                if not public_url(claim.get('url')):raise ValueError('Publisher claim URL must be public HTTP(S)')
                attrs={k:policy[k] for k in POLICY_FIELDS if k in policy}
                attrs.update(producer=PRODUCER,observingAccountId=aid,
                    cacheObservationId=ref['cacheObservationId'],associationRef=ref['associationRef'],
                    claimKind=kind,claimSourceIndex=claim['sourceIndex'],
                    claimSourcePointer=claim.get('pointer',''),
                    linkLabel=claim.get('label') or claim.get('name') or kind,
                    linkContext='Publisher declaration, not verified account ownership, current employment or contactability.')
                if person:
                    attrs.update(claimPersonName=person.get('name',{}).get('value',''),
                        claimSubjectPointer=person['pointer'])
                if kind in ('worksFor','affiliation','alumniOf'):
                    attrs['claimOrganisationName']=claim.get('name','')
                    for field in ('resolvedPointer','namePointer','urlPointer'):
                        if field in claim:attrs['claim'+field[0].upper()+field[1:]]=claim[field]
                writer.relation(writer.entity('web_resource',page['url']),'page_links_to',
                    writer.entity('web_resource',claim['url']),ref['snapshotId'],pointer,ref['observedAt'],attrs)
    report['publisherLinkObservations']=db.execute('SELECT count(*) FROM relation').fetchone()[0]-before
    return report
