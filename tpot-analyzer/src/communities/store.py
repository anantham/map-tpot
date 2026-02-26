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

Commit contract:
  - Layer 1 bulk writers (save_run, save_memberships, save_definitions) commit
    internally because they're called from scripts that expect atomic writes.
  - Layer 2 single-row writers (upsert_community, upsert_community_account) do
    NOT commit — callers must conn.commit() after batching multiple writes.
  - Destructive operations (delete_community, clear_seeded_communities,
    reseed_nmf_memberships) commit internally for safety.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


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

CREATE TABLE IF NOT EXISTS account_note (
    account_id TEXT PRIMARY KEY,
    note       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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
    """Insert or update a community row. Does NOT commit — caller must commit."""
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
    """Insert or update an account→community assignment. Does NOT commit — caller must commit."""
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
    """Return canonical community memberships for an account.

    Human-overrides-NMF precedence is handled at write time: upsert_community_account
    with source='human' overwrites any existing source='nmf' row (PK is
    (community_id, account_id)). So this query always returns the canonical view.

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
    """Remove Layer 2 communities seeded from a specific run. Commits internally.

    WARNING: This deletes community rows AND all associated community_account
    rows (via ON DELETE CASCADE), including source='human' edits. For safe
    re-seeding that preserves human edits, use reseed_nmf_memberships() instead.

    Returns the number of communities deleted.
    """
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


# ── Account notes ─────────────────────────────────────────────────────────────

def get_account_note(conn: sqlite3.Connection, account_id: str) -> Optional[str]:
    """Return the curator's note for an account, or None."""
    row = conn.execute(
        "SELECT note FROM account_note WHERE account_id = ?", (account_id,)
    ).fetchone()
    return row[0] if row else None


def upsert_account_note(conn: sqlite3.Connection, account_id: str, note: str) -> None:
    """Save or update the curator's note. Does NOT commit — caller must commit."""
    conn.execute(
        """INSERT INTO account_note (account_id, note, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(account_id) DO UPDATE SET
               note=excluded.note, updated_at=excluded.updated_at""",
        (account_id, note, now_utc()),
    )


# ── Account preview data ─────────────────────────────────────────────────────

def get_account_preview(
    conn: sqlite3.Connection,
    account_id: str,
    ego_account_id: Optional[str] = None,
) -> dict:
    """Assemble rich preview data for a single account.

    Returns dict with keys: profile, communities, mutual_follows, recent_tweets,
    top_tweets, liked_tweets, top_rt_targets, tpot_score, note.
    Does not commit.
    """
    # Profile
    profile = conn.execute(
        "SELECT username, display_name, bio, location, website FROM profiles WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    profile_dict = {
        "username": profile[0] if profile else None,
        "display_name": profile[1] if profile else None,
        "bio": profile[2] if profile else None,
        "location": profile[3] if profile else None,
        "website": profile[4] if profile else None,
    }

    # Community weights
    communities = []
    for cid, name, color, weight, source in get_account_communities(conn, account_id):
        communities.append({
            "community_id": cid, "name": name, "color": color,
            "weight": weight, "source": source,
        })

    # Followers you know: people you (ego) follow who also follow this account
    followers_you_know = []
    if ego_account_id:
        rows = conn.execute(
            """SELECT af.follower_account_id, p.username, p.bio
               FROM account_followers af
               JOIN account_following ego_f
                   ON ego_f.following_account_id = af.follower_account_id
                   AND ego_f.account_id = ?
               LEFT JOIN profiles p ON p.account_id = af.follower_account_id
               WHERE af.account_id = ?
               ORDER BY p.username""",
            (ego_account_id, account_id),
        ).fetchall()
        for fid, fusername, fbio in rows:
            fk_comms = []
            for cid, cname, ccolor, cw, csrc in get_account_communities(conn, fid):
                fk_comms.append({"community_id": cid, "name": cname, "color": ccolor})
            followers_you_know.append({
                "account_id": fid, "username": fusername, "bio": fbio,
                "communities": fk_comms,
            })

    # Notable followees: high-TPOT-score accounts that this person follows
    # (accounts they follow that are also community members, ranked by in-degree)
    notable_followees = []
    followee_rows = conn.execute(
        """SELECT af.following_account_id, p.username, p.bio,
                  COUNT(DISTINCT af2.follower_account_id) as tpot_score
           FROM account_following af
           JOIN community_account ca ON ca.account_id = af.following_account_id
           LEFT JOIN profiles p ON p.account_id = af.following_account_id
           LEFT JOIN account_followers af2
               ON af2.account_id = af.following_account_id
               AND af2.follower_account_id IN (
                   SELECT DISTINCT account_id FROM community_account
               )
           WHERE af.account_id = ?
             AND af.following_account_id != ?
           GROUP BY af.following_account_id
           ORDER BY tpot_score DESC
           LIMIT 30""",
        (account_id, account_id),
    ).fetchall()
    for fid, fusername, fbio, fscore in followee_rows:
        nf_comms = []
        for cid, cname, ccolor, cw, csrc in get_account_communities(conn, fid):
            nf_comms.append({"community_id": cid, "name": cname, "color": ccolor})
        notable_followees.append({
            "account_id": fid, "username": fusername, "bio": fbio,
            "tpot_score": fscore, "communities": nf_comms,
        })

    # Recent tweets (15)
    recent_tweets = []
    for tid, text, created, fav, rt_count in conn.execute(
        """SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
           FROM tweets WHERE account_id = ?
           ORDER BY created_at DESC LIMIT 15""",
        (account_id,),
    ).fetchall():
        recent_tweets.append({
            "tweet_id": tid, "text": text, "created_at": created,
            "favorites": fav, "retweets": rt_count,
        })

    # Top liked tweets (their most popular tweets by favorites)
    top_tweets = []
    for tid, text, created, fav, rt_count in conn.execute(
        """SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
           FROM tweets WHERE account_id = ?
           ORDER BY favorite_count DESC LIMIT 10""",
        (account_id,),
    ).fetchall():
        top_tweets.append({
            "tweet_id": tid, "text": text, "created_at": created,
            "favorites": fav, "retweets": rt_count,
        })

    # Tweets they liked (sample)
    liked_tweets = []
    for text, expanded_url in conn.execute(
        """SELECT full_text, expanded_url FROM likes
           WHERE liker_account_id = ?
           ORDER BY rowid DESC LIMIT 10""",
        (account_id,),
    ).fetchall():
        liked_tweets.append({"text": text, "url": expanded_url})

    # Top RT targets
    top_rt_targets = []
    for rt_username, count in conn.execute(
        """SELECT rt_of_username, COUNT(*) as cnt
           FROM retweets WHERE account_id = ?
           GROUP BY rt_of_username ORDER BY cnt DESC LIMIT 8""",
        (account_id,),
    ).fetchall():
        top_rt_targets.append({"username": rt_username, "count": count})

    # TPOT score: in-degree within the community member subgraph
    # = how many other community members follow this account
    tpot_score = conn.execute(
        """SELECT COUNT(DISTINCT af.follower_account_id)
           FROM account_followers af
           WHERE af.account_id = ?
             AND af.follower_account_id IN (
                 SELECT DISTINCT account_id FROM community_account
             )""",
        (account_id,),
    ).fetchone()[0]

    # Total community members for context
    total_community_members = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM community_account"
    ).fetchone()[0]

    # Note
    note = get_account_note(conn, account_id)

    return {
        "account_id": account_id,
        "profile": profile_dict,
        "communities": communities,
        "followers_you_know": followers_you_know,
        "followers_you_know_count": len(followers_you_know),
        "notable_followees": notable_followees,
        "recent_tweets": recent_tweets,
        "top_tweets": top_tweets,
        "liked_tweets": liked_tweets,
        "top_rt_targets": top_rt_targets,
        "tpot_score": tpot_score,
        "tpot_score_max": total_community_members,
        "note": note,
    }


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


# ── Branch & snapshot versioning ──────────────────────────────────────────────

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
