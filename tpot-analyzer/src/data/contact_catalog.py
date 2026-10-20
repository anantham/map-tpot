"""Historical exported channel mentions,not verified identities or contact routes."""
import hashlib
import json
import re
import sqlite3

from src.data.published_profile_access import SOURCE_KIND
from src.data.saved_capture_import import CaptureWriter,public_url
from src.enrichment.website_context import EMAIL

PRODUCER='saved-contact-channel-catalog-v1'
ENTRY='contact_catalog_observation'
MENTION='research_mentions_channel'
OTHER={'bluesky','mastodon','telegram','threads','substack'}


def _json(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def _attrs(row):
    value=json.loads(row['attributes_json'])
    if not isinstance(value,dict):raise ValueError('Channel observation attributes must be an object')
    return value


def _snapshot(db,sid):
    if not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{64}',sid):
        raise ValueError('Channel sources require an exact retained snapshot ID')
    row=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(sid,)).fetchone()
    if row is None or not isinstance(row[0],bytes) or hashlib.sha256(row[0]).hexdigest()!=sid:
        raise ValueError('Channel source snapshot is missing or disagrees with its hash')
    return json.loads(row[0])


def _values(person,index):
    fields=[]
    for field in ('email','linkedin','instagram'):
        if not isinstance(person.get(field),list):raise ValueError('Channel catalogue public fields must be arrays')
        fields.append((field,person[field]))
    other=person.get('other')
    if not isinstance(other,dict) or set(other)-OTHER:
        raise ValueError('Channel catalogue has an unsupported public category')
    for field,items in other.items():
        if not isinstance(items,list):raise ValueError('Channel catalogue categories must be arrays')
        fields.append(('other/'+field,items))
    for field,items in fields:
        for number,value in enumerate(items):
            if (not isinstance(value,str) or value.strip()!=value or any(ord(c)<32 for c in value)
                    or (not EMAIL.fullmatch(value) if field=='email' else public_url(value)!=value)):
                raise ValueError('Channel catalogue contains an invalid literal public value')
            yield {'kind':'email' if field=='email' else 'url','value':value,
                   'category':field.replace('/','.'),'pointer':f'/people/{index}/{field}/{number}'}


def _catalog(payload):
    if (not isinstance(payload,dict) or not isinstance(payload.get('people'),list)
            or not 1<=len(payload['people'])<=20000 or not isinstance(payload.get('generated'),str)
            or not isinstance(payload.get('method'),str)):
        raise ValueError('Channel catalogue envelope is invalid')
    for index,person in enumerate(payload['people']):
        if (not isinstance(person,dict) or not isinstance(person.get('handle'),str)
                or not re.fullmatch('[A-Za-z0-9_]{1,15}',person['handle'])):
            raise ValueError('Channel catalogue requires valid captured handles')
        list(_values(person,index))  # Validate only the allowlisted public fields.
    return payload['people']


def _binding(db,sid,pointer,aid,handle):
    rows=db.execute("""SELECT r.*,e.source_key account_id FROM relation r JOIN entity e ON e.entity_id=r.subject_id
      WHERE r.predicate='profile_observation' AND r.snapshot_id=? AND r.source_pointer=?
      AND e.kind='x_account' AND e.source_key=?""",(sid,pointer,aid)).fetchall()
    if len(rows)!=1:raise ValueError('Channel binding requires one exact retained profile observation')
    row=rows[0];attrs=_attrs(row)
    if attrs.get('sourceKind')==SOURCE_KIND or not isinstance(attrs.get('handle'),str) or attrs['handle'].casefold()!=handle.casefold():
        raise ValueError('Channel binding is not the independent captured-handle witness')
    return {'relationId':row['relation_id'],'snapshotId':sid,'sourcePointer':pointer,
            'accountId':aid,'handle':attrs['handle'],'observedAt':row['observed_at']}


def import_contact_catalog(db,path,profile_witness):
    """Caller owns a copied graph/transaction;private fields remain raw-only."""
    db.row_factory=sqlite3.Row;writer=CaptureWriter(db)
    sid,payload=writer.source(path);people=_catalog(payload)
    profiles=_snapshot(db,profile_witness)
    if not isinstance(profiles,list) or not profiles:raise ValueError('Channel profile witness must be a saved capture list')
    by_handle={}
    for n,profile in enumerate(profiles):
        if (not isinstance(profile,dict) or not isinstance(profile.get('account_id'),str)
                or not re.fullmatch('[0-9]+',profile['account_id']) or not isinstance(profile.get('handle'),str)):
            raise ValueError('Channel profile witness has an invalid identity')
        by_handle.setdefault(profile['handle'].casefold(),[]).append((n,profile['account_id']))
    domains=db.execute("SELECT DISTINCT json_extract(attributes_json,'$.bindingRef.snapshotId') FROM relation WHERE predicate=? AND snapshot_id=?",(ENTRY,sid))
    if any(row[0]!=profile_witness for row in domains):raise ValueError('Catalogue is already bound to a different frozen profile witness')
    before={p:db.execute('SELECT count(*) FROM relation WHERE predicate=?',(p,)).fetchone()[0] for p in (ENTRY,MENTION)}
    for index,person in enumerate(people):
        candidates=by_handle.get(person['handle'].casefold(),[])
        if len(candidates)!=1:raise ValueError('Catalogue handle is missing or ambiguous in the frozen profile witness')
        n,aid=candidates[0];binding=_binding(db,profile_witness,f'/{n}',aid,person['handle'])
        account=writer.entity('x_account',aid);entry=writer.entity('contact_catalog_entry',_json([sid,index]))
        writer.relation(account,ENTRY,entry,sid,f'/people/{index}',None,
            {'producer':PRODUCER,'capturedHandle':person['handle'],
             'timestampLiteral':payload['generated'],'bindingRef':binding})
        for item in _values(person,index):
            target=writer.entity('email_address' if item['kind']=='email' else 'web_resource',item['value'])
            writer.relation(entry,MENTION,target,sid,item['pointer'],None,
                {'producer':PRODUCER,'kind':item['kind'],'category':item['category']})
    return {'catalogSnapshotId':sid,'profileWitnessSnapshotId':profile_witness,'catalogEntries':len(people),
        'newCatalogEntries':db.execute('SELECT count(*) FROM relation WHERE predicate=?',(ENTRY,)).fetchone()[0]-before[ENTRY],
        'channelMentions':db.execute('SELECT count(*) FROM relation WHERE predicate=?',(MENTION,)).fetchone()[0]-before[MENTION]}


def read_contact_catalog(db,account_ids,*,limit=8,matching_value=None):
    """Source-qualified,requested-ID-only metadata; no raw/private fields escape."""
    if (not isinstance(account_ids,list) or len(account_ids)>50 or type(limit) is not int or not 1<=limit<=20
            or any(not isinstance(a,str) or not re.fullmatch('[0-9]+',a) for a in account_ids)):
        raise ValueError('Channel read requires up to50 exact IDs and limit1–20')
    if not account_ids:return {}
    db.row_factory=sqlite3.Row;placeholders=','.join('?' for _ in account_ids)
    rows=db.execute(f"""SELECT r.*,a.source_key account_id,t.kind target_kind,t.source_key entry_key
      FROM relation r JOIN entity a ON a.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id
      WHERE r.predicate=? AND a.kind='x_account' AND a.source_key IN ({placeholders})
      AND json_extract(r.attributes_json,'$.producer')=? ORDER BY r.snapshot_id,r.source_pointer""",(ENTRY,*account_ids,PRODUCER)).fetchall()
    sources={};result={};groups={}
    for row in rows:
        attrs=_attrs(row);sid=row['snapshot_id'];aid=row['account_id']
        if sid not in sources:
            payload=_snapshot(db,sid);sources[sid]=(payload,_catalog(payload))
        payload,people=sources[sid];match=re.fullmatch('/people/(0|[1-9][0-9]*)',row['source_pointer'])
        if not match or int(match[1])>=len(people):raise ValueError('Channel entry pointer is outside its source')
        index=int(match[1]);person=people[index]
        if (row['target_kind']!='contact_catalog_entry' or row['entry_key']!=_json([sid,index])
                or attrs.get('capturedHandle')!=person['handle'] or attrs.get('timestampLiteral')!=payload['generated']
                or row['observed_at'] is not None or not isinstance(attrs.get('bindingRef'),dict)):
            raise ValueError('Channel entry disagrees with its original source')
        ref=attrs['bindingRef']
        if _binding(db,ref.get('snapshotId'),ref.get('sourcePointer'),aid,person['handle'])!=ref:
            raise ValueError('Channel entry frozen binding disagrees')
        out=result.setdefault(aid,{'status':'available','accountId':aid,'entryCount':0,'distinctValues':0,
            'totalOccurrences':0,'missingOccurrences':0,'catalogs':[],'items':[],'truncated':False})
        out['entryCount']+=1;out['catalogs'].append({'timestampLiteral':payload['generated'],
            'sourceRef':{'snapshotId':sid,'sourcePointer':row['source_pointer']},'bindingRef':ref})
        expected={v['pointer']:v for v in _values(person,index)};out['totalOccurrences']+=len(expected);found=set()
        children=db.execute("""SELECT r.*,t.kind target_kind,t.source_key value FROM relation r
          JOIN entity t ON t.entity_id=r.object_id WHERE r.subject_id=? AND r.predicate=? AND r.snapshot_id=?
          ORDER BY r.source_pointer""",(row['object_id'],MENTION,sid))
        for child in children:
            child_attrs=_attrs(child);item=expected.get(child['source_pointer'])
            if (item is None or child_attrs!={'producer':PRODUCER,'kind':item['kind'],'category':item['category']}
                    or child['target_kind']!=('email_address' if item['kind']=='email' else 'web_resource')
                    or child['value']!=item['value'] or child['observed_at'] is not None):
                raise ValueError('Channel mention disagrees with its original source')
            if child['source_pointer'] in found:raise ValueError('Channel source pointer has conflicting duplicate observations')
            found.add(child['source_pointer']);key=(aid,item['kind'],item['value'])
            group=groups.setdefault(key,{'kind':item['kind'],'value':item['value'],'categories':set(),'sourceRefs':[]})
            group['categories'].add(item['category']);group['sourceRefs'].append({'snapshotId':sid,
                'sourcePointer':child['source_pointer'],'entryPointer':row['source_pointer']})
        out['missingOccurrences']+=len(expected)-len(found)
    for aid,out in result.items():
        values=[{**v,'categories':sorted(v['categories'])} for (account,_,_),v in groups.items() if account==aid]
        values.sort(key=lambda v:(v['kind'],v['value']))
        shown=values if matching_value is None else [v for v in values if v['value']==matching_value]
        out.update(status='partial' if out['missingOccurrences'] else 'available',distinctValues=len(values),
                   items=shown[:limit],truncated=len(shown)>limit)
    return result


def catalog_value_matches(db,value):
    """Inspect original public values before typed-child/presentation limits."""
    db.row_factory=sqlite3.Row
    rows=db.execute("""SELECT r.snapshot_id,r.source_pointer,a.source_key account_id
      FROM relation r JOIN entity a ON a.entity_id=r.subject_id
      WHERE r.predicate=? AND a.kind='x_account'
      AND json_extract(r.attributes_json,'$.producer')=?""",(ENTRY,PRODUCER)).fetchall()
    sources={};bindings={};candidates=set();partial=False
    for row in rows:
        bindings.setdefault((row['snapshot_id'],row['source_pointer']),set()).add(row['account_id'])
        if row['snapshot_id'] not in sources:
            sources[row['snapshot_id']]=_catalog(_snapshot(db,row['snapshot_id']))
    for sid,people in sources.items():
        for index,person in enumerate(people):
            aids=bindings.get((sid,f'/people/{index}'),set())
            partial|=len(aids)!=1
            if any(item['value']==value for item in _values(person,index)):candidates.update(aids)
    matches={};ids=sorted(candidates)
    for start in range(0,len(ids),50):
        qualified=read_contact_catalog(db,ids[start:start+50],matching_value=value)
        for aid,out in qualified.items():
            partial|=out['status']!='available'
            if out['items']:
                matches[aid]=[{'kind':'catalogue','item':item,'catalogs':out['catalogs']}
                              for item in out['items']]
    return {'status':'partial' if partial else 'available' if rows else 'not_present',
            'entryObservations':len(rows),'byAccount':matches}
