"""Test intent: shared path prefixes are one witness, not repeated confirmations.

- Collapse identical observations in the public contact-card result.
- Preserve distinct source, field, time and claim evidence for equal URLs.
- Coverage counts describe displayed observations after deduplication.
"""
from copy import deepcopy

import pytest

from src.data.contact_card import contact_card_preview


ACCOUNT = '9007199254740993'
URL = 'https://github.com/synthetic'


def path():
    return {'nodes': [{'kind': 'x_account', 'key': ACCOUNT},
                      {'kind': 'web_resource', 'key': URL}],
            'edges': [{'predicate': 'profile_links_to', 'snapshotId': 'a' * 64,
                       'sourcePointer': '/profile/url', 'observedAt': '2026-10-01'}]}


def card(paths):
    return contact_card_preview(None, account_id=ACCOUNT,
        account={'accountId': ACCOUNT},
        relationships={'status': 'available', 'accountId': ACCOUNT,
                       'paths': paths, 'contacts': []})


def test_shared_path_witness_is_displayed_and_counted_once():
    result = card([path() for _ in range(40)])
    assert len(result['items']) == 1
    assert len(result['items'][0]['observations']) == 1
    observation = result['items'][0]['observations'][0]
    assert observation['sourceRefs'] == [{'snapshotId': 'a' * 64,
        'sourcePointer': '/profile/url', 'observedAt': '2026-10-01'}]
    coverage = next(c for c in result['coverage'] if c['key'] == 'relationships')
    assert coverage['shownCount'] == 1


@pytest.mark.parametrize('field,value', [
    ('snapshotId', 'b' * 64),
    ('sourcePointer', '/profile/description/urls/0'),
    ('observedAt', '2026-10-02'),
    ('linkLabel', 'Public projects'),
    ('linkContext', 'A link mentioned in the saved page'),
    ('claimKind', 'sameAs'),
    ('boundary', 'Historical publisher assertion only'),
    ('capturedAt', '2026-09-30'),
])
def test_equal_url_preserves_every_distinct_observation(field, value):
    first = path()
    second = deepcopy(first)
    second['edges'][0][field] = value
    result = card([first, second, deepcopy(first), deepcopy(second)])
    assert len(result['items']) == 1
    assert len(result['items'][0]['observations']) == 2
    assert next(c for c in result['coverage']
                if c['key'] == 'relationships')['shownCount'] == 2


def test_equal_target_keeps_distinct_source_pages():
    first = path()
    first['nodes'][0] = {'kind': 'web_resource', 'key': 'https://one.test/'}
    second = deepcopy(first)
    second['nodes'][0]['key'] = 'https://two.test/'
    result = card([first, second, deepcopy(first)])
    observations = result['items'][0]['observations']
    assert len(observations) == 2
    assert {o['sourceUrl'] for o in observations} == {'https://one.test/', 'https://two.test/'}
