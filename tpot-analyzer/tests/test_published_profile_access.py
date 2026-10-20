"""Current eligibility is request-scoped; independent evidence survives refusal."""
import json
import sqlite3

import httpx
import pytest

from scripts.verify_current_archive_profiles import build_profile_copy
from src.data.published_profile_access import BASE, load_published_profile_access
from src.data.relationship_dossier import relationship_preview
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import saved_preview, search_saved_evidence
from tests.test_published_profiles import bundle, legacy_graph

ACCOUNT = '9007199254740993'


@pytest.fixture
def graph(bundle, tmp_path):
    original = legacy_graph(tmp_path)
    copied = tmp_path/'copied'
    build_profile_copy(bundle, original, copied)
    database = copied/'relationships.db'
    extra = tmp_path/'independent.json'
    extra.write_text(json.dumps({'url': 'https://example.test/alpha', 'link': 'https://bsky.app/profile/example.test',
        'follow': {'source': ACCOUNT, 'target': '200'}, 'request': {'userId': ACCOUNT}}))
    with sqlite3.connect(database) as db:
        writer = CaptureWriter(db)
        snapshot, _ = writer.source(extra)
        writer.relation(writer.entity('web_resource', 'https://example.test/alpha'), 'page_links_to',
            writer.entity('web_resource', 'https://bsky.app/profile/example.test'), snapshot, '/link', None, {})
        writer.relation(writer.entity('x_account', ACCOUNT), 'follows_observed', writer.entity('x_account', '200'),
            snapshot, '/follow', None, {'receiptRef': {'snapshotId': snapshot, 'sourcePointer': '/request'}})
    return database, bundle


def upstream(bundle, fault=None):
    pointer = json.loads((bundle/'latest.json').read_bytes())
    manifest = json.loads((bundle/'manifest.json').read_bytes())
    if fault == 'withdrawn': manifest['publication']['status'] = 'withdrawn'
    if fault == 'checksum': manifest['files']['profiles']['sha256'] = '0'*64
    if fault == 'missing-subject':
        pointer['eligible_account_ids'][0] = '999'
    if fault == 'superseded':
        pointer['export_id'] = manifest['export_id'] = '2026-10-16T07-06-19Z'
        pointer['manifest_url'] = BASE+'v1/'+pointer['export_id']+'/manifest.json'
        manifest['publication']['urls']['profiles'] = BASE+'v1/'+pointer['export_id']+'/profiles.parquet'
    if fault == 'schema': pointer['eligible_account_ids'] = [ACCOUNT, ACCOUNT]
    requests = []
    def respond(request):
        requests.append(str(request.url))
        assert request.method == 'GET' and not request.url.query
        if fault == 'http': return httpx.Response(503)
        if fault == 'oversize': return httpx.Response(200, content=b' '*131073)
        return httpx.Response(200, json=pointer if request.url.path.endswith('/latest.json') else manifest)
    return httpx.Client(transport=httpx.MockTransport(respond)), requests


def test_current_profile_is_visible_with_provenance_and_no_source_mutation(graph):
    database, folder = graph
    before = database.read_bytes()
    with upstream(folder)[0] as client:
        access = load_published_profile_access(database, client=client)
    assert access.status == 'available'
    result = search_saved_evidence(database, 'Contemplative', published_access=access)
    assert result['total'] == 1 and result['coverage']['profileAccounts'] == 2
    assert result['publishedProfiles']['status'] == 'available'
    hit = result['results'][0]
    assert hit['accountId'] == ACCOUNT
    assert hit['sourceKind'] == 'community_archive_published_profile'
    assert 'not field-level' in hit['sourceBoundary']
    view = saved_preview(database, handle='Alpha', account_id=ACCOUNT, published_access=access)
    assert view['account']['website'] == 'https://example.test/alpha'
    paths = relationship_preview(database, account_id=ACCOUNT, published_access=access)['paths']
    assert len(paths) == 1 and paths[0]['edges'][0]['sourceKind'] == hit['sourceKind']
    assert database.read_bytes() == before


@pytest.mark.parametrize('fault', ['withdrawn', 'checksum', 'missing-subject', 'superseded', 'schema', 'http', 'oversize'])
def test_unusable_current_source_hides_profile_and_website_not_independent_profile(graph, fault):
    database, folder = graph
    with upstream(folder, fault)[0] as client:
        access = load_published_profile_access(database, client=client)
    found = search_saved_evidence(database, 'Contemplative', published_access=access)
    assert found['total'] == 0
    assert found['publishedProfiles']['hiddenProfileObservations'] >= 1
    assert saved_preview(database, handle='Alpha', published_access=access)['status'] == 'not_found'
    assert relationship_preview(database, account_id=ACCOUNT, published_access=access)['paths'] == []
    old = search_saved_evidence(database, 'OldBeta', published_access=access)
    # Beta remains eligible in a partial withdrawal, so its current handle wins.
    if fault != 'missing-subject': assert old['total'] == 1
    assert database.exists()


def test_unchecked_readers_never_show_new_archive_facts(graph):
    database, _ = graph
    assert saved_preview(database, handle='Alpha')['status'] == 'not_found'
    assert search_saved_evidence(database, 'Contemplative')['total'] == 0
    assert relationship_preview(database, account_id=ACCOUNT)['paths'] == []
    assert search_saved_evidence(database, 'OldBeta')['total'] == 1


def test_store_without_this_source_does_not_fetch_metadata(tmp_path):
    database = legacy_graph(tmp_path)
    database.chmod(0o600)
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail('unexpected network'))) as client:
        assert load_published_profile_access(database, client=client).status == 'not_present'


@pytest.mark.parametrize('fault', [None, 'withdrawn', 'http', 'checksum'])
def test_review_routes_share_one_fresh_gate_and_do_not_fallback_to_hidden_profiles(graph, tmp_path, monkeypatch, fault):
    database, folder = graph
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(database))
    monkeypatch.delenv('MAP_TPOT_DOSSIER_PATH', raising=False)
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE', 'community_archive_rest')
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(research_notes_bp)
    transport_client, requests = upstream(folder, fault)
    def respond(request):
        if '/rest/v1/' in request.url.path:
            return httpx.Response(200, json=[])
        return transport_client.send(transport_client.build_request('GET', str(request.url)))
    with transport_client, httpx.Client(transport=httpx.MockTransport(respond)) as public, app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        assert client.get('/api/research-notes/search?q=Contemplative').status_code == 401
        assert not requests
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
        result = client.get('/api/research-notes/search?q=Contemplative').get_json()
        assert result['total'] == (1 if fault is None else 0)
        dossier = client.get(f'/api/research-notes/dossiers/Alpha?accountId={ACCOUNT}')
        if fault is None:
            assert dossier.status_code == 200
            payload = dossier.get_json()
            assert payload['account']['sourceKind'] == 'community_archive_published_profile'
            assert payload['archiveStatus'] == 'unavailable' and payload['tweets'] == []
            assert len(payload['relationshipEvidence']['paths']) == 1
            assert payload['publishedProfiles']['status'] == 'available'
        else:
            assert dossier.status_code == 404
            assert 'hidden' in dossier.get_json()['error']
            assert dossier.get_json()['details']['publishedProfiles']['status'] != 'available'
            assert 'example.test/alpha' not in dossier.get_data(as_text=True)
            old = client.get('/api/research-notes/dossiers/OldBeta?accountId=200')
            assert old.status_code == 200
            assert old.get_json()['account']['username'] == 'OldBeta'


def test_retry_rechecks_publication_without_stale_permission(graph):
    database, folder = graph
    with upstream(folder, 'withdrawn')[0] as client:
        refused = load_published_profile_access(database, client=client)
    assert search_saved_evidence(database, 'Contemplative', published_access=refused)['total'] == 0
    with upstream(folder)[0] as client:
        current = load_published_profile_access(database, client=client)
    assert search_saved_evidence(database, 'Contemplative', published_access=current)['total'] == 1


@pytest.mark.parametrize('fault', ['withdrawn', 'checksum', 'http'])
def test_scoped_search_survives_hidden_root_profile_without_using_its_name(graph, fault):
    database, folder = graph
    with upstream(folder, fault)[0] as client:
        access = load_published_profile_access(database, client=client)
    result = search_saved_evidence(database, 'OldBeta', from_account_id=ACCOUNT, published_access=access)
    assert result['total'] == 1
    assert result['networkScope']['fromUsername'] is None
    path = result['results'][0]['networkPath']
    assert path['nodes'][0]['accountId'] == ACCOUNT and path['nodes'][0]['username'] is None
    assert 'Alpha' not in json.dumps(path)


def test_hidden_handle_reuse_is_not_a_false_identity_conflict(graph):
    database, folder = graph
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT relation_id,attributes_json FROM relation WHERE json_extract(attributes_json,'$.handle')='OldBeta'").fetchone()
        attrs = json.loads(row[1]); attrs['handle'] = 'Alpha'
        db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?', (json.dumps(attrs), row[0]))
    with upstream(folder, 'withdrawn')[0] as client:
        access = load_published_profile_access(database, client=client)
    assert saved_preview(database, handle='Alpha', account_id=ACCOUNT, published_access=access)['status'] == 'not_found'
    with pytest.raises(ValueError, match='disagree'):
        saved_preview(database, handle='Alpha', account_id='999', published_access=access)


def test_damaged_profile_attributes_are_server_unavailability_not_bad_user_input(graph):
    database, _ = graph
    with sqlite3.connect(database) as db:
        db.execute("UPDATE relation SET attributes_json='[]' WHERE predicate='profile_observation'")
    with pytest.raises(RuntimeError, match='attributes'):
        search_saved_evidence(database, 'OldBeta')
