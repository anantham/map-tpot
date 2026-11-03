"""Source-bound consumer contracts for the distinct v3 decoded-email clue kind."""
import base64
import gzip
import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from src.data.cached_websites import describe_cached_page, cached_website_preview
from src.data.page_contact_clues import (append_page_contact_clues,page_email_matches,
    project_page_contact_clues,read_page_contact_clues)
from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_capture_import import CaptureWriter
from src.data.website_evidence import website_page_observations
from tests.test_cached_websites import cached_sources

AID = '9007199254740993'
HTML = ('<p>Contact options</p>'
        '<a href="/cdn-cgi/l/email-protection#423627232f02273a232f322e276c36273136">Main contact</a>'
        '<span class="__cf_email__" data-cfemail="423627232f02273a232f322e276c36273136">Email us</span>'
        '<a href="mailto:legacy@example.test">Legacy route</a>')
ADDRESS = 'team@example.test'


def _raw_attribute(tag, name):
    import re
    match = re.search(rf'<{tag}\b[^>]*\b{name}="([^"]+)"', HTML)
    assert match
    return match.group(1), HTML[:match.start()].count('\n') + 1, match.start() - HTML.rfind('\n', 0, match.start()) - 1


def _install_page_revisions(inputs, *, protected=False):
    archive, graph, access = inputs
    raw = gzip.compress(HTML.encode())
    with sqlite3.connect(archive) as db:
        db.row_factory = sqlite3.Row
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?', (raw, AID))
        row = db.execute('SELECT * FROM bio_link_profile WHERE account_id=?', (AID,)).fetchone()
    base = describe_cached_page(row, {})
    base.pop('association')
    assert base['evidenceRef']['parserVersion'] == 'website-context-v3'
    versions = []
    for version in ('website-context-v2', 'website-context-v3'):
        page = json.loads(json.dumps(base))
        page['evidenceRef']['parserVersion'] = version
        if version == 'website-context-v2':
            page['emailClues'] = [x for x in page.get('emailClues', []) if x.get('kind') != 'cloudflare_decoded']
            page['emailClueCount'] = len(page['emailClues'])
            href, _, _ = _raw_attribute('a', 'href')
            page['links'].append({'url': 'https://example.test' + href,
                'label': 'Main contact', 'context': 'Contact options Main contact Email us Legacy route'})
            page['linkCount'] = len(page['links'])
        versions.append(page)

    source = {key: row[key] for key in ('account_id', 'source_url', 'resolved_url', 'title', 'fetched_at', 'error')}
    source['htmlGzipBase64'] = base64.b64encode(raw).decode('ascii')
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        writer = CaptureWriter(db)
        if not protected:
            writer.relation(writer.entity('x_account', AID), 'profile_links_to',
                writer.entity('web_resource', 'https://example.test/'), 'fixture',
                '/encoded-contact-fixture', None, {})
        root = db.execute("SELECT r.*,target.source_key url FROM relation r "
            "JOIN entity account ON account.entity_id=r.subject_id "
            "JOIN entity target ON target.entity_id=r.object_id "
            "WHERE account.kind='x_account' AND account.source_key=? AND r.predicate='profile_links_to' "
            "AND r.source_pointer=?", (AID, '/website' if protected else '/encoded-contact-fixture')).fetchone()
        policy = json.loads(root['attributes_json'])
        association = {'relationId': root['relation_id'], 'snapshotId': root['snapshot_id'],
            'sourcePointer': root['source_pointer'], 'observedAt': root['observed_at'], 'url': root['url']}
        cache_id = hashlib.sha256(json.dumps([AID, row['source_url'], row['fetched_at'],
            hashlib.sha256(raw).hexdigest()], sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()
        for page in versions:
            payload = {'kind': 'cached-public-website-observation', 'visibility': 'private',
                'producer': 'cached-website-context-v1', 'source': source, 'derived': page}
            blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
            snapshot = hashlib.sha256(blob).hexdigest()
            db.execute('INSERT INTO evidence_snapshot VALUES (?,?,?,?)',
                (snapshot, 'synthetic-cache', row['fetched_at'], blob))
            attrs = {k: policy[k] for k in ('sourceKind', 'archiveExportId', 'profileFileRef',
                'packageRef', 'eligibilityRef', 'boundary') if k in policy}
            attrs.update(producer='cached-website-context-v1', observingAccountId=AID,
                cacheObservationId=cache_id, associationRef=association,
                cacheRef={'snapshotId': snapshot, 'sourcePointer': '/source'}, page=page)
            writer.relation(writer.entity('x_account', AID), 'website_observed_for',
                writer.entity('web_resource', page['url']), snapshot, '/source', row['fetched_at'], attrs)
    return archive, graph, access


def test_v3_decoded_clues_keep_source_locator_date_and_policy_without_identity_promotion(cached_sources):
    archive, graph, access = _install_page_revisions(cached_sources)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        result = project_page_contact_clues(db)
        assert result['pageContactObservations'] >= 2
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN "
            "('has_contact_route','same_person','works_at')").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='page_lists_email' "
            "AND json_extract(attributes_json,'$.clueKind')='email'").fetchone()[0] >= 1
        old_page_snapshots = {row[0] for row in db.execute("SELECT snapshot_id FROM relation "
            "WHERE predicate='website_observed_for' AND json_extract(attributes_json,'$.page.evidenceRef.parserVersion')='website-context-v2'")}
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='page_lists_email' "
            "AND snapshot_id IN (%s)" % ','.join('?' for _ in old_page_snapshots),
            tuple(old_page_snapshots)).fetchone()[0] >= 1

    with closing(sqlite3.connect(graph)) as db:
        view = read_page_contact_clues(db, [AID], published_access=access)
    assert view[AID]['status'] == 'available'
    assert view[AID]['emailStrings'] == 2
    decoded = [item for item in view[AID]['items'] if item['clue']['kind'] == 'cloudflare_decoded']
    assert len(decoded) == 2
    assert {item['clue']['decoding']['attribute'] for item in decoded} == {'href', 'data-cfemail'}
    assert {item['clue']['address'] for item in decoded} == {ADDRESS}
    assert all(item['capturedAt'] == '2026-07-30T00:00:00Z' for item in decoded)
    assert all(item['evidenceRef']['sourcePointer'].startswith('/derived/emailClues/') for item in decoded)
    assert {item['clue']['decoding']['tag'] for item in decoded} == {'a', 'span'}
    for item in decoded:
        source = item['clue']['decoding']
        value, line, column = _raw_attribute(source['tag'], source['attribute'])
        assert (source['value'], source['line'], source['column']) == (value, line, column)
    assert any(item['clue']['address'] == 'legacy@example.test'
               and item['clue']['kind'] == 'mailto' for item in view[AID]['items'])

    pages = cached_website_preview(archive, graph, account_id=AID, published_access=access)['pages']
    assert len(pages) == 1 and pages[0]['evidenceRef']['parserVersion'] == 'website-context-v3'
    with closing(sqlite3.connect(graph)) as db:
        db.row_factory = sqlite3.Row
        exact = page_email_matches(db, ADDRESS, published_access=access)
        legacy = page_email_matches(db, 'legacy@example.test', published_access=access)
    assert list(exact['byAccount']) == [AID] and exact['status'] == 'available'
    assert list(legacy['byAccount']) == [AID]


def test_v3_source_still_obeys_explicit_publication_access(cached_sources):
    _, graph, access = _install_page_revisions(cached_sources, protected=True)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        pages = list(website_page_observations(db, published_access=access, account_id=AID))
        v3 = next((aid, page, attrs) for aid, page, attrs in pages
                  if page['evidenceRef']['parserVersion'] == 'website-context-v3')
        aid, page, attrs = v3
        append_page_contact_clues(CaptureWriter(db), page, page['graphEvidenceRef']['snapshotId'],
            page['graphEvidenceRef']['observedAt'], attrs)
        visible = read_page_contact_clues(db, [AID], published_access=access)[AID]
        hidden = read_page_contact_clues(db, [AID], published_access=PublishedProfileAccess('withdrawn'))[AID]
    assert any(item['clue']['kind'] == 'cloudflare_decoded' for item in visible['items'])
    assert hidden['items'] == [] and hidden['emailStrings'] == 0


@pytest.mark.parametrize('mutation', ['method', 'attribute-value', 'address', 'locator', 'source-text'])
def test_v3_source_disagreement_is_refused(cached_sources, mutation):
    _, graph, _ = _install_page_revisions(cached_sources)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='website_observed_for' "
            "AND json_extract(attributes_json,'$.page.evidenceRef.parserVersion')='website-context-v3'").fetchone()
        attrs = json.loads(row['attributes_json'])
        clue = next(x for x in attrs['page']['emailClues'] if x['kind'] == 'cloudflare_decoded')
        if mutation == 'method': clue['decoding']['method'] = 'other'
        elif mutation == 'attribute-value': clue['decoding']['value'] = 'not-a-cloudflare-email'
        elif mutation == 'address': clue['address'] = 'different@example.test'
        elif mutation == 'locator': clue['decoding']['line'] = 0
        else: attrs['page']['text'] += ' changed after capture'
        db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',
            (json.dumps(attrs), row['relation_id']))
        with pytest.raises(ValueError):
            project_page_contact_clues(db)


def test_v3_projected_child_tampering_is_refused(cached_sources):
    _, graph, access = _install_page_revisions(cached_sources)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        project_page_contact_clues(db)
        row = db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='page_lists_email' "
            "AND json_extract(attributes_json,'$.clue.kind')='cloudflare_decoded'").fetchone()
        attrs = json.loads(row['attributes_json'])
        attrs['clue']['decoding']['value'] = 'disagrees-with-page'
        db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',
            (json.dumps(attrs), row['relation_id']))
        with pytest.raises(ValueError):
            read_page_contact_clues(db, [AID], published_access=access)
