"""Bounded source-backed contact/channel projection for a resolved dossier."""
from __future__ import annotations

import re
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from src.data.contact_catalog import read_contact_catalog
from src.data.website_evidence import profile_link_preview

_EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
_PLATFORMS = {
    'instagram.com':'Instagram', 'linkedin.com':'LinkedIn', 'discord.com':'Discord',
    'discord.gg':'Discord', 'signal.me':'Signal', 'whatsapp.com':'WhatsApp',
    't.me':'Telegram', 'telegram.me':'Telegram', 'bsky.app':'Bluesky',
    'github.com':'GitHub', 'substack.com':'Substack',
}
_ROUTE_TYPES={'work_email','personal_email','organisation_email','organisation_forwarding',
              'contact_form','contact_page'}
_EMAIL_ROUTE_TYPES={'work_email','personal_email','organisation_email','organisation_forwarding'}
_BOUNDARY = ('Historical source observations, not confirmed ownership, identity, current contactability, '
             'or delivery. Forms and research pages are not submission routes; missing evidence is not evidence of absence.')


def _safe_url(value):
    if not isinstance(value, str) or not value or value.strip() != value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        if any(ord(char) < 32 for char in value):
            return None
        return value
    except ValueError:
        return None


def _platform(value, kind=None):
    if kind == 'email' or (isinstance(value,str) and _EMAIL.fullmatch(value)):
        return 'email'
    try:
        host = (urlsplit(value).hostname or '').lower().removeprefix('www.')
    except (TypeError,ValueError):
        host = ''
    return _PLATFORMS.get(host, 'website')


def _ref(source, pointer=None, observed=None):
    if not isinstance(source,dict):
        return []
    sid=source.get('snapshotId');ptr=pointer or source.get('sourcePointer')
    if not isinstance(sid,str) or not isinstance(ptr,str):
        return []
    ref={'snapshotId':sid,'sourcePointer':ptr}
    when=observed if observed is not None else source.get('observedAt')
    if isinstance(when,str):ref['observedAt']=when
    for key in ('sourceKind','boundary','capturedAt'):
        if isinstance(source.get(key),str):ref[key]=source[key]
    return [ref]


def _observation(kind,label,association,note=None,observed=None,source_url=None,refs=None):
    return {'kind':str(kind or 'reported'),'label':str(label or 'Reported contact detail'),
        'association':str(association or 'Source-reported; not independently verified.'),
        'note':note if isinstance(note,str) else None,'observedAt':observed if isinstance(observed,str) else None,
        'sourceUrl':_safe_url(source_url),'sourceRefs':refs or []}


def contact_card_preview(path, *, account_id, account=None, joined=None, relationships=None,
                         cached=None, published_access=None, limit=40):
    """Combine already-projected, exact-account DTOs without fetching or mutating stores."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('contact card limit must be between 1 and 100')
    if not isinstance(account_id,str) or not re.fullmatch(r'[0-9]+',account_id):
        return {'status':'unresolved_identity','accountId':account_id if isinstance(account_id,str) else None,
                'items':[],'coverage':[],'truncated':False,'boundary':_BOUNDARY}
    if not isinstance(account,dict) or account.get('accountId') != account_id:
        return {'status':'unresolved_identity','accountId':account_id,'items':[],'coverage':[],
                'truncated':False,'boundary':_BOUNDARY}

    grouped={};coverage=[];family_counts={}
    def add(value,kind,label,association,note=None,observed=None,source_url=None,refs=None,family=None):
        if not isinstance(value,str) or not value or value.strip()!=value or any(ord(c)<32 for c in value):return
        if value.startswith(('http://','https://')) and not _safe_url(value):return
        item=grouped.setdefault(value,{'value':value,'platform':_platform(value,kind),'url':_safe_url(value),
                                       'observations':[]})
        item['observations'].append(_observation(kind,label,association,note,observed,source_url,refs))
        if family:family_counts.setdefault(family,{}).setdefault(value,0);family_counts[family][value]+=1

    def status(family,bound=None):
        if not isinstance(family,dict):return 'not_checked'
        if bound is False:return 'unavailable'
        return family.get('status','unavailable')

    website=account.get('website')
    if _safe_url(website):
        add(website,'profile_website','Profile website','Profile website listed in the resolved account record.',
            observed=account.get('fetchedAt'),source_url=website,family='profile')
    coverage.append({'key':'profile','label':'Resolved profile','status':'available',
                     'shownCount':int(bool(_safe_url(website))),'truncated':False,'note':None})

    joined_ok=isinstance(joined,dict) and joined.get('status') in ('available','partial') and joined.get('accountId')==account_id
    jcount=0
    if joined_ok:
        for site in joined.get('websites',[]):
            if not isinstance(site,dict):continue
            page=_safe_url(site.get('url'))
            for link in site.get('links',[]) if site.get('linkStatus')=='available' else []:
                if _safe_url(link):
                    add(link,'website_link','Link listed on profile-associated website',
                        'Historical link from a website associated with this profile.',
                        observed=site.get('capturedAt'),source_url=page,
                        refs=_ref(site.get('evidenceRef')),family='joined');jcount+=1
        for contact in joined.get('contacts',[]):
            if not isinstance(contact,dict):continue
            value=contact.get('address');source=_safe_url(contact.get('source_url'));kind=contact.get('type')
            if kind in _ROUTE_TYPES and value and (_EMAIL.fullmatch(value) if kind in _EMAIL_ROUTE_TYPES else _safe_url(value)):
                note=' — '.join(part for part in (contact.get('instruction'),contact.get('evidence')) if isinstance(part,str) and part)
                add(value,kind,'Research contact detail',
                    'Source-backed research record; not confirmed current or deliverable.',
                    note or None,observed=contact.get('verified_on'),source_url=source,
                    refs=_ref(contact.get('evidenceRef')),family='joined');jcount+=1
    joined_bound=joined.get('accountId')==account_id if isinstance(joined,dict) else None
    coverage.append({'key':'joined','label':'Joined dossier evidence','status':status(joined,joined_bound),
                     'shownCount':jcount,'truncated':False,'note':None})

    rel_ok=isinstance(relationships,dict) and relationships.get('status') in ('available','partial') and relationships.get('accountId')==account_id
    rcount=0
    if rel_ok:
        for contact in relationships.get('contacts',[]):
            if not isinstance(contact,dict):continue
            value=contact.get('address');source=_safe_url(contact.get('source_url'));kind=contact.get('type')
            if kind in _ROUTE_TYPES and value and (_EMAIL.fullmatch(value) if kind in _EMAIL_ROUTE_TYPES else _safe_url(value)):
                note=' — '.join(part for part in (contact.get('instruction'),contact.get('evidence')) if isinstance(part,str) and part)
                add(value,kind,'Reported contact route',
                    'Historical reported route; not confirmation of current delivery.',note or None,
                    observed=contact.get('verified_on'),source_url=source,refs=_ref(contact.get('evidenceRef')),
                    family='relationships');rcount+=1
        for path_item in relationships.get('paths',[]):
            if not isinstance(path_item,dict):continue
            nodes=path_item.get('nodes',[]);edges=path_item.get('edges',[])
            for index,edge in enumerate(edges):
                if not isinstance(edge,dict):continue
                if edge.get('predicate') not in ('profile_links_to','page_links_to','page_resolves_to'):continue
                source_node=nodes[index] if index<len(nodes) else {}
                target_node=nodes[index+1] if index+1<len(nodes) else {}
                candidate=target_node.get('key') if isinstance(target_node,dict) else None
                if candidate:
                    note='; '.join(str(edge[field]) for field in ('linkLabel','linkContext','claimKind',
                        'claimPersonName','claimOrganisationName') if isinstance(edge.get(field),str) and edge[field])
                    add(candidate,'research_path','Saved profile link' if edge['predicate']=='profile_links_to' else 'Linked research source',
                        'A reported relationship path reaches this source; it is not an account profile assertion.',
                        note or None,observed=edge.get('observedAt'),
                        source_url=source_node.get('key') if isinstance(source_node,dict) else None,
                        refs=_ref(edge),family='relationships');rcount+=1
        sources=relationships.get('researchSources',{})
        if isinstance(sources,dict) and sources.get('status') in ('available','partial'):
            if sources.get('accountId') == account_id:
                for source in sources.get('items',[]):
                    if not isinstance(source,dict) or not _safe_url(source.get('url')):continue
                    refs=[]
                    for ref in source.get('sourceRefs',[]):
                        refs.extend(_ref(ref))
                        for pointer in ref.get('qualificationPointers',{}).values():
                            refs.extend(_ref(ref,pointer=pointer))
                    note=source.get('researchNote')
                    if isinstance(source.get('retrievalCaveat'),str):
                        note=(note+' '+source['retrievalCaveat']) if isinstance(note,str) else source['retrievalCaveat']
                    witness_role=source.get('witnessRole')
                    if isinstance(witness_role,str) and witness_role:
                        note=(note+' ' if isinstance(note,str) else '')+f'Saved research context: {witness_role}'
                    for field,value in source.get('sourceQualifications',{}).items():
                        if not (isinstance(value,str) or type(value) in (bool,int) or value is None):continue
                        literal=value if isinstance(value,str) else json.dumps(value)
                        note=(note+' ' if isinstance(note,str) else '')+f'Saved source qualification {field}: {literal}'
                    add(source['url'],'research_source','Cited research source',
                        'A cited research source associated with the account; not an owned profile or contact route.',
                        note,None,source['url'],refs,family='relationships');rcount+=1
    rel_sources=relationships.get('researchSources',{}) if rel_ok else {}
    rel_truncated=bool(rel_ok and (relationships.get('truncated') or
        isinstance(rel_sources,dict) and (rel_sources.get('truncated') or rel_sources.get('status')=='partial')))
    rel_bound=relationships.get('accountId')==account_id if isinstance(relationships,dict) else None
    rel_status=status(relationships,rel_bound)
    if rel_ok and isinstance(rel_sources,dict) and rel_sources.get('status')=='partial' and rel_status=='available':rel_status='partial'
    coverage.append({'key':'relationships','label':'Relationship evidence','status':rel_status,
                     'shownCount':rcount,'truncated':rel_truncated,'note':None})

    cache_ok=isinstance(cached,dict) and cached.get('status') in ('available','partial') and cached.get('accountId')==account_id
    ccount=0
    if cache_ok:
        for page in cached.get('pages',[]):
            if not isinstance(page,dict):continue
            if page.get('status')!='available':continue
            cache_ref=page.get('evidenceRef',{}).get('cacheRow',{}) if isinstance(page.get('evidenceRef'),dict) else {}
            if cache_ref.get('accountId')!=account_id:continue
            page_url=_safe_url(page.get('url')) or _safe_url(page.get('sourceUrl'))
            parent_ref=page.get('graphEvidenceRef')
            refs=_ref(parent_ref)
            def derived_refs(field,index):
                return refs+([{'snapshotId':parent_ref['snapshotId'],'sourcePointer':f'/derived/{field}/{index}'}]
                    if isinstance(parent_ref,dict) and isinstance(parent_ref.get('snapshotId'),str) else [])
            for index,clue in enumerate(page.get('emailClues',[])):
                if isinstance(clue,dict) and isinstance(clue.get('address'),str) and _EMAIL.fullmatch(clue['address']):
                    add(clue['address'],'cached_email','Email found on cached page',
                        'Historical cached-page clue, not a reviewed route.',clue.get('context'),
                        observed=page.get('capturedAt'),source_url=page_url,refs=derived_refs('emailClues',index),
                        family='cached');ccount+=1
            for index,form in enumerate(page.get('messageForms',[])):
                add(page_url,'contact_form','Form present on cached page',
                    'Form is not a guaranteed contact route; no submit action is exposed.',
                    form.get('context') if isinstance(form,dict) else 'A contact form was observed.',
                    observed=page.get('capturedAt'),source_url=page_url,
                    refs=derived_refs('messageForms',index),family='cached');ccount+=1
            for index,link in enumerate(page.get('links',[])):
                if isinstance(link,dict) and _safe_url(link.get('url')):
                    add(link['url'],'cached_link',link.get('label') or 'Link found on cached page',
                        'Historical cached-page link, not verified ownership.',link.get('context'),
                        observed=page.get('capturedAt'),source_url=page_url,
                        refs=derived_refs('links',index),family='cached');ccount+=1
    cache_mismatch=bool(cache_ok and any(not isinstance(p,dict) or
        not isinstance(p.get('evidenceRef'),dict) or
        p['evidenceRef'].get('cacheRow',{}).get('accountId')!=account_id
        for p in cached.get('pages',[])))
    cache_partial=bool(cache_ok and (cache_mismatch or any(isinstance(p,dict) and
        (p.get('status')!='available' or p.get('emailCluesTruncated') or p.get('formsTruncated') or p.get('linksTruncated'))
        for p in cached.get('pages',[]))))
    cache_bound=cached.get('accountId')==account_id if isinstance(cached,dict) else None
    cache_status=status(cached,cache_bound)
    if cache_partial and cache_status=='available':cache_status='partial'
    coverage.append({'key':'cached','label':'Cached website evidence','status':cache_status,
                     'shownCount':ccount,'truncated':bool(cache_ok and (cached.get('truncated') or cache_partial)),'note':None})

    links=profile_link_preview(path,account_id=account_id,published_access=published_access,limit=limit)
    for link in links.get('items',[]):
        add(link.get('url'),'profile_link','Link mentioned in saved profile',
            'A saved profile mentioned this URL; it is not an owned profile or contact route.',
            link.get('boundary'),observed=link.get('observedAt'),source_url=link.get('url'),
            refs=_ref(link),family='profile_links')
    coverage.append({'key':'profile_links','label':'Saved profile links','status':links['status'],
        'shownCount':len(links.get('items',[])),'truncated':links.get('truncated',False),
        'note':'Counts are saved link observations; equal URLs are grouped, not separate people.'+
            ((' '+links['note']) if links.get('note') else '')})

    catalog_status='not_configured' if not path else 'unavailable';catalog_count=0;catalog_truncated=False
    if path:
        try:
            source_path=Path(path).resolve(strict=True)
            with closing(sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
                db.execute('PRAGMA query_only=ON')
                data=read_contact_catalog(db,[account_id],limit=min(limit,20))
            record=data.get(account_id)
            if record:
                catalog_status=record.get('status','unavailable');catalog_truncated=bool(record.get('truncated'))
            else:
                catalog_status='not_present'
            if record:
                for item in record.get('items',[]):
                    if not isinstance(item,dict):continue
                    value=item.get('value');kind=item.get('kind')
                    if not isinstance(value,str):continue
                    source_refs=[]
                    for ref in item.get('sourceRefs',[]):
                        source_refs.extend(_ref(ref))
                    cats=item.get('categories',[])
                    catalog_note='Historical exported channel catalogue; captured-handle binding is not identity proof.'
                    for catalog in record.get('catalogs',[]):
                        literal=catalog.get('timestampLiteral')
                        if isinstance(literal,str):catalog_note+=f' Catalogue date literal: {literal}.'
                    if isinstance(cats,list) and cats:
                        labels=', '.join(str(category).replace('.',' ').replace('_',' ').title() for category in cats)
                        catalog_note+=f' Source-reported catalogue category labels (not verified platform identity): {labels}.'
                    add(value,kind,'Exported channel mention','A historical channel value appeared in an exported catalogue.',
                        catalog_note,None,value if _safe_url(value) else None,source_refs,family='catalogue');catalog_count+=1
        except (OSError,ValueError,TypeError,sqlite3.Error):
            catalog_status='unavailable'
    coverage.append({'key':'catalogue','label':'Exported channel catalogue','status':catalog_status,
                     'shownCount':catalog_count,'truncated':catalog_truncated,'note':None})

    all_items=list(grouped.values());was_truncated=(len(all_items)>limit or catalog_truncated or links.get('truncated') or
        bool(cache_ok and cached.get('truncated')) or rel_truncated)
    items=all_items[:limit]
    displayed={item['value'] for item in items}
    for entry in coverage:
        entry['truncated']=entry['truncated'] or (entry['key']=='card' and was_truncated)
        if entry['key'] in family_counts:
            entry['shownCount']=sum(count for value,count in family_counts[entry['key']].items() if value in displayed)
    if was_truncated:
        coverage.append({'key':'card','label':'Contact card limit','status':'partial',
                         'shownCount':len(items),'truncated':True,'note':'Additional grouped values were omitted by the display limit.'})
    status_value='available' if items or website or any(c['status'] in ('available','not_present') for c in coverage) else 'unavailable'
    return {'status':status_value,'accountId':account_id,'items':items,'coverage':coverage,
            'truncated':was_truncated,'boundary':_BOUNDARY}
