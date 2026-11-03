"""Explain explicit website publisher assertions without inferring account identity."""
from contextlib import closing
import logging
from pathlib import Path
import re
import sqlite3

from src.data.website_evidence import projected_website_pages

logger=logging.getLogger(__name__)


def _same_evidence(item,page):
    for source in item['evidence']:
        if (source['sourceType']!='historical_cache' or source['url']!=page['url']
                or source.get('sourceDigest')!=page['graphEvidenceRef']['snapshotId']
                or source['observedAt']!=page.get('capturedAt')):
            continue
        pointer=re.fullmatch(r'/derived/links/([0-9]+)',source.get('sourcePointer',''))
        if pointer:
            index=int(pointer[1]);links=page.get('links',[])
            if index<len(links) and links[index]['url']==item['value']:return True
    return False


def attach_website_claims(result,graph):
    """Read only the exact account's admitted pages. Failure preserves healthy candidates."""
    rows=[{**item,'websiteClaims':[]} for item in result['matches']]
    try:
        source=Path(graph).resolve(strict=True)
        if not source.is_file() or source.stat().st_mode & 0o077:
            raise ValueError('Website claim source must be private')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
            pages=projected_website_pages(db,account_id=result['accountId']).get(result['accountId'],[])
        for item in rows:
            if item['kind']!='profile':continue
            for page in pages:
                if not _same_evidence(item,page):continue
                claims=page.get('publicClaims',{})
                explicit=[('rel_me',claim) for claim in claims.get('selfLinks',[])]
                explicit.extend(('person_same_as',claim) for person in claims.get('people',[])
                                for claim in person.get('sameAs',[]))
                for kind,claim in explicit:
                    if claim.get('url')!=item['value']:continue
                    evidence={'kind':kind,'url':page['url'],'observedAt':page.get('capturedAt'),
                              'sourceDigest':page['graphEvidenceRef']['snapshotId']}
                    if evidence not in item['websiteClaims']:item['websiteClaims'].append(evidence)
        status='available'
    except (OSError,ValueError,RuntimeError,sqlite3.Error,TypeError,KeyError) as error:
        logger.warning('Website publisher claims unavailable (%s)',type(error).__name__)
        rows=[{**item,'websiteClaims':[]} for item in result['matches']]
        status='unavailable'
    return {**result,'matches':rows,'websiteClaimStatus':status}
