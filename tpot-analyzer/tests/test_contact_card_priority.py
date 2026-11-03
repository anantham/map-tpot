"""Contact-card behavior, not confidence scoring or new evidence admission.

Intent:
- Email/form/reported-contact affordances survive generic URL preview pressure.
- Ordering is stable within a tier and preserves complete grouped witnesses.
- Source/identity refusal, bounds and honest displayed counts remain in force.
"""
import copy

import pytest

from src.data.contact_card import contact_card_preview

ID = '9007199254740993'


def noisy_inputs():
    paths = [{'nodes': [{'kind': 'x_account', 'key': ID},
                       {'kind': 'web_resource', 'key': f'https://example.test/work/{n}'}],
              'edges': [{'predicate': 'profile_links_to', 'snapshotId': 'a'*64,
                         'sourcePointer': f'/links/{n}', 'observedAt': '2026-10-01'}]}
             for n in range(45)]
    return dict(account_id=ID, account={'accountId': ID},
                relationships={'status': 'available', 'accountId': ID,
                               'contacts': [], 'paths': paths},
                cached={'status': 'available', 'accountId': ID, 'pages': [{
                    'status': 'available', 'url': 'https://example.test/contact',
                    'sourceUrl': 'https://example.test/contact', 'capturedAt': '2026-10-02',
                    'emailClues': [{'address': 'office@example.test',
                                   'context': 'Organisation inbox; ask for the named member.'}],
                    'messageForms': [{'action': 'https://example.test/submit',
                                      'context': 'Untested message form'}],
                    'links': [], 'evidenceRef': {'cacheRow': {'accountId': ID}},
                    'graphEvidenceRef': {'snapshotId': 'b'*64, 'sourcePointer': '/source'}}]})


def test_page_email_and_form_survive_default_card_limit_with_source_caveats():
    result = contact_card_preview(None, **noisy_inputs())
    assert len(result['items']) == 40 and result['truncated']
    assert [item['value'] for item in result['items'][:2]] == [
        'office@example.test', 'https://example.test/contact']
    email, form = result['items'][:2]
    assert email['observations'][0]['kind'] == 'cached_email'
    assert 'not a reviewed route' in email['observations'][0]['association']
    assert email['observations'][0]['sourceRefs'][-1]['sourcePointer'] == '/derived/emailClues/0'
    assert form['observations'][0]['kind'] == 'contact_form'
    assert 'https://example.test/submit' not in repr(result)
    assert next(c for c in result['coverage'] if c['key'] == 'cached')['shownCount'] == 2


def test_reported_contacts_survive_links_from_the_same_earlier_family():
    inputs = noisy_inputs()
    inputs['joined'] = {'status': 'available', 'accountId': ID,
        'websites': [{'url': 'https://example.test/', 'linkStatus': 'available',
                      'links': [f'https://example.test/earlier/{n}' for n in range(45)]}],
        'contacts': [{'type': 'organisation_forwarding', 'address': 'team@example.test',
                      'source_url': 'https://example.test/team', 'instruction': 'Ask for the member'}]}
    result = contact_card_preview(None, **inputs, limit=3)
    assert {item['value'] for item in result['items']} == {
        'team@example.test', 'office@example.test', 'https://example.test/contact'}
    assert result['items'][0]['observations'][0]['kind'] == 'organisation_forwarding'


def test_wide_card_keeps_all_values_complete_witnesses_and_stable_order():
    inputs = noisy_inputs()
    inputs['cached']['pages'][0]['links'] = [{'url': 'https://example.test/work/0',
        'label': 'Same work from another source', 'context': 'Distinct observation'}]
    original = copy.deepcopy(inputs)
    wide = contact_card_preview(None, **inputs, limit=100)
    narrow = contact_card_preview(None, **inputs, limit=40)
    assert len(wide['items']) == 47 and not wide['truncated']
    assert narrow['items'] == wide['items'][:40]
    assert [item['value'] for item in wide['items'][2:]] == [
        f'https://example.test/work/{n}' for n in range(45)]
    assert len(wide['items'][2]['observations']) == 2
    assert inputs == original


@pytest.mark.parametrize('failure', ['wrong_account', 'unavailable_page', 'unbound_page'])
def test_priority_does_not_admit_wrong_or_unavailable_cached_clues(failure):
    inputs = noisy_inputs()
    if failure == 'wrong_account':
        inputs['cached']['accountId'] = '200'
    elif failure == 'unavailable_page':
        inputs['cached']['pages'][0]['status'] = 'unavailable'
    else:
        inputs['cached']['pages'][0]['evidenceRef']['cacheRow']['accountId'] = '200'
    result = contact_card_preview(None, **inputs)
    assert not any(item['platform'] == 'email' for item in result['items'])
    assert result['items'][0]['value'] == 'https://example.test/work/0'


def test_contact_only_limit_remains_explicit_and_stable():
    inputs = noisy_inputs()
    page = inputs['cached']['pages'][0]
    page['emailClues'] = [{'address': f'team{n}@example.test', 'context': 'Public company inbox'}
                          for n in range(5)]
    result = contact_card_preview(None, **inputs, limit=2)
    assert [item['value'] for item in result['items']] == ['team0@example.test', 'team1@example.test']
    assert result['truncated']
    assert next(c for c in result['coverage'] if c['key'] == 'cached')['shownCount'] == 2
