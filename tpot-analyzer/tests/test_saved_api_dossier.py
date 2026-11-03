"""Test intent: already-admitted API posts reach the exact-account Review card.

- Archive failure does not hide independent historical posts or their sources.
- Limits/counts, foreign identities, restrictions and optional-store errors stay honest.
- Reads preserve graph/source bytes; no fetching, new admission or tag mutation.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.saved_api_posts import import_api_post_observations
from tests.test_saved_api_posts import inputs

ALICE = '9007199254740993'


@pytest.fixture
def api_dossier(inputs, monkeypatch, tmp_path, temp_snapshot_dir):
    source, graph = inputs
    with sqlite3.connect(graph) as db:
        import_api_post_observations(db, source)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(graph))
    monkeypatch.setenv('MAP_TPOT_DOSSIER_PATH', str(tmp_path/'no-joined-file'))
    monkeypatch.setenv('ARCHIVE_DB_PATH', str(source))
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE', 'community_archive_rest')
    monkeypatch.setenv('TPOT_LOG_DIR', str(tmp_path/'logs'))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-api-dossier')
    from src.api.server import create_app
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as upstream:
        app = create_app({'TESTING': True, 'COMMUNITY_ARCHIVE_HTTP_CLIENT': upstream})
        with app.test_client() as client:
            client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-api-dossier'
            yield client, source, graph


def test_independent_posts_survive_archive_failure_with_exact_sources(api_dossier):
    client, source, graph = api_dossier
    before = {path: path.read_bytes() for path in (source, graph)}
    response = client.get(f'/api/research-notes/dossiers/alice?accountId={ALICE}&limit=1')
    assert response.status_code == 200
    data = response.get_json()
    evidence = data.get('savedApiPosts', {})
    assert evidence.get('status') == 'available'
    assert evidence['accountId'] == data['account']['accountId'] == ALICE
    assert data['tweets'] == [] and data['archiveStatus'] == 'unavailable'
    assert evidence['total'] == 2 and evidence['truncated'] is True
    assert len(evidence['posts']) == 1
    post = evidence['posts'][0]
    assert post['tweetId'] == '1002' and post['text'] == 'Buddhism Marxist tools 1002'
    assert post['evidenceRef']['sourcePointer'] == '/row/text'
    assert post['references'][0]['targetAccountId'] == '300'
    with sqlite3.connect(graph) as db:
        payload = json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',
            (post['evidenceRef']['snapshotId'],)).fetchone()[0])
    assert payload['row']['text'] == post['text']
    assert str(source) not in response.get_data(as_text=True)
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_another_account_has_no_posts_not_alices_posts(api_dossier):
    client, _, _ = api_dossier
    response = client.get('/api/research-notes/dossiers/bob?accountId=200')
    assert response.status_code == 200
    evidence = response.get_json().get('savedApiPosts', {})
    assert evidence.get('status') == 'not_present'
    assert evidence['accountId'] == '200' and evidence['posts'] == []
    assert 'Buddhism Marxist' not in response.get_data(as_text=True)


def test_optional_post_projection_failure_keeps_healthy_card(api_dossier, monkeypatch):
    import src.api.routes.research_notes as routes
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE_CANARY must not enter the response')
    monkeypatch.setattr(routes, 'saved_api_post_preview', fail, raising=False)
    client, _, _ = api_dossier
    response = client.get(f'/api/research-notes/dossiers/alice?accountId={ALICE}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['account']['accountId'] == ALICE
    assert data.get('savedApiPosts', {}).get('status') == 'unavailable'
    assert data['savedApiPosts']['total'] is None
    assert 'PRIVATE_CANARY' not in response.get_data(as_text=True)


def test_identity_disagreement_and_explicit_restriction_still_refuse(api_dossier, monkeypatch):
    import src.api.routes.research_notes as routes
    from src.data.community_archive_dossier import PublicAccountRestricted
    client, _, _ = api_dossier
    mismatch = client.get('/api/research-notes/dossiers/alice?accountId=200')
    assert mismatch.status_code == 400 and 'savedApiPosts' not in mismatch.get_json()
    def restricted(*args, **kwargs):
        raise PublicAccountRestricted('Account restricted')
    monkeypatch.setattr(routes, 'load_public_archive_dossier', restricted)
    response = client.get(f'/api/research-notes/dossiers/alice?accountId={ALICE}')
    assert response.status_code == 404
    assert 'savedApiPosts' not in response.get_json()
    assert 'Buddhism Marxist' not in response.get_data(as_text=True)


def test_posts_remain_private(api_dossier):
    client, _, _ = api_dossier
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get(f'/api/research-notes/dossiers/alice?accountId={ALICE}').status_code == 401
