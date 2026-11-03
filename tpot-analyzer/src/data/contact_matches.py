"""Private recovered-link candidates and reversible curator association decisions.

No raw, tag or relationship store writes. Confirmation is a curator opinion,
not a verified identity edge or permission to contact anyone.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

STATES=('possible','confirmed','rejected')
SCOPES=('person','organisation','reference','unknown')
KINDS=('profile','website','email','contact_form','contact_page')
SOURCE_TYPES=('historical_cache','saved_destination','saved_bio_mention','public_research')
BOUNDARY='Your association decision only; not verified ownership, current contactability or permission to contact.'
logger=logging.getLogger(__name__)


def _text(value, limit, *, empty=False):
    if (not isinstance(value,str) or len(value)>limit or value!=value.strip()
            or not empty and not value or any(ord(c)<32 for c in value)):
        raise ValueError('Recovered candidate text is invalid')
    return value


def _url(value):
    value=_text(value,2048);parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Recovered candidate URL must be public HTTP(S) without credentials')
    return value


def _private(path):
    path=Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Recovered evidence must be stored privately')
    return path


def normalize_match_subject(account_id,ego):
    if not isinstance(account_id,str) or not re.fullmatch('[0-9]{1,30}',account_id):
        raise ValueError('Exact numeric account ID is required')
    if not isinstance(ego,str):raise ValueError('Reviewer identity is required')
    ego=ego.strip().removeprefix('@').casefold()
    if not re.fullmatch('[a-z0-9_]{1,64}',ego):raise ValueError('Reviewer identity is required')
    return account_id,ego


def load_candidates(path):
    """Allowlist prepared observations; never expose arbitrary input fields."""
    path=_private(path)
    if path.stat().st_size>20_000_000:raise ValueError('Recovered catalogue exceeds size limit')
    payload=json.loads(path.read_bytes())
    if not isinstance(payload,dict) or type(payload.get('schemaVersion')) is not int or payload['schemaVersion']!=1:
        raise ValueError('Unsupported recovered catalogue version')
    rows=payload.get('candidates')
    if not isinstance(rows,list) or len(rows)>20000:raise ValueError('Recovered catalogue requires a bounded candidate list')
    result={}
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Recovered candidate must be an object')
        aid,_=normalize_match_subject(row.get('accountId'),'validation')
        kind=row.get('kind');scope=row.get('scope')
        if kind not in KINDS or scope not in SCOPES:raise ValueError('Recovered candidate kind/scope is invalid')
        value=_text(row.get('value'),2048)
        if kind=='email':
            if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value):raise ValueError('Invalid recovered email clue')
        else:_url(value)
        platform=_text(row.get('platform'),80)
        evidence=row.get('evidence')
        if not isinstance(evidence,list) or not 1<=len(evidence)<=30:raise ValueError('Recovered candidate needs source evidence')
        refs=[]
        for source in evidence:
            if not isinstance(source,dict) or source.get('sourceType') not in SOURCE_TYPES:
                raise ValueError('Recovered source type is invalid')
            when=source.get('observedAt')
            if when is not None:_text(when,80)
            ref={'url':_url(source.get('url')),'note':_text(source.get('note'),4000),
                 'observedAt':when,'sourceType':source['sourceType']}
            if 'sourcePointer' in source:ref['sourcePointer']=_text(source['sourcePointer'],500)
            if 'sourceDigest' in source:
                if not isinstance(source['sourceDigest'],str) or not re.fullmatch('[0-9a-f]{64}',source['sourceDigest']):
                    raise ValueError('Recovered source digest is invalid')
                ref['sourceDigest']=source['sourceDigest']
            if ref not in refs:refs.append(ref)
        identity={'accountId':aid,'value':value,'kind':kind,'scope':scope,'platform':platform}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        item={**identity,'candidateId':key,'evidence':refs}
        if key in result:raise ValueError('Duplicate recovered candidate identity')
        result[key]=item
    return result


def _decisions(path,aid,ego):
    path=Path(path)
    if not path.exists():return {}
    path=_private(path)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        rows=db.execute('SELECT candidate_id,state,created_at,event_id FROM contact_match_events '
            'WHERE account_id=? AND ego=? ORDER BY event_id',(aid,ego)).fetchall()
    return {key:{'state':state,'reviewedAt':when,'eventId':event} for key,state,when,event in rows}


def contact_match_preview(catalogue,journal,*,account_id,ego):
    aid,ego=normalize_match_subject(account_id,ego)
    candidates=load_candidates(catalogue)
    decisions=_decisions(journal,aid,ego)
    items=[{**item,**decisions.get(key,{'state':'possible','reviewedAt':None,'eventId':None})}
           for key,item in candidates.items() if item['accountId']==aid]
    return {'status':'available','accountId':aid,'ego':ego,'matches':items,'boundary':BOUNDARY}


def attach_roster_clue_counts(roster,catalogue):
    """Optional catalogue coverage, never candidate values or a contact-completeness claim."""
    status='not_configured';counts={}
    if catalogue:
        try:
            for item in load_candidates(catalogue).values():
                aid=item['accountId'];counts[aid]=counts.get(aid,0)+1
            status='available'
        except (OSError,ValueError,RuntimeError) as error:
            logger.warning('Recovered roster clue counts unavailable (%s)',type(error).__name__)
            status='unavailable'
    rows=[]
    for row in roster['accounts']:
        admitted=bool(row.get('locatorSource',{}).get('evidenceRef'))
        rows.append({**row,'recoveredClueCount':counts.get(row['accountId'],0)
                     if status=='available' and admitted else None})
    summary={'status':status}
    if status=='available':
        summary.update(accounts=sum(bool(row['recoveredClueCount']) for row in rows),
                       candidates=sum(row['recoveredClueCount'] or 0 for row in rows))
    return {**roster,'accounts':rows,'recoveredClues':summary}


def roster_platform_associations(roster,catalogue,journal):
    """Platform names only, with curator-scoped decisions; no ownership claim."""
    empty={'status':'not_admitted','confirmed':[],'possible':[],'rejected':[]}
    result={row['accountId']:dict(empty) for row in roster['accounts']}
    admitted={row['accountId'] for row in roster['accounts']
              if row.get('locatorSource',{}).get('evidenceRef')}
    try:
        if not catalogue or not journal:raise ValueError('Association sources are not configured')
        candidates=load_candidates(catalogue);decisions={}
        if Path(journal).exists():
            path=_private(journal)
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
                rows=db.execute('SELECT account_id,candidate_id,state FROM contact_match_events '
                    'WHERE ego=? ORDER BY event_id',(roster['ego'],))
                decisions={(aid,key):state for aid,key,state in rows}
        for aid in admitted:result[aid]={'status':'available','confirmed':[],'possible':[],'rejected':[]}
        for key,item in candidates.items():
            aid=item['accountId']
            if aid not in admitted or item['kind']!='profile':continue
            state=decisions.get((aid,key),'possible')
            if state not in STATES:raise ValueError('Invalid stored association state')
            if item['platform'] not in result[aid][state]:result[aid][state].append(item['platform'])
        for aid in admitted:
            for state in STATES:result[aid][state].sort()
    except (OSError,ValueError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Roster platform decisions unavailable (%s)',type(error).__name__)
        for aid in admitted:result[aid]={**empty,'status':'unavailable'}
    return result


def record_contact_match(catalogue,journal,*,account_id,ego,candidate_id,state,source):
    aid,ego=normalize_match_subject(account_id,ego)
    if state not in STATES:raise ValueError('State must be possible, confirmed or rejected')
    if not isinstance(candidate_id,str):raise ValueError('Candidate ID is required')
    candidate=load_candidates(catalogue).get(candidate_id)
    if candidate is None or candidate['accountId']!=aid:raise LookupError('Candidate does not belong to this account')
    if source not in ('human_curator_api','agent_assisted_curator','verification_script'):
        raise ValueError('Valid curation source is required')
    journal=Path(journal)
    if journal.name!='person_card_reviews.db':raise ValueError('A separate person_card_reviews.db is required')
    journal.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if journal.exists():_private(journal)
    else:
        try:
            fd=os.open(journal,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        except FileExistsError:_private(journal)
    with closing(sqlite3.connect(journal,timeout=5)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS contact_match_events('
            'event_id INTEGER PRIMARY KEY,ego TEXT NOT NULL,account_id TEXT NOT NULL,'
            'candidate_id TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN (\'possible\',\'confirmed\',\'rejected\')),'
            'source TEXT NOT NULL,created_at TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS contact_match_subject '
                   'ON contact_match_events(ego,account_id,candidate_id,event_id)')
        prior=db.execute('SELECT state FROM contact_match_events WHERE ego=? AND account_id=? '
            'AND candidate_id=? ORDER BY event_id DESC LIMIT 1',(ego,aid,candidate_id)).fetchone()
        if prior is None or prior[0]!=state:
            db.execute('INSERT INTO contact_match_events(ego,account_id,candidate_id,state,source,created_at) '
                'VALUES(?,?,?,?,?,?)',(ego,aid,candidate_id,state,source,datetime.now(timezone.utc).isoformat()))
    return contact_match_preview(catalogue,journal,account_id=aid,ego=ego)
