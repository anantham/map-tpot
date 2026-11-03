"""Separate historical handle observations; never resolve them to numeric IDs."""
import hashlib
import json
import logging
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from src.data.saved_capture_import import CaptureWriter, append_profile_bio_links
from src.data.shadow_profile_counts import captured_profile_counts

logger=logging.getLogger(__name__)
PRODUCER='shadow-handle-observations-v1'
FOLLOW='shadow_follows_observed'
PROFILE='shadow_profile_observation'
SCOPE='shadow_scope_observation'
CHANNELS={'hybrid_selenium','x_api','selenium_profile_scrape'}
BOUNDARY=('Historical observations for this handle, not a verified match to the current '
          'account or person. No numeric identity merge, membership, friendship or competence is inferred.')


def _alias(handle):
    if not isinstance(handle,str) or not re.fullmatch('[A-Za-z0-9_]{1,15}',handle):
        raise ValueError('Shadow evidence requires an exact valid handle')
    return 'shadow:'+handle.casefold()


def _kind(key):
    if isinstance(key,str) and re.fullmatch('[0-9]+',key):return 'x_account'
    if isinstance(key,str) and re.fullmatch('shadow:[A-Za-z0-9_]{1,15}',key):return 'unresolved_account'
    raise ValueError('Unsupported shadow endpoint identity')


def _time_basis(value):
    try:moment=datetime.fromisoformat(value)
    except (ValueError,TypeError) as error:raise ValueError('Shadow capture date is malformed') from error
    return 'Stored capture time; timezone unspecified' if moment.utcoffset() is None else 'Stored timezone-aware capture time'


def _snapshot(db,path,table,row):
    payload={'producer':PRODUCER,'visibility':'private','sourceTable':table,'row':row}
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    key=hashlib.sha256(raw).hexdigest()
    db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES(?,?,?,?)',
        (key,str(path)+'#'+table,None,raw))
    return key


def _bio_link_count(db):
    return db.execute("SELECT count(*) FROM relation WHERE predicate='profile_links_to' "
        "AND json_extract(attributes_json,'$.producer')='profile-bio-links-v2'").fetchone()[0]


def project_shadow_bio_links(db):
    """Backfill existing independent profile claims on a caller-owned graph copy."""
    db.row_factory=sqlite3.Row
    writer=CaptureWriter(db);before=_bio_link_count(db);profiles=0
    rows=db.execute("SELECT e.source_key,r.* FROM relation r JOIN entity e ON e.entity_id=r.subject_id "
        "WHERE e.kind='unresolved_account' AND r.predicate=? ORDER BY r.relation_id",(PROFILE,)).fetchall()
    for row in rows:
        attrs=json.loads(row['attributes_json'])
        if not isinstance(attrs,dict):raise ValueError('Historical bio-link profile fields are malformed')
        if attrs.get('sourceChannel') not in CHANNELS:continue
        if _alias(attrs.get('username'))!=row['source_key']:
            raise ValueError('Historical bio-link profile identity disagrees')
        if attrs.get('fetched_at')!=row['observed_at']:
            raise ValueError('Historical bio-link source dates disagree')
        basis=_time_basis(row['observed_at'])
        profiles+=1
        append_profile_bio_links(writer,row['subject_id'],row['snapshot_id'],row['source_pointer'],
            row['observed_at'],attrs.get('bio'),{'sourceChannel':attrs['sourceChannel'],'captureTimeBasis':basis},
            include_bare=True)
    return {'historicalProfileObservations':profiles,'bioLinkObservations':_bio_link_count(db)-before}


def shadow_bio_links(db, profile_row, profile):
    """Only links from the exact displayed historical profile observation."""
    from src.enrichment.bio_url_mentions import normalize_bio_url
    db.row_factory=sqlite3.Row
    rows=db.execute('SELECT r.*,t.source_key url FROM relation r JOIN entity t ON t.entity_id=r.object_id '
        "WHERE r.subject_id=? AND r.predicate='profile_links_to' AND t.kind='web_resource' "
        'AND r.snapshot_id=? AND r.source_pointer=? AND r.observed_at IS ?',
        (profile_row['subject_id'],profile_row['snapshot_id'],profile_row['source_pointer']+'/bio',
         profile_row['observed_at'])).fetchall()
    links=[]
    for row in rows:
        attrs=json.loads(row['attributes_json'])
        if attrs.get('producer')!='profile-bio-links-v2':continue
        literal=attrs.get('bioUrlText');assumed=attrs.get('bioSchemeAssumed')
        if (not isinstance(literal,str) or literal not in (profile.get('bio') or '')
                or attrs.get('sourceChannel')!=profile['sourceChannel']
                or normalize_bio_url(literal,assumed)!=row['url']
                or type(attrs.get('bioUrlIndex')) is not int or attrs['bioUrlIndex']<0):
            raise ValueError('Historical bio link disagrees with its source profile')
        links.append({'url':row['url'],'literal':literal,'schemeAssumed':assumed,
            'sourceIndex':attrs['bioUrlIndex'],'evidenceRef':_ref(row),
            'sourceChannel':attrs['sourceChannel'],'captureTimeBasis':profile.get('captureTimeBasis'),
            'association':attrs['association']})
    return sorted(links,key=lambda link:link['sourceIndex'])


def import_shadow_aliases(db, path, handles=None, *, limit=500,offset=0):
    """Append bounded neighborhoods or deterministic alias-row windows."""
    row_mode=handles is None
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=(10000 if row_mode else 2000):
        raise ValueError('Invalid shadow offset/limit; row windows allow1–10000 rows')
    if not row_mode and (not isinstance(handles,list) or not 1<=len(handles)<=20 or offset):
        raise ValueError('Select1–20 handles without a row offset')
    aliases=[] if row_mode else sorted({_alias(handle) for handle in handles})
    if not row_mode and len(aliases)!=len(handles):raise ValueError('Duplicate shadow handle selection')
    path=Path(path).resolve(strict=True)
    writer=CaptureWriter(db)
    report={'followObservations':0,'aliasProfiles':0,'selectedRows':0,'excludedSourceRows':0,
            'excludedProfileRows':0,'missingProfileRows':0,'scopes':[]}
    before=db.execute('SELECT count(*) FROM relation WHERE predicate=?',(FOLLOW,)).fetchone()[0]
    before_links=_bio_link_count(db)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as source:
        source.row_factory=sqlite3.Row;source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
        selected={}; endpoints=set();groups=[]
        if row_mode:
            domain="(source_id LIKE 'shadow:%' OR target_id LIKE 'shadow:%')"
            total=source.execute('SELECT count(*) FROM shadow_edge WHERE '+domain).fetchone()[0]
            self_rows=source.execute('SELECT count(*) FROM shadow_edge WHERE '+domain+' AND source_id=target_id').fetchone()[0]
            rows=[dict(r) for r in source.execute('SELECT * FROM shadow_edge WHERE '+domain+
                ' AND source_id!=target_id ORDER BY source_id,target_id,direction LIMIT ? OFFSET ?',(limit,offset))]
            report.update(rowMode=True,offset=offset,nextOffset=offset+len(rows),selectedRows=len(rows),
                totalAliasRowsAtImport=total,selfRowsExcludedFromDomain=self_rows,
                eligibleAliasRowsAtImport=total-self_rows,hasMore=offset+len(rows)<total-self_rows)
            groups.append(rows)
        for alias in aliases:
            total=source.execute('SELECT count(*) FROM shadow_edge WHERE source_id=? OR target_id=?',(alias,alias)).fetchone()[0]
            rows=[dict(row) for row in source.execute('SELECT * FROM shadow_edge WHERE source_id=? OR target_id=? ORDER BY source_id,target_id,direction LIMIT ?', (alias,alias,limit))]
            scope={'alias':alias,'selectedRows':len(rows),'totalRowsAtImport':total,
                   'truncated':total>len(rows),'limit':limit}
            report['scopes'].append(scope);report['selectedRows']+=len(rows)
            scope_id=_snapshot(db,path,'derived_shadow_selection',scope)
            node=writer.entity('unresolved_account',alias)
            writer.relation(node,SCOPE,node,scope_id,'/row',None,scope)
            groups.append(rows)
        for rows in groups:
            for row in rows:
                if row['source_channel'] not in CHANNELS:
                    report['excludedSourceRows']+=1;continue
                if row['direction'] not in ('inbound','outbound') or row['source_id']==row['target_id']:
                    raise ValueError('Invalid shadow edge direction or self edge')
                _kind(row['source_id']);_kind(row['target_id']);_time_basis(row['fetched_at'])
                try:metadata=json.loads(row['metadata'])
                except (ValueError,TypeError) as error:raise ValueError('Malformed shadow edge metadata') from error
                if not isinstance(metadata,dict):raise ValueError('Shadow metadata must be an object')
                selected[(row['source_id'],row['target_id'],row['direction'])]=row
                endpoints.update((row['source_id'],row['target_id']))
        for key in sorted(endpoints):
            if not key.startswith('shadow:'):continue
            profile=source.execute('SELECT * FROM shadow_account WHERE account_id=?',(key,)).fetchone()
            if profile is None:report['missingProfileRows']+=1;continue
            if profile['source_channel'] not in CHANNELS:report['excludedProfileRows']+=1;continue
            row=dict(profile)
            if _alias(row['username'])!=key:raise ValueError('Shadow profile handle and alias disagree')
            if any(row.get(field) is not None and not isinstance(row[field],str)
                   for field in ('display_name','bio','website','location')):
                raise ValueError('Shadow profile text has an unsupported type')
            snapshot=_snapshot(db,path,'shadow_account',row)
            attrs={field:row.get(field) for field in ('username','display_name','bio','website','location','fetched_at')}
            attrs.update(captured_profile_counts(row))
            attrs.update(sourceChannel=row['source_channel'],captureTimeBasis=_time_basis(row['fetched_at']))
            account=writer.entity('unresolved_account',key)
            writer.relation(account,PROFILE,
                writer.entity('shadow_profile',key),snapshot,'/row',row['fetched_at'],attrs)
            append_profile_bio_links(writer,account,snapshot,'/row',row['fetched_at'],row.get('bio'),
                {field:attrs[field] for field in ('sourceChannel','captureTimeBasis')},include_bare=True)
            report['aliasProfiles']+=1
        for row in selected.values():
            snapshot=_snapshot(db,path,'shadow_edge',row)
            attrs={'sourceChannel':row['source_channel'],'captureDirection':row['direction'],
                   'captureTimeBasis':_time_basis(row['fetched_at'])}
            writer.relation(writer.entity(_kind(row['source_id']),row['source_id']),FOLLOW,
                writer.entity(_kind(row['target_id']),row['target_id']),snapshot,'/row',row['fetched_at'],attrs)
        report['qualifiedFollowRows']=len(selected)
        report['followObservations']=(db.execute('SELECT count(*) FROM relation WHERE predicate=?',(FOLLOW,)).fetchone()[0]-before
                                      if row_mode else len(selected))
        report['bioLinkObservations']=_bio_link_count(db)-before_links
    return report


def _ref(row):
    return {'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
            'observedAt':row['observed_at']}


def shadow_alias_preview(path, *, handle, limit=20):
    """Separate bounded handle-only DTO; never a numeric-account supplement."""
    alias=_alias(handle)
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Shadow preview limit must be1–100')
    base={'alias':alias,'bindingStatus':'unresolved_handle_only','boundary':BOUNDARY}
    if not path:return {**base,'status':'not_configured'}
    try:
        file=Path(path).resolve(strict=True)
        if not file.is_file() or file.stat().st_mode & 0o077:raise ValueError('Graph must be private')
        with closing(sqlite3.connect(file.as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
            root=db.execute("SELECT entity_id FROM entity WHERE kind='unresolved_account' AND source_key=?",(alias,)).fetchone()
            if root is None:return {**base,'status':'not_imported'}
            scope=db.execute('SELECT * FROM relation WHERE subject_id=? AND predicate=? ORDER BY rowid DESC LIMIT 1',(root[0],SCOPE)).fetchone()
            if scope is None and not db.execute('SELECT 1 FROM relation WHERE predicate=? AND (subject_id=? OR object_id=?) LIMIT 1',
                    (FOLLOW,root[0],root[0])).fetchone():return {**base,'status':'not_imported'}
            nodes={}
            def node(entity_id):
                if entity_id not in nodes:
                    item=db.execute('SELECT kind,source_key FROM entity WHERE entity_id=?',(entity_id,)).fetchone()
                    profile=db.execute('SELECT * FROM relation WHERE subject_id=? AND predicate=? ORDER BY relation_id LIMIT 1',(entity_id,PROFILE)).fetchone()
                    attrs=json.loads(profile['attributes_json']) if profile else None
                    if attrs is not None:
                        if attrs.get('sourceChannel') not in CHANNELS:raise ValueError('Unsupported profile source')
                        attrs={**attrs,'evidenceRef':_ref(profile)}
                    nodes[entity_id]={'kind':item['kind'],'key':item['source_key'],'profile':attrs}
                return nodes[entity_id]
            scope_attrs=json.loads(scope['attributes_json']) if scope else {'selectionKind':'partial_import','truncated':True}
            result={**base,'status':'available','scope':scope_attrs,
                    'scopeRef':_ref(scope) if scope else None,'truncated':bool(scope_attrs['truncated'])}
            for name,column,other in [('outgoing','subject_id','object_id'),('incoming','object_id','subject_id')]:
                count=db.execute(f'SELECT count(DISTINCT {other}) FROM relation WHERE {column}=? AND predicate=?',(root[0],FOLLOW)).fetchone()[0]
                rows=db.execute(f'''WITH ranked AS (SELECT *,count(*) OVER(PARTITION BY subject_id,object_id) n,
                    row_number() OVER(PARTITION BY subject_id,object_id ORDER BY relation_id) position
                    FROM relation WHERE {column}=? AND predicate=?)
                    SELECT * FROM ranked WHERE position=1 ORDER BY subject_id,object_id LIMIT ?''',(root[0],FOLLOW,limit)).fetchall()
                result[name+'Count']=count;result['truncated']|=count>len(rows)
                result[name]=[{**_ref(row),**json.loads(row['attributes_json']),
                    'observationCount':row['n'],'source':node(row['subject_id']),
                    'target':node(row['object_id'])} for row in rows]
            return result
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as error:
        logger.warning('Stored shadow observations unavailable (%s)',type(error).__name__)
        return {**base,'status':'unavailable'}
