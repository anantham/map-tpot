"""Saved research cites a page;it does not establish account/channel ownership."""
import hashlib
import json
import re
import sqlite3

from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_capture_import import CaptureWriter,public_url

PREDICATE='research_cites_identity_source'
PRODUCER='saved-research-source-links-v1'
QUALIFICATION_STR_FIELDS=('current_role_caveat','historical_named_role_passage','missing_reciprocal_handle',
    'reciprocal_account_link','strength','current_role_limit','limits','ownership_limit',
    'previous_source_record','type','association','extent','conclusion','locator','limit',
    'geographic_conflict','basis','level','primary_bridge_extent','primary_bridge_passage',
    'primary_named_role_extent','primary_work_byline','primary_named_work_extent',
    'role_context_extent','owned_site_extent','owned_site_access_limit','captured_name',
    'captured_professional_context','observed_location','observed_reader_redirect','reciprocal_handle')
CANONICAL_QUALIFICATION_STR_FIELDS=('current_role_caveat','historical_named_role_passage','missing_reciprocal_handle',
    'reciprocal_account_link','strength','current_role_limit','limits','ownership_limit',
    'previous_source_record','type','association','extent','conclusion','locator','limit','geographic_conflict')
QUALIFICATION_BOOL_FIELD='reciprocal_handle_observed_without_X_read'
QUALIFICATION_BOOL_FIELDS=('reciprocal_link_visited','observed_location_visited','profile_destinations_visited')
QUALIFICATION_INT_FIELDS=('ordinary_head_status','head_status')
QUALIFICATION_NULLABLE_STR_FIELDS=('exact_reciprocal_handle_observed',)
URL_STR_FIELDS=('url','source_url','supporting_url')
URL_LIST_FIELDS=('source_urls','urls')
WITNESS_ROOT_STR={
    'captured_website':'captured URL','captured_profile_website':'captured URL',
    'owned_site_url':'saved site-ownership claim','primary_bridge_url':'work-role bridge',
    'primary_named_role_url':'work-role bridge','primary_named_work_url':'work-role bridge',
    'role_context_url':'work-role bridge'}
WITNESS_ROOT_LIST={'primary_bridge_urls':'work-role bridge'}
WITNESS_NESTED={
    'evidence':{'url':'research evidence page'},'sources':{'url':'research evidence page','resolved_url':'saved URL resolution'},
    'source':{'url':'research evidence page','final_url':'saved URL resolution'},
    'primary_bridge':{'url':'work-role bridge'},'primary_named_role_bridge':{'url':'work-role bridge'},
    'link_metadata_followup':{'resolved_url':'saved URL resolution'}}
NESTED_STR_FIELDS=('url','final_url','resolved_url','paraphrase','locator','method','extent','coverage','date',
    'inspected_extent','location','nofollow_location','scope','title','author_profile_href','conclusion')
NESTED_INT_FIELDS=('http_status','status')
NESTED_BOOL_FIELDS=('destination_not_retrieved','metadata_only','literal_handle_present','profile_body_inspected')


def _typed_context(obj,prefix,pointer):
    values={};refs={}
    for field in NESTED_STR_FIELDS:
        if field in obj:
            if type(obj[field]) is not str:raise ValueError(f'Research witness {prefix}.{field} must be a string')
            values[f'{prefix}.{field}']=obj[field];refs[f'{prefix}.{field}']=f'{pointer}/{field}'
    for field in NESTED_INT_FIELDS:
        if field in obj:
            if type(obj[field]) is not int:raise ValueError(f'Research witness {prefix}.{field} must be an integer')
            values[f'{prefix}.{field}']=obj[field];refs[f'{prefix}.{field}']=f'{pointer}/{field}'
    for field in NESTED_BOOL_FIELDS:
        if field in obj:
            if type(obj[field]) is not bool:raise ValueError(f'Research witness {prefix}.{field} must be a boolean')
            values[f'{prefix}.{field}']=obj[field];refs[f'{prefix}.{field}']=f'{pointer}/{field}'
    return values,refs


def _witness_records(binding,n):
    """Read only the reviewed fixed URL shapes; unknown containers remain raw."""
    records=[];context={};context_refs={}
    for field,role in WITNESS_ROOT_STR.items():
        if field in binding:
            if type(binding[field]) is not str:raise ValueError(f'Research witness {field} must be a string')
            context[field]=binding[field];context_refs[field]=f'/cards/{n}/identity_binding/{field}'
    for field,role in WITNESS_ROOT_LIST.items():
        if field in binding:
            if type(binding[field]) is not list:raise ValueError(f'Research witness {field} must be a list')
            for i,value in enumerate(binding[field]):
                if type(value) is not str:raise ValueError(f'Research witness {field} values must be strings')
                context[f'{field}/{i}']=value;context_refs[f'{field}/{i}']=f'/cards/{n}/identity_binding/{field}/{i}'
    for field in (*QUALIFICATION_STR_FIELDS,*QUALIFICATION_NULLABLE_STR_FIELDS):
        if field in binding:
            if field in QUALIFICATION_NULLABLE_STR_FIELDS and binding[field] is None:
                context[field]=None;context_refs[field]=f'/cards/{n}/identity_binding/{field}';continue
            if type(binding[field]) is not str:raise ValueError(f'Research qualification {field} must be a string')
            context[field]=binding[field];context_refs[field]=f'/cards/{n}/identity_binding/{field}'
    for field in (QUALIFICATION_BOOL_FIELD,*QUALIFICATION_BOOL_FIELDS):
        if field in binding:
            if type(binding[field]) is not bool:raise ValueError(f'Research qualification {field} must be a boolean')
            context[field]=binding[field];context_refs[field]=f'/cards/{n}/identity_binding/{field}'
    for field in QUALIFICATION_INT_FIELDS:
        if field in binding:
            if type(binding[field]) is not int:raise ValueError(f'Research qualification {field} must be an integer')
            context[field]=binding[field];context_refs[field]=f'/cards/{n}/identity_binding/{field}'
    if 'ordinary_head' in binding:
        head=binding['ordinary_head']
        if not isinstance(head,dict):raise ValueError('Research witness ordinary_head must be an object')
        for key,value in head.items():
            if key not in ('status','location','date_header'):continue
            expected=int if key=='status' else str
            if type(value) is not expected:raise ValueError(f'Research witness ordinary_head.{key} has an invalid type')
            context[f'ordinary_head.{key}']=value
            context_refs[f'ordinary_head.{key}']=f'/cards/{n}/identity_binding/ordinary_head/{key}'
    root_context=dict(context);root_refs=dict(context_refs)
    for field,role in WITNESS_ROOT_STR.items():
        if field in binding:
            records.append((binding[field],role,f'/cards/{n}/identity_binding/{field}',dict(root_context),dict(root_refs),None))
    for field,role in WITNESS_ROOT_LIST.items():
        for i,value in enumerate(binding.get(field,[])):
            records.append((value,role,f'/cards/{n}/identity_binding/{field}/{i}',dict(root_context),dict(root_refs),None))
    for container,urls in WITNESS_NESTED.items():
        if container not in binding:continue
        raw=binding[container]
        if container=='source' and isinstance(raw,str):
            records.append((raw,'research evidence page',f'/cards/{n}/identity_binding/source',
                dict(root_context),dict(root_refs),None));continue
        many=container in ('evidence','sources')
        if many:
            if container=='evidence' and isinstance(raw,str):continue
            if container=='evidence' and not isinstance(raw,list):
                raise ValueError('Research citation URLs,note or retrieval caveat are invalid')
            if not isinstance(raw,list):raise ValueError(f'Research witness {container} must be a list')
            entries=list(enumerate(raw))
        else:
            if not isinstance(raw,dict):raise ValueError(f'Research witness {container} must be an object')
            entries=[(None,raw)]
        for index,obj in entries:
            if container=='sources' and isinstance(obj,str):
                records.append((obj,'research evidence page',f'/cards/{n}/identity_binding/sources/{index}',
                    dict(root_context),dict(root_refs),None));continue
            if not isinstance(obj,dict):raise ValueError(f'Research witness {container} entries must be objects')
            pointer=f'/cards/{n}/identity_binding/{container}'+(f'/{index}' if index is not None else '')
            if container=='evidence' and (not isinstance(obj.get('paraphrase'),str) or not obj['paraphrase']):
                raise ValueError('Research evidence witness requires a nonempty paraphrase')
            local,local_refs=_typed_context(obj,f'{container}',pointer)
            for url_field,role in urls.items():
                if url_field not in obj:continue
                if type(obj[url_field]) is not str:raise ValueError(f'Research witness {container}.{url_field} must be a string')
                if container=='evidence':
                    note=obj.get('paraphrase')
                    note_pointer=f'{pointer}/paraphrase'
                else:note=None
                combined={**root_context,**local};refs={**root_refs,**local_refs}
                key=f'{container}.{url_field}';combined[key]=obj[url_field];refs[key]=f'{pointer}/{url_field}'
                records.append((obj[url_field],role,f'{pointer}/{url_field}',combined,refs,
                    (note,note_pointer) if container=='evidence' else None))
    return records


def _records(db,sid,access):
    if not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{64}',sid):
        raise ValueError('Research citation requires an exact retained snapshot ID')
    raw=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(sid,)).fetchone()
    if raw is None or not isinstance(raw[0],bytes) or hashlib.sha256(raw[0]).hexdigest()!=sid:
        raise ValueError('Research citation snapshot is missing or disagrees with its hash')
    payload=json.loads(raw[0]);cards=payload.get('cards') if isinstance(payload,dict) else None
    if not isinstance(cards,list) or not cards:raise ValueError('Research citation source requires nonempty cards')
    prepared=payload.get('prepared_on')
    if prepared is not None and not isinstance(prepared,str):raise ValueError('Source preparation date must be literal text or unknown')
    anchors={}
    for row in db.execute("""SELECT r.*,a.kind account_kind,a.source_key account_id,t.kind target_kind,t.source_key url
      FROM relation r JOIN entity a ON a.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id
      WHERE r.predicate='research_associates_with' AND r.snapshot_id=?""",(sid,)):
        anchors.setdefault(row['source_pointer'],[]).append(row)
    for n,card in enumerate(cards):
        if not isinstance(card,dict):raise ValueError('Research citation card must be an object')
        binding=card.get('identity_binding')
        if binding is None:continue
        if not isinstance(binding,dict):
            raise ValueError('Research citation binding must be an object')
        witnesses=_witness_records(binding,n)
        canonical=any(field in binding for field in (*URL_STR_FIELDS,*URL_LIST_FIELDS))
        if binding.get('retrieval_caveat') is not None and not isinstance(binding['retrieval_caveat'],str):
            raise ValueError('Research citation URLs,note or retrieval caveat are invalid')
        if not canonical and not witnesses:continue
        if (canonical and any(field in binding and type(binding[field]) is not str for field in URL_STR_FIELDS)
                or canonical and any(field in binding and type(binding[field]) is not list for field in URL_LIST_FIELDS)
                or canonical and not isinstance(binding.get('evidence'),str)):
            raise ValueError('Research citation URLs,note or retrieval caveat are invalid')
        qualifications={}
        for field in CANONICAL_QUALIFICATION_STR_FIELDS:
            if field in binding:
                if type(binding[field]) is not str:raise ValueError(f'Research qualification {field} must be a string')
                qualifications[field]=binding[field]
        if QUALIFICATION_BOOL_FIELD in binding:
            if type(binding[QUALIFICATION_BOOL_FIELD]) is not bool:
                raise ValueError(f'Research qualification {QUALIFICATION_BOOL_FIELD} must be a boolean')
            qualifications[QUALIFICATION_BOOL_FIELD]=binding[QUALIFICATION_BOOL_FIELD]
        sources=[]
        for field in (*URL_STR_FIELDS,*URL_LIST_FIELDS):
            if field not in binding:continue
            values=[binding[field]] if field in URL_STR_FIELDS else binding[field]
            sources.extend((url,f'/cards/{n}/identity_binding/{field}'+
                (f'/{index}' if field in URL_LIST_FIELDS else '')) for index,url in enumerate(values))
        if not sources and not witnesses:continue
        aid=card.get('account_id');artifact=card.get('artifact');work_pointer=f'/cards/{n}/artifact'
        if (not isinstance(aid,str) or not re.fullmatch('[0-9]+',aid) or not isinstance(artifact,dict)
                or not isinstance(artifact.get('title'),str) or not public_url(artifact.get('url'))):
            raise ValueError('Research citation requires exact account/work fields')
        parents=anchors.get(work_pointer,[])
        if not parents:raise ValueError('Research citation has no retained exact work anchor')
        eligible=[]
        for parent in parents:
            attrs=json.loads(parent['attributes_json'])
            if (not isinstance(attrs,dict) or parent['account_kind']!='x_account' or parent['account_id']!=aid
                    or parent['target_kind']!='web_resource' or parent['url']!=public_url(artifact['url'])
                    or attrs.get('title')!=artifact['title'] or attrs.get('url')!=artifact['url']):
                raise ValueError('Research citation work anchor disagrees with its original card')
            if access.allows(attrs,aid):eligible.append(parent)
        if not eligible:continue
        root_note=binding.get('evidence')
        root_note_pointer=f'/cards/{n}/identity_binding/evidence'
        if isinstance(root_note,list):
            root_note=binding.get('conclusion');root_note_pointer=f'/cards/{n}/identity_binding/conclusion'
        if witnesses and (not isinstance(root_note,str) or not root_note):
            if any(note is None for *_,note in witnesses):
                raise ValueError('Research witness links require a nonempty source conclusion')
        attrs={'producer':PRODUCER,'researchNote':root_note,
            'retrievalCaveat':binding.get('retrieval_caveat'),'workTitle':artifact['title'],
            'workUrl':artifact['url'],'sourcePreparedLiteral':prepared}
        if qualifications:attrs['sourceQualifications']=qualifications
        all_sources=[(url,pointer,attrs,None,None) for url,pointer in sources]
        for url,role,pointer,local_qualifications,local_pointers,note in witnesses:
            witness_attrs={**attrs,'witnessRole':role,'sourceQualifications':local_qualifications}
            if note is not None:
                witness_attrs['researchNote']=note[0]
            all_sources.append((url,pointer,witness_attrs,local_pointers,note))
        for url,pointer,source_attrs,local_pointers,note in all_sources:
            if (not isinstance(url,str) or public_url(url)!=url or any(c.isspace() or ord(c)<32 for c in url)):
                raise ValueError('Research citation URLs must be literal public HTTP(S) without credentials')
            qualification_pointers=local_pointers if local_pointers is not None else {field:f'/cards/{n}/identity_binding/{field}' for field in qualifications}
            yield {'accountId':aid,'subjectId':eligible[0]['subject_id'],'url':url,'attrs':source_attrs,
                'pointer':pointer,
                'contextPointer':note[1] if note is not None else root_note_pointer,'workPointer':work_pointer,
                'caveatPointer':f'/cards/{n}/identity_binding/retrieval_caveat' if binding.get('retrieval_caveat') is not None else None,
                'qualificationPointers':qualification_pointers}


def project_research_sources(db,snapshot_id):
    """Caller owns a copied transaction;only append citations for retained work."""
    db.row_factory=sqlite3.Row;records=list(_records(db,snapshot_id,PublishedProfileAccess('unchecked')))
    if not records:raise ValueError('No source-qualified research citations in this snapshot')
    before=db.execute('SELECT count(*) FROM relation WHERE predicate=?',(PREDICATE,)).fetchone()[0]
    writer=CaptureWriter(db)
    for item in records:
        writer.relation(item['subjectId'],PREDICATE,writer.entity('web_resource',item['url']),
            snapshot_id,item['pointer'],None,item['attrs'])
    return {'researchSourceObservations':db.execute('SELECT count(*) FROM relation WHERE predicate=?',(PREDICATE,)).fetchone()[0]-before,
        'sourceSnapshotId':snapshot_id,'sourceAccounts':len({r['accountId'] for r in records}),
        'citedUrlOccurrences':len(records),'distinctAccountUrls':len({(r['accountId'],r['url']) for r in records})}


def read_research_sources(db,*,account_id=None,value=None,limit=40,published_access=None):
    """Validate against original source and admitted work anchor before limits."""
    if account_id is not None and (not isinstance(account_id,str) or not re.fullmatch('[0-9]+',account_id)):
        raise ValueError('Research citation account ID must be an exact numeric string')
    if limit is not None and (type(limit) is not int or not 1<=limit<=100):raise ValueError('Research citation limit must be1–100')
    db.row_factory=sqlite3.Row;access=published_access or PublishedProfileAccess()
    rows=db.execute("""SELECT r.*,a.source_key account_id,a.kind account_kind,t.kind target_kind,t.source_key url
      FROM relation r JOIN entity a ON a.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id
      WHERE r.predicate=? ORDER BY r.snapshot_id,r.source_pointer""",(PREDICATE,)).fetchall()
    expected={}
    for sid in sorted({r['snapshot_id'] for r in rows}):
        for record in _records(db,sid,access):
            if account_id is None or record['accountId']==account_id:expected[(sid,record['pointer'])]=record
    found=set();groups={}
    for row in rows:
        key=(row['snapshot_id'],row['source_pointer']);record=expected.get(key)
        if record is None:continue  # A hidden parent is never a citation fallback.
        if (row['account_kind']!='x_account' or row['account_id']!=record['accountId']
                or row['target_kind']!='web_resource' or row['url']!=record['url']
                or json.loads(row['attributes_json'])!=record['attrs'] or row['observed_at'] is not None):
            raise ValueError('Projected research citation disagrees with its original source')
        found.add(key)
        if value is not None and row['url']!=value:continue
        attrs=record['attrs'];group_key=(row['account_id'],row['url'],json.dumps(attrs,sort_keys=True))
        item=groups.setdefault(group_key,{'accountId':row['account_id'],'url':row['url'],
            **{k:v for k,v in attrs.items() if k!='producer'},'sourceRefs':[]})
        ref={'predicate':PREDICATE,'snapshotId':row['snapshot_id'],
            'sourcePointer':row['source_pointer'],'observedAt':None,'status':'reported',
            'researchContextPointer':record['contextPointer'],'workPointer':record['workPointer'],
            'retrievalCaveatPointer':record['caveatPointer']}
        if record['qualificationPointers']:ref['qualificationPointers']=record['qualificationPointers']
        item['sourceRefs'].append(ref)
    items=[groups[k] for k in sorted(groups)];missing=len(expected.keys()-found)
    return {'status':'partial' if missing else 'available' if expected else 'not_present',
        'accountId':account_id,'total':len(items),'observationCount':len(found),'missingObservations':missing,
        'items':items if limit is None else items[:limit],'truncated':limit is not None and len(items)>limit}


def research_source_value_matches(db,value,*,published_access=None):
    result=read_research_sources(db,value=value,limit=None,published_access=published_access);by_account={}
    for item in result['items']:
        by_account.setdefault(item['accountId'],[]).append({**item,'kind':'research_source','value':item['url']})
    return {'status':result['status'],'missingObservations':result['missingObservations'],'byAccount':by_account}
