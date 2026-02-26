"""Branch and snapshot versioning for Layer 2 community data.

Allows capturing and restoring named snapshots of the curated community state
(community rows, community_account assignments, account_note rows), and switching
between named branches (each branch maintains its own snapshot history).

Tables (defined in store.SCHEMA):
  community_branch        — named branches (one active at a time)
  community_snapshot      — named snapshots per branch
  community_snapshot_data — serialized rows for each snapshot (kind: community|assignment|note)

Separated from store.py because:
- This is an independent versioning system (~350 LOC)
- It changes on a different cadence from the core persistence layer
- It has no dependencies on store.py beyond now_utc()
"""

import json
import sqlite3
from typing import Optional
from uuid import uuid4

from src.communities.store import now_utc


# ── Branch operations ──────────────────────────────────────────────────────────

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


def set_active_branch(conn: sqlite3.Connection, branch_id: str) -> None:
    """Set exactly one branch as active. Does NOT commit."""
    conn.execute("UPDATE community_branch SET is_active = 0")
    conn.execute(
        "UPDATE community_branch SET is_active = 1, updated_at = ? WHERE id = ?",
        (now_utc(), branch_id),
    )


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


# ── Snapshot operations ────────────────────────────────────────────────────────

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
