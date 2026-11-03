"""Test Intent: Research Notes HTTP responses are always private and non-cacheable.

- Exercise both a root endpoint and a registered nested endpoint over HTTP.
- Preserve successful status codes and representative non-empty payloads.
- Apply the same cache policy to auth refusals and validation errors.
"""
from __future__ import annotations

import pytest

from src.api.server import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "cache-policy-test-token")
    app = create_app({"TESTING": True})
    with app.test_client() as test_client:
        test_client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = "cache-policy-test-token"
        yield test_client


def test_successful_root_and_nested_responses_are_private(client, monkeypatch):
    root_payload = {"ego": "account-1", "results": [{"accountId": "account-2"}]}
    nested_payload = {"sources": [{"kind": "follows", "count": 3}]}
    monkeypatch.setattr(
        "src.api.routes.research_notes.build_target_follow_frontier",
        lambda **_kwargs: root_payload,
    )
    monkeypatch.setattr(
        "src.api.routes.research_notes_search.saved_social_sources",
        lambda _path: nested_payload,
    )

    root = client.get("/api/research-notes/frontier?ego=account-1&tag=review")
    nested = client.get("/api/research-notes/network/sources")

    assert root.status_code == 200
    assert root.get_json() == root_payload
    assert root.headers["Cache-Control"] == "private, no-store"
    assert nested.status_code == 200
    assert nested.get_json() == nested_payload
    assert nested.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/api/research-notes/frontier?ego=account-1&tag=review", 401),
        ("/api/research-notes/network/sources", 401),
        ("/api/research-notes/frontier", 400),
    ],
)
def test_refusals_and_validation_errors_are_private(client, path, status):
    if status == 401:
        client.environ_base.pop("HTTP_X_TPOT_CURATOR_TOKEN")

    response = client.get(path)

    assert response.status_code == status
    assert response.get_json()["error"]
    assert response.headers["Cache-Control"] == "private, no-store"
