"""Decode a publisher-bound profile package into copied relationship state.

No network or active-source binding. Publication/eligibility are historical
observations, not permission to display this layer without current checks.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.archive.snapshot import utc_iso
from src.data.saved_capture_import import CaptureWriter, public_url, append_profile_bio_links, PROFILE_POLICY_FIELDS

BASE='https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/community-archive-public-export/'
PROFILE_FIELDS=('account_id','username','display_name','account_created_at','bio','location','website',
    'avatar_media_url','header_media_url','num_tweets','num_following','num_followers','num_likes','latest_observed_at')
ATTRIBUTE_FIELDS={'handle':'username','name':'display_name','bio':'bio','website':'website',
    'location':'location','followers':'num_followers','following':'num_following','captured_at':'latest_observed_at'}


def _id(value):
    return isinstance(value,str) and re.fullmatch(r'[0-9]+',value) is not None


def _bounded_bytes(path,limit):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Published profile input exceeds byte limit')
    return raw


def read_profile_bundle(folder):
    folder=Path(folder)
    pointer_raw=_bounded_bytes(folder/'latest.json',131072); manifest_raw=_bounded_bytes(folder/'manifest.json',131072)
    pointer=json.loads(pointer_raw); manifest=json.loads(manifest_raw)
    if not isinstance(pointer,dict) or not isinstance(manifest,dict):
        raise ValueError('Published profile metadata must be objects')
    export=pointer.get('export_id')
    if not isinstance(export,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z',export):
        raise ValueError('Published profile export identity is invalid')
    try:
        info=manifest['files']['profiles']; consent=manifest['consent']; publication=manifest['publication']
        if pointer['schema_version']!='1.0.0' or manifest['schema_version']!='1.0.0' or manifest['export_id']!=export:
            raise ValueError('Profile pointer/manifest schema or export mismatch')
        prefix=BASE+'v1/'+export+'/'
        if publication['status']!='published' or pointer['manifest_url']!=prefix+'manifest.json' or publication['urls']['profiles']!=prefix+'profiles.parquet' or info['path']!='profiles.parquet':
            raise ValueError('Profile package is not a bound published source')
        if any(type(info[key]) is not int or info[key]<=0 for key in ('bytes','rows')) or info['bytes']>4*1024*1024 or info['rows']>20000:
            raise ValueError('Profile size/row count exceeds bounded package contract')
        if type(consent['eligible_accounts']) is not int or consent['eligible_accounts']!=info['rows']:
            raise ValueError('Profile consent count and manifest disagree')
        eligible=pointer['eligible_account_ids']
        if not isinstance(eligible,list) or any(not _id(value) for value in eligible) or len(set(eligible))!=len(eligible) or len(eligible)!=info['rows']:
            raise ValueError('Profile eligible-account set is invalid')
        if not isinstance(consent['snapshot_at'],str) or not consent['snapshot_at']:
            raise ValueError('Profile consent snapshot is missing')
        if not isinstance(info['columns'],list) or len(set(info['columns']))!=len(info['columns']) or not set(PROFILE_FIELDS)<=set(info['columns']):
            raise ValueError('Profile declared columns are incomplete')
        if not isinstance(info['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',info['sha256']):
            raise ValueError('Profile publisher checksum is invalid')
    except (KeyError,TypeError) as error:
        raise ValueError('Published profile metadata fields are invalid') from error
    raw=_bounded_bytes(folder/'profiles.parquet',info['bytes'])
    if len(raw)!=info['bytes'] or hashlib.sha256(raw).hexdigest()!=info['sha256']:
        raise ValueError('Profile bytes/checksum differ from publisher manifest')
    parquet=pq.ParquetFile(io.BytesIO(raw))  # Parse the same bytes we hashed.
    if parquet.schema_arrow.names!=info['columns'] or parquet.metadata.num_rows!=info['rows']:
        raise ValueError('Profile physical schema/rows differ from publisher manifest')
    for name in ('account_id','username'):
        if not (pa.types.is_string(parquet.schema_arrow.field(name).type) or pa.types.is_large_string(parquet.schema_arrow.field(name).type)):
            raise ValueError('Profile identities must be strings')
    observed_type=parquet.schema_arrow.field('latest_observed_at').type
    if not pa.types.is_timestamp(observed_type) or observed_type.tz is None:
        raise ValueError('Profile observation time must be timezone-aware')
    rows=parquet.read().to_pylist(); ids=[row['account_id'] for row in rows]
    if any(not _id(value) for value in ids) or len(set(ids))!=len(ids) or set(ids)!=set(eligible):
        raise ValueError('Profile records do not exactly match eligible account IDs')
    profiles=[]
    for row in rows:
        # The publisher can explicitly lack a handle; the eligible numeric ID remains exact.
        if not isinstance(row['username'],str) or (row['username'] != '' and not re.fullmatch('[A-Za-z0-9_]{1,15}',row['username'])):
            raise ValueError('Profile handle is invalid; no inferred identity')
        if any(value is not None and not isinstance(value,str) for key,value in row.items() if key in ('display_name','bio','location','website','avatar_media_url','header_media_url')):
            raise ValueError('Profile text field has an invalid type')
        if any(row[key] is not None and (type(row[key]) is not int or row[key]<0) for key in ('num_tweets','num_following','num_followers','num_likes')):
            raise ValueError('Profile counts must be nonnegative integers or unknown')
        if not isinstance(row['latest_observed_at'],datetime) or row['latest_observed_at'].utcoffset() is None:
            raise ValueError('Profile observation time is missing or naive')
        if row['account_created_at'] is not None and (not isinstance(row['account_created_at'],datetime) or row['account_created_at'].utcoffset() is None):
            raise ValueError('Profile account creation time is invalid')
        profiles.append({key:utc_iso(value) if isinstance(value,datetime) else value for key,value in row.items()})
    try:json.dumps(profiles,allow_nan=False)
    except (TypeError,ValueError) as error:
        raise ValueError('Profile source fields cannot be encoded losslessly as JSON') from error
    return {'kind':'decoded-community-archive-published-profiles','visibility':'private',
        'exportId':export,'consentSnapshot':consent,'rawSource':{
            'profileSha256':info['sha256'],'profileBytes':info['bytes'],'profileUrl':publication['urls']['profiles'],
            'manifestSha256':hashlib.sha256(manifest_raw).hexdigest(),'pointerSha256':hashlib.sha256(pointer_raw).hexdigest(),
            'encoding':'Original Arrow columns/row order; aware timestamps encoded as UTC ISO strings. Raw Parquet retained separately.'},
        'profiles':profiles}


def import_published_profiles(db,folder,projection):
    payload=read_profile_bundle(folder)
    projection=Path(projection)
    encoded=(json.dumps(payload,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
    if projection.exists():
        if projection.read_bytes()!=encoded:
            raise ValueError('Existing profile projection differs; refusing overwrite')
    else:
        descriptor=os.open(projection,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(descriptor,'wb') as output:output.write(encoded)
    writer=CaptureWriter(db)
    manifest_id,_=writer.source(Path(folder)/'manifest.json')
    pointer_id,_=writer.source(Path(folder)/'latest.json')
    if manifest_id!=payload['rawSource']['manifestSha256'] or pointer_id!=payload['rawSource']['pointerSha256']:
        raise ValueError('Profile metadata changed during import')
    snapshot,_=writer.source(projection)
    websites=0;bio_links=0
    for index,row in enumerate(payload['profiles']):
        attrs={key:row[field] for key,field in ATTRIBUTE_FIELDS.items()}
        attrs.update(sourceKind='community_archive_published_profile',archiveExportId=payload['exportId'],
            observedAtField='latest_observed_at',
            packageRef={'snapshotId':manifest_id,'sourcePointer':'/files/profiles'},
            eligibilityRef={'snapshotId':pointer_id,'sourcePointer':'/eligible_account_ids'},
            profileFileRef={'sha256':payload['rawSource']['profileSha256'],'row':index},
            boundary='Publisher latest account observation, not field-level capture time. Revalidate current eligibility before active display.')
        account=writer.entity('x_account',row['account_id']); observed=row['latest_observed_at']; pointer=f'/profiles/{index}'
        writer.relation(account,'profile_observation',writer.entity('x_profile',row['account_id']),snapshot,pointer,observed,attrs)
        website=public_url(row['website'])
        policy={key:attrs[key] for key in PROFILE_POLICY_FIELDS}
        if website:
            writer.relation(account,'profile_links_to',writer.entity('web_resource',website),snapshot,pointer+'/website',observed,
                policy)
            websites+=1
        bio_links+=append_profile_bio_links(writer,account,snapshot,pointer,observed,row['bio'],policy)
    return {'profiles':len(payload['profiles']),'websiteLinks':websites,'bioLinkObservations':bio_links,
            'exportId':payload['exportId'],'projectionSnapshotId':snapshot}
