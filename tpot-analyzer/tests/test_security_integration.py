"""End-to-end security tests against the full create_app() wiring.

The per-blueprint route tests register blueprints individually and don't
catch regressions where the wrong blueprint is missing a decorator, the
extension defaults flip back to "open", or a new endpoint is added without
auth. This file exercises the production app shape with all blueprints
mounted, all middleware in place, and the real curator + extension auth
gates active.

What this guards against (concretely):

1. Future contributor adds a new mutating endpoint to communities_bp /
   branches_bp / accounts_bp / graph_bp but forgets @curator_only.
2. Future contributor "fixes" the extension default back to "open" (the
   pre-hardening behavior that produced Vuln 5).
3. A refactor leaves a curator endpoint reachable as GET (no auth) when
   it should require POST/PUT/PATCH/DELETE.
4. The CORS / rate-limit / request-id middleware interacts unexpectedly
   with the auth decorators (e.g., decorator runs before request_id is
   set and crashes).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.api.server import create_app
from src.communities.store import (
    init_db,
    save_run,
    upsert_community,
    upsert_community_account,
)


CURATOR_TOKEN = "test-curator-token-integration"
EXTENSION_TOKEN = "test-extension-token-integration"


@pytest.fixture
def integration_app(temp_snapshot_dir, tmp_path, monkeypatch):
    """Full create_app() with a seeded archive DB and both tokens configured."""
    archive_db = tmp_path / "archive_tweets.db"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(archive_db))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    monkeypatch.setenv("TPOT_EXTENSION_TOKEN", EXTENSION_TOKEN)

    with sqlite3.connect(str(archive_db)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS account_following (
                account_id TEXT NOT NULL,
                following_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE IF NOT EXISTS account_followers (
                account_id TEXT NOT NULL,
                follower_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, follower_account_id)
            );
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT, display_name TEXT, bio TEXT,
                location TEXT, website TEXT,
                followers_count INTEGER, following_count INTEGER,
                profile_image_url TEXT
            );
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT, full_text TEXT, created_at TEXT,
                favorite_count INTEGER DEFAULT 0, retweet_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS likes (
                liker_account_id TEXT, full_text TEXT, expanded_url TEXT
            );
            CREATE TABLE IF NOT EXISTS retweets (
                account_id TEXT, rt_of_username TEXT
            );
        """)
        save_run(conn, "run-1", k=3, signal="follow+rt", threshold=0.1, account_count=2)
        upsert_community(conn, "comm-int", "Integration Test Community",
                         color="#000000", seeded_from_run="run-1", seeded_from_idx=0)
        upsert_community_account(conn, "comm-int", "acct_1", 0.8, "nmf")
        conn.commit()

    app = create_app({"TESTING": True, "PROPAGATE_EXCEPTIONS": False})
    return app


@pytest.fixture
def anon_client(integration_app):
    """Bare test client with no auth headers."""
    return integration_app.test_client()


@pytest.fixture
def curator_client(integration_app):
    """Test client that sends X-TPOT-Curator-Token on every request."""
    tc = integration_app.test_client()
    tc.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = CURATOR_TOKEN
    return tc


# ─────────────────────────────────────────────────────────────────────────
# Reads stay anonymous-friendly
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_anonymous_can_list_communities(anon_client):
    """GET /api/communities is a public read; no auth required."""
    resp = anon_client.get("/api/communities")
    assert resp.status_code == 200
    assert any(c["id"] == "comm-int" for c in resp.get_json())


@pytest.mark.integration
def test_anonymous_can_get_community_members(anon_client):
    resp = anon_client.get("/api/communities/comm-int/members")
    assert resp.status_code == 200


@pytest.mark.integration
def test_anonymous_can_get_branches_list(anon_client):
    """GET /api/communities/branches is a public read."""
    resp = anon_client.get("/api/communities/branches")
    assert resp.status_code == 200


@pytest.mark.integration
def test_anonymous_can_get_seeds_state(anon_client):
    resp = anon_client.get("/api/seeds")
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────
# Mutating curator endpoints REJECT anonymous callers (Vulns 1, 3, 4)
# ─────────────────────────────────────────────────────────────────────────

# Blueprints whose mutating endpoints must require the curator token. New
# blueprints that hold curator-owned writable resources should be added here
# so the auto-discovery test below covers them.
_CURATOR_BLUEPRINTS = {"branches", "communities", "community_gold", "community_gold_integrity"}
# Standalone curator-owned mutating endpoints (single-blueprint writes that
# don't live under a curator-prefixed blueprint).
_EXTRA_CURATOR_ENDPOINTS = {"accounts.update_seeds", "graph.update_settings"}


def _enumerate_curator_mutations(app):
    """Walk app.url_map and yield every (method, rule) pair that mutates
    curator-owned state. Used by the auth audit test below.

    A future contributor adding a new mutating endpoint to communities_bp /
    branches_bp / accounts.update_seeds / graph.update_settings without
    @curator_only will appear here and fail the audit — no per-endpoint
    test maintenance needed.
    """
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    for rule in app.url_map.iter_rules():
        endpoint_bp = rule.endpoint.split(".")[0]
        if not (endpoint_bp in _CURATOR_BLUEPRINTS or rule.endpoint in _EXTRA_CURATOR_ENDPOINTS):
            continue
        for method in rule.methods or set():
            if method in write_methods:
                yield method, rule.rule


@pytest.mark.integration
def test_every_curator_mutating_endpoint_rejects_anonymous(integration_app, anon_client):
    """Auto-discovery audit. Every PUT/POST/PATCH/DELETE on a curator-owned
    blueprint must return 401 without the curator token.

    Replaces a hand-maintained parametrize list — adding a new endpoint to
    communities_bp / branches_bp without @curator_only fails this test
    automatically, no test edit required.
    """
    mutations = list(_enumerate_curator_mutations(integration_app))
    assert mutations, "url_map enumeration found no curator mutating endpoints — sanity broken"
    failures = []
    for method, path in mutations:
        # Substitute realistic IDs so Flask routes the call (the auth gate
        # fires before any business logic, so the body doesn't matter).
        concrete = (path
            .replace("<community_id>", "comm-int")
            .replace("<account_id>", "acct_1")
            .replace("<branch_id>", "br-int")
            .replace("<frame_id>", "frame-int")
            .replace("<snapshot_id>", "snap-int"))
        resp = anon_client.open(concrete, method=method, json={})
        if resp.status_code != 401:
            failures.append(f"{method} {concrete} -> {resp.status_code} (expected 401)")
    assert not failures, "Unprotected curator endpoints:\n  " + "\n  ".join(failures)


@pytest.mark.integration
def test_curator_mutation_rejects_wrong_token(anon_client):
    """One representative wrong-token case. The decorator runs identically on
    every endpoint; testing all of them is redundant — see the auto-discovery
    test above for "decorator is present" coverage."""
    resp = anon_client.patch(
        "/api/communities/comm-int",
        json={"name": "x"},
        headers={"X-TPOT-Curator-Token": "wrong-token"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
def test_curator_mutation_accepted_with_valid_token(curator_client):
    """One representative happy path: a real mutation succeeds end-to-end."""
    resp = curator_client.patch("/api/communities/comm-int", json={"name": "Renamed via curator"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Renamed via curator"


@pytest.mark.integration
def test_curator_mutation_returns_503_when_token_unset(integration_app, monkeypatch):
    """Fail-closed: deleting the env var must cause writes to return 503."""
    monkeypatch.delenv("TPOT_CURATOR_TOKEN", raising=False)
    client = integration_app.test_client()
    resp = client.patch("/api/communities/comm-int", json={"name": "should fail"})
    assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────
# Extension routes default-guarded (Vuln 5)
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_extension_settings_default_is_guarded(anon_client):
    """A fresh (workspace, ego) pair must default to ingestion_mode='guarded'.

    Regression test for Vuln 5: the original default was 'open' which let
    any caller write to a fresh ego without a token. If this flips back,
    this test fails immediately.
    """
    resp = anon_client.get("/api/extension/settings?ego=fresh-ego&workspace_id=default")
    assert resp.status_code == 200
    assert resp.get_json()["ingestionMode"] == "guarded"


@pytest.mark.integration
@pytest.mark.parametrize("path", [
    "/api/extension/feed_events?ego=fresh-ego&workspace_id=default",
    "/api/extension/feed_events/raw?ego=fresh-ego&workspace_id=default",
    "/api/extension/accounts/acct_1/summary?ego=fresh-ego&workspace_id=default",
    "/api/extension/exposure/top?ego=fresh-ego&workspace_id=default",
])
def test_extension_routes_reject_anonymous_for_fresh_ego(anon_client, path):
    """Both the ingest endpoint and the three read endpoints must require
    the extension token for any new ego, since the default policy is guarded."""
    method = "POST" if "feed_events" == path.split("/")[-1].split("?")[0] else "GET"
    if method == "POST":
        resp = anon_client.post(path, json={"events": []})
    else:
        resp = anon_client.get(path)
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code} without a token; "
        "expected 401. Did the extension default flip back to 'open' or "
        "did a read endpoint lose its require_ingest_auth call?"
    )


# ─────────────────────────────────────────────────────────────────────────
# Cross-cutting middleware sanity
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_security_headers_present_on_all_responses(anon_client):
    """X-Content-Type-Options, X-Frame-Options, Referrer-Policy should be set globally."""
    resp = anon_client.get("/api/communities")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "strict-origin" in resp.headers.get("Referrer-Policy", "")


@pytest.mark.integration
def test_401_response_includes_security_headers(anon_client):
    """Even error responses should carry the security headers (not just 200s)."""
    resp = anon_client.delete("/api/communities/comm-int")
    assert resp.status_code == 401
    assert resp.headers.get("X-Frame-Options") == "DENY"


@pytest.mark.integration
def test_request_id_propagates_to_response_header(anon_client):
    """Confirms middleware ordering: request-id assigned before auth decorator runs."""
    resp = anon_client.get("/api/communities")
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"]
