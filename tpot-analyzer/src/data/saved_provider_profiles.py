"""Historical provider profiles, never a fallback to mixed-origin Archive rows."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from src.data.saved_capture_import import CaptureWriter,append_profile_bio_links,public_url,PROFILE_POLICY_FIELDS

SOURCE_KIND='saved_twitterapi_profile'
SOURCE_LABEL='Saved public-provider profile'
BOUNDARY=('Historical saved provider user object, not a transport receipt or '
          'current availability, ownership or contact check.')


def decode_provider_profile(row):
    """Qualify a stored provider object by exact identity and explicit privacy."""
    raw=row['raw_json']
    if not isinstance(raw,str) or not raw.strip():return None,'missing_raw'
    try:profile=json.loads(raw)
    except ValueError:return None,'malformed_raw'
    if (not isinstance(profile,dict) or profile.get('id')!=row['account_id']
            or not isinstance(profile.get('userName'),str)
            or not re.fullmatch('[A-Za-z0-9_]{1,15}',profile['userName'])
            or profile['userName'].casefold()!=(row['username'] or '').casefold()):
        return None,'identity_mismatch'
    if profile.get('protected') is True:return None,'protected_at_capture'
    if profile.get('protected') is not False:return None,'privacy_not_explicit'
    if profile.get('unavailable') is True:return None,'unavailable_at_capture'
    if (any(profile.get(k) is not None and not isinstance(profile[k],str)
            for k in ('name','description','location','url'))
            or any(profile.get(k) is not None and (type(profile[k]) is not int or profile[k]<0)
                   for k in ('followers','following'))
            or row['fetched_at'] is not None and not isinstance(row['fetched_at'],str)):
        return None,'unsupported_fields'
    entities=profile.get('entities')
    if entities is not None and not isinstance(entities,dict):return None,'unsupported_fields'
    url_entity=(entities or {}).get('url')
    if url_entity is not None and not isinstance(url_entity,dict):return None,'unsupported_fields'
    urls=(url_entity or {}).get('urls',[])
    if not isinstance(urls,list) or any(not isinstance(u,dict) for u in urls):return None,'unsupported_fields'
    description_entity=(entities or {}).get('description')
    if description_entity is not None and not isinstance(description_entity,dict):return None,'unsupported_fields'
    description_urls=(description_entity or {}).get('urls',[])
    if not isinstance(description_urls,list) or any(not isinstance(u,dict) for u in description_urls):
        return None,'unsupported_fields'
    return profile,None


def append_provider_profile(writer, profile, snapshot, pointer, observed, *, observed_field='user_profile_cache.fetched_at'):
    """Project the same qualified fields from cache rows or captured thread authors."""
    aid=profile['id']
    attrs={'handle':profile['userName'],'name':profile.get('name'),'bio':profile.get('description'),
        'location':profile.get('location'),'website':public_url(profile.get('url')),
        'followers':profile.get('followers'),'following':profile.get('following'),
        'captured_at':observed,'sourceKind':SOURCE_KIND,'bioSourceField':'description',
        'observedAtField':observed_field,'boundary':BOUNDARY}
    account=writer.entity('x_account',aid)
    writer.relation(account,'profile_observation',writer.entity('x_profile',aid),snapshot,pointer,observed,attrs)
    policy={k:attrs[k] for k in PROFILE_POLICY_FIELDS if k in attrs}
    links=[(pointer+'/url',profile.get('url'))]
    for index,item in enumerate(((profile.get('entities') or {}).get('url') or {}).get('urls',[])):
        links.extend((f'{pointer}/entities/url/urls/{index}/{field}',item.get(field)) for field in ('url','expanded_url'))
    for index,item in enumerate(((profile.get('entities') or {}).get('description') or {}).get('urls',[])):
        links.extend((f'{pointer}/entities/description/urls/{index}/{field}',item.get(field))
                     for field in ('url','expanded_url'))
    for source_pointer,raw_url in links:
        if url:=public_url(raw_url):
            writer.relation(account,'profile_links_to',writer.entity('web_resource',url),snapshot,source_pointer,observed,policy)
    append_profile_bio_links(writer,account,snapshot,pointer,observed,attrs['bio'],policy,field='description')


def import_saved_provider_profiles(db,archive_path,account_ids):
    """Caller owns a private copied graph/transaction; archive is read-only.

    Exclusions are explicit, never negative contact findings. Source rows and
    raw_json strings are retained, with the decoded object for field pointers.
    No HTTP, app import, source mutation or legacy profiles-table fallback.
    """
    if (not isinstance(account_ids,list) or not 1<=len(account_ids)<=20000
            or any(not isinstance(a,str) or not re.fullmatch('[0-9]+',a) for a in account_ids)
            or len(set(account_ids))!=len(account_ids)):
        raise ValueError('Provider recovery requires unique exact numeric account IDs')
    archive=Path(archive_path).resolve(strict=True)
    report={'selectedAccounts':len(account_ids),'profiles':0,'projectedAccountIds':[],'exclusions':[]}
    w=CaptureWriter(db)
    with closing(sqlite3.connect(archive.as_uri()+'?mode=ro',uri=True)) as source:
        source.row_factory=sqlite3.Row;source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
        source.execute('SELECT account_id,username,raw_json,fetched_at FROM user_profile_cache LIMIT 0')
        flagged={r[0] for r in source.execute('SELECT account_id FROM protected_accounts')}
        for aid in account_ids:
            row=source.execute('SELECT * FROM user_profile_cache WHERE account_id=?',(aid,)).fetchone()
            profile,reason=(None,'not_in_provider_cache') if row is None else decode_provider_profile(row)
            if aid in flagged:reason='flagged_account'
            if reason:
                report['exclusions'].append({'accountId':aid,'reason':reason});continue
            observed=row['fetched_at']
            payload={'kind':'saved-provider-profile-row','visibility':'private','producer':'saved-provider-profile-v1',
                'sourceTable':'user_profile_cache','row':dict(row),'raw':profile}
            encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
            snapshot=hashlib.sha256(encoded).hexdigest()
            db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES (?,?,?,?)',
                (snapshot,str(archive)+'#user_profile_cache',observed,encoded))
            append_provider_profile(w,profile,snapshot,'/raw',observed)
            report['profiles']+=1;report['projectedAccountIds'].append(aid)
    return report


def project_stored_provider_links(db):
    """Backfill links from retained provider-row snapshots only; never reread Archive.

    Thread-author observations share the profile projection but have a different
    snapshot envelope, so they are deliberately outside this backfill.
    """
    db.row_factory=sqlite3.Row
    rows=db.execute("""SELECT r.*,a.kind account_kind,a.source_key account_id,
      p.kind profile_kind,p.source_key profile_id,s.payload
      FROM relation r JOIN entity a ON a.entity_id=r.subject_id
      JOIN entity p ON p.entity_id=r.object_id
      JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id
      WHERE r.predicate='profile_observation'
      AND json_extract(r.attributes_json,'$.sourceKind')=?
      AND (json_extract(s.payload,'$.kind')=? OR r.source_pointer='/raw')
      ORDER BY r.snapshot_id,r.source_pointer,r.relation_id""",
      (SOURCE_KIND,'saved-provider-profile-row')).fetchall()
    qualified=[];seen=set()
    for anchor in rows:
        if (anchor['account_kind']!='x_account' or anchor['profile_kind']!='x_profile'
                or anchor['source_pointer']!='/raw'):
            raise ValueError('Stored provider profile link anchor is not an exact /raw account/profile pair')
        if anchor['snapshot_id'] in seen:
            raise ValueError('Stored provider profile snapshot has duplicate /raw anchors')
        seen.add(anchor['snapshot_id'])
        payload_bytes=anchor['payload']
        if not isinstance(payload_bytes,bytes) or hashlib.sha256(payload_bytes).hexdigest()!=anchor['snapshot_id']:
            raise ValueError('Stored provider profile snapshot hash disagrees')
        try:payload=json.loads(payload_bytes)
        except (TypeError,ValueError) as error:
            raise ValueError('Stored provider profile snapshot is malformed') from error
        if (not isinstance(payload,dict) or payload.get('kind')!='saved-provider-profile-row'
                or payload.get('visibility')!='private' or payload.get('producer')!='saved-provider-profile-v1'
                or payload.get('sourceTable')!='user_profile_cache' or not isinstance(payload.get('row'),dict)):
            raise ValueError('Stored provider profile snapshot envelope is unsupported')
        row=payload['row']
        try:profile,reason=decode_provider_profile(row)
        except (KeyError,TypeError) as error:
            raise ValueError('Stored provider profile row is malformed') from error
        if reason or profile is None or payload.get('raw')!=profile:
            raise ValueError('Stored provider profile row no longer qualifies as its captured public profile')
        aid=profile['id']
        attrs=json.loads(anchor['attributes_json'])
        expected={'handle':profile['userName'],'name':profile.get('name'),'bio':profile.get('description'),
            'location':profile.get('location'),'website':public_url(profile.get('url')),
            'followers':profile.get('followers'),'following':profile.get('following'),
            'captured_at':row.get('fetched_at'),'sourceKind':SOURCE_KIND,'bioSourceField':'description',
            'observedAtField':'user_profile_cache.fetched_at','boundary':BOUNDARY}
        if (anchor['account_id']!=aid or anchor['profile_id']!=aid or anchor['observed_at']!=row.get('fetched_at')
                or attrs!=expected):
            raise ValueError('Stored provider profile observation disagrees with its exact captured account anchor')
        qualified.append((profile,anchor['snapshot_id'],row['fetched_at']))
    before=db.execute("SELECT count(*) FROM relation WHERE predicate='profile_links_to'").fetchone()[0]
    writer=CaptureWriter(db)
    for profile,snapshot,observed in qualified:
        append_provider_profile(writer,profile,snapshot,'/raw',observed)
    after=db.execute("SELECT count(*) FROM relation WHERE predicate='profile_links_to'").fetchone()[0]
    return {'profiles':len(qualified),'bioLinkObservations':after-before}
