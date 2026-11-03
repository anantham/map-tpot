"""Test intent: preserve literal URL candidates without claiming verification.

- Recover bare/explicit Unicode bio links, punctuation and HTML query text.
- Retain distinct assumed/explicit schemes; exclude unsafe/non-web destinations.
- Email addresses and version numbers are not web links; filenames can be ambiguous.
"""
import pytest

from src.enrichment.bio_url_mentions import bio_url_mentions, normalize_bio_url


def test_literal_text_scheme_and_query_survive_recognition():
    text = '🪷 (alice.example.org/path). https://example.org/?a=1&amp;b=2'
    links = bio_url_mentions(text)
    assert links == [
        {'url':'https://alice.example.org/path','literal':'alice.example.org/path','schemeAssumed':True},
        {'url':'https://example.org/?a=1&b=2','literal':'https://example.org/?a=1&amp;b=2','schemeAssumed':False}]
    assert all(link['literal'] in text for link in links)


def test_qualified_mentions_are_not_collapsed_and_all_links_survive():
    links = bio_url_mentions('example.org https://example.org example.org')
    assert len(links) == 2 and {link['schemeAssumed'] for link in links} == {False,True}
    assert len(bio_url_mentions(' '.join(f'site{n}.example.org/' for n in range(7)))) == 7
    assert bio_url_mentions('//example.org/a')[0]['url'] == 'https://example.org/a'


def test_unsafe_nonweb_email_and_version_text_is_not_a_site():
    text = ('alice@example.org javascript:alert(1) ftp://example.org/ file:///tmp/a '
            'https://user:secret@example.org/ http://localhost/a http://127.0.0.1/a '
            'https://x.com/alice https://twitter.com/alice Version 1.2.3.4')
    assert bio_url_mentions(text) == []
    assert bio_url_mentions(None) == []
    with pytest.raises(ValueError,match='text or unknown'):bio_url_mentions({'bio':'bad'})


@pytest.mark.parametrize('literal,assumed',[
    ('example.org',1),('https://example.org',True),('example.org',False),
    ('example.org\n.evil.test',True),('http://example.org:invalid/',False),
    ('http://127.1/',False),('http://0177.0.0.1/',False),
    ('https://[::1]/',False),('https://example.local/',False)])
def test_normalization_refuses_conflicting_or_damaged_claims(literal,assumed):
    assert normalize_bio_url(literal,assumed) is None


def test_ambiguous_domain_like_filename_remains_a_candidate_not_a_verified_site():
    link = bio_url_mentions('notes.md')[0]  # .md is also a domain suffix.
    assert link['literal'] == 'notes.md' and link['schemeAssumed'] is True
    assert 'verified' not in link


@pytest.mark.parametrize('prefix',['My channel','私'])
def test_explicit_http_link_survives_when_glued_to_preceding_text(prefix):
    links=bio_url_mentions(prefix+'https://example.org/channel.')
    assert links==[{'url':'https://example.org/channel','literal':'https://example.org/channel.',
                    'schemeAssumed':False}]
