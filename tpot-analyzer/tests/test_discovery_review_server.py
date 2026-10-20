"""Tailnet review: owner access, same-origin writes, private static files.

Tests use synthetic evidence and separate temporary answer databases.
"""
import json

import pytest

from scripts.serve_discovery_review import create_review_app

ORIGIN = "https://review.example.ts.net:5444"
OWNER = "owner@example.test"


@pytest.fixture
def review_server(tmp_path, monkeypatch):
    packet = tmp_path / "manifest.json"
    packet.write_text(json.dumps({
        "kind": "formative_discovery_review", "status": "unjudged",
        "freeze": {"ego": "curator"}, "review_order": ["101"],
        "evidence": {"101": {"account_id": "101", "username": "example",
                              "profile": None, "posts": []}},
    }))
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "assets").mkdir()
    (dist / "discovery-review.html").write_text("<h1>Discovery review</h1>")
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "server-test-secret")
    app = create_review_app(packet_path=packet, answer_db=tmp_path / "answers.db",
                            dist_dir=dist, owner_login=OWNER, origin=ORIGIN)
    app.config["TESTING"] = True
    return app.test_client()


def test_owner_gets_review_and_masked_api(review_server):
    headers = {"Tailscale-User-Login": OWNER}
    page = review_server.get("/", base_url=ORIGIN, headers=headers)
    assert page.status_code == 200
    assert b"Discovery review" in page.data
    response = review_server.get("/api/discovery-review", base_url=ORIGIN, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["totalCount"] == 1
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("headers", [{}, {"Tailscale-User-Login": "other@example.test"}])
def test_missing_or_other_owner_cannot_read(review_server, headers):
    assert review_server.get("/", base_url=ORIGIN, headers=headers).status_code == 403
    assert review_server.get("/api/discovery-review", base_url=ORIGIN,
                             headers=headers).status_code == 403


def test_direct_nonloopback_request_is_rejected(review_server):
    response = review_server.get("/", base_url=ORIGIN,
                                 headers={"Tailscale-User-Login": OWNER},
                                 environ_overrides={"REMOTE_ADDR": "100.64.0.9"})
    assert response.status_code == 403


def test_origin_required_for_writes_and_correct_origin_saves(review_server):
    owner = {"Tailscale-User-Login": OWNER}
    packet = review_server.get("/api/discovery-review", base_url=ORIGIN, headers=owner).get_json()
    body = {"packetId": packet["packetId"], "relevance": "IN", "known": "NO",
            "glad": "YES", "note": "Synthetic test answer"}
    url = "/api/discovery-review/answers/101"
    for origin in (None, "https://other.example.test"):
        headers = dict(owner)
        if origin:
            headers["Origin"] = origin
        assert review_server.put(url, base_url=ORIGIN, headers=headers, json=body).status_code == 403
    response = review_server.put(url, base_url=ORIGIN, json=body,
                                 headers={**owner, "Origin": ORIGIN})
    assert response.status_code == 200
    assert response.get_json()["completedCount"] == 1


def test_server_does_not_serve_private_packet_or_other_api(review_server):
    headers = {"Tailscale-User-Login": OWNER}
    for path in ("/manifest.json", "/data/private/manifest.json", "/api/account-tags"):
        assert review_server.get(path, base_url=ORIGIN, headers=headers).status_code == 404
