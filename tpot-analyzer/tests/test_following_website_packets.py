"""Packet verification preserves multiple retained observations of one URL."""
import base64
import gzip
import json

import pytest

from scripts.verify_following_website_packets import verify
from src.enrichment.website_context import extract_website_context


def test_duplicate_parent_urls_do_not_discard_a_retained_discovery_link(tmp_path):
    cohort = tmp_path/'cohort.json'
    packets = tmp_path/'packets'
    packets.mkdir(mode=0o700)
    root = 'https://example.test/'
    child = root+'contact'
    cohort.write_text(json.dumps({'accounts': [{'accountId': '123', 'handle': 'example',
        'status': 'pending', 'roots': [{'url': root}], 'savedPages': [],
        'existingPages': [{'url': root, 'links': [{'url': child}]},
                          {'url': root, 'links': [{'url': root+'other'}]}]}]}))
    cohort.chmod(0o600)
    html = b'<p>Contact the studio: team@example.test</p>'
    packet = {'accountId': '123', 'handle': 'example', 'checks': [], 'pages': [{
        'account_id': '123', 'source_url': child, 'resolved_url': child,
        'fetched_at': '2026-10-22T00:00:00Z', 'discoveredFrom': root,
        'htmlGzipBase64': base64.b64encode(gzip.compress(html)).decode(),
        'context': extract_website_context(html.decode(), child), 'acquisition': 'public_get'}]}
    path = packets/'123.json'
    path.write_text(json.dumps(packet));path.chmod(0o600)
    result = verify(cohort, [packets])
    assert result['packetAccounts'] == 1 and result['publicPagesFetched'] == 1
    assert result['emailClueObservations'] == 1
    # Having a parent URL alone is not sufficient: a literal discovery link is required.
    packet['pages'][0]['source_url'] = root+'unlinked'
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError, match='discovery link'):
        verify(cohort, [packets])
