"""Read-only literal clues from already-admitted exact-account profile fields.

Channel text is not an owned account, a verified contact route or a URL template.
No crawling, person matching, graph writes or timestamp inference happens here.
"""
import json
import logging
import re
import sqlite3

from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_evidence import PROFILE_SQL, read_saved_store
from src.data.website_evidence import profile_link_preview

logger=logging.getLogger(__name__)
_HTTP=re.compile(r'https?://[^\s<>]+',re.I)
_ADDRESS=re.compile(r'(?<![\w@/.+-])@?[A-Za-z0-9_][A-Za-z0-9_.+-]*@'
                    r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\b'
                    r'(?![\w@+-]|\.[A-Za-z0-9.-])',re.ASCII)
_LABEL=re.compile(r'\b(Telegram|Instagram|Discord|Signal|WhatsApp|Bluesky|Mastodon)'
                  r'\s*[:=]?\s*(@[A-Za-z0-9_][A-Za-z0-9_.-]{0,63})'
                  r'(?![\w@.-])',re.I|re.ASCII)
_MASTODON=re.compile(r'\bMastodon\s*[:=]?\s*$',re.I)
_NAMES={name.lower():name for name in ('Telegram','Instagram','Discord','Signal',
                                     'WhatsApp','Bluesky','Mastodon')}
_ASSOCIATION='A literal saved bio mention, not verified ownership, person identity or a deliverable contact route.'


def bio_contact_mentions(text):
    """Recognize conservative literal text; preserve case/spelling and offsets."""
    if text is None:return []
    if not isinstance(text,str):raise ValueError('Saved bio must be text or unknown')
    urls=[m.span() for m in _HTTP.finditer(text)]
    candidates=[]
    for match in _ADDRESS.finditer(text):
        platform=('Federated handle' if match.group().startswith('@') else
                  'Mastodon' if _MASTODON.search(text[max(0,match.start()-24):match.start()]) else 'email')
        candidates.append((match.start(),match.end(),match.group(),platform))
    for match in _LABEL.finditer(text):
        start,end=match.span(2)
        candidates.append((start,end,match.group(2),_NAMES[match.group(1).lower()]))
    result=[];seen=set()
    for start,end,literal,platform in sorted(candidates):
        if any(a<end and start<b for a,b in urls):continue
        if (start,end) in seen:continue
        seen.add((start,end))
        result.append({'value':literal,'platform':platform,'start':start,'end':end,
                       'context':text[max(0,start-60):min(len(text),end+60)]})
    return result


def profile_mention_matches(db,value,*,published_access=None):
    """Exact email associations across visible observations,using the card parser."""
    access=published_access or PublishedProfileAccess()
    result={};visible=hidden=0
    rows=db.execute(PROFILE_SQL+' ORDER BY r.observed_at DESC,r.relation_id')
    for row in rows:
        aid=row['account_id']
        if not access.allows(row['attributes_json'],aid):hidden+=1;continue
        attrs=json.loads(row['attributes_json'])
        if not isinstance(attrs,dict):raise ValueError('Profile clue attributes must be an object')
        visible+=1
        for mention in bio_contact_mentions(attrs.get('bio')):
            if mention['platform']!='email' or mention['value']!=value:continue
            ref={'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
                 'observedAt':row['observed_at']}
            for key in ('sourceKind','boundary'):
                if isinstance(attrs.get(key),str):ref[key]=attrs[key]
            result.setdefault(aid,[]).append({'kind':'profile_contact_mention',**mention,'evidenceRef':ref})
    return {'status':'partial' if hidden else 'available' if visible else 'not_present',
            'profileObservations':visible,'hiddenProfileObservations':hidden,'byAccount':result}


def profile_contact_mentions(path,*,account_id,published_access=None,limit=40):
    """Bounded observations, not completed contact checks or a new graph import."""
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Profile clue limit must be between 1 and 100')
    result={'status':'not_configured' if not path else 'unavailable','items':[],'truncated':False,
            'accountId':account_id,'note':'Literal bio text only; other formats may remain unrecognized. Not an exhaustive contact check.'}
    if not path:return result
    if not isinstance(account_id,str) or not re.fullmatch('[0-9]+',account_id):
        return {**result,'status':'unresolved_identity'}
    access=published_access or PublishedProfileAccess()
    try:
        with read_saved_store(path) as db:
            rows=db.execute(PROFILE_SQL+' AND e.source_key=? ORDER BY r.observed_at DESC,r.relation_id',
                            (account_id,)).fetchall()
        items=[];hidden=0
        for row in rows:
            if not access.allows(row['attributes_json'],account_id):hidden+=1;continue
            attrs=json.loads(row['attributes_json'])
            if not isinstance(attrs,dict):raise ValueError('Profile clue attributes must be an object')
            for mention in bio_contact_mentions(attrs.get('bio')):
                ref={'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
                     'observedAt':row['observed_at']}
                for key in ('sourceKind','boundary'):
                    if isinstance(attrs.get(key),str):ref[key]=attrs[key]
                items.append({**mention,'sourceRef':ref,'observedAt':row['observed_at']})
        if hidden:result['note']+=f' {hidden} saved Archive profile observation(s) hidden by publication policy.'
        return {**result,'status':'not_present' if not rows else 'partial' if hidden else 'available',
                'items':items[:limit],'truncated':len(items)>limit}
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Saved bio contact clues unavailable (%s)',type(error).__name__)
        return result


def profile_clue_projection(path,*,account_id,published_access=None,limit=40):
    """One profile-clue family owns URL and literal-bio adapters for the card."""
    links=profile_link_preview(path,account_id=account_id,published_access=published_access,limit=limit)
    mentions=profile_contact_mentions(path,account_id=account_id,published_access=published_access,limit=limit)
    entries=[]
    for link in links.get('items',[]):
        ref={key:link[key] for key in ('snapshotId','sourcePointer','observedAt','capturedAt',
             'sourceKind','boundary') if key in link}
        entries.append({'value':link['url'],'kind':'profile_link','label':'Link mentioned in saved profile',
            'association':'A saved profile mentioned this URL; it is not an owned profile or contact route.',
            'note':link.get('boundary'),'observed':link.get('observedAt'),'source_url':link['url'],
            'refs':[ref],'family':'profile_links'})
    for mention in mentions['items']:
        ref=mention['sourceRef']
        entries.append({'value':mention['value'],'platform':mention['platform'],'kind':'profile_contact_mention',
            'label':'Literal contact or channel mention in saved bio','association':_ASSOCIATION,
            'note':f"Bio characters {mention['start']}–{mention['end']}: {mention['context']}",
            'observed':mention['observedAt'],'refs':[ref],'family':'profile_mentions'})
    coverage=[{'key':'profile_links','label':'Saved profile links','status':links['status'],
        'shownCount':len(links.get('items',[])),'truncated':links.get('truncated',False),
        'note':'Counts are saved link observations; equal URLs are grouped, not separate people.'+
            ((' '+links['note']) if links.get('note') else '')},
        {'key':'profile_mentions','label':'Saved bio contact/channel mentions','status':mentions['status'],
         'shownCount':len(mentions['items']),'truncated':mentions['truncated'],'note':mentions['note']}]
    return {'entries':entries,'coverage':coverage,
            'truncated':bool(links.get('truncated') or mentions['truncated'])}
