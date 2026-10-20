"""Read cached pages through exact, visible graph website associations only."""
import gzip
import hashlib
import io
import json
import logging
import re
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path

from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_capture_import import public_url
from src.data.saved_evidence import read_saved_store
from src.data.website_evidence import projected_website_pages
from src.enrichment.website_context import extract_website_context

logger = logging.getLogger(__name__)


def _visible_sites(path, account_id, access):
    with read_saved_store(path) as db:
        rows = db.execute('SELECT target.source_key url,r.* FROM relation r '
            'JOIN entity subject ON subject.entity_id=r.subject_id '
            'JOIN entity target ON target.entity_id=r.object_id '
            'WHERE subject.kind=? AND subject.source_key=? AND r.predicate=? '
            'ORDER BY r.observed_at DESC,r.relation_id',('x_account',account_id,'profile_links_to'))
        sites = {}
        for row in rows:
            if access.allows(row['attributes_json'],account_id) and (url := public_url(row['url'])):
                sites.setdefault(url,{'url':url,'evidenceRef':{'predicate':'profile_links_to',
                    'snapshotId':row['snapshot_id'],'sourcePointer':row['source_pointer'],
                    'observedAt':row['observed_at'],'status':'reported'}})
        return sites


def describe_cached_page(row, association):
    """Describe one retained SQL row without network, writes or ownership claims."""
    page = {'url':public_url(row['resolved_url']) or public_url(row['source_url']),
        'sourceUrl':row['source_url'],'title':row['title'],'capturedAt':row['fetched_at'],
        'association':association,'fetchErrorRecorded':bool(row['error']),
        'status':'not_cached','evidenceRef':{'cacheRow':{
        'accountId':row['account_id'],'sourceUrl':row['source_url']},'parserVersion':'website-context-v2'}}
    raw = row['html_gz']
    if raw is None:
        return page
    try:
        if not isinstance(raw,bytes) or not raw:
            raise ValueError('Cached page is not a gzip payload')
        page['evidenceRef']['gzipSha256'] = hashlib.sha256(raw).hexdigest()
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            decoded = compressed.read(1_200_001)
        if len(decoded)>1_200_000:
            raise ValueError('Cached page exceeds original capture bound')
        final_url = public_url(row['resolved_url'])
        context = extract_website_context(decoded.decode('utf8'),final_url or '')
        page.update(context,status='available',linkBaseRecorded=bool(final_url) or context['linkBaseFromMarkup'])
    except (OSError,EOFError,TypeError,ValueError,zlib.error) as error:
        logger.warning('Cached website page could not be decoded (%s)',type(error).__name__)
        page['status'] = 'unavailable'
    return page


def cached_website_preview(archive_path, relationship_path, *, account_id, published_access=None, limit=8):
    """No network/imports. Exact source-account ID AND visible URL are required."""
    result = {'accountId':account_id,'pages':[],
        'boundary':'Historical, possibly truncated cached pages. Source dates are not current verification. '
                   'Listed emails/forms/links are clues, not reviewed routes or proof of ownership. '
                   'Missing or unmatched cache does not mean no contact method exists.'}
    if not isinstance(account_id,str) or not re.fullmatch('[0-9]+',account_id):
        return {**result,'status':'unresolved_identity'}
    if type(limit) is not int or not 1<=limit<=20:
        raise ValueError('Cached website limit must be1–20')
    if not relationship_path:
        return {**result,'status':'not_configured'}
    try:
        with read_saved_store(relationship_path) as graph:
            projected=projected_website_pages(graph,published_access=published_access,account_id=account_id).get(account_id,[])
        if projected:
            return {**result,'status':'available','pages':projected[:limit],
                    'total':len(projected),'truncated':len(projected)>limit,'source':'projected_cached_website'}
        if not archive_path:return {**result,'status':'not_configured'}
        sites = _visible_sites(relationship_path,account_id,published_access or PublishedProfileAccess())
        if not sites:
            return {**result,'status':'no_linked_sites'}
        archive = Path(archive_path).resolve(strict=True)
        if not archive.is_file():
            raise ValueError('Cached website source must be a file')
        with closing(sqlite3.connect(archive.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            rows = db.execute('SELECT account_id,source_url,resolved_url,title,fetched_at,error,html_gz '
                'FROM bio_link_profile WHERE account_id=? ORDER BY fetched_at DESC,source_url',(account_id,))
            matched = []
            for row in rows:
                match = next((url for raw in (row['source_url'],row['resolved_url'])
                              if (url := public_url(raw)) in sites),None)
                if match:
                    matched.append((row,sites[match]))
            if not matched:
                return {**result,'status':'no_cached_match'}
            return {**result,'status':'available','pages':[describe_cached_page(row,ref) for row,ref in matched[:limit]],
                    'total':len(matched),'truncated':len(matched)>limit}
    except (OSError,ValueError,TypeError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Cached website evidence unavailable (%s)',type(error).__name__)
        return {**result,'status':'unavailable'}
