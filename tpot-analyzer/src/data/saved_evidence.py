"""Local literal evidence search and exact-account read views, never raw blobs."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.data.saved_capture_import import WORK_CONTEXT, WORK_TEXT, public_url
from src.data.relationship_dossier import contact_summaries
from src.data.published_profile_access import PublishedProfileAccess, SOURCE_KIND
from src.data.saved_provider_profiles import SOURCE_KIND as PROVIDER_KIND,SOURCE_LABEL as PROVIDER_LABEL
from src.data.website_evidence import projected_website_pages, website_fragments
from src.data.social_paths import directed_follow_paths, explain_follow_path, follow_scope_coverage, social_sources
from src.data.saved_api_posts import api_post_fragments
from src.data.evidence_text import matched_words, explain_fragments, MATCHING_DESCRIPTION
from src.data.page_contact_clues import read_page_contact_clues
from src.data.contact_catalog import read_contact_catalog

logger = logging.getLogger(__name__)
class SavedIdentityError(ValueError):
    """Explicit handle/ID disagreement, not a damaged evidence record."""


class SavedEvidenceUnavailable(RuntimeError):
    """Configured local evidence cannot be safely read."""

PROFILE_SQL = """SELECT e.source_key account_id,r.attributes_json,r.snapshot_id,r.source_pointer,r.observed_at
FROM relation r JOIN entity e ON e.entity_id=r.subject_id
WHERE r.predicate='profile_observation' AND e.kind='x_account'"""
WORK_SQL = """SELECT e.source_key account_id,r.attributes_json,r.snapshot_id,r.source_pointer,r.observed_at
FROM relation r JOIN entity e ON e.entity_id=r.subject_id
WHERE r.predicate='research_associates_with' AND e.kind='x_account'"""


@contextmanager
def read_saved_store(path):
    if not path:
        raise FileNotFoundError('Saved evidence is not configured')
    source = Path(path).resolve(strict=True)
    if not source.is_file() or source.stat().st_mode & 0o077:
        raise SavedEvidenceUnavailable('Saved evidence requires a private local file')
    db = sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=5)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        yield db
    finally:
        db.close()


def _ref(row):
    return {'snapshotId': row['snapshot_id'], 'sourcePointer': row['source_pointer'],
            'observedAt': row['observed_at'], 'status': 'reported'}


def _profile(row):
    attrs = _attributes(row)
    if not isinstance(attrs.get('handle'), str):
        raise SavedEvidenceUnavailable('Saved profile requires a handle')
    source = ({'sourceKind': SOURCE_KIND, 'archiveExportId': attrs.get('archiveExportId'),
               'sourceBoundary': attrs.get('boundary')} if attrs.get('sourceKind') == SOURCE_KIND else {})
    if attrs.get('sourceKind')==PROVIDER_KIND:
        source={'sourceKind':PROVIDER_KIND,'sourceLabel':PROVIDER_LABEL,'sourceBoundary':attrs.get('boundary')}
    return {**source, 'accountId': row['account_id'], 'username': attrs['handle'],
            'displayName': attrs.get('name'), 'bio': attrs.get('bio'),
            'location': attrs.get('location'), 'website': attrs.get('website'),
            'fetchedAt': attrs.get('captured_at'), 'evidenceRef': _ref(row)}


def _work(row):
    context_fields=(*WORK_CONTEXT,'caveats','caveats_source')
    attrs = {key: value for key, value in _attributes(row).items()
             if key in ('title', 'url', *WORK_TEXT, *context_fields)}
    if not isinstance(attrs.get('title'), str) or not public_url(attrs.get('url')):
        raise SavedEvidenceUnavailable('Saved work requires a public source')
    text = '\n'.join(value for field in WORK_TEXT
                     if isinstance((value := attrs.get(field)), str) and value.strip())
    return {**attrs, 'evidence': text, 'evidenceRef': _ref(row),
            'sourceContext': [{'field': key, 'value': attrs[key]} for key in context_fields if key in attrs],
            'association': 'Saved research associates this account with this work; authorship is not verified.'}


def _attributes(row):
    try:
        attrs = json.loads(row['attributes_json'])
        if not isinstance(attrs, dict):
            raise ValueError('Not an object')
        return attrs
    except (ValueError, TypeError) as error:
        raise SavedEvidenceUnavailable('Saved evidence attributes are invalid') from error


def _work_identity(work):
    text = work.get('evidence') or '\n'.join(work[key] for key in WORK_TEXT
        if key != 'evidence' and isinstance(work.get(key), str) and work[key])
    return json.dumps({'url': work.get('url'), 'title': work.get('title'), 'text': text,
        'context': {key: work[key] for key in (*WORK_CONTEXT, 'caveats') if work.get(key)}}, sort_keys=True)


def _dedup_work(rows):
    result, seen, records = [], set(), set()
    # Projection upgrades are not additional research observations. Only prefer
    # v2 within the exact raw source record, never merge merely by account/URL.
    for row in sorted(rows,key=lambda row:_attributes(row).get('workProjectionVersion')==2,reverse=True):
        record=(row['snapshot_id'],row['source_pointer'])
        if record in records:continue
        records.add(record)
        work = _work(row)
        identity = json.dumps({k: v for k, v in work.items() if k != 'evidenceRef'}, sort_keys=True)
        if identity not in seen:
            seen.add(identity)
            result.append(work)
    return result


def saved_preview(path, *, handle, account_id=None, published_access=None):
    """Resolve by handle AND optional exact ID; never merge same-handle accounts."""
    normalized = str(handle).strip().lstrip('@').lower()
    access = published_access or PublishedProfileAccess()
    if not path:
        return {'status': 'not_configured'}
    try:
        with read_saved_store(path) as db:
            rows = db.execute(PROFILE_SQL + " AND lower(json_extract(r.attributes_json,'$.handle'))=? ORDER BY r.observed_at DESC,r.relation_id", (normalized,)).fetchall()
            source_status = access.summary(rows)
            all_ids = {row['account_id'] for row in rows}
            rows = [row for row in rows if access.allows(row['attributes_json'], row['account_id'])]
            ids = {row['account_id'] for row in rows}
            if account_id:
                if ids and account_id not in ids:
                    if account_id in all_ids:
                        return {'status': 'not_found', 'publishedProfiles': source_status}
                    raise SavedIdentityError('requested account ID and saved handle disagree')
                rows = [row for row in rows if row['account_id'] == account_id]
            elif len(ids) > 1:
                raise SavedIdentityError('handle resolves to multiple saved IDs; select an exact ID')
            if not rows:
                return {'status': 'not_found', 'publishedProfiles': source_status}
            account = _profile(rows[0])
            works = _dedup_work(db.execute(WORK_SQL + ' AND e.source_key=? ORDER BY r.relation_id', (account['accountId'],)).fetchall())
            return {'status': 'available', 'accountId': account['accountId'], 'account': account,
                    'publishedProfiles': source_status,
                    'profiles': [{**account, 'source': account.get('sourceLabel') or account.get('sourceKind', 'saved_october_profile'), 'capturedAt': account['fetchedAt']}],
                    'publicWork': works, 'websites': [], 'contacts': [], 'contactChecks': [],
                    'boundary': 'Historical saved profiles and work associations; not current platform eligibility or verified authorship.'}
    except SavedIdentityError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Saved profile evidence unavailable (%s)', type(error).__name__)
        return {'status': 'unavailable', 'message': 'Saved profile evidence is unavailable.'}


def combine_previews(joined, saved):
    """Keep original contact/check evidence; add new profile/work observations."""
    if saved.get('status') != 'available':
        return joined
    if joined.get('status') != 'available':
        return saved
    if joined['accountId'] != saved['accountId']:
        raise ValueError('saved and joined account IDs disagree')
    result = {**joined, 'profiles': [*joined.get('profiles', []), *saved['profiles']]}
    # Prefer the new source-referenced card over its old pilot copy. Different
    # passages/qualifiers remain separate; URL equality alone is not equivalence.
    works = list(saved['publicWork'])
    for work in joined.get('publicWork', []):
        if not any(_work_identity(work) == _work_identity(other) for other in works):
            works.append(work)
    return {**result, 'publicWork': works}


def search_saved_evidence(path, query, *, limit=25, from_account_id=None, max_hops=2, published_access=None, any_word=False, include_contact_clues=True):
    """All words must occur in public profile/work/page text; no semantic score."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120:
        raise ValueError('Search requires 2–120 characters')
    terms = query.strip().casefold().lstrip('@').split()
    if not terms:
        raise ValueError('Search requires words or a handle')
    if len(terms) > 8:
        raise ValueError('Search supports up to eight words')
    if not (limit is None and any_word) and (type(limit) is not int or not 1 <= limit <= 50):
        raise ValueError('Search limit must be between1 and50')
    if type(max_hops) is not int or max_hops not in (1, 2):
        raise ValueError('maxHops must be1 or2')
    access = published_access or PublishedProfileAccess()
    with read_saved_store(path) as db:
        contacts = contact_summaries(db, published_access=access)
        websites = projected_website_pages(db,published_access=access)
        api_posts, api_coverage = api_post_fragments(db)
        work_rows = db.execute(WORK_SQL + ' ORDER BY r.relation_id').fetchall()
        works = {}
        for row in work_rows:
            works.setdefault(row['account_id'], []).append(row)
        profile_rows = db.execute(PROFILE_SQL + ' ORDER BY r.observed_at DESC,r.relation_id').fetchall()
        profiles = {}
        for row in profile_rows:
            if access.allows(row['attributes_json'], row['account_id']):
                profiles.setdefault(row['account_id'], _profile(row))
        if not profile_rows:
            raise RuntimeError('No saved profiles have been imported; this is not an empty search result')
        # An independent follow can remain usable even when a node's profile is
        # hidden. Expose only that edge's exact ID, never the hidden profile name.
        path_profiles = {row['account_id']: {'accountId': row['account_id']} for row in profile_rows}
        path_profiles.update(profiles)
        paths = directed_follow_paths(db, from_account_id, max_hops) if from_account_id is not None else None
        hits = []
        for account_id, profile in profiles.items():
            if paths is not None and account_id not in paths:
                continue
            public_work = _dedup_work(works.get(account_id, []))
            labels = {'username': 'X handle', 'displayName': 'Display name', 'bio': 'Profile bio',
                      'location': 'Self-described profile location, historical', 'website': 'Profile website link'}
            fragments = [{'kind': 'profile', 'label': label, 'text': profile[key],
                          'evidenceRef': profile['evidenceRef']} for key, label in labels.items() if profile.get(key)]
            fragments.extend({'kind': 'work', 'label': work['title'],
                              'text': f"{work['title']}\n{work['evidence']}", 'url': work['url'],
                              'evidenceRef': work['evidenceRef'], 'association': work['association'],
                              'sourceContext': work['sourceContext']} for work in public_work)
            fragments.extend(website_fragments(websites.get(account_id,[])))
            fragments.extend(api_posts.get(account_id, []))
            combined = '\n'.join(fragment['text'] for fragment in fragments)
            matched_terms = matched_words(combined, terms)
            if not matched_terms or (not any_word and len(matched_terms) != len(terms)):
                continue
            hits.append({**profile, 'matches': explain_fragments(fragments, matched_terms), 'workCount': len(public_work),
                'websitePageCount':len(websites.get(account_id,[])),
                'networkPath': explain_follow_path(paths[account_id], path_profiles) if paths is not None else None,
                'contactSummary': contacts.get(account_id, {'routeCount': 0, 'types': [],
                    'incompleteCheckCount': 0, 'status': 'not_checked_here'})})
        hits.sort(key=lambda hit: (hit['username'].casefold() != query.strip().lstrip('@').casefold(), hit['username'].casefold(), hit['accountId']))
        returned=hits[:limit]
        if include_contact_clues and limit is not None:
            try:
                clues=read_page_contact_clues(db,[hit['accountId'] for hit in returned],published_access=access)
                for hit in returned:hit['pageContactClues']=clues[hit['accountId']]
            except (ValueError,RuntimeError,sqlite3.Error) as error:
                logger.warning('Saved page contact clues unavailable (%s)',type(error).__name__)
                for hit in returned:hit['pageContactClues']={'status':'unavailable','accountId':hit['accountId'],'items':[]}
            try:
                mentions=read_contact_catalog(db,[hit['accountId'] for hit in returned])
                for hit in returned:
                    if hit['accountId'] in mentions:hit['channelMentions']=mentions[hit['accountId']]
            except (ValueError,RuntimeError,sqlite3.Error) as error:
                logger.warning('Saved channel catalogue unavailable (%s)',type(error).__name__)
                for hit in returned:hit['channelMentions']={'status':'unavailable','accountId':hit['accountId'],'items':[]}
        return {'status': 'available', 'query': query.strip(), 'results': returned,
                'publishedProfiles': access.summary(profile_rows),
                'total': len(hits), 'truncated': limit is not None and len(hits)>limit,
                'networkScope': {'fromAccountId': from_account_id, 'maxHops': max_hops,
                    'fromUsername': profiles.get(from_account_id, {}).get('username'),
                    'reachableAccounts': len(paths),
                    **follow_scope_coverage(db, from_account_id)} if paths is not None else None,
                'coverage': {'profileAccounts': len(profiles),
                    'workObservations':len({(row['snapshot_id'],row['source_pointer']) for row in work_rows}),
                    'workAccounts': len(works),
                    'websitePageAccounts':sum(bool(pages) for aid,pages in websites.items() if aid in profiles),
                    'websitePages':sum(len(pages) for aid,pages in websites.items() if aid in profiles),
                    'contactRouteAccounts': sum(item['routeCount'] > 0 for key, item in contacts.items() if key in profiles),
                    'incompleteCheckAccounts': sum(item['incompleteCheckCount'] > 0 for key, item in contacts.items() if key in profiles),
                    **api_coverage},
                'method': MATCHING_DESCRIPTION+' Exact handle first, then alphabetical. Not semantic relevance or membership confidence.'}


def saved_social_sources(path):
    with read_saved_store(path) as db:
        return social_sources(db)
