"""Source-qualified read views of saved profile URLs and cached pages, never raw snapshots."""
import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_capture_import import public_url

logger=logging.getLogger(__name__)

PRODUCER='cached-website-context-v1'
PAGE_SQL=f"""SELECT account.source_key account_id,r.*,parent.attributes_json parent_attributes,
 parent.subject_id parent_subject,parent.predicate parent_predicate,parent_target.source_key parent_url,
 target.source_key page_url
 FROM relation r JOIN entity account ON account.entity_id=r.subject_id
 JOIN entity target ON target.entity_id=r.object_id
 JOIN relation parent ON parent.relation_id=json_extract(r.attributes_json,'$.associationRef.relationId')
 JOIN entity parent_target ON parent_target.entity_id=parent.object_id
 WHERE account.kind='x_account' AND r.predicate='website_observed_for'
 AND json_extract(r.attributes_json,'$.producer')='{PRODUCER}'"""


def website_page_observations(db, *, published_access=None,account_id=None):
    """All admitted source bindings;the ordinary page view deduplicates below."""
    access=published_access or PublishedProfileAccess()
    sql=PAGE_SQL+(' AND account.source_key=?' if account_id is not None else '')+""" ORDER BY r.observed_at DESC,
      CASE WHEN json_extract(r.attributes_json,'$.page.evidenceRef.parserVersion')='website-context-v2'
      THEN 1 ELSE 0 END DESC,r.relation_id"""
    for row in db.execute(sql,(account_id,) if account_id is not None else ()):
        if (row['parent_subject']!=row['subject_id'] or row['parent_predicate']!='profile_links_to'
                or not access.allows(row['attributes_json'],row['account_id'])
                or not access.allows(row['parent_attributes'],row['account_id'])):
            continue
        attrs=json.loads(row['attributes_json']);page=attrs.get('page')
        if (not isinstance(page,dict) or not isinstance(page.get('text'),str)
                or page.get('status')!='available' or not public_url(page.get('url'))
                or page['url']!=row['page_url'] or page.get('evidenceRef',{}).get('cacheRow',{}).get('accountId')!=row['account_id']
                or public_url(row['parent_url']) not in (public_url(page.get('url')),public_url(page.get('sourceUrl')))):
            raise RuntimeError('Projected website identity/source fields are invalid')
        ref={'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
             'observedAt':row['observed_at'],'status':'reported','associationRef':attrs['associationRef'],
             'cacheObservationId':attrs['cacheObservationId']}
        yield row['account_id'],{**page,'graphEvidenceRef':ref,
            'association':{'url':row['parent_url'],'evidenceRef':attrs['associationRef']}},attrs


def projected_website_pages(db, *, published_access=None,account_id=None):
    result,seen={},set()
    for aid,page,_ in website_page_observations(db,published_access=published_access,account_id=account_id):
        key=(aid,page['graphEvidenceRef']['cacheObservationId'])
        if key in seen:continue
        seen.add(key)
        result.setdefault(aid,[]).append(page)
    return result


def website_fragments(pages):
    """Search page/anchor text, not raw blobs, contact-route metadata or models."""
    fragments=[]
    for page in pages:
        text='\n'.join([page.get('title') or '',page['text'],
            *[f"{link['label']}\n{link['context']}" for link in page.get('links',[])]])
        fragments.append({'kind':'website','label':page.get('title') or 'Cached website page',
            'text':text,'url':page['url'],'evidenceRef':page['graphEvidenceRef'],
            'association':'Historical page/anchor text, not verified ownership, authorship or agreement.',
            'sourceContext':[{'field':'cached_at','value':page.get('capturedAt') or 'unknown'},
                             {'field':'limits','value':page.get('boundary') or 'Historical truncated page'}]})
        for person in page.get('publicClaims',{}).get('people',[]):
            fields=[person.get('name',{}).get('value','')]
            fields.extend(item['value'] for item in person.get('jobTitle',[]))
            fields.extend(item['url'] for item in person.get('sameAs',[]))
            for key in ('worksFor','affiliation','alumniOf'):
                fields.extend(f"{key}: {item.get('name','')} {item.get('url','')}"
                              for item in person.get(key,[]))
            fragments.append({'kind':'website','label':'Page-subject metadata',
                'text':'\n'.join(fields),'url':page['url'],'evidenceRef':page['graphEvidenceRef'],
                'association':'Historical reported page-subject metadata, not a verified account identity or current employer.',
                'sourceContext':[{'field':'cached_at','value':page.get('capturedAt') or 'unknown'},
                    {'field':'json_ld_script_index','value':str(person['sourceIndex'])},
                    {'field':'json_pointer','value':person['pointer']},
                    {'field':'limits','value':page['publicClaims']['boundary']}]})
    return fragments


PROFILE_LINK_SQL="""SELECT a.source_key account_id,t.source_key url,r.snapshot_id,r.source_pointer,
 r.observed_at,r.attributes_json,s.captured_at FROM relation r
 JOIN entity a ON a.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id
 JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id
 WHERE a.kind='x_account' AND a.source_key=? AND r.predicate='profile_links_to'
 AND t.kind='web_resource' ORDER BY julianday(r.observed_at) DESC,r.relation_id"""


def profile_link_preview(path, *, account_id, published_access=None, limit=40):
    """Read exact-account saved profile URL mentions, never raw snapshot content."""
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('profile link limit must be between 1 and 100')
    if not isinstance(account_id,str) or not account_id.isascii() or not account_id.isdigit():
        return {'status':'unresolved_identity','accountId':account_id,'items':[],'truncated':False}
    if not path:return {'status':'not_configured','accountId':account_id,'items':[],'truncated':False}
    try:
        source=Path(path).resolve(strict=True)
        if not source.is_file() or source.stat().st_mode & 0o077:
            raise ValueError('Profile link preview requires a private sidecar')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
            rows=db.execute(PROFILE_LINK_SQL,(account_id,)).fetchall()
    except (OSError,ValueError,sqlite3.Error) as error:
        logger.warning('Saved profile-link sidecar unavailable (%s)',type(error).__name__)
        return {'status':'unavailable','accountId':account_id,'items':[],'truncated':False}
    access=published_access or PublishedProfileAccess();items=[];hidden=0;invalid=0
    try:
        for row in rows:
            if not access.allows(row['attributes_json'],account_id):hidden+=1;continue
            attrs=json.loads(row['attributes_json'])
            if not isinstance(attrs,dict):raise ValueError('Profile link source attributes must be an object')
            url=public_url(row['url'])
            if not url or url!=row['url']:invalid+=1;continue
            items.append({'url':url,'sourceKind':attrs.get('sourceKind'),
                'boundary':attrs.get('boundary') if isinstance(attrs.get('boundary'),str) else None,
                'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
                'observedAt':row['observed_at'],'capturedAt':row['captured_at']})
    except (ValueError,TypeError,RuntimeError) as error:
        logger.warning('Saved profile-link source refused (%s)',type(error).__name__)
        return {'status':'unavailable','accountId':account_id,'items':[],'truncated':False}
    if invalid:
        logger.warning('Saved profile-link source refused (unsafe or malformed URL)')
        return {'status':'unavailable','accountId':account_id,'items':[],'truncated':False}
    truncated=len(items)>limit;items=items[:limit]
    status='not_present' if not rows else ('partial' if hidden else 'available')
    note=f'{hidden} saved Archive profile link(s) are hidden by current publication policy.' if hidden else None
    return {'status':status,'accountId':account_id,'items':items,'truncated':truncated,'note':note}
