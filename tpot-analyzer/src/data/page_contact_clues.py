"""Literal page affordances,not account-owned or reviewed contact routes."""
import hashlib
import json
import re
import sqlite3

from src.data.saved_capture_import import CaptureWriter,public_url
from src.data.website_evidence import PRODUCER as PAGE_PRODUCER,website_page_observations
from src.enrichment.website_context import EMAIL
from src.data.published_profile_access import PublishedProfileAccess

PRODUCER='saved-page-contact-clues-v1'
POLICY=('sourceKind','archiveExportId','profileFileRef','packageRef','eligibilityRef','boundary',
        'observingAccountId','cacheObservationId','associationRef')
PREDICATES=('page_lists_email','page_has_message_form')


def _json(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def _items(page,observation):
    if page.get('evidenceRef',{}).get('parserVersion')!='website-context-v2':return
    for field,predicate in zip(('emailClues','messageForms'),PREDICATES):
        items=page.get(field,[])
        if not isinstance(items,list):raise ValueError('Saved page contact clues must be arrays')
        for index,item in enumerate(items):
            if not isinstance(item,dict):raise ValueError('Saved page contact clue must be an object')
            if field=='emailClues':
                keys=('address','kind','label','context')
                if (any(not isinstance(item.get(k),str) for k in keys)
                        or not EMAIL.fullmatch(item['address']) or item['kind'] not in ('mailto','visible_text')):
                    raise ValueError('Saved page email clue is malformed')
                target_kind,target='email_address',item['address'];kind='email'
            else:
                keys=('action','method','context','tested')
                if (any(k not in item for k in keys)
                        or item.get('action') is not None and public_url(item['action'])!=item['action']
                        or not isinstance(item.get('method'),str) or not isinstance(item.get('context'),str)
                        or item.get('tested') is not False):
                    raise ValueError('Saved page message-form clue is malformed or tested')
                target_kind='message_form';target=hashlib.sha256(_json([observation,index]).encode()).hexdigest()
                kind='message_form'
            yield predicate,target_kind,target,f'/derived/{field}/{index}',kind,{k:item[k] for k in keys}


def append_page_contact_clues(writer,page,snapshot,observed,source_attrs):
    """Append from an exact already-retained derived page;caller owns transaction."""
    items=list(_items(page,source_attrs['cacheObservationId']))
    if not items:return 0
    raw=writer.db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(snapshot,)).fetchone()
    if raw is None or hashlib.sha256(raw[0]).hexdigest()!=snapshot:
        raise ValueError('Page contact source snapshot hash disagrees')
    payload=json.loads(raw[0]);original={k:v for k,v in page.items() if k not in ('graphEvidenceRef','association')}
    if (not isinstance(payload,dict) or not isinstance(payload.get('source'),dict)
            or payload.get('kind')!='cached-public-website-observation' or payload.get('producer')!=PAGE_PRODUCER
            or payload.get('visibility')!='private' or payload.get('derived')!=original
            or payload.get('source',{}).get('account_id')!=source_attrs.get('observingAccountId')
            or payload.get('source',{}).get('fetched_at')!=observed):
        raise ValueError('Page contact clue disagrees with its captured page')
    subject=writer.entity('web_resource',page['url']);added=0
    for predicate,target_kind,target,pointer,kind,clue in items:
        object_id=writer.entity(target_kind,target);before=writer.db.total_changes
        writer.relation(subject,predicate,object_id,snapshot,pointer,observed,
            {**{k:source_attrs[k] for k in POLICY if k in source_attrs},
             'producer':PRODUCER,'clueKind':kind,'clue':clue})
        added+=writer.db.total_changes-before
    return added


def project_page_contact_clues(db):
    """Offline backfill of independent admitted pages on a caller-owned copy."""
    db.row_factory=sqlite3.Row
    writer=CaptureWriter(db);added=bindings=0;captures=set();legacy=0
    for aid,page,attrs in list(website_page_observations(db)):
        if page.get('evidenceRef',{}).get('parserVersion')!='website-context-v2':legacy+=1;continue
        ref=page['graphEvidenceRef'];bindings+=1;captures.add((aid,ref['cacheObservationId']))
        added+=append_page_contact_clues(writer,page,ref['snapshotId'],ref['observedAt'],attrs)
    return {'qualifiedPageBindings':bindings,'capturedPages':len(captures),
            'legacyBindingsDeferred':legacy,'pageContactObservations':added}


def read_page_contact_clues(db,account_ids,*,published_access=None,limit=6,matching_value=None):
    """Only requested exact IDs and admitted page bindings;no ownership inference."""
    if (not isinstance(account_ids,list) or len(account_ids)>50
            or any(not isinstance(a,str) or not re.fullmatch('[0-9]+',a) for a in account_ids)
            or type(limit) is not int or not 1<=limit<=20):
        raise ValueError('Page contact read requires up to50 exact numeric IDs and limit1–20')
    if not account_ids:return {}
    db.row_factory=sqlite3.Row;access=published_access or PublishedProfileAccess()
    selected=set(account_ids);expected={};wanted={a:set() for a in selected};pages={a:set() for a in selected}
    limited={a:False for a in selected}
    legacy={a:set() for a in selected}
    for aid,page,_ in website_page_observations(db,published_access=access):
        if aid not in selected:continue
        ref=page['graphEvidenceRef'];observation=ref['cacheObservationId']
        if page.get('evidenceRef',{}).get('parserVersion')!='website-context-v2':
            legacy[aid].add(observation);continue
        pages[aid].add(observation)
        limited[aid]|=bool(page.get('emailCluesTruncated') or page.get('formsTruncated'))
        for predicate,target_kind,target,pointer,kind,clue in _items(page,observation):
            canonical=(observation,pointer,_json(clue));wanted[aid].add(canonical)
            key=(aid,observation,ref['snapshotId'],ref['associationRef']['relationId'],pointer)
            expected[key]=(canonical,predicate,target_kind,target,kind,clue,page)
    found={a:{} for a in selected}
    placeholders=','.join('?' for _ in selected)
    rows=db.execute(f'''SELECT r.*,s.kind subject_kind,s.source_key page_url,
      t.kind target_kind,t.source_key target FROM relation r
      JOIN entity s ON s.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id
      WHERE r.predicate IN (?,?) AND json_extract(r.attributes_json,'$.observingAccountId') IN ({placeholders})
      ORDER BY r.observed_at DESC,r.relation_id''',(*PREDICATES,*sorted(selected)))
    for row in rows:
        attrs=json.loads(row['attributes_json'])
        if not isinstance(attrs,dict):raise ValueError('Typed page contact attributes must be an object')
        if attrs.get('producer')!=PRODUCER:continue
        aid=attrs.get('observingAccountId')
        if not access.allows(attrs,aid):continue
        if not isinstance(attrs.get('associationRef'),dict):raise ValueError('Typed page contact association is malformed')
        key=(aid,attrs.get('cacheObservationId'),row['snapshot_id'],
             attrs.get('associationRef',{}).get('relationId'),row['source_pointer'])
        if key not in expected:continue  # Hidden or unbound source is not a contact fallback.
        canonical,predicate,target_kind,target,kind,clue,page=expected[key]
        if (row['predicate']!=predicate or row['subject_kind']!='web_resource' or row['page_url']!=page['url']
                or row['target_kind']!=target_kind or row['target']!=target or attrs.get('clue')!=clue
                or attrs.get('clueKind')!=kind or row['observed_at']!=page['graphEvidenceRef']['observedAt']):
            raise ValueError('Typed page contact clue disagrees with admitted source')
        found[aid].setdefault(canonical,{'kind':kind,'clue':clue,'sourceUrl':page['url'],
            'capturedAt':row['observed_at'],'targetKey':target,'evidenceRef':{
                'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
                'associationRef':page['graphEvidenceRef']['associationRef']}})
    result={}
    for aid in sorted(selected):
        values=sorted(found[aid].values(),key=lambda item:(item['sourceUrl'],item['kind'],_json(item['clue'])))
        missing=len(wanted[aid]-found[aid].keys())
        deferred=len(legacy[aid]-pages[aid])
        incomplete=bool(missing or deferred)
        shown=values if matching_value is None else [v for v in values if v['kind']=='email' and v['clue']['address']==matching_value]
        result[aid]={'status':'partial' if incomplete and values else 'not_projected' if incomplete else 'available',
            'accountId':aid,'emailStrings':len({v['clue']['address'] for v in values if v['kind']=='email'}),
            'messageForms':len({v['targetKey'] for v in values if v['kind']=='message_form'}),
            'pageObservations':len(pages[aid]),'legacyPageObservations':deferred,
            'observationCount':len(values),'missingObservations':missing,
            'items':shown[:limit],'truncated':len(shown)>limit,'sourceTruncated':limited[aid]}
    return result


def page_email_matches(db,value,*,published_access=None):
    """Search admitted source emails,not generic forms or only projected children."""
    candidates=set();captures=set();partial=False
    for aid,page,_ in website_page_observations(db,published_access=published_access):
        captures.add((aid,page['graphEvidenceRef']['cacheObservationId']))
        partial|=page.get('evidenceRef',{}).get('parserVersion')!='website-context-v2'
        partial|=bool(page.get('emailCluesTruncated'))
        for _,_,_,_,kind,clue in _items(page,page['graphEvidenceRef']['cacheObservationId']):
            if kind=='email' and clue['address']==value:candidates.add(aid)
    matches={};ids=sorted(candidates)
    for start in range(0,len(ids),50):
        qualified=read_page_contact_clues(db,ids[start:start+50],published_access=published_access,
                                        matching_value=value,limit=20)
        for aid,out in qualified.items():
            partial|=out['status']!='available' or out['sourceTruncated'] or out['truncated']
            if out['items']:matches[aid]=[{**item,'kind':'page_email'} for item in out['items']]
    return {'status':'partial' if partial else 'available' if captures else 'not_present',
            'capturedPages':len(captures),'byAccount':matches}
