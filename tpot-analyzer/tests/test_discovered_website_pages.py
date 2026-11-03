"""Direct contact/about links may bind cached pages without implying ownership."""
import gzip
import json
import sqlite3

from src.data.cached_website_import import project_cached_websites
from src.data.cached_websites import cached_website_preview
from src.data.contact_card import contact_card_preview
from src.data.published_profile_access import PublishedProfileAccess
from src.data.relationship_dossier import relationship_preview
from src.data.saved_evidence import search_saved_evidence
from tests.test_cached_websites import cached_sources

ACCOUNT = '9007199254740993'


def _pages(cached_sources):
    archive, graph, access = cached_sources
    root_html = '''<a href="/contact">Contact</a><a href="/about">About</a>
      <a href="/projects">Projects</a><a href="https://elsewhere.test/contact">Contact elsewhere</a>'''
    contact_html = '''<p>Public contact desk</p><a href="mailto:team@example.test">Email the team</a>
      <form action="/submit" method="post"><textarea name="message"></textarea></form>
      <a href="https://github.com/example">Code profile</a>'''
    rows = [
        (ACCOUNT, 'https://t.co/stored', 'https://example.test/', 'Home', '2026-07-30T00:00:00Z', None, root_html),
        (ACCOUNT, 'https://example.test/contact', 'https://example.test/contact', 'Contact', '2026-07-31T00:00:00Z', None, contact_html),
        (ACCOUNT, 'https://example.test/about', 'https://example.test/about', 'About', '2026-08-01T00:00:00Z', None,
         '<p>About the studio and its work</p>'),
        (ACCOUNT, 'https://example.test/orphan-contact', 'https://example.test/orphan-contact', 'Orphan', '2026-08-02T00:00:00Z', None,
         '<p>orphan@example.test</p>'),
        (ACCOUNT, 'https://elsewhere.test/contact', 'https://elsewhere.test/contact', 'External', '2026-08-02T00:00:00Z', None,
         '<p>external@example.test</p>'),
        ('200', 'https://example.test/contact', 'https://example.test/contact', 'Other account', '2026-08-03T00:00:00Z', None,
         '<p>other@example.test</p>'),
    ]
    with sqlite3.connect(archive) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',
                   (gzip.compress(root_html.encode()), ACCOUNT))
        for account_id, source, resolved, title, fetched, error, html in rows[1:]:
            db.execute('INSERT INTO bio_link_profile VALUES (?,?,?,?,?,?,?)',
                       (account_id, source, resolved, title, fetched, error, gzip.compress(html.encode())))
    return archive, graph, access


def test_direct_contact_and_about_pages_reach_existing_readers_with_two_source_steps(cached_sources):
    archive, graph, access = _pages(cached_sources)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        default = project_cached_websites(db, archive, [ACCOUNT], published_access=access)
        assert default['pages'] == 1  # Opt-in preserves the existing root-only contract.
        expanded = project_cached_websites(db, archive, [ACCOUNT], published_access=access,
                                           allow_discovered=True)
        assert expanded['pages'] == 3
        before = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('entity', 'relation', 'evidence_snapshot')}
        project_cached_websites(db, archive, [ACCOUNT], published_access=access,
                                allow_discovered=True)
        assert before == {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                          for table in before}
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('has_contact_route','same_person','works_at')").fetchone()[0] == 0

    preview = cached_website_preview(archive, graph, account_id=ACCOUNT, published_access=access)
    pages = {page['url']: page for page in preview['pages']}
    contact = pages['https://example.test/contact']
    about = pages['https://example.test/about']
    assert len(pages) == 3
    assert contact['association']['url'] == 'https://example.test/'
    assert contact['graphEvidenceRef']['associationRef']['relationId'] == \
        pages['https://example.test/']['graphEvidenceRef']['associationRef']['relationId']
    discovery = contact['graphEvidenceRef']['discoveryRef']
    assert discovery['url'] == contact['url']
    assert discovery['snapshotId'] == pages['https://example.test/']['graphEvidenceRef']['snapshotId']
    assert discovery['sourcePointer'].startswith('/derived/links/')

    relationship = relationship_preview(graph, account_id=ACCOUNT, published_access=access)
    path = next(path for path in relationship['paths'] if path['nodes'][-1]['key'] == contact['url'])
    assert [edge['predicate'] for edge in path['edges']] == ['profile_links_to', 'page_links_to']
    link = path['edges'][-1]
    assert link['snapshotId'] == discovery['snapshotId']
    assert link['sourcePointer'] == discovery['sourcePointer']

    card = contact_card_preview(None, account_id=ACCOUNT, account={'accountId': ACCOUNT}, cached=preview)
    values = {item['value']: item for item in card['items']}
    assert 'team@example.test' in values
    assert 'https://example.test/contact' in values  # Form is shown as page clue, not submit URL.
    assert 'https://github.com/example' in values
    assert 'https://example.test/submit' not in values
    assert 'not a reviewed route' in values['team@example.test']['observations'][0]['association']
    assert values['https://example.test/contact']['observations'][0]['kind'] == 'contact_form'

    search = search_saved_evidence(graph, 'studio work', published_access=access)
    hit = next(item for item in search['results'] if item['accountId'] == ACCOUNT)
    assert any(match['evidenceRef']['snapshotId'] == about['graphEvidenceRef']['snapshotId']
               for match in hit['matches'])
    assert 'orphan@example.test' not in json.dumps(preview)
    assert 'external@example.test' not in json.dumps(preview)
    assert 'other@example.test' not in json.dumps(preview)
    assert 'https://elsewhere.test/contact' not in {page['url'] for page in pages.values()}


def test_discovered_page_reader_requires_retained_visible_parent_link(cached_sources):
    archive, graph, access = _pages(cached_sources)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        project_cached_websites(db, archive, [ACCOUNT], published_access=access,
                                allow_discovered=True)
        row = db.execute("SELECT relation_id FROM relation WHERE predicate='page_links_to' "
                         "AND json_extract(attributes_json,'$.linkLabel')='Contact'").fetchone()
        assert row is not None
        db.execute('DELETE FROM relation WHERE relation_id=?', (row['relation_id'],))

    visible = cached_website_preview(archive, graph, account_id=ACCOUNT, published_access=access)
    assert {page['url'] for page in visible['pages']} == {
        'https://example.test/', 'https://example.test/about'}
    withdrawn = cached_website_preview(archive, graph, account_id=ACCOUNT,
                                       published_access=PublishedProfileAccess('withdrawn'))
    assert withdrawn['pages'] == []
