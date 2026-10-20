"""Intent: separate retreat relevance from Dharma; preserve evidence and revisions.

Exercise the public owner-only API with synthetic packets/answers only. Changing
purpose must not reuse an old answer, and invalid evidence links must not render.
"""
import json
import sqlite3

import pytest

from scripts.serve_discovery_review import create_review_app

ORIGIN = "https://review.example.ts.net:5444"
OWNER = {"Tailscale-User-Login": "owner@example.test"}
BASE = "/api/discovery-review"
PURPOSE = {
    "key": "ooty-retreat", "title": "People for the Ooty retreat",
    "description": "Consider contributors, not community membership.",
    "relevance_question": "Worth considering for the retreat?",
}


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "synthetic-only")
    path = tmp_path / "packet.json"
    manifest = {
        "freeze": {"ego": "synthetic-curator"}, "purpose": PURPOSE,
        "review_order": ["101"],
        "evidence": {"101": {
            "account_id": "101", "username": "example", "profile": None, "posts": [],
            "discovery": {
                "contribution_hypothesis": "Could lead a visualization session.",
                "connection": "Observed follow from a supplied seed; captured 2025-11-01.",
                "location_evidence": "Old self-description: Bengaluru; current location unknown.",
                "work": [{"label": "Example project", "url": "https://example.test/work",
                          "detail": "A public demo.", "checked_at": "2026-10-05"}],
                "unknowns": ["Availability", "Willingness"], "rank": "hidden-method",
            },
        }},
    }
    path.write_text(json.dumps(manifest))
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "discovery-review.html").write_text("<h1>Synthetic review</h1>")
    db = tmp_path / "answers.db"

    def client():
        return create_review_app(packet_path=path, answer_db=db, dist_dir=dist,
                                 owner_login=OWNER["Tailscale-User-Login"], origin=ORIGIN).test_client()

    return path, manifest, db, client


def test_retreat_purpose_and_public_work_reach_review_without_method_fields(context):
    _, _, _, client = context
    response = client().get(BASE, base_url=ORIGIN, headers=OWNER)
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["targetTag"] == "ooty-retreat"
    assert payload["purpose"]["relevanceQuestion"] == PURPOSE["relevance_question"]
    card = payload["cards"][0]
    assert card["discovery"]["work"][0]["url"] == "https://example.test/work"
    assert card["discovery"]["unknowns"] == ["Availability", "Willingness"]
    assert "hidden-method" not in response.get_data(as_text=True)


def test_purpose_change_keeps_old_answers_but_does_not_relabel_them(context):
    path, manifest, db, client = context
    first = client().get(BASE, base_url=ORIGIN, headers=OWNER).get_json()
    response = client().put(f"{BASE}/answers/101", base_url=ORIGIN,
        headers={**OWNER, "Origin": ORIGIN}, json={
            "packetId": first["packetId"], "relevance": "IN", "known": "NO",
            "glad": "YES", "note": "Synthetic retreat judgment",
        })
    assert response.status_code == 200
    manifest.pop("purpose")
    path.write_text(json.dumps(manifest))
    legacy = client().get(BASE, base_url=ORIGIN, headers=OWNER).get_json()
    assert legacy["targetTag"] == "dharma"
    assert legacy["answers"] == {}
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM discovery_review_answer_events").fetchone()[0] == 1


def test_invalid_public_work_url_fails_before_creating_answer_database(context):
    path, manifest, db, client = context
    manifest["evidence"]["101"]["discovery"]["work"][0]["url"] = "javascript:alert(1)"
    path.write_text(json.dumps(manifest))
    response = client().get(BASE, base_url=ORIGIN, headers=OWNER)
    assert response.status_code == 503
    assert not db.exists()
