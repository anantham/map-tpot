"""Test intent: authenticated current tags can use independent saved API evidence.

- Source selection never fetches Archive, silently ignores filters or falls back.
- Exact tag changes alter the actual result; wrong source/types/missing data refuse.
- Original paths and private stores are preserved; no private path leaks to clients.
"""
from pathlib import Path

import httpx
import pytest

from tests.test_saved_api_posts import inputs
from tests.test_saved_api_paths import ALICE, typed


@pytest.fixture
def api(typed, tmp_path, monkeypatch):
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH', 'MAP_TPOT_POST_INDEX', 'MAP_TPOT_ARCHIVE_CACHE_DIR',
                'TPOT_LEASE_ROOT', 'TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('SNAPSHOT_DIR', str(tmp_path))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(typed))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from src.data.account_tags import AccountTagStore
    store = AccountTagStore(tmp_path/'account_tags.db')
    for account in (ALICE, '200'):
        store.upsert_tag(ego='curator', account_id=account, tag='Builders', polarity=1)
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.register_blueprint(research_notes_bp)
    requests = []
    def refuse(request):
        requests.append(str(request.url))
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(refuse)) as upstream, app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = upstream
        yield client, store, requests


URL = '/api/research-notes/posts/frontier?source=saved_api_refs&ego=curator&tag=Builders'


def test_explicit_saved_source_auth_path_and_real_tag_refresh(api, typed):
    client, store, requests = api
    original = typed.read_bytes()
    assert client.get(URL).status_code == 401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    response = client.get(URL)
    assert response.status_code == 200
    value = response.get_json()
    assert value['semantics']['channel'] == 'saved_api_refs'
    assert {row['accountId'] for row in value['candidates']} == {'300', '400'}
    assert value['candidates'][0]['supportingPaths'][0]['kind'] == 'saved_api_refs'
    assert str(Path(typed).parent) not in response.get_data(as_text=True)
    store.upsert_tag(ego='curator', account_id='300', tag='Builders', polarity=-1)
    assert {row['accountId'] for row in client.get(URL).get_json()['candidates']} == {'400'}
    store.delete_tag(ego='curator', account_id='300', tag='Builders')
    assert {row['accountId'] for row in client.get(URL).get_json()['candidates']} == {'300', '400'}
    assert not requests and typed.read_bytes() == original


def test_unsupported_filters_and_source_do_not_silently_change_the_request(api):
    client, _, requests = api
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    for suffix in ('minSupport=0', 'limit=0', 'types=', 'types=follow', 'direction=both',
                   'q=design', 'postWithinDays=30', 'latestWithinDays=90', 'minPosts=3'):
        assert client.get(URL+'&'+suffix).status_code == 400, suffix
    assert client.get(URL.replace('source=saved_api_refs', 'source=unknown')).status_code == 400
    assert not requests


def test_missing_saved_graph_is_unavailable_not_empty_or_archive_fallback(api, tmp_path, monkeypatch):
    client, _, requests = api
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(tmp_path/'missing'))
    response = client.get(URL)
    assert response.status_code == 503
    assert str(tmp_path) not in response.get_data(as_text=True)
    assert not requests
