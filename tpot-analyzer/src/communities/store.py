"""
Community persistence layer for archive_tweets.db.

Two-layer design:
  Layer 1 — NMF snapshots (immutable, recomputable):
    community_run        — one row per NMF run
    community_membership — W matrix: (run, account, community_idx, weight)
    community_definition — H matrix top signals per community

  Layer 2 — Curator's canonical map (human-managed):
    community         — named communities (seeded from NMF, then human-edited)
    community_account — account→community assignments (source: 'nmf' | 'human')
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS community_run (
    run_id        TEXT PRIMARY KEY,
    k             INTEGER NOT NULL,
    signal        TEXT NOT NULL,
    threshold     REAL NOT NULL,
    account_count INTEGER NOT NULL,
    notes         TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS community_membership (
    run_id        TEXT NOT NULL,
    account_id    TEXT NOT NULL,
    community_idx INTEGER NOT NULL,
    weight        REAL NOT NULL,
    PRIMARY KEY (run_id, account_id, community_idx),
    FOREIGN KEY (run_id) REFERENCES community_run(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_definition (
    run_id        TEXT NOT NULL,
    community_idx INTEGER NOT NULL,
    feature_type  TEXT NOT NULL,
    target        TEXT NOT NULL,
    score         REAL NOT NULL,
    rank          INTEGER NOT NULL,
    PRIMARY KEY (run_id, community_idx, feature_type, rank),
    FOREIGN KEY (run_id) REFERENCES community_run(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    description      TEXT,
    color            TEXT,
    seeded_from_run  TEXT,
    seeded_from_idx  INTEGER,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS community_account (
    community_id TEXT NOT NULL,
    account_id   TEXT NOT NULL,
    weight       REAL NOT NULL,
    source       TEXT NOT NULL CHECK (source IN ('nmf', 'human')),
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (community_id, account_id),
    FOREIGN KEY (community_id) REFERENCES community(id) ON DELETE CASCADE
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Layer 1: NMF runs ─────────────────────────────────────────────────────────

def save_run(
    conn: sqlite3.Connection,
    run_id: str,
    k: int,
    signal: str,
    threshold: float,
    account_count: int,
    notes: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO community_run VALUES (?,?,?,?,?,?,?)",
        (run_id, k, signal, threshold, account_count, notes, now_utc()),
    )
    conn.commit()


def save_memberships(
    conn: sqlite3.Connection,
    run_id: str,
    rows: list,        # [(account_id, community_idx, weight), ...]
) -> None:
    """Write W matrix rows. Replaces all existing rows for this run_id."""
    conn.execute("DELETE FROM community_membership WHERE run_id = ?", (run_id,))
    conn.executemany(
        "INSERT INTO community_membership VALUES (?,?,?,?)",
        [(run_id, aid, cidx, w) for aid, cidx, w in rows],
    )
    conn.commit()


def save_definitions(
    conn: sqlite3.Connection,
    run_id: str,
    rows: list,        # [(community_idx, feature_type, target, score, rank), ...]
) -> None:
    """Write H matrix top features. Replaces all existing rows for this run_id."""
    conn.execute("DELETE FROM community_definition WHERE run_id = ?", (run_id,))
    conn.executemany(
        "INSERT INTO community_definition VALUES (?,?,?,?,?,?)",
        [(run_id, cidx, ftype, target, score, rank) for cidx, ftype, target, score, rank in rows],
    )
    conn.commit()


def list_runs(conn: sqlite3.Connection) -> list:
    """Return all runs ordered newest-first."""
    return conn.execute(
        "SELECT run_id, k, signal, threshold, account_count, notes, created_at"
        " FROM community_run ORDER BY created_at DESC"
    ).fetchall()


def get_memberships(conn: sqlite3.Connection, run_id: str) -> list:
    return conn.execute(
        "SELECT account_id, community_idx, weight FROM community_membership"
        " WHERE run_id = ? ORDER BY community_idx, weight DESC",
        (run_id,),
    ).fetchall()


def get_definitions(conn: sqlite3.Connection, run_id: str) -> list:
    return conn.execute(
        "SELECT community_idx, feature_type, target, score, rank"
        " FROM community_definition WHERE run_id = ?"
        " ORDER BY community_idx, feature_type, rank",
        (run_id,),
    ).fetchall()


# ── Layer 2: Curator's map ────────────────────────────────────────────────────

def upsert_community(
    conn: sqlite3.Connection,
    community_id: str,
    name: str,
    color: Optional[str] = None,
    description: Optional[str] = None,
    seeded_from_run: Optional[str] = None,
    seeded_from_idx: Optional[int] = None,
) -> None:
    now = now_utc()
    conn.execute(
        """INSERT INTO community (id, name, description, color,
               seeded_from_run, seeded_from_idx, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
               name=excluded.name,
               description=excluded.description,
               color=excluded.color,
               updated_at=excluded.updated_at""",
        (community_id, name, description, color,
         seeded_from_run, seeded_from_idx, now, now),
    )


def upsert_community_account(
    conn: sqlite3.Connection,
    community_id: str,
    account_id: str,
    weight: float,
    source: str = "nmf",
) -> None:
    conn.execute(
        """INSERT INTO community_account (community_id, account_id, weight, source, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(community_id, account_id) DO UPDATE SET
               weight=excluded.weight,
               source=excluded.source,
               updated_at=excluded.updated_at""",
        (community_id, account_id, weight, source, now_utc()),
    )


def list_communities(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """SELECT c.id, c.name, c.color, c.description,
                  c.seeded_from_run, c.seeded_from_idx,
                  COUNT(ca.account_id) as member_count,
                  c.created_at, c.updated_at
           FROM community c
           LEFT JOIN community_account ca ON ca.community_id = c.id
           GROUP BY c.id
           ORDER BY member_count DESC"""
    ).fetchall()


def get_community_members(
    conn: sqlite3.Connection,
    community_id: str,
    min_weight: float = 0.0,
) -> list:
    return conn.execute(
        """SELECT ca.account_id, p.username, ca.weight, ca.source, p.bio
           FROM community_account ca
           LEFT JOIN profiles p ON p.account_id = ca.account_id
           WHERE ca.community_id = ? AND ca.weight >= ?
           ORDER BY ca.weight DESC""",
        (community_id, min_weight),
    ).fetchall()


def get_account_communities(conn: sqlite3.Connection, account_id: str) -> list:
    """Return all community memberships for an account (Layer 2 view)."""
    return conn.execute(
        """SELECT c.id, c.name, c.color, ca.weight, ca.source
           FROM community_account ca
           JOIN community c ON c.id = ca.community_id
           WHERE ca.account_id = ?
           ORDER BY ca.weight DESC""",
        (account_id,),
    ).fetchall()


def get_account_communities_canonical(conn: sqlite3.Connection, account_id: str) -> list:
    """Return communities for an account with human-overrides-nmf precedence.

    With the current PK of (community_id, account_id), each account can only
    have ONE row per community. So precedence is handled at write time —
    upsert_community_account with source='human' overwrites the source='nmf' row.
    This function returns the canonical view.

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


def delete_community(conn: sqlite3.Connection, community_id: str) -> None:
    """Cascade deletes community_account rows too (FK ON DELETE CASCADE)."""
    conn.execute("DELETE FROM community WHERE id = ?", (community_id,))
    conn.commit()


def clear_seeded_communities(conn: sqlite3.Connection, run_id: str) -> int:
    """Remove Layer 2 communities that were seeded from a specific run.
    Returns the number of communities deleted."""
    result = conn.execute(
        "DELETE FROM community WHERE seeded_from_run = ?", (run_id,)
    )
    conn.commit()
    return result.rowcount


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
