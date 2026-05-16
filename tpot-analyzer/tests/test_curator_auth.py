"""Tests for curator-token auth on mutating endpoints.

These tests guard against regressions in the security gate added to
prevent unauthenticated mutation of curator data.
"""
from __future__ import annotations

import pytest
from flask import Flask, jsonify

from src.api.curator_auth import (
    CURATOR_TOKEN_ENV,
    CURATOR_TOKEN_HEADER,
    CuratorMisconfiguredError,
    CuratorUnauthorizedError,
    curator_only,
    require_curator_auth,
)


CURATOR_TOKEN = "test-curator-token"


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/protected", methods=["POST"])
    @curator_only
    def protected():
        return jsonify({"ok": True})

    @app.route("/public", methods=["GET"])
    def public():
        return jsonify({"ok": True})

    return app


@pytest.mark.unit
def test_misconfigured_when_env_unset(app, monkeypatch):
    monkeypatch.delenv(CURATOR_TOKEN_ENV, raising=False)
    client = app.test_client()
    resp = client.post("/protected")
    assert resp.status_code == 503
    assert "not configured" in resp.get_json()["error"]


@pytest.mark.unit
def test_unauthorized_when_header_missing(app, monkeypatch):
    monkeypatch.setenv(CURATOR_TOKEN_ENV, CURATOR_TOKEN)
    client = app.test_client()
    resp = client.post("/protected")
    assert resp.status_code == 401
    assert "invalid" in resp.get_json()["error"] or "missing" in resp.get_json()["error"]


@pytest.mark.unit
def test_unauthorized_when_header_wrong(app, monkeypatch):
    monkeypatch.setenv(CURATOR_TOKEN_ENV, CURATOR_TOKEN)
    client = app.test_client()
    resp = client.post("/protected", headers={CURATOR_TOKEN_HEADER: "wrong"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_authorized_when_header_correct(app, monkeypatch):
    monkeypatch.setenv(CURATOR_TOKEN_ENV, CURATOR_TOKEN)
    client = app.test_client()
    resp = client.post("/protected", headers={CURATOR_TOKEN_HEADER: CURATOR_TOKEN})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


@pytest.mark.unit
def test_get_endpoints_unaffected(app, monkeypatch):
    """GET endpoints without @curator_only should still work without a token."""
    monkeypatch.delenv(CURATOR_TOKEN_ENV, raising=False)
    client = app.test_client()
    resp = client.get("/public")
    assert resp.status_code == 200


@pytest.mark.unit
def test_require_curator_auth_raises_misconfigured(app, monkeypatch):
    monkeypatch.delenv(CURATOR_TOKEN_ENV, raising=False)
    with app.test_request_context("/", method="POST"):
        from flask import request

        with pytest.raises(CuratorMisconfiguredError):
            require_curator_auth(request)


@pytest.mark.unit
def test_require_curator_auth_raises_unauthorized(app, monkeypatch):
    monkeypatch.setenv(CURATOR_TOKEN_ENV, CURATOR_TOKEN)
    with app.test_request_context("/", method="POST"):
        from flask import request

        with pytest.raises(CuratorUnauthorizedError):
            require_curator_auth(request)
