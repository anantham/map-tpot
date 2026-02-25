# Communities Curation Tab — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a minimalist Communities tab where the ego user can browse NMF-seeded communities, see which members they follow, and manually curate membership (assign/remove/move accounts) with edits persisted as `source='human'` for future LLM training.

**Architecture:** Three layers built in order: (1) fix store.py for safe reseed + canonical override, (2) new Flask blueprint at `/api/communities` with read+write endpoints, (3) table-first React UI inspired by Labeling.jsx's clean layout — left community list, center member table, right account detail panel.

**Tech Stack:** Python/Flask/SQLite backend, React 19 frontend, Vitest for JS tests, pytest for Python tests.

---

## Task 1: Fix store.py — Safe Reseed

**Files:**
- Modify: `src/communities/store.py:244-251`
- Modify: `scripts/seed_communities.py:34,113`
- Test: `tests/test_communities_store.py` (create)

**Step 1: Write the failing test**

Create `tests/test_communities_store.py`:

```python
"""Tests for communities.store — Layer 1 + Layer 2 persistence."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.communities.store import (
    init_db,
    save_run,
    save_memberships,
    save_definitions,
    list_runs,
    get_memberships,
    get_definitions,
    upsert_community,
    upsert_community_account,
    list_communities,
    get_community_members,
    get_account_communities,
    delete_community,
    clear_seeded_communities,
    reseed_nmf_memberships,
)


@pytest.fixture
def db():
    """In-memory SQLite DB with community schema initialized."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


@pytest.fixture
def seeded_db(db):
    """DB with one NMF run seeded into Layer 2, plus one human override."""
    # Layer 1
    save_run(db, "run-1", k=3, signal="follow+rt", threshold=0.1, account_count=10)
    save_memberships(db, "run-1", [
        ("acct_1", 0, 0.8),
        ("acct_1", 1, 0.15),
        ("acct_2", 0, 0.6),
        ("acct_3", 1, 0.9),
    ])

    # Layer 2: two communities seeded from run-1
    upsert_community(db, "comm-A", "EA / forecasting", color="#4a90e2",
                     seeded_from_run="run-1", seeded_from_idx=0)
    upsert_community(db, "comm-B", "Rationalist", color="#e67e22",
                     seeded_from_run="run-1", seeded_from_idx=1)

    # NMF-seeded memberships
    upsert_community_account(db, "comm-A", "acct_1", weight=0.8, source="nmf")
    upsert_community_account(db, "comm-A", "acct_2", weight=0.6, source="nmf")
    upsert_community_account(db, "comm-B", "acct_3", weight=0.9, source="nmf")

    # Human override: acct_1 manually placed in comm-B
    upsert_community_account(db, "comm-B", "acct_1", weight=1.0, source="human")

    db.commit()
    return db


def test_reseed_preserves_human_edits(seeded_db):
    """reseed_nmf_memberships deletes nmf rows but keeps human rows."""
    reseed_nmf_memberships(seeded_db, "run-1")

    # Human row for acct_1 in comm-B should survive
    rows = seeded_db.execute(
        "SELECT account_id, source FROM community_account WHERE community_id = 'comm-B'"
    ).fetchall()
    assert ("acct_1", "human") in rows

    # NMF rows should be gone
    nmf_rows = seeded_db.execute(
        "SELECT COUNT(*) FROM community_account WHERE source = 'nmf'"
    ).fetchone()[0]
    assert nmf_rows == 0


def test_reseed_preserves_community_metadata(seeded_db):
    """reseed_nmf_memberships does NOT delete community rows (names, colors)."""
    reseed_nmf_memberships(seeded_db, "run-1")

    communities = seeded_db.execute("SELECT id, name FROM community").fetchall()
    names = {name for _, name in communities}
    assert "EA / forecasting" in names
    assert "Rationalist" in names


def test_clear_seeded_communities_still_works(seeded_db):
    """Original clear_seeded_communities still works for full wipe."""
    deleted = clear_seeded_communities(seeded_db, "run-1")
    assert deleted == 2
    assert seeded_db.execute("SELECT COUNT(*) FROM community").fetchone()[0] == 0
    # CASCADE should have removed all account rows too
    assert seeded_db.execute("SELECT COUNT(*) FROM community_account").fetchone()[0] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_store.py -v`
Expected: ImportError for `reseed_nmf_memberships` (doesn't exist yet)

**Step 3: Implement reseed_nmf_memberships in store.py**

Add after `clear_seeded_communities` (line 251):

```python
def reseed_nmf_memberships(conn: sqlite3.Connection, run_id: str) -> int:
    """Delete only nmf-sourced memberships for communities seeded from run_id.

    Preserves:
    - All community rows (names, colors, descriptions)
    - All source='human' community_account rows

    Returns the number of nmf rows deleted.
    """
    result = conn.execute(
        """DELETE FROM community_account
           WHERE source = 'nmf'
           AND community_id IN (
               SELECT id FROM community WHERE seeded_from_run = ?
           )""",
        (run_id,),
    )
    conn.commit()
    return result.rowcount
```

**Step 4: Run test to verify it passes**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_store.py -v`
Expected: 3 PASSED

**Step 5: Update seed_communities.py to use reseed_nmf_memberships**

In `scripts/seed_communities.py`:
- Line 34: Add `reseed_nmf_memberships` to imports
- Line 113: Replace `clear_seeded_communities(conn, run_id)` with `reseed_nmf_memberships(conn, run_id)`
- Update the print message accordingly

**Step 6: Commit**

```bash
git add src/communities/store.py scripts/seed_communities.py tests/test_communities_store.py
git commit -m "fix(communities): safe reseed preserving human edits"
```

---

## Task 2: Add Canonical Override Function

**Files:**
- Modify: `src/communities/store.py` (add function)
- Modify: `tests/test_communities_store.py` (add tests)

**Step 1: Write the failing test**

Add to `tests/test_communities_store.py`:

```python
from src.communities.store import get_account_communities_canonical


def test_canonical_override_human_beats_nmf(seeded_db):
    """When account has both nmf and human rows, canonical returns human."""
    result = get_account_communities_canonical(seeded_db, "acct_1")
    # acct_1 is in comm-A (nmf, 0.8) and comm-B (human, 1.0)
    # Both should appear, but comm-B should show source='human'
    by_comm = {r[0]: r for r in result}
    assert "comm-A" in by_comm
    assert "comm-B" in by_comm
    assert by_comm["comm-B"][4] == "human"  # source column
    assert by_comm["comm-B"][3] == 1.0      # weight column


def test_canonical_override_nmf_only(seeded_db):
    """Account with only nmf rows returns nmf source."""
    result = get_account_communities_canonical(seeded_db, "acct_2")
    assert len(result) == 1
    assert result[0][4] == "nmf"


def test_canonical_override_no_memberships(seeded_db):
    """Account not in any community returns empty list."""
    result = get_account_communities_canonical(seeded_db, "nonexistent")
    assert result == []
```

**Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_store.py::test_canonical_override_human_beats_nmf -v`
Expected: ImportError

**Step 3: Implement get_account_communities_canonical**

Add to `src/communities/store.py` after `get_account_communities`:

```python
def get_account_communities_canonical(conn: sqlite3.Connection, account_id: str) -> list:
    """Return communities for an account with human-overrides-nmf precedence.

    For each (community, account) pair, if both source='nmf' and source='human'
    rows exist, only the human row is returned. This is the canonical view
    that all API consumers should use.

    Returns: [(community_id, name, color, weight, source), ...]
    """
    return conn.execute(
        """SELECT c.id, c.name, c.color, ca.weight, ca.source
           FROM community_account ca
           JOIN community c ON c.id = ca.community_id
           WHERE ca.account_id = ?
           ORDER BY ca.weight DESC""",
        (account_id,),
    ).fetchall()
```

Note: With the current PK of `(community_id, account_id)`, each account can only have ONE row per community. So precedence is handled at write time — `upsert_community_account` with `source='human'` overwrites the `source='nmf'` row. The canonical function just reflects what's in the DB. If we later want both to coexist (e.g., show "NMF suggested 0.8, you confirmed 1.0"), we'd change the PK to `(community_id, account_id, source)`. For now, single-row-per-pair is simpler.

**Step 4: Run tests**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_store.py -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add src/communities/store.py tests/test_communities_store.py
git commit -m "feat(communities): canonical override function for human-over-nmf reads"
```

---

## Task 3: Add Ego Following Query to Store

**Files:**
- Modify: `src/communities/store.py` (add function)
- Modify: `tests/test_communities_store.py` (add test)

**Step 1: Write the failing test**

```python
from src.communities.store import get_ego_following_set


def test_ego_following_set(db):
    """get_ego_following_set returns set of account_ids ego follows."""
    # Create account_following table (it's in archive schema, not communities schema)
    db.execute("""CREATE TABLE IF NOT EXISTS account_following (
        account_id TEXT NOT NULL,
        following_account_id TEXT NOT NULL,
        PRIMARY KEY (account_id, following_account_id)
    )""")
    db.executemany(
        "INSERT INTO account_following VALUES (?, ?)",
        [("ego_1", "acct_1"), ("ego_1", "acct_2"), ("ego_1", "acct_5"),
         ("other", "acct_3")],
    )
    db.commit()

    result = get_ego_following_set(db, "ego_1")
    assert result == {"acct_1", "acct_2", "acct_5"}


def test_ego_following_set_empty(db):
    """Returns empty set if ego has no following entries."""
    db.execute("""CREATE TABLE IF NOT EXISTS account_following (
        account_id TEXT NOT NULL,
        following_account_id TEXT NOT NULL,
        PRIMARY KEY (account_id, following_account_id)
    )""")
    result = get_ego_following_set(db, "nobody")
    assert result == set()
```

**Step 2: Implement**

Add to `src/communities/store.py`:

```python
def get_ego_following_set(conn: sqlite3.Connection, ego_account_id: str) -> set:
    """Return the set of account_ids that ego follows.

    Reads from account_following table (part of archive schema, not communities).
    Used to power 'I follow' badges in the UI.
    """
    rows = conn.execute(
        "SELECT following_account_id FROM account_following WHERE account_id = ?",
        (ego_account_id,),
    ).fetchall()
    return {r[0] for r in rows}
```

**Step 3: Run tests, commit**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_store.py -v`

```bash
git add src/communities/store.py tests/test_communities_store.py
git commit -m "feat(communities): ego following set query for I-follow badges"
```

---

## Task 4: API Blueprint — Read Endpoints

**Files:**
- Create: `src/api/routes/communities.py`
- Modify: `src/api/server.py:28,131` (import + register blueprint)
- Create: `tests/test_communities_routes.py`

**Step 1: Write the test fixture + first test**

Create `tests/test_communities_routes.py`:

```python
"""Tests for /api/communities endpoints."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.communities import communities_bp
from src.communities.store import (
    init_db, save_run, save_memberships, save_definitions,
    upsert_community, upsert_community_account,
)


@pytest.fixture
def communities_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    """Flask app with communities blueprint and test data."""
    db_path = tmp_path / "archive_tweets.db"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        # Create account_following + profiles tables
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS account_following (
                account_id TEXT NOT NULL,
                following_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                bio TEXT,
                followers_count INTEGER,
                following_count INTEGER,
                profile_image_url TEXT
            );
        """)

        # Seed a run
        save_run(conn, "run-1", k=3, signal="follow+rt", threshold=0.1, account_count=5)

        # Layer 2 communities
        upsert_community(conn, "comm-A", "EA / forecasting",
                         color="#4a90e2", seeded_from_run="run-1", seeded_from_idx=0)
        upsert_community(conn, "comm-B", "Rationalist",
                         color="#e67e22", seeded_from_run="run-1", seeded_from_idx=1)

        # Members
        upsert_community_account(conn, "comm-A", "acct_1", 0.8, "nmf")
        upsert_community_account(conn, "comm-A", "acct_2", 0.6, "nmf")
        upsert_community_account(conn, "comm-B", "acct_3", 0.9, "nmf")
        upsert_community_account(conn, "comm-B", "acct_1", 1.0, "human")

        # Profiles
        conn.executemany(
            "INSERT INTO profiles (account_id, username, bio) VALUES (?, ?, ?)",
            [("acct_1", "thezvi", "EA writer"),
             ("acct_2", "nunosempere", "Forecaster"),
             ("acct_3", "eigenrobot", "Rationalist")],
        )

        # Ego follows acct_1 and acct_3
        conn.executemany(
            "INSERT INTO account_following VALUES (?, ?)",
            [("ego_1", "acct_1"), ("ego_1", "acct_3")],
        )
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(communities_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(communities_app):
    return communities_app.test_client()


def test_list_communities(client):
    res = client.get("/api/communities")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 2
    names = {c["name"] for c in data}
    assert "EA / forecasting" in names
    assert "Rationalist" in names
    # Check member_count
    ea = next(c for c in data if c["name"] == "EA / forecasting")
    assert ea["member_count"] == 2
    assert ea["color"] == "#4a90e2"


def test_get_community_members(client):
    res = client.get("/api/communities/comm-A/members")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["members"]) == 2
    usernames = {m["username"] for m in data["members"]}
    assert "thezvi" in usernames


def test_get_community_members_with_ego(client):
    """Members endpoint includes i_follow flag when ego param provided."""
    res = client.get("/api/communities/comm-A/members?ego=ego_1")
    assert res.status_code == 200
    data = res.get_json()
    by_user = {m["username"]: m for m in data["members"]}
    assert by_user["thezvi"]["i_follow"] is True
    assert by_user["nunosempere"]["i_follow"] is False


def test_get_account_communities(client):
    res = client.get("/api/communities/account/acct_1")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["communities"]) == 2


def test_community_not_found(client):
    res = client.get("/api/communities/nonexistent/members")
    assert res.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_routes.py -v`
Expected: ImportError (communities blueprint doesn't exist)

**Step 3: Implement the blueprint**

Create `src/api/routes/communities.py`:

```python
"""Communities API — read and write curated community memberships.

Blueprint: /api/communities
Data source: communities.store (Layer 2 of archive_tweets.db)
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.communities import store

logger = logging.getLogger(__name__)

communities_bp = Blueprint("communities", __name__, url_prefix="/api/communities")

# Default DB path — can be overridden via ARCHIVE_DB_PATH env var
_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "archive_tweets.db"


def _get_db() -> sqlite3.Connection:
    db_path = os.getenv("ARCHIVE_DB_PATH", str(_DEFAULT_DB))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@communities_bp.route("", methods=["GET"])
def list_communities_route():
    """List all communities with member counts."""
    conn = _get_db()
    try:
        rows = store.list_communities(conn)
        result = []
        for cid, name, color, desc, sfrun, sfidx, count, created, updated in rows:
            result.append({
                "id": cid,
                "name": name,
                "color": color,
                "description": desc,
                "seeded_from_run": sfrun,
                "seeded_from_idx": sfidx,
                "member_count": count,
                "created_at": created,
                "updated_at": updated,
            })
        return jsonify(result)
    finally:
        conn.close()


@communities_bp.route("/<community_id>/members", methods=["GET"])
def get_members_route(community_id):
    """Paginated member list for a community, with optional ego I-follow badge."""
    ego = request.args.get("ego")
    conn = _get_db()
    try:
        # Verify community exists
        exists = conn.execute(
            "SELECT 1 FROM community WHERE id = ?", (community_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        members = store.get_community_members(conn, community_id)
        ego_following = store.get_ego_following_set(conn, ego) if ego else set()

        result = []
        for acct_id, username, weight, source, bio in members:
            result.append({
                "account_id": acct_id,
                "username": username,
                "weight": weight,
                "source": source,
                "bio": bio,
                "i_follow": acct_id in ego_following,
            })
        return jsonify({"community_id": community_id, "members": result})
    finally:
        conn.close()


@communities_bp.route("/account/<account_id>", methods=["GET"])
def get_account_communities_route(account_id):
    """Which communities does this account belong to?"""
    conn = _get_db()
    try:
        rows = store.get_account_communities_canonical(conn, account_id)
        result = []
        for cid, name, color, weight, source in rows:
            result.append({
                "community_id": cid,
                "name": name,
                "color": color,
                "weight": weight,
                "source": source,
            })
        return jsonify({"account_id": account_id, "communities": result})
    finally:
        conn.close()
```

**Step 4: Register in server.py**

Add to `src/api/server.py`:
- Line 28 area: `from src.api.routes.communities import communities_bp`
- Line 131 area: `app.register_blueprint(communities_bp)`

**Step 5: Run tests**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_routes.py -v`
Expected: All PASSED

**Step 6: Commit**

```bash
git add src/api/routes/communities.py src/api/server.py tests/test_communities_routes.py
git commit -m "feat(api): communities read endpoints with ego I-follow badge"
```

---

## Task 5: API Blueprint — Write Endpoints

**Files:**
- Modify: `src/api/routes/communities.py` (add PUT, DELETE, PATCH)
- Modify: `tests/test_communities_routes.py` (add write tests)

**Step 1: Write the failing tests**

Add to `tests/test_communities_routes.py`:

```python
def test_assign_account_to_community(client):
    """PUT assigns account with source='human', weight=1.0."""
    res = client.put("/api/communities/comm-A/members/acct_3")
    assert res.status_code == 200
    data = res.get_json()
    assert data["source"] == "human"
    assert data["weight"] == 1.0

    # Verify in member list
    res2 = client.get("/api/communities/comm-A/members")
    usernames = {m["username"] for m in res2.get_json()["members"]}
    assert "eigenrobot" in usernames


def test_remove_account_from_community(client):
    res = client.delete("/api/communities/comm-A/members/acct_2")
    assert res.status_code == 200

    # Verify removed
    res2 = client.get("/api/communities/comm-A/members")
    acct_ids = {m["account_id"] for m in res2.get_json()["members"]}
    assert "acct_2" not in acct_ids


def test_rename_community(client):
    res = client.patch(
        "/api/communities/comm-A",
        json={"name": "EA / x-risk"},
    )
    assert res.status_code == 200

    res2 = client.get("/api/communities")
    names = {c["name"] for c in res2.get_json()}
    assert "EA / x-risk" in names
    assert "EA / forecasting" not in names


def test_update_community_color(client):
    res = client.patch(
        "/api/communities/comm-B",
        json={"color": "#ff0000"},
    )
    assert res.status_code == 200
    assert res.get_json()["color"] == "#ff0000"


def test_assign_to_nonexistent_community_404(client):
    res = client.put("/api/communities/nonexistent/members/acct_1")
    assert res.status_code == 404
```

**Step 2: Implement write endpoints**

Add to `src/api/routes/communities.py`:

```python
@communities_bp.route("/<community_id>/members/<account_id>", methods=["PUT"])
def assign_member_route(community_id, account_id):
    """Manually assign account to community (source='human', weight=1.0)."""
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM community WHERE id = ?", (community_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        store.upsert_community_account(
            conn, community_id, account_id, weight=1.0, source="human"
        )
        conn.commit()
        return jsonify({
            "community_id": community_id,
            "account_id": account_id,
            "weight": 1.0,
            "source": "human",
        })
    finally:
        conn.close()


@communities_bp.route("/<community_id>/members/<account_id>", methods=["DELETE"])
def remove_member_route(community_id, account_id):
    """Remove account from community."""
    conn = _get_db()
    try:
        conn.execute(
            "DELETE FROM community_account WHERE community_id = ? AND account_id = ?",
            (community_id, account_id),
        )
        conn.commit()
        return jsonify({"removed": True})
    finally:
        conn.close()


@communities_bp.route("/<community_id>", methods=["PATCH"])
def update_community_route(community_id):
    """Update community name, color, or description."""
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT name, color, description FROM community WHERE id = ?",
            (community_id,),
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        body = request.get_json() or {}
        name = body.get("name", exists[0])
        color = body.get("color", exists[1])
        description = body.get("description", exists[2])

        store.upsert_community(
            conn, community_id, name=name, color=color, description=description
        )
        conn.commit()
        return jsonify({
            "id": community_id,
            "name": name,
            "color": color,
            "description": description,
        })
    finally:
        conn.close()
```

**Step 3: Run tests**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_routes.py -v`
Expected: All PASSED

**Step 4: Commit**

```bash
git add src/api/routes/communities.py tests/test_communities_routes.py
git commit -m "feat(api): communities write endpoints — assign, remove, rename"
```

---

## Task 6: Frontend — communitiesApi.js

**Files:**
- Create: `graph-explorer/src/communitiesApi.js`

**Step 1: Create the API client**

```javascript
import { API_BASE_URL } from './config'

const BASE = `${API_BASE_URL}/api/communities`

export async function fetchCommunities() {
  const res = await fetch(BASE)
  if (!res.ok) throw new Error(`communities list failed: ${res.status}`)
  return res.json()
}

export async function fetchCommunityMembers(communityId, { ego } = {}) {
  const params = new URLSearchParams()
  if (ego) params.set('ego', ego)
  const url = `${BASE}/${communityId}/members${params.toString() ? '?' + params : ''}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`members failed: ${res.status}`)
  return res.json()
}

export async function fetchAccountCommunities(accountId) {
  const res = await fetch(`${BASE}/account/${accountId}`)
  if (!res.ok) throw new Error(`account communities failed: ${res.status}`)
  return res.json()
}

export async function assignMember(communityId, accountId) {
  const res = await fetch(`${BASE}/${communityId}/members/${accountId}`, {
    method: 'PUT',
  })
  if (!res.ok) throw new Error(`assign failed: ${res.status}`)
  return res.json()
}

export async function removeMember(communityId, accountId) {
  const res = await fetch(`${BASE}/${communityId}/members/${accountId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`remove failed: ${res.status}`)
  return res.json()
}

export async function updateCommunity(communityId, updates) {
  const res = await fetch(`${BASE}/${communityId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`update failed: ${res.status}`)
  return res.json()
}
```

**Step 2: Commit**

```bash
git add graph-explorer/src/communitiesApi.js
git commit -m "feat(ui): communities API client"
```

---

## Task 7: Frontend — Communities.jsx Tab

**Files:**
- Create: `graph-explorer/src/Communities.jsx`
- Modify: `graph-explorer/src/App.jsx` (add tab + route)

This is the largest task. The component follows Labeling.jsx's structure: header with stats, clean 3-panel layout, minimal state.

**Step 1: Create Communities.jsx**

```jsx
/**
 * Communities — Account community curation dashboard.
 *
 * Flow:
 *   1. Load communities list from /api/communities
 *   2. Click community → load members with I-follow badges
 *   3. Click member → see community distribution + bio + actions
 *   4. Assign/remove/move accounts → persists as source='human'
 */
import { useState, useEffect, useCallback } from 'react'
import {
  fetchCommunities,
  fetchCommunityMembers,
  fetchAccountCommunities,
  assignMember,
  removeMember,
  updateCommunity,
} from './communitiesApi'

function CommunityList({ communities, selectedId, onSelect }) {
  return (
    <div style={{
      width: 240, borderRight: '1px solid var(--panel-border, #1e293b)',
      overflowY: 'auto', padding: '12px 0',
    }}>
      <div style={{ padding: '0 12px 8px', fontSize: 11, fontWeight: 700,
        color: '#64748b', textTransform: 'uppercase' }}>
        Communities ({communities.length})
      </div>
      {communities.map(c => (
        <button
          key={c.id}
          onClick={() => onSelect(c)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            width: '100%', padding: '8px 12px', border: 'none',
            background: selectedId === c.id ? 'var(--accent-dim, rgba(59,130,246,0.15))' : 'transparent',
            color: 'var(--text, #e2e8f0)', cursor: 'pointer',
            textAlign: 'left', fontSize: 13,
          }}
        >
          <span style={{
            width: 10, height: 10, borderRadius: '50%',
            background: c.color || '#64748b', flexShrink: 0,
          }} />
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', fontWeight: selectedId === c.id ? 600 : 400 }}>
            {c.name}
          </span>
          <span style={{ fontSize: 11, color: '#64748b', flexShrink: 0 }}>
            {c.member_count}
          </span>
        </button>
      ))}
    </div>
  )
}

function MemberTable({ members, selectedAccountId, onSelectAccount, showFollowOnly,
  onToggleFollowOnly, searchQuery, onSearchChange }) {
  const filtered = members.filter(m => {
    if (showFollowOnly && !m.i_follow) return false
    if (searchQuery && !m.username?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {/* Filters */}
      <div style={{
        display: 'flex', gap: 8, padding: '8px 12px', alignItems: 'center',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
      }}>
        <input
          type="text" placeholder="Search @handle..."
          value={searchQuery} onChange={e => onSearchChange(e.target.value)}
          style={{
            flex: 1, padding: '6px 10px', background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)', borderRadius: 6,
            color: 'var(--text, #e2e8f0)', fontSize: 13,
          }}
        />
        <button
          onClick={onToggleFollowOnly}
          style={{
            padding: '6px 12px', fontSize: 12, fontWeight: 600,
            border: '1px solid var(--panel-border, #2d3748)', borderRadius: 6,
            background: showFollowOnly ? 'var(--accent, #3b82f6)' : 'transparent',
            color: showFollowOnly ? '#fff' : 'var(--text, #e2e8f0)',
            cursor: 'pointer',
          }}
        >
          I follow
        </button>
        <span style={{ fontSize: 12, color: '#64748b' }}>
          {filtered.length}/{members.length}
        </span>
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--panel-border, #1e293b)',
              color: '#64748b', fontSize: 11, textTransform: 'uppercase' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>Account</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, width: 60 }}>Weight</th>
              <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, width: 60 }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(m => (
              <tr
                key={m.account_id}
                onClick={() => onSelectAccount(m)}
                style={{
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--panel-border, #0f172a)',
                  background: selectedAccountId === m.account_id
                    ? 'var(--accent-dim, rgba(59,130,246,0.1))' : 'transparent',
                }}
              >
                <td style={{ padding: '8px 12px' }}>
                  <span style={{ fontWeight: 500 }}>@{m.username || m.account_id.slice(0, 8)}</span>
                  {m.i_follow && (
                    <span style={{ marginLeft: 6, fontSize: 11, color: '#f59e0b' }} title="You follow this account">
                      ★
                    </span>
                  )}
                  {m.bio && (
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 2,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      maxWidth: 300 }}>
                      {m.bio}
                    </div>
                  )}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                  {(m.weight * 100).toFixed(0)}%
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                    background: m.source === 'human' ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
                    color: m.source === 'human' ? '#22c55e' : '#94a3b8',
                  }}>
                    {m.source === 'human' ? 'HUMAN' : 'NMF'}
                  </span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={3} style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>
                  {members.length === 0 ? 'No members' : 'No matches'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AccountDetail({ account, accountCommunities, communities, currentCommunityId,
  onAssign, onRemove, assigning }) {
  if (!account) return (
    <div style={{
      width: 300, borderLeft: '1px solid var(--panel-border, #1e293b)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#475569', fontSize: 13, padding: 24, textAlign: 'center',
    }}>
      Click an account to see details
    </div>
  )

  const [moveTarget, setMoveTarget] = useState('')
  const otherCommunities = communities.filter(c => c.id !== currentCommunityId)

  return (
    <div style={{
      width: 300, borderLeft: '1px solid var(--panel-border, #1e293b)',
      overflowY: 'auto', padding: 16,
    }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 16, fontWeight: 700 }}>@{account.username || account.account_id}</div>
        {account.bio && (
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4, lineHeight: 1.5 }}>
            {account.bio}
          </div>
        )}
        <a
          href={`https://x.com/${account.username}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 12, color: '#3b82f6', marginTop: 6, display: 'inline-block' }}
        >
          Open on X →
        </a>
      </div>

      {/* Community memberships */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b',
          textTransform: 'uppercase', marginBottom: 8 }}>
          Communities
        </div>
        {accountCommunities.map(c => (
          <div key={c.community_id} style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: c.color || '#64748b',
            }} />
            <span style={{ flex: 1, fontSize: 13 }}>{c.name}</span>
            <div style={{
              width: 60, height: 6, background: 'rgba(148,163,184,0.2)',
              borderRadius: 3, overflow: 'hidden',
            }}>
              <div style={{
                width: `${(c.weight * 100)}%`, height: '100%',
                background: c.color || '#3b82f6', borderRadius: 3,
              }} />
            </div>
            <span style={{ fontSize: 11, color: '#94a3b8', width: 32, textAlign: 'right',
              fontVariantNumeric: 'tabular-nums' }}>
              {(c.weight * 100).toFixed(0)}%
            </span>
          </div>
        ))}
        {accountCommunities.length === 0 && (
          <div style={{ fontSize: 12, color: '#475569' }}>Not in any community</div>
        )}
      </div>

      {/* Actions */}
      <div style={{
        background: 'var(--panel, #1e293b)',
        border: '1px solid var(--panel-border, #2d3748)',
        borderRadius: 8, padding: 12,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b',
          textTransform: 'uppercase', marginBottom: 8 }}>
          Actions
        </div>

        {/* Assign to community */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          <select
            value={moveTarget}
            onChange={e => setMoveTarget(e.target.value)}
            style={{
              flex: 1, padding: '6px 8px', fontSize: 12,
              background: 'var(--bg, #0f172a)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 4, color: 'var(--text, #e2e8f0)',
            }}
          >
            <option value="">Assign to...</option>
            {otherCommunities.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button
            onClick={() => moveTarget && onAssign(moveTarget, account.account_id)}
            disabled={!moveTarget || assigning}
            style={{
              padding: '6px 12px', fontSize: 12, fontWeight: 600,
              background: moveTarget ? '#3b82f6' : '#334155',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: moveTarget ? 'pointer' : 'not-allowed',
            }}
          >
            {assigning ? '...' : 'Add'}
          </button>
        </div>

        {/* Remove from current */}
        {currentCommunityId && (
          <button
            onClick={() => onRemove(currentCommunityId, account.account_id)}
            disabled={assigning}
            style={{
              width: '100%', padding: '6px 0', fontSize: 12, fontWeight: 600,
              background: 'transparent', color: '#f87171',
              border: '1px solid rgba(248,113,113,0.3)', borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Remove from this community
          </button>
        )}
      </div>
    </div>
  )
}

export default function Communities({ ego: defaultEgo }) {
  // Data state
  const [communities, setCommunities] = useState([])
  const [selectedCommunity, setSelectedCommunity] = useState(null)
  const [members, setMembers] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [accountCommunities, setAccountCommunities] = useState([])

  // UI state
  const [loading, setLoading] = useState(true)
  const [membersLoading, setMembersLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showFollowOnly, setShowFollowOnly] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [assigning, setAssigning] = useState(false)

  // Ego state — changeable
  const [ego, setEgo] = useState(defaultEgo || '')
  const [egoInput, setEgoInput] = useState(defaultEgo || '')
  const [egoAccountId, setEgoAccountId] = useState(null)

  // Resolve ego handle to account_id on change
  useEffect(() => {
    if (!ego) { setEgoAccountId(null); return }
    fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:5001'}/api/accounts/search?q=${ego}&limit=1`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const match = data?.results?.[0]
        if (match && match.username?.toLowerCase() === ego.toLowerCase()) {
          setEgoAccountId(match.account_id)
        }
      })
      .catch(() => {})
  }, [ego])

  // Load communities on mount
  useEffect(() => {
    setLoading(true)
    fetchCommunities()
      .then(data => {
        setCommunities(data)
        if (data.length > 0) setSelectedCommunity(data[0])
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Load members when selected community or ego changes
  useEffect(() => {
    if (!selectedCommunity) return
    setMembersLoading(true)
    setSelectedAccount(null)
    setAccountCommunities([])
    setSearchQuery('')
    fetchCommunityMembers(selectedCommunity.id, { ego: egoAccountId })
      .then(data => setMembers(data.members || []))
      .catch(e => setError(e.message))
      .finally(() => setMembersLoading(false))
  }, [selectedCommunity?.id, egoAccountId])

  // Load account communities when account selected
  useEffect(() => {
    if (!selectedAccount) return
    fetchAccountCommunities(selectedAccount.account_id)
      .then(data => setAccountCommunities(data.communities || []))
      .catch(() => setAccountCommunities([]))
  }, [selectedAccount?.account_id])

  const handleAssign = useCallback(async (communityId, accountId) => {
    setAssigning(true)
    try {
      await assignMember(communityId, accountId)
      // Refresh member list + account communities
      if (selectedCommunity) {
        const data = await fetchCommunityMembers(selectedCommunity.id, { ego: egoAccountId })
        setMembers(data.members || [])
      }
      const acData = await fetchAccountCommunities(accountId)
      setAccountCommunities(acData.communities || [])
      // Refresh community counts
      const comms = await fetchCommunities()
      setCommunities(comms)
    } catch (e) {
      setError(e.message)
    } finally {
      setAssigning(false)
    }
  }, [selectedCommunity, egoAccountId])

  const handleRemove = useCallback(async (communityId, accountId) => {
    setAssigning(true)
    try {
      await removeMember(communityId, accountId)
      // Refresh
      if (selectedCommunity) {
        const data = await fetchCommunityMembers(selectedCommunity.id, { ego: egoAccountId })
        setMembers(data.members || [])
      }
      setSelectedAccount(null)
      setAccountCommunities([])
      const comms = await fetchCommunities()
      setCommunities(comms)
    } catch (e) {
      setError(e.message)
    } finally {
      setAssigning(false)
    }
  }, [selectedCommunity, egoAccountId])

  if (loading) return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: '#64748b' }}>
      Loading communities...
    </div>
  )

  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      background: 'var(--bg, #0f172a)', color: 'var(--text, #e2e8f0)',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid var(--panel-border, #1e293b)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Communities</h2>
        <div style={{ fontSize: 12, color: '#64748b' }}>
          {communities.length} communities · {communities.reduce((s, c) => s + c.member_count, 0)} members
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <span style={{ color: '#64748b' }}>ego:</span>
          <input
            type="text" value={egoInput}
            onChange={e => setEgoInput(e.target.value)}
            onBlur={() => setEgo(egoInput)}
            onKeyDown={e => e.key === 'Enter' && setEgo(egoInput)}
            placeholder="@handle"
            style={{
              width: 140, padding: '4px 8px',
              background: 'var(--bg, #0f172a)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 4, color: 'var(--text, #e2e8f0)', fontSize: 12,
            }}
          />
          {egoAccountId && <span style={{ color: '#22c55e', fontSize: 11 }}>✓</span>}
        </div>
      </div>

      {error && (
        <div style={{
          padding: '8px 16px', background: 'rgba(239,68,68,0.1)',
          color: '#f87171', fontSize: 13,
        }}>
          {error}
          <button onClick={() => setError(null)}
            style={{ marginLeft: 8, background: 'none', border: 'none',
              color: '#f87171', cursor: 'pointer' }}>
            ✕
          </button>
        </div>
      )}

      {/* Main 3-panel layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <CommunityList
          communities={communities}
          selectedId={selectedCommunity?.id}
          onSelect={setSelectedCommunity}
        />

        {membersLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center',
            justifyContent: 'center', color: '#64748b' }}>
            Loading members...
          </div>
        ) : (
          <MemberTable
            members={members}
            selectedAccountId={selectedAccount?.account_id}
            onSelectAccount={setSelectedAccount}
            showFollowOnly={showFollowOnly}
            onToggleFollowOnly={() => setShowFollowOnly(v => !v)}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
          />
        )}

        <AccountDetail
          account={selectedAccount}
          accountCommunities={accountCommunities}
          communities={communities}
          currentCommunityId={selectedCommunity?.id}
          onAssign={handleAssign}
          onRemove={handleRemove}
          assigning={assigning}
        />
      </div>
    </div>
  )
}
```

**Step 2: Wire into App.jsx**

Add to `graph-explorer/src/App.jsx`:
- Import: `import Communities from './Communities'`
- Add tab button for "Communities" after Cluster View (always enabled)
- Add view render block: `{currentView === 'communities' && <Communities ego={accountStatus.handle} />}`
- Update `getInitialView` to accept `'communities'`

**Step 3: Test manually**

Start backend: `cd tpot-analyzer && PYTHONPATH=src .venv/bin/python3 -m flask --app src.api.server:create_app run -p 5001`
Start frontend: `cd tpot-analyzer/graph-explorer && npm run dev`
Open: http://localhost:5174/?view=communities

Verify:
- [ ] Community list loads with 14 communities
- [ ] Click community → member table populates
- [ ] Members show weight, source badge, bio snippet
- [ ] Set ego to "adityaarpitha" → ★ badges appear on followed accounts
- [ ] "I follow" toggle filters to only followed accounts
- [ ] Click account → right panel shows community distribution with weight bars
- [ ] "Open on X" link works
- [ ] Assign account to different community → member list and counts refresh
- [ ] Remove account → disappears from list

**Step 4: Commit**

```bash
git add graph-explorer/src/Communities.jsx graph-explorer/src/communitiesApi.js graph-explorer/src/App.jsx
git commit -m "feat(ui): communities curation tab with ego I-follow badges"
```

---

## Task 8: Verification Script

**Files:**
- Create: `scripts/verify_communities_persistence.py`

**Step 1: Create verification script**

```python
#!/usr/bin/env python3
"""Verify communities persistence: schema, data integrity, override behavior."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"


def check(label, ok, detail=""):
    status = "✓" if ok else "✗"
    print(f"  {status}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def main():
    if not ARCHIVE_DB.exists():
        print(f"✗  Database not found: {ARCHIVE_DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(ARCHIVE_DB))
    all_ok = True

    print("Schema checks:")
    for table in ["community_run", "community_membership", "community_definition",
                  "community", "community_account"]:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        all_ok &= check(f"Table {table} exists", exists is not None)

    print("\nData checks:")
    runs = conn.execute("SELECT COUNT(*) FROM community_run").fetchone()[0]
    all_ok &= check("At least one saved run", runs > 0, f"{runs} runs")

    comms = conn.execute("SELECT COUNT(*) FROM community").fetchone()[0]
    all_ok &= check("Communities exist", comms > 0, f"{comms} communities")

    memberships = conn.execute("SELECT COUNT(*) FROM community_account").fetchone()[0]
    all_ok &= check("Community memberships exist", memberships > 0, f"{memberships} total")

    nmf_count = conn.execute(
        "SELECT COUNT(*) FROM community_account WHERE source='nmf'"
    ).fetchone()[0]
    human_count = conn.execute(
        "SELECT COUNT(*) FROM community_account WHERE source='human'"
    ).fetchone()[0]
    check("NMF memberships", True, f"{nmf_count}")
    check("Human memberships", True, f"{human_count}")

    print("\nReferential integrity:")
    orphan_ca = conn.execute("""
        SELECT COUNT(*) FROM community_account ca
        WHERE NOT EXISTS (SELECT 1 FROM community c WHERE c.id = ca.community_id)
    """).fetchone()[0]
    all_ok &= check("community_account → community FK", orphan_ca == 0,
                     f"{orphan_ca} orphans" if orphan_ca else "clean")

    orphan_cm = conn.execute("""
        SELECT COUNT(*) FROM community_membership cm
        WHERE NOT EXISTS (SELECT 1 FROM community_run cr WHERE cr.run_id = cm.run_id)
    """).fetchone()[0]
    all_ok &= check("community_membership → community_run FK", orphan_cm == 0,
                     f"{orphan_cm} orphans" if orphan_cm else "clean")

    print("\nMetrics:")
    for run_id, k, signal, thresh, acct_count, notes, created in conn.execute(
        "SELECT * FROM community_run ORDER BY created_at DESC"
    ).fetchall():
        print(f"  Run: {run_id}  k={k}  accounts={acct_count}  notes={notes}")

    print(f"\n  Communities: {comms}")
    print(f"  Memberships: {memberships} ({nmf_count} nmf, {human_count} human)")

    print(f"\n{'✓ ALL CHECKS PASSED' if all_ok else '✗ SOME CHECKS FAILED'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
```

**Step 2: Run it**

Run: `cd tpot-analyzer && .venv/bin/python3 scripts/verify_communities_persistence.py`
Expected: All ✓ checks pass

**Step 3: Commit**

```bash
git add scripts/verify_communities_persistence.py
git commit -m "feat(scripts): communities persistence verification script"
```

---

## Execution Order Summary

| Task | What | Est. | Dependencies |
|------|------|------|-------------|
| 1 | Safe reseed in store.py | 5 min | None |
| 2 | Canonical override function | 5 min | Task 1 |
| 3 | Ego following set query | 3 min | None |
| 4 | API read endpoints | 10 min | Tasks 1-3 |
| 5 | API write endpoints | 8 min | Task 4 |
| 6 | communitiesApi.js | 3 min | None |
| 7 | Communities.jsx + App.jsx wiring | 15 min | Tasks 4-6 |
| 8 | Verification script | 5 min | Task 1 |

Tasks 1-3 are independent and can be parallelized. Task 8 is independent of 4-7.
