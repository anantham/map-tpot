# Community Map Snapshots — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add branch/snapshot versioning to community curation so the curator can save checkpoints, create named branches (e.g. "Kegan Stage 3"), switch between them, and restore from any save point.

**Architecture:** Layer 2 tables (`community`, `community_account`, `account_note`) remain the single mutable working state. New tables store named branches and immutable JSON snapshots. Switching branches wipes and restores Layer 2 in a transaction. One branch is active at a time. On first use, auto-create "main" branch from current state.

**Tech Stack:** Python 3.9, SQLite, Flask, React 19, Vitest

**Design doc:** `docs/plans/2026-02-26-community-snapshots-design.md`

---

## Context for the implementer

### Key files
- `src/communities/store.py` — persistence layer. Has `SCHEMA` string, `init_db()`, and all Layer 1/2 functions. Uses `now_utc()` helper. Commit contract: single-row writers do NOT commit, bulk/destructive writers commit internally.
- `src/api/routes/communities.py` — Flask blueprint at `/api/communities`. Uses `_get_db()` helper. Pattern: get conn, try/finally close.
- `graph-explorer/src/communitiesApi.js` — frontend API client. Pattern: fetch + throw on !ok.
- `graph-explorer/src/Communities.jsx` — main view component. Header bar + community list sidebar + center panel.
- `tests/test_communities_store.py` — store tests. Uses `db` fixture (in-memory) and `seeded_db` fixture (with NMF run + 2 communities + assignments).
- `tests/test_communities_routes.py` — route tests. Uses `communities_app` fixture with test Flask app.

### Existing schema (Layer 2 tables to snapshot)
```sql
community (id, name, description, color, seeded_from_run, seeded_from_idx, created_at, updated_at)
community_account (community_id, account_id, weight, source, updated_at)  -- PK: (community_id, account_id)
account_note (account_id, note, updated_at)  -- PK: account_id
```

### Test commands
```bash
# Backend tests
cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_communities_store.py tests/test_communities_routes.py -v

# Frontend build check
cd tpot-analyzer/graph-explorer && npx vite build
```

---

## Task 1: Schema — add branch and snapshot tables to store.py

**Files:**
- Modify: `src/communities/store.py` (SCHEMA string, lines 28-85)
- Test: `tests/test_communities_store.py`

**Step 1: Write the failing test**

Add to `tests/test_communities_store.py`:

```python
from src.communities.store import (
    # ... existing imports ...
    # New imports for this task:
    create_branch,
    list_branches,
    get_active_branch,
)

def test_init_db_creates_branch_tables(db):
    """init_db creates community_branch, community_snapshot, community_snapshot_data tables."""
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "community_branch" in tables
    assert "community_snapshot" in tables
    assert "community_snapshot_data" in tables
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py::test_init_db_creates_branch_tables -v`
Expected: FAIL (ImportError or table not found)

**Step 3: Add schema and stub functions to store.py**

Add to the `SCHEMA` string in `src/communities/store.py` (after the `account_note` table, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS community_branch (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    base_run_id  TEXT,
    is_active    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (base_run_id) REFERENCES community_run(run_id)
);

CREATE TABLE IF NOT EXISTS community_snapshot (
    id           TEXT PRIMARY KEY,
    branch_id    TEXT NOT NULL,
    name         TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (branch_id) REFERENCES community_branch(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_snapshot_data (
    snapshot_id   TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('community', 'assignment', 'note')),
    data          TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES community_snapshot(id) ON DELETE CASCADE
);
```

Add stub functions (empty for now, will be implemented in Task 2-4):

```python
def get_active_branch(conn: sqlite3.Connection) -> Optional[dict]:
    """Return the active branch as a dict, or None."""
    row = conn.execute(
        "SELECT id, name, description, base_run_id, created_at, updated_at"
        " FROM community_branch WHERE is_active = 1"
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "name": row[1], "description": row[2],
        "base_run_id": row[3], "created_at": row[4], "updated_at": row[5],
    }


def list_branches(conn: sqlite3.Connection) -> list:
    """Return all branches with snapshot counts."""
    return conn.execute(
        """SELECT b.id, b.name, b.description, b.base_run_id, b.is_active,
                  COUNT(s.id) as snapshot_count, b.created_at, b.updated_at
           FROM community_branch b
           LEFT JOIN community_snapshot s ON s.branch_id = b.id
           GROUP BY b.id
           ORDER BY b.created_at"""
    ).fetchall()


def create_branch(
    conn: sqlite3.Connection,
    branch_id: str,
    name: str,
    description: Optional[str] = None,
    base_run_id: Optional[str] = None,
    is_active: bool = False,
) -> None:
    """Create a new branch row. Does NOT commit."""
    now = now_utc()
    conn.execute(
        """INSERT INTO community_branch (id, name, description, base_run_id, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (branch_id, name, description, base_run_id, 1 if is_active else 0, now, now),
    )
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py::test_init_db_creates_branch_tables -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/communities/store.py tests/test_communities_store.py
git commit -m "feat(snapshots): add branch/snapshot schema and stub functions"
```

---

## Task 2: Snapshot capture and restore functions

**Files:**
- Modify: `src/communities/store.py`
- Test: `tests/test_communities_store.py`

**Step 1: Write the failing tests**

```python
import json
from src.communities.store import (
    # ... add to existing imports:
    capture_snapshot,
    restore_snapshot,
    list_snapshots,
)


def test_capture_snapshot(seeded_db):
    """capture_snapshot freezes Layer 2 state as JSON."""
    create_branch(seeded_db, "br-1", "main", is_active=True)
    seeded_db.commit()
    snap_id = capture_snapshot(seeded_db, "br-1", name="initial")

    # Verify snapshot exists
    row = seeded_db.execute(
        "SELECT id, branch_id, name FROM community_snapshot WHERE id = ?",
        (snap_id,),
    ).fetchone()
    assert row is not None
    assert row[1] == "br-1"
    assert row[2] == "initial"

    # Verify data was captured
    kinds = {r[0] for r in seeded_db.execute(
        "SELECT DISTINCT kind FROM community_snapshot_data WHERE snapshot_id = ?",
        (snap_id,),
    ).fetchall()}
    assert "community" in kinds
    assert "assignment" in kinds


def test_restore_snapshot(seeded_db):
    """restore_snapshot wipes Layer 2 and restores from snapshot."""
    create_branch(seeded_db, "br-1", "main", is_active=True)
    seeded_db.commit()
    snap_id = capture_snapshot(seeded_db, "br-1", name="before-change")

    # Mutate Layer 2
    seeded_db.execute("DELETE FROM community WHERE id = 'comm-A'")
    seeded_db.commit()
    assert seeded_db.execute("SELECT COUNT(*) FROM community").fetchone()[0] == 1

    # Restore
    restore_snapshot(seeded_db, snap_id)

    # Verify full state restored
    assert seeded_db.execute("SELECT COUNT(*) FROM community").fetchone()[0] == 2
    names = {r[0] for r in seeded_db.execute("SELECT name FROM community").fetchall()}
    assert "EA / forecasting" in names
    assert "Rationalist" in names


def test_restore_snapshot_includes_assignments(seeded_db):
    """Restored snapshot includes community_account rows."""
    create_branch(seeded_db, "br-1", "main", is_active=True)
    seeded_db.commit()
    snap_id = capture_snapshot(seeded_db, "br-1")

    original_count = seeded_db.execute(
        "SELECT COUNT(*) FROM community_account"
    ).fetchone()[0]

    # Wipe assignments
    seeded_db.execute("DELETE FROM community_account")
    seeded_db.commit()

    restore_snapshot(seeded_db, snap_id)
    restored_count = seeded_db.execute(
        "SELECT COUNT(*) FROM community_account"
    ).fetchone()[0]
    assert restored_count == original_count


def test_restore_snapshot_includes_notes(seeded_db):
    """Restored snapshot includes account_note rows."""
    upsert_account_note(seeded_db, "acct_1", "Important person")
    seeded_db.commit()

    create_branch(seeded_db, "br-1", "main", is_active=True)
    seeded_db.commit()
    snap_id = capture_snapshot(seeded_db, "br-1")

    seeded_db.execute("DELETE FROM account_note")
    seeded_db.commit()

    restore_snapshot(seeded_db, snap_id)
    assert get_account_note(seeded_db, "acct_1") == "Important person"


def test_list_snapshots(seeded_db):
    """list_snapshots returns snapshots for a branch ordered newest-first."""
    create_branch(seeded_db, "br-1", "main", is_active=True)
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-1", name="first")
    capture_snapshot(seeded_db, "br-1", name="second")

    snaps = list_snapshots(seeded_db, "br-1")
    assert len(snaps) == 2
    assert snaps[0]["name"] == "second"  # newest first
    assert snaps[1]["name"] == "first"
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py -k "snapshot" -v`
Expected: FAIL (ImportError)

**Step 3: Implement capture_snapshot, restore_snapshot, list_snapshots**

Add to `src/communities/store.py`:

```python
import json
from uuid import uuid4


def capture_snapshot(
    conn: sqlite3.Connection,
    branch_id: str,
    name: Optional[str] = None,
) -> str:
    """Freeze current Layer 2 state into a snapshot. Commits internally.

    Serializes all community, community_account, and account_note rows
    as JSON into community_snapshot_data.

    Returns the snapshot_id.
    """
    snap_id = str(uuid4())
    now = now_utc()

    conn.execute(
        "INSERT INTO community_snapshot (id, branch_id, name, created_at) VALUES (?,?,?,?)",
        (snap_id, branch_id, name, now),
    )

    # Capture communities
    for row in conn.execute(
        "SELECT id, name, description, color, seeded_from_run, seeded_from_idx, created_at, updated_at"
        " FROM community"
    ).fetchall():
        conn.execute(
            "INSERT INTO community_snapshot_data (snapshot_id, kind, data) VALUES (?,?,?)",
            (snap_id, "community", json.dumps({
                "id": row[0], "name": row[1], "description": row[2], "color": row[3],
                "seeded_from_run": row[4], "seeded_from_idx": row[5],
                "created_at": row[6], "updated_at": row[7],
            })),
        )

    # Capture assignments
    for row in conn.execute(
        "SELECT community_id, account_id, weight, source, updated_at FROM community_account"
    ).fetchall():
        conn.execute(
            "INSERT INTO community_snapshot_data (snapshot_id, kind, data) VALUES (?,?,?)",
            (snap_id, "assignment", json.dumps({
                "community_id": row[0], "account_id": row[1],
                "weight": row[2], "source": row[3], "updated_at": row[4],
            })),
        )

    # Capture notes
    for row in conn.execute(
        "SELECT account_id, note, updated_at FROM account_note"
    ).fetchall():
        conn.execute(
            "INSERT INTO community_snapshot_data (snapshot_id, kind, data) VALUES (?,?,?)",
            (snap_id, "note", json.dumps({
                "account_id": row[0], "note": row[1], "updated_at": row[2],
            })),
        )

    conn.commit()
    return snap_id


def restore_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> None:
    """Wipe Layer 2 and restore from a snapshot. Commits internally.

    WARNING: Destructive — deletes all community, community_account,
    and account_note rows before restoring.
    """
    rows = conn.execute(
        "SELECT kind, data FROM community_snapshot_data WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchall()

    if not rows:
        # Empty snapshot — just wipe
        conn.execute("DELETE FROM community_account")
        conn.execute("DELETE FROM account_note")
        conn.execute("DELETE FROM community")
        conn.commit()
        return

    # Wipe Layer 2 (order matters for FK constraints)
    conn.execute("DELETE FROM community_account")
    conn.execute("DELETE FROM account_note")
    conn.execute("DELETE FROM community")

    # Restore from snapshot
    for kind, data_json in rows:
        d = json.loads(data_json)
        if kind == "community":
            conn.execute(
                """INSERT INTO community (id, name, description, color,
                       seeded_from_run, seeded_from_idx, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (d["id"], d["name"], d["description"], d["color"],
                 d["seeded_from_run"], d["seeded_from_idx"],
                 d["created_at"], d["updated_at"]),
            )
        elif kind == "assignment":
            conn.execute(
                """INSERT INTO community_account
                       (community_id, account_id, weight, source, updated_at)
                   VALUES (?,?,?,?,?)""",
                (d["community_id"], d["account_id"],
                 d["weight"], d["source"], d["updated_at"]),
            )
        elif kind == "note":
            conn.execute(
                """INSERT INTO account_note (account_id, note, updated_at)
                   VALUES (?,?,?)""",
                (d["account_id"], d["note"], d["updated_at"]),
            )

    conn.commit()


def list_snapshots(conn: sqlite3.Connection, branch_id: str) -> list:
    """Return snapshots for a branch, newest first."""
    rows = conn.execute(
        """SELECT id, branch_id, name, created_at
           FROM community_snapshot
           WHERE branch_id = ?
           ORDER BY created_at DESC""",
        (branch_id,),
    ).fetchall()
    return [
        {"id": r[0], "branch_id": r[1], "name": r[2], "created_at": r[3]}
        for r in rows
    ]
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py -k "snapshot" -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/communities/store.py tests/test_communities_store.py
git commit -m "feat(snapshots): capture and restore snapshot functions with tests"
```

---

## Task 3: Branch switch, dirty detection, delete, and bootstrap

**Files:**
- Modify: `src/communities/store.py`
- Test: `tests/test_communities_store.py`

**Step 1: Write the failing tests**

```python
from src.communities.store import (
    # add to imports:
    switch_branch,
    is_branch_dirty,
    delete_branch,
    ensure_main_branch,
    set_active_branch,
)


def test_switch_branch_with_save(seeded_db):
    """Switching branches saves current state and restores target."""
    # Create two branches
    create_branch(seeded_db, "br-main", "main", is_active=True)
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-main", name="initial")

    # Create branch B as fork
    create_branch(seeded_db, "br-b", "experiment")
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-b", name="fork")

    # Modify Layer 2 on main (rename a community)
    seeded_db.execute("UPDATE community SET name = 'RENAMED' WHERE id = 'comm-A'")
    seeded_db.commit()

    # Switch to B with save
    switch_branch(seeded_db, "br-b", save_current=True)

    # After switch: Layer 2 should have the original names (from br-b's snapshot)
    row = seeded_db.execute("SELECT name FROM community WHERE id = 'comm-A'").fetchone()
    assert row[0] == "EA / forecasting"

    # br-main should now be inactive, br-b active
    assert get_active_branch(seeded_db)["id"] == "br-b"

    # Switch back to main — should have the rename saved
    switch_branch(seeded_db, "br-main", save_current=False)
    row = seeded_db.execute("SELECT name FROM community WHERE id = 'comm-A'").fetchone()
    assert row[0] == "RENAMED"


def test_switch_branch_with_discard(seeded_db):
    """Switching with discard drops unsaved changes."""
    create_branch(seeded_db, "br-main", "main", is_active=True)
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-main", name="initial")

    create_branch(seeded_db, "br-b", "experiment")
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-b", name="fork")

    # Modify Layer 2
    seeded_db.execute("UPDATE community SET name = 'RENAMED' WHERE id = 'comm-A'")
    seeded_db.commit()

    # Switch with discard (save_current=False)
    switch_branch(seeded_db, "br-b", save_current=False)

    # Switch back — rename should be gone (was discarded)
    switch_branch(seeded_db, "br-main", save_current=False)
    row = seeded_db.execute("SELECT name FROM community WHERE id = 'comm-A'").fetchone()
    assert row[0] == "EA / forecasting"


def test_is_branch_dirty(seeded_db):
    """Dirty detection compares Layer 2 against latest snapshot."""
    create_branch(seeded_db, "br-main", "main", is_active=True)
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-main")

    assert is_branch_dirty(seeded_db, "br-main") is False

    # Modify Layer 2
    seeded_db.execute("UPDATE community SET name = 'CHANGED' WHERE id = 'comm-A'")
    seeded_db.commit()

    assert is_branch_dirty(seeded_db, "br-main") is True


def test_is_branch_dirty_no_snapshots(seeded_db):
    """Branch with no snapshots is considered clean."""
    create_branch(seeded_db, "br-main", "main", is_active=True)
    seeded_db.commit()
    assert is_branch_dirty(seeded_db, "br-main") is False


def test_delete_branch(seeded_db):
    """Deleting a branch cascades to its snapshots."""
    create_branch(seeded_db, "br-main", "main", is_active=True)
    create_branch(seeded_db, "br-b", "experiment")
    seeded_db.commit()
    capture_snapshot(seeded_db, "br-b", name="test")

    delete_branch(seeded_db, "br-b")

    branches = list_branches(seeded_db)
    assert len(branches) == 1
    snaps = list_snapshots(seeded_db, "br-b")
    assert len(snaps) == 0


def test_delete_active_branch_raises(seeded_db):
    """Cannot delete the active branch."""
    create_branch(seeded_db, "br-main", "main", is_active=True)
    seeded_db.commit()

    with pytest.raises(ValueError, match="cannot delete active branch"):
        delete_branch(seeded_db, "br-main")


def test_ensure_main_branch_creates_on_empty(seeded_db):
    """ensure_main_branch creates 'main' branch with snapshot if none exist."""
    ensure_main_branch(seeded_db)

    branch = get_active_branch(seeded_db)
    assert branch is not None
    assert branch["name"] == "main"

    snaps = list_snapshots(seeded_db, branch["id"])
    assert len(snaps) == 1


def test_ensure_main_branch_noop_if_exists(seeded_db):
    """ensure_main_branch is idempotent."""
    create_branch(seeded_db, "br-main", "main", is_active=True)
    seeded_db.commit()

    ensure_main_branch(seeded_db)

    branches = list_branches(seeded_db)
    assert len(branches) == 1
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py -k "branch or dirty or ensure" -v`
Expected: FAIL (ImportError)

**Step 3: Implement the functions**

Add to `src/communities/store.py`:

```python
def set_active_branch(conn: sqlite3.Connection, branch_id: str) -> None:
    """Set exactly one branch as active. Does NOT commit."""
    conn.execute("UPDATE community_branch SET is_active = 0")
    conn.execute(
        "UPDATE community_branch SET is_active = 1, updated_at = ? WHERE id = ?",
        (now_utc(), branch_id),
    )


def switch_branch(
    conn: sqlite3.Connection,
    target_branch_id: str,
    save_current: bool = True,
) -> None:
    """Switch to a different branch. Commits internally.

    If save_current=True, snapshots current Layer 2 onto the current active branch
    before switching. If False, current unsaved changes are discarded.
    """
    current = get_active_branch(conn)
    if current and current["id"] == target_branch_id:
        return  # Already on this branch

    # Optionally save current state
    if save_current and current:
        capture_snapshot(conn, current["id"], name="auto-save before switch")

    # Find target branch's latest snapshot
    latest = conn.execute(
        """SELECT id FROM community_snapshot
           WHERE branch_id = ? ORDER BY created_at DESC LIMIT 1""",
        (target_branch_id,),
    ).fetchone()

    if latest:
        restore_snapshot(conn, latest[0])
    else:
        # No snapshots on target — wipe to empty
        conn.execute("DELETE FROM community_account")
        conn.execute("DELETE FROM account_note")
        conn.execute("DELETE FROM community")
        conn.commit()

    set_active_branch(conn, target_branch_id)
    conn.commit()


def is_branch_dirty(conn: sqlite3.Connection, branch_id: str) -> bool:
    """Check if working Layer 2 state differs from the latest snapshot.

    Returns False if the branch has no snapshots (treated as clean).
    """
    latest = conn.execute(
        """SELECT id FROM community_snapshot
           WHERE branch_id = ? ORDER BY created_at DESC LIMIT 1""",
        (branch_id,),
    ).fetchone()

    if not latest:
        return False

    snapshot_id = latest[0]

    # Compare community rows
    current_communities = sorted(
        conn.execute(
            "SELECT id, name, description, color FROM community ORDER BY id"
        ).fetchall()
    )
    snap_communities = sorted(
        (
            (d["id"], d["name"], d["description"], d["color"])
            for d in (
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT data FROM community_snapshot_data WHERE snapshot_id = ? AND kind = 'community'",
                    (snapshot_id,),
                ).fetchall()
            )
        )
    )
    if current_communities != snap_communities:
        return True

    # Compare assignment rows
    current_assignments = sorted(
        conn.execute(
            "SELECT community_id, account_id, weight, source FROM community_account ORDER BY community_id, account_id"
        ).fetchall()
    )
    snap_assignments = sorted(
        (
            (d["community_id"], d["account_id"], d["weight"], d["source"])
            for d in (
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT data FROM community_snapshot_data WHERE snapshot_id = ? AND kind = 'assignment'",
                    (snapshot_id,),
                ).fetchall()
            )
        )
    )
    if current_assignments != snap_assignments:
        return True

    # Compare note rows
    current_notes = sorted(
        conn.execute(
            "SELECT account_id, note FROM account_note ORDER BY account_id"
        ).fetchall()
    )
    snap_notes = sorted(
        (
            (d["account_id"], d["note"])
            for d in (
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT data FROM community_snapshot_data WHERE snapshot_id = ? AND kind = 'note'",
                    (snapshot_id,),
                ).fetchall()
            )
        )
    )
    return current_notes != snap_notes


def delete_branch(conn: sqlite3.Connection, branch_id: str) -> None:
    """Delete a branch and cascade to its snapshots. Commits internally.

    Raises ValueError if attempting to delete the active branch.
    """
    active = get_active_branch(conn)
    if active and active["id"] == branch_id:
        raise ValueError("cannot delete active branch")

    conn.execute("DELETE FROM community_branch WHERE id = ?", (branch_id,))
    conn.commit()


def ensure_main_branch(conn: sqlite3.Connection) -> dict:
    """Create 'main' branch if no branches exist. Returns the active branch.

    On first use, snapshots the current Layer 2 state.
    Idempotent — does nothing if branches already exist.
    Commits internally.
    """
    existing = get_active_branch(conn)
    if existing:
        return existing

    # Check if any branches exist at all
    count = conn.execute("SELECT COUNT(*) FROM community_branch").fetchone()[0]
    if count > 0:
        # Branches exist but none active — activate the first one
        first = conn.execute(
            "SELECT id FROM community_branch ORDER BY created_at LIMIT 1"
        ).fetchone()
        set_active_branch(conn, first[0])
        conn.commit()
        return get_active_branch(conn)

    # No branches at all — create "main"
    branch_id = str(uuid4())

    # Find latest NMF run for base_run_id
    latest_run = conn.execute(
        "SELECT run_id FROM community_run ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    base_run_id = latest_run[0] if latest_run else None

    create_branch(conn, branch_id, "main", base_run_id=base_run_id, is_active=True)
    conn.commit()
    capture_snapshot(conn, branch_id, name="initial state")

    return get_active_branch(conn)
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py -k "branch or dirty or ensure" -v`
Expected: ALL PASS

Run full suite: `.venv/bin/python3 -m pytest tests/test_communities_store.py -v`
Expected: ALL PASS (existing tests still work)

**Step 5: Commit**

```bash
git add src/communities/store.py tests/test_communities_store.py
git commit -m "feat(snapshots): switch, dirty detection, delete, bootstrap functions"
```

---

## Task 4: API routes for branches and snapshots

**Files:**
- Create: `src/api/routes/branches.py`
- Modify: `src/api/server.py` (register blueprint)
- Test: `tests/test_branches_routes.py`

**Step 1: Write the failing tests**

Create `tests/test_branches_routes.py`:

```python
"""Tests for /api/communities/branches endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.communities import communities_bp
from src.api.routes.branches import branches_bp
from src.communities.store import (
    init_db, save_run,
    upsert_community, upsert_community_account,
    create_branch, capture_snapshot,
)


@pytest.fixture
def branches_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    db_path = tmp_path / "archive_tweets.db"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY, username TEXT, display_name TEXT,
                bio TEXT, location TEXT, website TEXT
            );
            CREATE TABLE IF NOT EXISTS account_following (
                account_id TEXT NOT NULL, following_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE IF NOT EXISTS account_followers (
                account_id TEXT, follower_account_id TEXT,
                PRIMARY KEY (account_id, follower_account_id)
            );
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY, account_id TEXT, full_text TEXT,
                created_at TEXT, favorite_count INTEGER DEFAULT 0, retweet_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS likes (liker_account_id TEXT, full_text TEXT, expanded_url TEXT);
            CREATE TABLE IF NOT EXISTS retweets (account_id TEXT, rt_of_username TEXT);
        """)

        save_run(conn, "run-1", k=3, signal="follow+rt", threshold=0.1, account_count=5)
        upsert_community(conn, "comm-A", "EA", color="#4a90e2",
                         seeded_from_run="run-1", seeded_from_idx=0)
        upsert_community_account(conn, "comm-A", "acct_1", 0.8, "nmf")
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(communities_bp)
    app.register_blueprint(branches_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(branches_app):
    return branches_app.test_client()


def test_list_branches_bootstraps_main(client):
    """First GET creates 'main' branch."""
    res = client.get("/api/communities/branches")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "main"
    assert data[0]["is_active"] is True


def test_create_branch(client):
    """POST creates a new branch forked from current."""
    # Bootstrap main
    client.get("/api/communities/branches")

    res = client.post("/api/communities/branches", json={
        "name": "experiment",
        "description": "Testing a new framing",
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["name"] == "experiment"
    assert data["is_active"] is True  # New branch becomes active

    # Now two branches
    res2 = client.get("/api/communities/branches")
    assert len(res2.get_json()) == 2


def test_create_duplicate_name_fails(client):
    """Cannot create two branches with the same name."""
    client.get("/api/communities/branches")
    res = client.post("/api/communities/branches", json={"name": "main"})
    assert res.status_code == 409


def test_switch_branch(client):
    """POST switch changes active branch."""
    client.get("/api/communities/branches")

    # Create second branch
    res = client.post("/api/communities/branches", json={"name": "alt"})
    alt_id = res.get_json()["id"]

    # Get main branch id
    branches = client.get("/api/communities/branches").get_json()
    main_id = next(b["id"] for b in branches if b["name"] == "main")

    # Switch back to main
    res = client.post(f"/api/communities/branches/{main_id}/switch",
                      json={"action": "save"})
    assert res.status_code == 200

    active = next(b for b in client.get("/api/communities/branches").get_json()
                  if b["is_active"])
    assert active["name"] == "main"


def test_dirty_check(client):
    """GET dirty returns false for clean branch."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    res = client.get(f"/api/communities/branches/{main_id}/dirty")
    assert res.status_code == 200
    assert res.get_json()["dirty"] is False


def test_save_snapshot(client):
    """POST snapshot saves current state."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    res = client.post(f"/api/communities/branches/{main_id}/snapshots",
                      json={"name": "checkpoint"})
    assert res.status_code == 201
    assert res.get_json()["name"] == "checkpoint"


def test_list_snapshots(client):
    """GET snapshots returns list for branch."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    res = client.get(f"/api/communities/branches/{main_id}/snapshots")
    assert res.status_code == 200
    # Should have 1 snapshot from bootstrap
    assert len(res.get_json()) >= 1


def test_delete_branch(client):
    """DELETE removes non-active branch."""
    client.get("/api/communities/branches")
    client.post("/api/communities/branches", json={"name": "temp"})

    branches = client.get("/api/communities/branches").get_json()
    non_active = next(b for b in branches if not b["is_active"])

    res = client.delete(f"/api/communities/branches/{non_active['id']}")
    assert res.status_code == 200


def test_delete_active_branch_fails(client):
    """Cannot delete the active branch."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    active = next(b for b in branches if b["is_active"])

    res = client.delete(f"/api/communities/branches/{active['id']}")
    assert res.status_code == 409
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_branches_routes.py -v`
Expected: FAIL (ImportError — branches.py doesn't exist)

**Step 3: Create the routes file**

Create `src/api/routes/branches.py`:

```python
"""Branches API — branch/snapshot versioning for community maps.

Blueprint: /api/communities/branches
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, jsonify, request

from src.communities import store

logger = logging.getLogger(__name__)

branches_bp = Blueprint("branches", __name__, url_prefix="/api/communities/branches")

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "archive_tweets.db"


def _get_db() -> sqlite3.Connection:
    db_path = os.getenv("ARCHIVE_DB_PATH", str(_DEFAULT_DB))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@branches_bp.route("", methods=["GET"])
def list_branches_route():
    """List all branches. Auto-creates 'main' on first call."""
    conn = _get_db()
    try:
        store.ensure_main_branch(conn)
        rows = store.list_branches(conn)
        return jsonify([
            {
                "id": r[0], "name": r[1], "description": r[2],
                "base_run_id": r[3], "is_active": bool(r[4]),
                "snapshot_count": r[5], "created_at": r[6], "updated_at": r[7],
            }
            for r in rows
        ])
    finally:
        conn.close()


@branches_bp.route("", methods=["POST"])
def create_branch_route():
    """Create a new branch forked from current state."""
    conn = _get_db()
    try:
        store.ensure_main_branch(conn)
        body = request.get_json() or {}
        name = body.get("name")
        if not name:
            return jsonify({"error": "name is required"}), 400

        # Check uniqueness
        exists = conn.execute(
            "SELECT 1 FROM community_branch WHERE name = ?", (name,)
        ).fetchone()
        if exists:
            return jsonify({"error": f"branch '{name}' already exists"}), 409

        # Auto-save current branch
        current = store.get_active_branch(conn)
        if current:
            store.capture_snapshot(conn, current["id"], name="auto-save before fork")

        # Create new branch
        branch_id = str(uuid4())
        latest_run = conn.execute(
            "SELECT run_id FROM community_run ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        base_run_id = body.get("base_run_id") or (latest_run[0] if latest_run else None)

        store.create_branch(
            conn, branch_id, name,
            description=body.get("description"),
            base_run_id=base_run_id,
        )
        store.set_active_branch(conn, branch_id)
        conn.commit()

        # Snapshot current state onto new branch
        store.capture_snapshot(conn, branch_id, name="forked from " + (current["name"] if current else "scratch"))

        branch = store.get_active_branch(conn)
        return jsonify(branch), 201
    finally:
        conn.close()


@branches_bp.route("/<branch_id>", methods=["PATCH"])
def update_branch_route(branch_id):
    """Rename or update branch description."""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        name = body.get("name")
        description = body.get("description")

        if name:
            conn.execute(
                "UPDATE community_branch SET name = ?, updated_at = ? WHERE id = ?",
                (name, store.now_utc(), branch_id),
            )
        if description is not None:
            conn.execute(
                "UPDATE community_branch SET description = ?, updated_at = ? WHERE id = ?",
                (description, store.now_utc(), branch_id),
            )
        conn.commit()
        return jsonify({"updated": True})
    finally:
        conn.close()


@branches_bp.route("/<branch_id>", methods=["DELETE"])
def delete_branch_route(branch_id):
    """Delete a non-active branch."""
    conn = _get_db()
    try:
        try:
            store.delete_branch(conn, branch_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"deleted": True})
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/switch", methods=["POST"])
def switch_branch_route(branch_id):
    """Switch to a different branch."""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        action = body.get("action", "save")
        save_current = action == "save"

        store.switch_branch(conn, branch_id, save_current=save_current)
        branch = store.get_active_branch(conn)
        return jsonify(branch)
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/dirty", methods=["GET"])
def dirty_check_route(branch_id):
    """Check if working state differs from latest snapshot."""
    conn = _get_db()
    try:
        dirty = store.is_branch_dirty(conn, branch_id)
        return jsonify({"branch_id": branch_id, "dirty": dirty})
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/snapshots", methods=["GET"])
def list_snapshots_route(branch_id):
    """List snapshots on a branch."""
    conn = _get_db()
    try:
        snaps = store.list_snapshots(conn, branch_id)
        return jsonify(snaps)
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/snapshots", methods=["POST"])
def save_snapshot_route(branch_id):
    """Save a snapshot on the current branch."""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        snap_id = store.capture_snapshot(conn, branch_id, name=body.get("name"))
        snap = conn.execute(
            "SELECT id, branch_id, name, created_at FROM community_snapshot WHERE id = ?",
            (snap_id,),
        ).fetchone()
        return jsonify({
            "id": snap[0], "branch_id": snap[1],
            "name": snap[2], "created_at": snap[3],
        }), 201
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/snapshots/<snapshot_id>/restore", methods=["POST"])
def restore_snapshot_route(branch_id, snapshot_id):
    """Restore a snapshot."""
    conn = _get_db()
    try:
        # Verify snapshot belongs to branch
        snap = conn.execute(
            "SELECT 1 FROM community_snapshot WHERE id = ? AND branch_id = ?",
            (snapshot_id, branch_id),
        ).fetchone()
        if not snap:
            return jsonify({"error": "snapshot not found on this branch"}), 404

        store.restore_snapshot(conn, snapshot_id)
        return jsonify({"restored": True, "snapshot_id": snapshot_id})
    finally:
        conn.close()
```

**Step 4: Register the blueprint**

In `src/api/server.py`, add after the existing `from src.api.routes.communities import communities_bp` line:

```python
from src.api.routes.branches import branches_bp
```

And add after the existing `app.register_blueprint(communities_bp)` line:

```python
app.register_blueprint(branches_bp)
```

**Step 5: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_branches_routes.py -v`
Expected: ALL PASS

Run full backend suite:
```bash
.venv/bin/python3 -m pytest tests/test_communities_store.py tests/test_communities_routes.py tests/test_branches_routes.py -v
```
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/api/routes/branches.py src/api/server.py tests/test_branches_routes.py
git commit -m "feat(snapshots): branch API routes with full test coverage"
```

---

## Task 5: Frontend API client for branches

**Files:**
- Modify: `graph-explorer/src/communitiesApi.js`

**Step 1: Add branch API functions**

Add to the end of `graph-explorer/src/communitiesApi.js`:

```javascript
// ── Branch & Snapshot API ───────────────────────────────────────────

const BRANCHES = `${API_BASE_URL}/api/communities/branches`

export async function fetchBranches() {
  const res = await fetch(BRANCHES)
  if (!res.ok) throw new Error(`branches list failed: ${res.status}`)
  return res.json()
}

export async function createBranch(name, description) {
  const res = await fetch(BRANCHES, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || `create branch failed: ${res.status}`)
  }
  return res.json()
}

export async function updateBranch(branchId, updates) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`update branch failed: ${res.status}`)
  return res.json()
}

export async function deleteBranch(branchId) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`delete branch failed: ${res.status}`)
  return res.json()
}

export async function switchBranch(branchId, action = 'save') {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!res.ok) throw new Error(`switch branch failed: ${res.status}`)
  return res.json()
}

export async function checkBranchDirty(branchId) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/dirty`)
  if (!res.ok) throw new Error(`dirty check failed: ${res.status}`)
  return res.json()
}

export async function fetchSnapshots(branchId) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/snapshots`)
  if (!res.ok) throw new Error(`snapshots list failed: ${res.status}`)
  return res.json()
}

export async function saveSnapshot(branchId, name) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/snapshots`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`save snapshot failed: ${res.status}`)
  return res.json()
}

export async function restoreSnapshot(branchId, snapshotId) {
  const res = await fetch(
    `${BRANCHES}/${encodeURIComponent(branchId)}/snapshots/${encodeURIComponent(snapshotId)}/restore`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(`restore snapshot failed: ${res.status}`)
  return res.json()
}
```

**Step 2: Verify frontend builds**

Run: `cd graph-explorer && npx vite build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add graph-explorer/src/communitiesApi.js
git commit -m "feat(snapshots): frontend API client for branches and snapshots"
```

---

## Task 6: Branch bar UI in Communities.jsx

**Files:**
- Modify: `graph-explorer/src/Communities.jsx`

**Step 1: Add branch bar between header and main layout**

Import the new API functions at the top of `Communities.jsx`:

```javascript
import {
  fetchCommunities,
  fetchCommunityMembers,
  updateCommunity,
  // Add:
  fetchBranches,
  createBranch,
  switchBranch,
  saveSnapshot,
  checkBranchDirty,
} from './communitiesApi'
```

Add state variables inside the `Communities` component (after existing state):

```javascript
const [branches, setBranches] = useState([])
const [activeBranch, setActiveBranch] = useState(null)
const [isDirty, setIsDirty] = useState(false)
const [showBranchModal, setShowBranchModal] = useState(false) // 'switch-confirm' | 'new-branch' | false
const [pendingSwitchId, setPendingSwitchId] = useState(null)
const [newBranchName, setNewBranchName] = useState('')
```

Add a `loadBranches` function and effect:

```javascript
const loadBranches = useCallback(async () => {
  try {
    const data = await fetchBranches()
    setBranches(data)
    const active = data.find(b => b.is_active)
    setActiveBranch(active || null)
    if (active) {
      const dirtyResult = await checkBranchDirty(active.id)
      setIsDirty(dirtyResult.dirty)
    }
  } catch (e) { setError(e.message) }
}, [])

useEffect(() => { loadBranches() }, [loadBranches])
```

Add handler functions:

```javascript
const handleSwitchBranch = useCallback(async (branchId, action) => {
  try {
    await switchBranch(branchId, action)
    await loadBranches()
    // Reload communities for the new branch
    const comms = await fetchCommunities()
    setCommunities(comms)
    if (comms.length > 0) setSelectedCommunity(comms[0])
    setMembers([])
    setDeepDiveAccountId(null)
    setShowBranchModal(false)
    setPendingSwitchId(null)
  } catch (e) { setError(e.message) }
}, [loadBranches])

const handleCreateBranch = useCallback(async () => {
  if (!newBranchName.trim()) return
  try {
    await createBranch(newBranchName.trim())
    setNewBranchName('')
    setShowBranchModal(false)
    await loadBranches()
    // Reload communities
    const comms = await fetchCommunities()
    setCommunities(comms)
    if (comms.length > 0) setSelectedCommunity(comms[0])
  } catch (e) { setError(e.message) }
}, [newBranchName, loadBranches])

const handleSaveSnapshot = useCallback(async () => {
  if (!activeBranch) return
  try {
    const name = prompt('Snapshot name (optional):')
    await saveSnapshot(activeBranch.id, name || undefined)
    setIsDirty(false)
    await loadBranches()
  } catch (e) { setError(e.message) }
}, [activeBranch, loadBranches])

const initiateSwitch = useCallback(async (branchId) => {
  if (!activeBranch || branchId === activeBranch.id) return
  if (isDirty) {
    setPendingSwitchId(branchId)
    setShowBranchModal('switch-confirm')
  } else {
    await handleSwitchBranch(branchId, 'discard')
  }
}, [activeBranch, isDirty, handleSwitchBranch])
```

Add the branch bar JSX — insert between the `{error && ...}` block and the `{/* Main layout */}` block:

```jsx
{/* Branch bar */}
<div style={{
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '6px 16px',
  borderBottom: '1px solid var(--panel-border, #1e293b)',
  background: 'var(--panel, #1e293b)',
  fontSize: 12,
}}>
  <span style={{ color: '#64748b', fontWeight: 600 }}>Branch:</span>
  <select
    value={activeBranch?.id || ''}
    onChange={e => initiateSwitch(e.target.value)}
    style={{
      padding: '4px 8px', fontSize: 12,
      background: 'var(--bg, #0f172a)',
      border: '1px solid var(--panel-border, #2d3748)',
      borderRadius: 4, color: 'var(--text, #e2e8f0)',
    }}
  >
    {branches.map(b => (
      <option key={b.id} value={b.id}>
        {b.name} ({b.snapshot_count} saves)
      </option>
    ))}
  </select>
  <button onClick={handleSaveSnapshot} style={{
    padding: '4px 10px', fontSize: 12, fontWeight: 600,
    background: '#22c55e', color: '#fff', border: 'none',
    borderRadius: 4, cursor: 'pointer',
  }}>
    Save
  </button>
  <button onClick={() => setShowBranchModal('new-branch')} style={{
    padding: '4px 10px', fontSize: 12, fontWeight: 600,
    background: '#3b82f6', color: '#fff', border: 'none',
    borderRadius: 4, cursor: 'pointer',
  }}>
    Branch...
  </button>
  {isDirty && (
    <span style={{ color: '#f59e0b', fontWeight: 600 }}>
      unsaved changes
    </span>
  )}
</div>

{/* Switch confirmation modal */}
{showBranchModal === 'switch-confirm' && (
  <div style={{
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  }}>
    <div style={{
      background: 'var(--panel, #1e293b)', borderRadius: 8,
      padding: 24, maxWidth: 400, width: '90%',
      border: '1px solid var(--panel-border, #2d3748)',
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
        Unsaved changes on "{activeBranch?.name}"
      </div>
      <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
        Save your changes before switching, or discard them?
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={() => { setShowBranchModal(false); setPendingSwitchId(null) }}
          style={{ padding: '6px 16px', fontSize: 12, background: 'transparent',
            border: '1px solid var(--panel-border, #2d3748)', borderRadius: 4,
            color: 'var(--text, #e2e8f0)', cursor: 'pointer' }}>
          Cancel
        </button>
        <button onClick={() => handleSwitchBranch(pendingSwitchId, 'discard')}
          style={{ padding: '6px 16px', fontSize: 12, background: '#ef4444',
            color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          Discard
        </button>
        <button onClick={() => handleSwitchBranch(pendingSwitchId, 'save')}
          style={{ padding: '6px 16px', fontSize: 12, background: '#22c55e',
            color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          Save & Switch
        </button>
      </div>
    </div>
  </div>
)}

{/* New branch modal */}
{showBranchModal === 'new-branch' && (
  <div style={{
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  }}>
    <div style={{
      background: 'var(--panel, #1e293b)', borderRadius: 8,
      padding: 24, maxWidth: 400, width: '90%',
      border: '1px solid var(--panel-border, #2d3748)',
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
        Create New Branch
      </div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
        Fork from current state of "{activeBranch?.name}"
      </div>
      <input
        autoFocus
        type="text" placeholder="Branch name..."
        value={newBranchName}
        onChange={e => setNewBranchName(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleCreateBranch()}
        style={{
          width: '100%', padding: '8px 12px', fontSize: 13, marginBottom: 12,
          background: 'var(--bg, #0f172a)',
          border: '1px solid var(--panel-border, #2d3748)',
          borderRadius: 4, color: 'var(--text, #e2e8f0)',
        }}
      />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={() => { setShowBranchModal(false); setNewBranchName('') }}
          style={{ padding: '6px 16px', fontSize: 12, background: 'transparent',
            border: '1px solid var(--panel-border, #2d3748)', borderRadius: 4,
            color: 'var(--text, #e2e8f0)', cursor: 'pointer' }}>
          Cancel
        </button>
        <button onClick={handleCreateBranch}
          style={{ padding: '6px 16px', fontSize: 12, background: '#3b82f6',
            color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          Create
        </button>
      </div>
    </div>
  </div>
)}
```

**Step 2: Verify frontend builds**

Run: `cd graph-explorer && npx vite build`
Expected: Build succeeds

**Step 3: Run all backend tests to confirm nothing broken**

Run: `.venv/bin/python3 -m pytest tests/test_communities_store.py tests/test_communities_routes.py tests/test_branches_routes.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add graph-explorer/src/Communities.jsx graph-explorer/src/communitiesApi.js
git commit -m "feat(snapshots): branch bar UI with save, switch, and fork"
```

---

## Task 7: Dirty detection polling and integration test

**Files:**
- Modify: `graph-explorer/src/Communities.jsx` (add dirty polling)
- Test: manual verification

**Step 1: Add dirty polling**

Inside the Communities component, add an effect that polls dirty state when the user makes changes. After the existing `handleWeightsChanged` callback, add:

```javascript
// Poll dirty state after any mutation
const refreshDirtyState = useCallback(async () => {
  if (!activeBranch) return
  try {
    const result = await checkBranchDirty(activeBranch.id)
    setIsDirty(result.dirty)
  } catch { /* ignore polling errors */ }
}, [activeBranch])

// Refresh dirty state when communities or members change
useEffect(() => { refreshDirtyState() }, [communities, members, refreshDirtyState])
```

Also update `handleWeightsChanged` to refresh dirty state:

```javascript
const handleWeightsChanged = useCallback(async () => {
  loadMembers()
  const comms = await fetchCommunities()
  setCommunities(comms)
  refreshDirtyState()
}, [loadMembers, refreshDirtyState])
```

And update `handleUpdateCommunity` to refresh dirty state:

```javascript
const handleUpdateCommunity = useCallback(async (updates) => {
  if (!selectedCommunity) return
  try {
    const result = await updateCommunity(selectedCommunity.id, updates)
    const updated = { ...selectedCommunity, ...result }
    setSelectedCommunity(updated)
    setCommunities(prev => prev.map(c => c.id === updated.id ? { ...c, ...result } : c))
    setEditingName(null)
    refreshDirtyState()
  } catch (e) { setError(e.message) }
}, [selectedCommunity, refreshDirtyState])
```

**Step 2: Manual integration test**

1. Start backend: `PORT=8001 .venv/bin/python3 -m flask --app src.api.server:create_app run --port 8001`
2. Start frontend: `cd graph-explorer && VITE_API_URL=http://localhost:8001 npx vite --port 5174`
3. Open Communities tab — should see "Branch: main (1 saves)" in branch bar
4. Rename a community — "unsaved changes" badge should appear
5. Click Save — badge should disappear
6. Click Branch — create "experiment" — should switch to new branch
7. Make changes — click dropdown to switch back to main — should see confirmation modal
8. Test Save & Switch, Discard, Cancel

**Step 3: Commit**

```bash
git add graph-explorer/src/Communities.jsx
git commit -m "feat(snapshots): dirty detection polling and mutation integration"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Schema + stubs | store.py | 1 test |
| 2 | Capture + restore | store.py | 5 tests |
| 3 | Switch, dirty, delete, bootstrap | store.py | 8 tests |
| 4 | API routes | branches.py, server.py | 10 tests |
| 5 | Frontend API client | communitiesApi.js | build check |
| 6 | Branch bar UI | Communities.jsx | build + backend tests |
| 7 | Dirty polling + integration | Communities.jsx | manual test |

Total: ~24 automated tests + manual integration test
