"""Project saved public profiles/work into the existing three-table sidecar.

Raw sources stay private and byte-exact. Searchable fields are allowlisted;
invitation text, event-fit judgments and prior outreach never enter attributes.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from src.enrichment.site_features import urls_in_text

PROFILE_FIELDS = ('handle', 'name', 'bio', 'location', 'website', 'followers', 'following', 'captured_at')
WORK_TEXT = ('evidence', 'summary', 'passage_summary', 'passage_paraphrase',
             'concrete_passage', 'concrete_observation', 'contained_passage_summary',
             'substantive_observation', 'source_observation', 'substantive_passage', 'substance',
             'contribution','concrete_hook','exact_short_passage','paraphrase','selected_passage_notes','passage_notes')
WORK_CONTEXT = ('date', 'publication_date', 'date_precision', 'date_type', 'date_limits', 'evidence_url',
                'date_caveat', 'shared_credit', 'credit', 'credit_scope', 'attribution',
                'authorship', 'byline', 'author', 'authors', 'inspected_extent', 'limits',
                'coverage_limits', 'coverage_limit','coverage','found_at','source','source_type',
                'kind','selected_extent','inspection_extent','extent','outcome_limit','claim_limit',
                'date_basis','date_evidence','date_limit','event_date','capability_limits',
                'primary_passages','exact_passages','body_inspected','reproduced',
                'selected_work_complete','complete_selected_work')
PROFILE_POLICY_FIELDS = ('sourceKind','archiveExportId','packageRef','eligibilityRef',
                         'profileFileRef','observedAtField','boundary')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _key(*values):
    return hashlib.sha256(_json(values).encode()).hexdigest()


def public_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
        return value.strip() if parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password else None
    except ValueError:
        return None


def project_work_attributes(artifact):
    """Allowlisted work notes; dates/quotes/credit remain source claims, not facts."""
    if (not isinstance(artifact,dict) or not isinstance(artifact.get('title'),str)
            or not artifact['title'].strip() or not public_url(artifact.get('url'))):
        raise ValueError('Saved work requires a title and public HTTP(S) URL')
    attrs={key:artifact[key] for key in ('title','url',*WORK_TEXT,*WORK_CONTEXT)
           if key in artifact and artifact[key] is not None}
    if 'evidence_url' in attrs and not public_url(attrs['evidence_url']):
        raise ValueError('Saved work evidence URL must be public HTTP(S)')
    for field in ('primary_passages','exact_passages'):
        if field not in attrs:continue
        if not isinstance(attrs[field],list):raise ValueError('Saved work passages must be a list')
        passages=[]
        for item in attrs[field]:
            if isinstance(item,str):passages.append(item);continue
            if not isinstance(item,dict):raise ValueError('Saved work passage must be text or an object')
            allowed=('url','locator','quote','paraphrase','interpretation','context','passage','page')
            passage={k:v for k,v in item.items() if k in allowed and (isinstance(v,str) or k=='page' and type(v) is int)}
            if 'url' in passage and not public_url(passage['url']):raise ValueError('Saved passage source URL must be public HTTP(S)')
            if passage:passages.append(passage)
        attrs[field]=passages
    return {**attrs,'workProjectionVersion':2}


class CaptureWriter:
    """Append-only writer for the already-adopted sidecar schema."""
    def __init__(self, db):
        self.db = db

    def source(self, path):
        raw = Path(path).read_bytes()
        snapshot = hashlib.sha256(raw).hexdigest()
        # No timestamp imputed from file mtime, date-only preparation or publication.
        self.db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES (?,?,?,?)',
                        (snapshot, str(Path(path).resolve()), None, raw))
        return snapshot, json.loads(raw)

    def entity(self, kind, value):
        key = _key(kind, value)
        self.db.execute('INSERT OR IGNORE INTO entity VALUES (?,?,?)', (key, kind, value))
        return key

    def relation(self, subject, predicate, target, snapshot, pointer, observed, attrs):
        encoded = _json(attrs)
        key = _key(subject, predicate, target, snapshot, pointer, observed, encoded)
        self.db.execute('INSERT OR IGNORE INTO relation VALUES (?,?,?,?,?,?,?,?,?)',
                        (key, subject, predicate, target, snapshot, pointer, observed, encoded, 'reported'))


def append_profile_bio_links(writer, account, snapshot, pointer, observed, bio, source_attrs, *, field='bio', include_bare=False):
    """A bio mentions these URLs; ownership, endorsement and contact are unknown."""
    if bio is not None and not isinstance(bio,str):
        raise ValueError('Stored profile bio must be text or unknown')
    if field not in ('bio','description'):raise ValueError('Unsupported stored profile bio source field')
    if include_bare:
        from src.enrichment.bio_url_mentions import bio_url_mentions, RECOGNIZER
        mentions=bio_url_mentions(bio)
    else:
        mentions=[{'url':raw} for raw in urls_in_text(bio,limit=None)]
    count=0
    for index,mention in enumerate(mentions):
        url=public_url(mention['url'])
        if not url:continue
        extra=({'bioUrlText':mention['literal'],'bioSchemeAssumed':mention['schemeAssumed'],
                'recognizer':RECOGNIZER} if include_bare else {})
        writer.relation(account,'profile_links_to',writer.entity('web_resource',url),
            snapshot,pointer+'/'+field,observed,{**source_attrs,**extra,
            'producer':'profile-bio-links-v2' if include_bare else 'profile-bio-links-v1',
            'bioUrlIndex':index,'association':'URL mentioned in profile bio; not verified ownership, authorship or endorsement.'})
        count+=1
    return count


def import_saved_capture(db, capture_path, batch_paths):
    """Caller owns the transaction; malformed identities/sources abort the build."""
    writer = CaptureWriter(db)
    snapshot, profiles = writer.source(capture_path)
    if not isinstance(profiles, list) or not profiles:
        raise ValueError('Expected nonempty saved profile list')
    accounts = set();bio_links=0
    for index, row in enumerate(profiles):
        account_id = row.get('account_id') if isinstance(row, dict) else None
        if not isinstance(account_id, str) or not re.fullmatch(r'[0-9]+', account_id) or account_id in accounts:
            raise ValueError('Saved profile identity must be a unique numeric string')
        handle = row.get('handle')
        if not isinstance(handle, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle):
            raise ValueError('Saved profile requires a valid X handle')
        if any(row.get(field) is not None and not isinstance(row[field], str)
               for field in ('name', 'bio', 'location', 'website', 'captured_at')):
            raise ValueError('Saved profile text has an unexpected type')
        accounts.add(account_id)
        account = writer.entity('x_account', account_id)
        attrs = {key: row[key] for key in PROFILE_FIELDS if key in row}
        writer.relation(account, 'profile_observation', writer.entity('x_profile', account_id),
                        snapshot, f'/{index}', row.get('captured_at'), attrs)
        website = public_url(row.get('website'))
        if website:
            writer.relation(account, 'profile_links_to', writer.entity('web_resource', website),
                            snapshot, f'/{index}/website', row.get('captured_at'), {})
        bio_links+=append_profile_bio_links(writer,account,snapshot,f'/{index}',
            row.get('captured_at'),row.get('bio'),{})
    work_count = 0
    for path in sorted(map(Path, batch_paths)):
        snapshot, payload = writer.source(path)
        cards = payload.get('cards') if isinstance(payload, dict) else None
        if not isinstance(cards, list):
            raise ValueError('Saved work batch requires a cards list')
        for index, card in enumerate(cards):
            if not isinstance(card, dict) or card.get('account_id') not in accounts:
                raise ValueError('Work observation has no exact captured account identity')
            artifact = card.get('artifact')
            if artifact is None:
                continue
            attrs = project_work_attributes(artifact)
            # Original fields/aliases are retained, never converted into authorship.
            account = writer.entity('x_account', card['account_id'])
            writer.relation(account, 'research_associates_with',
                            writer.entity('web_resource', public_url(artifact['url'])),
                            snapshot, f'/cards/{index}/artifact', None, attrs)
            work_count += 1
    if not work_count:
        raise ValueError('No projectable work observations; capture is not ready')
    db.execute('CREATE INDEX IF NOT EXISTS relation_subject_predicate ON relation(subject_id,predicate)')
    db.execute('CREATE INDEX IF NOT EXISTS relation_predicate ON relation(predicate)')
    return {'profiles': len(accounts), 'workObservations': work_count,'bioLinkObservations':bio_links}


def import_saved_contacts(db, source_paths):
    """Retain sourced public routes and incomplete checks, never send metadata."""
    writer = CaptureWriter(db)
    handles = {}
    for account, encoded in db.execute("SELECT e.source_key,r.attributes_json FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE r.predicate='profile_observation'"):
        handles.setdefault(account, set()).add(json.loads(encoded)['handle'].casefold())
    counts = {'contactReviews': 0, 'contactRoutes': 0, 'incompleteChecks': 0}
    route_fields = ('type', 'address', 'source_url', 'verified_on', 'instruction', 'evidence')
    route_types = {'personal_email', 'work_email', 'organisation_forwarding', 'organisation_email', 'contact_form', 'contact_page'}

    def identity(record):
        if not isinstance(record, dict) or not isinstance(record.get('account_id'), str) or record['account_id'] not in handles:
            raise ValueError('Contact record has no exact captured account identity')
        if not isinstance(record.get('handle'), str) or record['handle'].casefold() not in handles[record['account_id']]:
            raise ValueError('Contact record handle and account identity disagree')
        return writer.entity('x_account', record['account_id'])

    def day(value):
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Contact observations require an explicit calendar date')
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ValueError('Contact observation date is invalid') from error
        return value

    for path in sorted(map(Path, source_paths)):
        snapshot, payload = writer.source(path)
        if not isinstance(payload, dict) or not isinstance(payload.get('reviews'), list):
            raise ValueError('Contact source requires a reviews list')
        checks = payload.get('checks', [])
        if not isinstance(checks, list):
            raise ValueError('Contact checks must be a list')
        for index, review in enumerate(payload['reviews']):
            account = identity(review)
            routes = review.get('routes')
            if not isinstance(routes, list) or not routes:
                raise ValueError('Empty contact review is not a negative finding')
            for number, route in enumerate(routes):
                if not isinstance(route, dict) or any(not isinstance(route.get(key), str) or not route[key].strip() for key in route_fields):
                    raise ValueError('Contact route lacks explicit fields and qualifications')
                if route['type'] not in route_types or not public_url(route['source_url']):
                    raise ValueError('Contact route type/source is invalid')
                if route['type'] in ('contact_form', 'contact_page'):
                    valid_address = public_url(route['address'])
                else:
                    valid_address = re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', route['address'])
                if not valid_address:
                    raise ValueError('Contact route address is invalid for its explicit type')
                observed = day(route['verified_on'])
                attrs = {key: route[key] for key in route_fields}
                pointer = f'/reviews/{index}/routes/{number}'
                target = writer.entity('contact_route', _json([route['type'], route['address']]))
                writer.relation(account, 'has_contact_route', target, snapshot, pointer, observed, attrs)
                writer.relation(target, 'reported_at', writer.entity('web_resource', route['source_url']),
                                snapshot, pointer+'/source_url', observed, {'type': route['type']})
                counts['contactRoutes'] += 1
            counts['contactReviews'] += 1
        for index, check in enumerate(checks):
            account = identity(check)
            observed = day(check.get('checked_on'))
            urls = check.get('source_urls')
            if not isinstance(check.get('reason'), str) or not check['reason'].strip() or not isinstance(urls, list) or not urls or any(not public_url(url) for url in urls):
                raise ValueError('Incomplete contact check lacks explicit sources/reason')
            attrs = {'checked_on': observed, 'reason': check['reason'], 'outcome': 'incomplete'}
            for number, url in enumerate(urls):
                writer.relation(account, 'contact_check', writer.entity('web_resource', url),
                                snapshot, f'/checks/{index}/source_urls/{number}', observed, attrs)
            counts['incompleteChecks'] += 1
    if not any(counts.values()):
        raise ValueError('No projectable contact observations; requested contact import is not ready')
    return counts
