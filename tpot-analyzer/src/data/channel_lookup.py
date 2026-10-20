"""Offline literal channel associations;never identity resolution or ranking."""
import json
import logging
import re
import sqlite3

from src.data.contact_catalog import catalog_value_matches
from src.data.page_contact_clues import page_email_matches
from src.data.published_profile_access import PublishedProfileAccess
from src.data.relationship_dossier import relationship_value_matches
from src.data.research_source_links import research_source_value_matches
from src.data.saved_capture_import import public_url
from src.data.saved_evidence import PROFILE_SQL,read_saved_store,SavedEvidenceUnavailable
from src.enrichment.website_context import EMAIL

logger=logging.getLogger(__name__)
SCOPE=('Independent saved numeric-account records only. Archive-restricted sources are excluded '
       'without a network check. Unresolved historical handles and unprojected raw backups are not searched.')
METHOD=('Literal equality after trimming input whitespace. No case,scheme,host,path or query normalization; '
        'no fuzzy identity inference. Sorted by saved account ID,not confidence. Shared values do not merge people.')


def validate_lookup(body):
    if not isinstance(body,dict) or set(body)-{'value','limit'}:
        raise ValueError('Expected only value and optional limit in the JSON object')
    value=body.get('value');limit=body.get('limit',25)
    if not isinstance(value,str) or not 1<=len(value)<=2048 or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Enter one plain email or HTTP(S) URL,at most2048 characters')
    value=value.strip()
    if any(c.isspace() for c in value):raise ValueError('Lookup requires one literal email or URL without internal whitespace')
    kind='email' if EMAIL.fullmatch(value) else 'url' if public_url(value)==value else None
    if not kind:raise ValueError('Enter a complete plain email or HTTP(S) URL without credentials')
    if type(limit) is not int or not 1<=limit<=25:raise ValueError('Lookup limit must be an integer1–25')
    return value,kind,limit


def lookup_saved_channel(path,body):
    value,kind,limit=validate_lookup(body);access=PublishedProfileAccess('unchecked')
    sources={};matches={}
    def collect(name,operation):
        try:
            source=operation();by_account=source.pop('byAccount')
            sources[name]=source
            for aid,items in by_account.items():
                if re.fullmatch('[0-9]+',aid):matches.setdefault(aid,[]).extend(items)
        except (ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error) as error:
            logger.warning('Saved channel family %s unavailable (%s)',name,type(error).__name__)
            sources[name]={'status':'unavailable'}
    with read_saved_store(path) as db:
        if not db.execute("SELECT 1 FROM relation WHERE predicate='profile_observation' LIMIT 1").fetchone():
            raise SavedEvidenceUnavailable('No saved profile observations are available')
        collect('catalogue',lambda:catalog_value_matches(db,value))
        collect('page_emails',lambda:page_email_matches(db,value,published_access=access))
        collect('research_sources',lambda:research_source_value_matches(db,value,published_access=access))
        try:
            for name,source in relationship_value_matches(db,value,published_access=access).items():
                collect(name,lambda source=source:source)
        except (ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error) as error:
            logger.warning('Saved channel relationships unavailable (%s)',type(error).__name__)
            for name in ('reviewed_routes','profile_urls'):sources[name]={'status':'unavailable'}
        if all(s['status'] in ('not_present','unavailable') for s in sources.values()):
            raise SavedEvidenceUnavailable('No searchable channel source family is available')
        ids=sorted(matches)[:limit];profiles={}
        if ids:
            sql=PROFILE_SQL+' AND e.source_key IN ('+','.join('?' for _ in ids)+') ORDER BY r.observed_at DESC,r.snapshot_id,r.source_pointer'
            for row in db.execute(sql,ids):
                aid=row['account_id']
                if aid in profiles or not access.allows(row['attributes_json'],aid):continue
                attrs=json.loads(row['attributes_json']);handle=attrs.get('handle')
                if isinstance(handle,str) and re.fullmatch('[A-Za-z0-9_]{1,15}',handle):
                    profiles[aid]={'username':handle,'displayName':attrs.get('name') if isinstance(attrs.get('name'),str) else None,
                        'profileRef':{'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
                                      'observedAt':row['observed_at']}}
        results=[{'accountId':aid,**profiles.get(aid,{}),'matches':matches[aid][:20],
                  'matchesTruncated':len(matches[aid])>20} for aid in ids]
    return {'status':'partial' if any(s['status']!='available' for s in sources.values()) else 'available',
            'value':value,'valueType':kind,'total':len(matches),'results':results,'truncated':len(matches)>limit,
            'sources':sources,'scope':SCOPE,'method':METHOD}
