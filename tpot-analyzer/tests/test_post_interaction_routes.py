"""Test intent: curator-only typed path discovery with synthetic publication/state.

- Search and source choices honor publication and intermediate-node eligibility.
- Missing projection is unavailable, not zero; independent contacts may be absent.
"""
import json
import sqlite3

import pytest

from tests.test_post_interactions import index, network_bundle
from tests.test_post_search import ACCOUNT, posts, public_client
from tests.test_published_profiles import bundle


@pytest.fixture
def api(index, network_bundle, tmp_path, monkeypatch):
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX', str(index))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    monkeypatch.delenv('MAP_TPOT_RELATIONSHIP_DB', raising=False)
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__); app.register_blueprint(research_notes_bp)
    with public_client(network_bundle) as public, app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        yield client, app


def test_typed_search_works_without_independent_follow_graph_and_stays_private(api, tmp_path):
    client, _ = api
    url = '/api/research-notes/posts/search?q=Buddhism+Marxist&networkKind=post_references&fromAccountId='+ACCOUNT
    assert client.get(url).status_code == 401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    response = client.get(url)
    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 1 and data['results'][0]['accountId'] == '300'
    path = data['results'][0]['networkPath']
    assert path['kind'] == 'post_references' and path['hopCount'] == 2
    assert [node['accountId'] for node in path['nodes']] == [ACCOUNT, '200', '300']
    assert str(tmp_path) not in response.get_data(as_text=True)


def test_incoming_search_does_not_reverse_the_original_observation(api):
    client, _ = api; client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    data = client.get('/api/research-notes/posts/search?q=Buddhism+Marxist&networkKind=post_references&fromAccountId=300&direction=incoming').get_json()
    assert data['total'] == 1 and data['results'][0]['accountId'] == ACCOUNT
    first = data['results'][0]['networkPath']['edges'][0]
    assert first['sourceAccountId'] == '200' and first['targetAccountId'] == '300'


def test_reference_source_choices_and_source_refusal(api, network_bundle):
    client, app = api
    url = '/api/research-notes/posts/network/sources'
    assert client.get(url).status_code == 401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    result = client.get(url)
    assert result.status_code == 200 and len(result.get_json()['sources']) == 3
    with public_client(network_bundle, 'withdrawn') as public:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        hidden = client.get(url).get_json()
        assert hidden['status'] == 'source_hidden' and hidden['sources'] == []
        assert hidden['coverage'] is None


def test_hidden_intermediate_does_not_bridge_and_invalid_types_refuse(api, network_bundle):
    client, app = api; client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    with public_client(network_bundle, 'subject') as public:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        response = client.get('/api/research-notes/posts/search?q=Buddhism&networkKind=post_references&fromAccountId='+ACCOUNT)
        assert response.status_code == 422 and 'Alpha' not in response.get_data(as_text=True)
    for suffix in ('networkKind=friendship', 'networkKind=post_references&types=friend', 'networkKind=post_references&direction=either'):
        assert client.get('/api/research-notes/posts/search?q=Buddhism&'+suffix).status_code == 400


def test_unbuilt_projection_refuses_but_text_search_still_works(api, index):
    client, _ = api; client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    with sqlite3.connect(index) as db:
        db.execute("DELETE FROM meta WHERE key='interactionVersion'")
    assert client.get('/api/research-notes/posts/network/sources').status_code == 503
    text = client.get('/api/research-notes/posts/search?q=Buddhism').get_json()
    assert text['status'] == 'available' and text['total'] == 3
