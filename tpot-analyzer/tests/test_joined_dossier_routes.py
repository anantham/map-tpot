"""Test intent: one private dossier consumes offline exact-ID evidence.

Synthetic roots are assigned before imports. Verify success, missing/invalid
supplement, duplicate/contradictory identity and refusal without changing sources.
Curator judgments are fetched through their existing ego-scoped API, not this view.
"""
import json
import os
import sqlite3

import httpx
import pytest


@pytest.fixture
def joined_client(tmp_path, monkeypatch):
    monkeypatch.delenv('MAP_TPOT_RELATIONSHIP_DB', raising=False)
    for name in ("SNAPSHOT_DIR", "TPOT_LOG_DIR", "CACHE_DB_PATH", "ARCHIVE_DB_PATH"):
        monkeypatch.setenv(name, str(tmp_path / name))
    archive = tmp_path / "archive.db"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(archive))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "synthetic-token")
    monkeypatch.setenv("MAP_TPOT_ARCHIVE_SOURCE", "local_custody")
    report = tmp_path / "pilot.json"
    monkeypatch.setenv("MAP_TPOT_DOSSIER_PATH", str(report))
    with sqlite3.connect(archive) as conn:
        conn.executescript("""
            CREATE TABLE profiles(account_id TEXT PRIMARY KEY, username TEXT,
              display_name TEXT, bio TEXT, location TEXT, website TEXT, fetched_at TEXT);
            INSERT INTO profiles VALUES ('100','existing','Example','Old bio',NULL,NULL,NULL);
            CREATE TABLE tweets(tweet_id TEXT, account_id TEXT, full_text TEXT,
              created_at TEXT, favorite_count INTEGER, retweet_count INTEGER, fetched_at TEXT);
            INSERT INTO tweets VALUES ('p200','200','Stored post without archive profile','2026-10-12',1,0,'2026-10-13');
        """)
    payload = {
        "kind": "map-tpot-custody-pilot", "visibility": "private",
        "createdAt": "2026-10-14T08:00:00+00:00", "dossiers": [{
            "accountId": "100", "profiles": [{"source": "archive", "record": {
                "account_id": "100", "username": "existing", "bio": "Old bio"}}],
            "websiteEvidence": [{"source_url": "https://example.org", "title": "Public site"}],
            "publicWorkResearch": [{"sourcePath": "private/source-batch.json", "artifact": {
                "url": "https://example.org/paper", "title": "A public paper", "evidence": "Public work evidence"}}],
            "contactResearch": [{"sourcePath": "private/contacts.json", "record": {
                "account_id": "100", "routes": [{"type": "organisation_forwarding",
                    "address": "public@example.org", "source_url": "https://example.org/contact",
                    "verified_on": "2026-10-13", "instruction": "Ask for the author"}]}}],
            "workingJudgments": [{"ego": "someone-else", "tag_key": "private-tag"}],
            "unresolvedHandleMatches": [{"accountId": "shadow:existing", "username": "existing"}],
        }, {
            "accountId": "200", "profiles": [{"source": "captures", "record": {
                "account_id": "200", "handle": "captureonly", "name": "Captured", "bio": "New bio",
                "captured_at": "2026-10-06"}}], "contactResearch": [],
        }],
    }
    report.write_text(json.dumps(payload))
    report.chmod(0o600)
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(research_notes_bp)
    with app.test_client() as client:
        client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = "synthetic-token"
        yield client, report, payload


def test_existing_profile_gains_source_backed_work_and_contacts(joined_client):
    client, report, _ = joined_client
    before = report.read_bytes()
    response = client.get("/api/research-notes/dossiers/existing?accountId=100")
    assert response.status_code == 200
    data = response.get_json()
    assert data["account"]["accountId"] == "100"
    evidence = data["joinedEvidence"]
    assert evidence["status"] == "available"
    assert evidence["contacts"][0]["type"] == "organisation_forwarding"
    assert evidence["contacts"][0]["instruction"] == "Ask for the author"
    assert evidence["publicWork"][0]["title"] == "A public paper"
    assert evidence["unresolvedHandleMatches"][0]["accountId"] == "shadow:existing"
    assert "private-tag" not in response.get_data(as_text=True)
    assert "someone-else" not in response.get_data(as_text=True)
    assert report.read_bytes() == before


def test_capture_only_profile_and_missing_archive_are_independent(joined_client, monkeypatch, tmp_path):
    client, _, _ = joined_client
    response = client.get("/api/research-notes/dossiers/captureonly?accountId=200")
    assert response.status_code == 200
    assert response.get_json()["account"]["bio"] == "New bio"
    assert response.get_json()["tweets"][0]["text"] == "Stored post without archive profile"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(tmp_path / "unavailable.db"))
    response = client.get("/api/research-notes/dossiers/captureonly?accountId=200")
    assert response.status_code == 200
    assert response.get_json()["archiveStatus"] == "unavailable"
    assert response.get_json()["tweets"] == []


@pytest.mark.parametrize("failure", ["missing", "invalid", "public", "wrong-route-id", "invalid-website-record"])
def test_bad_supplement_does_not_take_down_archive_preview(joined_client, failure):
    client, report, payload = joined_client
    if failure == "missing":
        report.unlink()
    elif failure == "invalid":
        report.write_text("not json")
    elif failure == "public":
        payload["visibility"] = "public"
        report.write_text(json.dumps(payload))
    elif failure == "invalid-website-record":
        payload["dossiers"][0]["websiteEvidence"] = [None]
        report.write_text(json.dumps(payload))
    else:
        payload["dossiers"][0]["contactResearch"][0]["record"]["account_id"] = "other"
        report.write_text(json.dumps(payload))
    response = client.get("/api/research-notes/dossiers/existing")
    assert response.status_code == 200
    assert response.get_json()["joinedEvidence"]["status"] == "unavailable"
    assert "public@example.org" not in response.get_data(as_text=True)


def test_wrong_id_and_duplicate_handle_refused(joined_client):
    client, report, payload = joined_client
    assert client.get("/api/research-notes/dossiers/existing?accountId=200").status_code == 400
    payload["dossiers"][1]["profiles"][0]["record"]["handle"] = "existing"
    report.write_text(json.dumps(payload))
    assert client.get("/api/research-notes/dossiers/existing").status_code == 400


def test_unauthorized_reader_gets_no_contact_data(joined_client):
    client, _, _ = joined_client
    client.environ_base.pop("HTTP_X_TPOT_CURATOR_TOKEN")
    response = client.get("/api/research-notes/dossiers/existing")
    assert response.status_code == 401
    assert "public@example.org" not in response.get_data(as_text=True)


def test_public_reader_is_joined_without_using_local_posts(joined_client, monkeypatch, tmp_path):
    client, _, _ = joined_client
    monkeypatch.delenv("MAP_TPOT_ARCHIVE_SOURCE")
    monkeypatch.setenv("MAP_TPOT_ARCHIVE_CACHE_DIR", str(tmp_path / "private-rest"))
    requests = []
    responses = {
        "all_account": [{"account_id": "100", "username": "existing",
                         "account_display_name": "Current name", "is_tombstone": False}],
        "all_profile": [{"account_id": "100", "bio": "Current public bio", "website": "https://example.org",
                         "location": None, "archive_upload_id": 5, "updated_at": "2026-10-14T00:00:00+00:00"}],
        "enriched_tweets": [{"account_id": "100", "tweet_id": "999", "username": "existing",
                            "full_text": "Current public post", "created_at": "2026-10-14T00:00:00+00:00",
                            "favorite_count": 0, "retweet_count": 0, "reply_to_tweet_id": None,
                            "reply_to_user_id": None, "quoted_tweet_id": None, "conversation_id": "999"}],
    }
    def handler(request):
        resource = request.url.path.rsplit("/", 1)[-1]
        requests.append(resource)
        return httpx.Response(200, json=responses[resource])
    with httpx.Client(transport=httpx.MockTransport(handler)) as upstream:
        client.application.config["COMMUNITY_ARCHIVE_HTTP_CLIENT"] = upstream
        response = client.get("/api/research-notes/dossiers/existing?accountId=100")
        assert response.status_code == 200
        data = response.get_json()
        assert data["account"]["bio"] == "Current public bio"
        assert data["tweets"][0]["text"] == "Current public post"
        assert data["provenance"]["source"] == "community_archive_public_rest"
        assert data["provenance"]["cacheStatus"] == "saved"
        assert data["joinedEvidence"]["contacts"][0]["type"] == "organisation_forwarding"
        requests.clear()
        client.environ_base.pop("HTTP_X_TPOT_CURATOR_TOKEN")
        assert client.get("/api/research-notes/dossiers/existing").status_code == 401
        assert requests == []
    assert len(list((tmp_path / "private-rest").glob("*.json"))) == 3


def test_public_failure_preserves_joined_evidence_without_local_post_fallback(joined_client, monkeypatch):
    client, _, _ = joined_client
    monkeypatch.setenv("MAP_TPOT_ARCHIVE_SOURCE", "community_archive_rest")
    with sqlite3.connect(os.environ["ARCHIVE_DB_PATH"]) as conn:
        conn.execute("INSERT INTO tweets VALUES ('old100','100','Historical text must not leak','2026-01-01',0,0,'2026-01-02')")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429, json={"message": "limited"}))) as upstream:
        client.application.config["COMMUNITY_ARCHIVE_HTTP_CLIENT"] = upstream
        response = client.get("/api/research-notes/dossiers/existing?accountId=100")
    assert response.status_code == 200
    assert response.get_json()["archiveStatus"] == "unavailable"
    assert response.get_json()["tweets"] == []
    assert response.get_json()["joinedEvidence"]["contacts"]
    assert "Historical text must not leak" not in response.get_data(as_text=True)


def test_relationship_sidecar_is_account_scoped_and_private(joined_client, monkeypatch, tmp_path):
    from scripts.verify_map_relationship_pilot import build_pilot
    client, report, payload = joined_client
    payload['dossiers'][0]['websiteEvidence'][0]['account_id'] = '100'
    report.write_text(json.dumps(payload))
    sidecar = tmp_path/'relationships.db'
    build_pilot(report, sidecar)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(sidecar))
    before = sidecar.read_bytes()
    response = client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code == 200
    relationships = response.get_json().get('relationshipEvidence', {})
    assert relationships.get('status') == 'available'
    assert relationships['contacts'][0]['type'] == 'organisation_forwarding'
    assert relationships['contacts'][0]['instruction'] == 'Ask for the author'
    assert 'private-tag' not in response.get_data(as_text=True)
    assert 'someone-else' not in response.get_data(as_text=True)
    assert sidecar.read_bytes() == before
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get('/api/research-notes/dossiers/existing?accountId=100').status_code == 401


def test_missing_relationship_store_does_not_disable_other_sources(joined_client, monkeypatch, tmp_path):
    client, _, _ = joined_client
    missing = tmp_path/'missing-sidecar.db'
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(missing))
    response = client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code == 200
    assert response.get_json().get('relationshipEvidence', {}).get('status') == 'unavailable'
    assert response.get_json()['joinedEvidence']['publicWork'][0]['title'] == 'A public paper'
    assert not missing.exists()

@pytest.mark.parametrize('flag', [True, 'true', 1, 't'])
def test_explicit_archive_tombstone_never_falls_back_to_historical_dossier(joined_client, monkeypatch, flag):
    client, _, _ = joined_client
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE', 'community_archive_rest')
    def transport(request):
        assert request.url.path.endswith('/all_account')
        return httpx.Response(200,json=[{'account_id':'100','username':'existing',
            'account_display_name':'Synthetic restricted record','is_tombstone':flag}])
    with httpx.Client(transport=httpx.MockTransport(transport)) as upstream:
        client.application.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = upstream
        response = client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code == 404
    assert 'Old bio' not in response.get_data(as_text=True)
    assert 'public@example.org' not in response.get_data(as_text=True)

def test_archive_absence_is_not_inferred_withdrawal_of_independent_research(joined_client, monkeypatch):
    client, _, _ = joined_client
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE', 'community_archive_rest')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=[]))) as upstream:
        client.application.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = upstream
        response = client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code == 200
    assert response.get_json()['joinedEvidence']['contacts']


def test_saved_search_requires_auth_and_reports_unconfigured_store(joined_client):
    client, _, _ = joined_client
    response = client.get('/api/research-notes/search?q=backend')
    assert response.status_code == 503
    assert response.get_json()['error']
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get('/api/research-notes/search?q=backend').status_code == 401


def test_saved_read_failure_is_visible_without_hiding_healthy_sources(joined_client, monkeypatch, tmp_path):
    client, _, _ = joined_client
    bad = tmp_path/'unreadable.db'
    bad.write_bytes(b'not a database')
    bad.chmod(0o600)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(bad))
    response = client.get('/api/research-notes/dossiers/existing')
    assert response.status_code == 200
    assert response.get_json()['savedEvidenceStatus'] == 'unavailable'
    assert response.get_json()['joinedEvidence']['publicWork']
    assert client.get('/api/research-notes/search?q=backend').status_code == 503
    bad.chmod(0o644)
    assert client.get('/api/research-notes/search?q=backend').status_code == 503
    assert client.get('/api/research-notes/search?q=x').status_code == 400
