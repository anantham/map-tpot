"""Test intent: retain literal link/contact context without inventing ownership.

- Public HTTP links preserve labels, relative URLs, Unicode and source context.
- Visible email/mailto clues survive independently of general link caps.
- Scripts/templates, unsafe URLs and forms without message fields are excluded.
- No HTML execution or network calls; legal/third-party links remain just links.
"""
from src.enrichment.website_context import extract_website_context


def test_link_labels_context_and_unclassified_email_are_retained():
    page=extract_website_context('''<title>Research home</title><p>Our organisation can forward notes.
        <a href="/contact?a=1&amp;b=2">Contact the team</a>
        <a href="mailto:team@example.test?subject=Hello">General inbox</a></p>
        <p>A theme by <a href="https://github.com/example/theme">Theme author</a>.</p>
        <p>Quoted guest address: guest@example.test</p>''','https://example.test/')
    assert len(page['links'])==2
    assert page['links'][0]['url']=='https://example.test/contact?a=1&b=2'
    assert page['links'][0]['label']=='Contact the team'
    assert 'organisation can forward' in page['links'][0]['context']
    assert {x['address'] for x in page['emailClues']}=={'team@example.test','guest@example.test'}
    assert next(x for x in page['emailClues'] if x['address']=='team@example.test')['kind']=='mailto'
    assert 'ownership' in page['boundary']
    assert 'person' not in page['links'][1]


def test_hidden_markup_does_not_generate_email_or_executable_links():
    page=extract_website_context('''<script>let x="secret@example.test"</script>
        <template><a href="mailto:hidden@example.test">Hidden</a></template>
        <style>ignored</style><p hidden>private@example.test</p>
        <a href="javascript:alert(1)">Bad</a><a href="https://user:pass@example.test">Bad</a>
        <a href="https://[">Malformed</a><a href="#local">Local</a>
        <a href="/notes">Déjà vu</a>''','https://example.test/')
    assert page['emailClues']==[]
    assert [x['label'] for x in page['links']]==['Déjà vu']
    assert 'secret@' not in page['text']


def test_email_after_many_links_is_preserved_and_truncation_is_explicit():
    html=''.join(f'<a href="/page/{n}">Page {n}</a>' for n in range(240))
    html+='<footer>Send a note <a href="mailto:hello@example.test">Email</a></footer>'
    page=extract_website_context(html,'https://example.test/')
    assert page['emailClues'][0]['address']=='hello@example.test'
    assert page['linkCount']==240 and page['linksTruncated'] is True


def test_message_forms_are_markup_not_tested_contact_routes():
    page=extract_website_context('''<p>Leave a message.</p><form action="/send" method="post">
        <input name="email"><textarea name="message"></textarea><button>Send</button></form>
        <form action="/subscribe"><input name="email"></form>''','https://example.test/')
    assert len(page['messageForms'])==1
    assert page['messageForms'][0]['action']=='https://example.test/send'
    assert page['messageForms'][0]['tested'] is False


def test_closing_ancestor_does_not_unhide_unclosed_noscript_content():
    page=extract_website_context('<div><noscript><p>ignored</div>hidden@example.test</noscript>'
        '<p>Actual page text</p>','https://example.test/')
    assert page['emailClues']==[]
    assert 'hidden@' not in page['text'] and 'Actual page text' in page['text']


def test_explicit_base_href_is_used_for_relative_links():
    page=extract_website_context('<head><base href="https://assets.example.test/notes/"></head>'
        '<a href="../about">About</a>','https://example.test/')
    assert page['links'][0]['url']=='https://assets.example.test/about'
    assert page['linkBaseFromMarkup'] is True
