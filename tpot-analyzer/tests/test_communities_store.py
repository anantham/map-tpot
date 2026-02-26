"""Tests for communities.store — Layer 1 + Layer 2 persistence."""
from __future__ import annotations

import sqlite3

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
    get_ego_following_set,
    get_account_note,
    upsert_account_note,
    get_account_preview,
    create_branch,
    list_branches,
    get_active_branch,
)


@pytest.fixture
def db():
    """In-memory SQLite DB with community schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    # Create profiles stub table (referenced by get_community_members JOIN)
    conn.execute("""CREATE TABLE IF NOT EXISTS profiles (
        account_id TEXT PRIMARY KEY,
        username TEXT,
        display_name TEXT,
        bio TEXT,
        location TEXT,
        website TEXT
    )""")
    conn.commit()
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


# ── Task 1: reseed_nmf_memberships ──────────────────────────────────────

def test_reseed_preserves_human_edits(seeded_db):
    """reseed_nmf_memberships deletes nmf rows but keeps human rows."""
    reseed_nmf_memberships(seeded_db, "run-1")

    rows = seeded_db.execute(
        "SELECT account_id, source FROM community_account WHERE community_id = 'comm-B'"
    ).fetchall()
    assert ("acct_1", "human") in rows

    nmf_rows = seeded_db.execute(
        "SELECT COUNT(*) FROM community_account WHERE source = 'nmf'"
    ).fetchone()[0]
    assert nmf_rows == 0


def test_reseed_preserves_community_metadata(seeded_db):
    """reseed_nmf_memberships does NOT delete community rows."""
    reseed_nmf_memberships(seeded_db, "run-1")

    communities = seeded_db.execute("SELECT id, name FROM community").fetchall()
    names = {name for _, name in communities}
    assert "EA / forecasting" in names
    assert "Rationalist" in names


def test_reseed_returns_deleted_count(seeded_db):
    """reseed_nmf_memberships returns the number of nmf rows deleted."""
    count = reseed_nmf_memberships(seeded_db, "run-1")
    assert count == 3  # acct_1 in comm-A, acct_2 in comm-A, acct_3 in comm-B


def test_reseed_no_op_for_unknown_run(seeded_db):
    """reseed for non-existent run deletes nothing."""
    count = reseed_nmf_memberships(seeded_db, "nonexistent-run")
    assert count == 0


def test_clear_seeded_communities_still_works(seeded_db):
    """Original clear_seeded_communities still works for full wipe."""
    deleted = clear_seeded_communities(seeded_db, "run-1")
    assert deleted == 2
    assert seeded_db.execute("SELECT COUNT(*) FROM community").fetchone()[0] == 0
    assert seeded_db.execute("SELECT COUNT(*) FROM community_account").fetchone()[0] == 0


# ── get_account_communities (canonical view) ─────────────────────────────

def test_canonical_returns_all_memberships(seeded_db):
    """Returns all communities an account belongs to."""
    result = get_account_communities(seeded_db, "acct_1")
    assert len(result) == 2
    comm_ids = {r[0] for r in result}
    assert "comm-A" in comm_ids
    assert "comm-B" in comm_ids


def test_canonical_shows_correct_source(seeded_db):
    """Source field reflects what's in DB (human overwrite or nmf)."""
    result = get_account_communities(seeded_db, "acct_1")
    by_comm = {r[0]: r for r in result}
    assert by_comm["comm-A"][4] == "nmf"
    assert by_comm["comm-B"][4] == "human"
    assert by_comm["comm-B"][3] == 1.0  # weight


def test_canonical_nmf_only_account(seeded_db):
    """Account with only nmf rows returns nmf source."""
    result = get_account_communities(seeded_db, "acct_2")
    assert len(result) == 1
    assert result[0][4] == "nmf"


def test_canonical_no_memberships(seeded_db):
    """Account not in any community returns empty list."""
    result = get_account_communities(seeded_db, "nonexistent")
    assert result == []


# ── Task 3: get_ego_following_set ────────────────────────────────────────

def test_ego_following_set(db):
    """Returns set of account_ids ego follows."""
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


# ── Layer 1 basic operations ────────────────────────────────────────────

def test_save_and_list_runs(db):
    """Runs can be saved and listed."""
    save_run(db, "r1", k=14, signal="follow+rt", threshold=0.1, account_count=298, notes="test")
    runs = list_runs(db)
    assert len(runs) == 1
    assert runs[0][0] == "r1"
    assert runs[0][1] == 14


def test_save_and_get_memberships(db):
    """Memberships can be saved and retrieved."""
    save_run(db, "r1", k=2, signal="s", threshold=0.1, account_count=2)
    save_memberships(db, "r1", [("a1", 0, 0.8), ("a1", 1, 0.2)])
    rows = get_memberships(db, "r1")
    assert len(rows) == 2


def test_save_and_get_definitions(db):
    """Definitions can be saved and retrieved."""
    save_run(db, "r1", k=2, signal="s", threshold=0.1, account_count=2)
    save_definitions(db, "r1", [(0, "rt", "@user", 0.5, 0), (0, "follow", "id1", 0.3, 0)])
    rows = get_definitions(db, "r1")
    assert len(rows) == 2


# ── Layer 2 basic operations ────────────────────────────────────────────

def test_list_communities_with_counts(seeded_db):
    """list_communities returns member counts."""
    comms = list_communities(seeded_db)
    assert len(comms) == 2
    # Sorted by member_count DESC
    counts = {c[1]: c[6] for c in comms}  # name: member_count
    assert counts["EA / forecasting"] == 2
    # Rationalist has acct_3 (nmf) + acct_1 (human) = 2
    assert counts["Rationalist"] == 2


def test_get_community_members(seeded_db):
    """get_community_members returns account details."""
    members = get_community_members(seeded_db, "comm-A")
    assert len(members) == 2
    acct_ids = {m[0] for m in members}
    assert "acct_1" in acct_ids
    assert "acct_2" in acct_ids


def test_delete_community_cascades(seeded_db):
    """Deleting a community removes its account rows too."""
    delete_community(seeded_db, "comm-A")
    assert seeded_db.execute(
        "SELECT COUNT(*) FROM community_account WHERE community_id = 'comm-A'"
    ).fetchone()[0] == 0


# ── Account notes ─────────────────────────────────────────────────────

def test_account_note_upsert_and_get(db):
    """Notes can be saved and retrieved."""
    upsert_account_note(db, "acct_1", "Great forecaster")
    db.commit()
    assert get_account_note(db, "acct_1") == "Great forecaster"


def test_account_note_update(db):
    """Upserting again updates existing note."""
    upsert_account_note(db, "acct_1", "First note")
    db.commit()
    upsert_account_note(db, "acct_1", "Updated note")
    db.commit()
    assert get_account_note(db, "acct_1") == "Updated note"


def test_account_note_missing(db):
    """get_account_note returns None for unknown account."""
    assert get_account_note(db, "nobody") is None


# ── Account preview ──────────────────────────────────────────────────

@pytest.fixture
def preview_db(seeded_db):
    """DB with extra tables needed by get_account_preview."""
    seeded_db.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            bio TEXT,
            location TEXT,
            website TEXT
        );
        CREATE TABLE IF NOT EXISTS tweets (
            tweet_id TEXT PRIMARY KEY,
            account_id TEXT,
            full_text TEXT,
            created_at TEXT,
            favorite_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS likes (
            liker_account_id TEXT,
            full_text TEXT,
            expanded_url TEXT
        );
        CREATE TABLE IF NOT EXISTS retweets (
            account_id TEXT,
            rt_of_username TEXT
        );
        CREATE TABLE IF NOT EXISTS account_followers (
            account_id TEXT,
            follower_account_id TEXT,
            PRIMARY KEY (account_id, follower_account_id)
        );
        CREATE TABLE IF NOT EXISTS account_following (
            account_id TEXT,
            following_account_id TEXT,
            PRIMARY KEY (account_id, following_account_id)
        );
    """)

    # Insert profile data
    seeded_db.execute(
        "INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
        ("acct_1", "thezvi", "Zvi Mowshowitz", "EA writer", "NYC", None),
    )

    # Insert tweets for acct_1
    seeded_db.executemany(
        "INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("t1", "acct_1", "Great post about EA", "2025-01-15 10:00:00", 50, 10),
            ("t2", "acct_1", "Another take", "2025-01-14 10:00:00", 20, 5),
        ],
    )

    # Insert likes
    seeded_db.execute(
        "INSERT INTO likes VALUES (?, ?, ?)",
        ("acct_1", "I liked this tweet", "https://x.com/status/123"),
    )

    # Insert retweets
    seeded_db.executemany(
        "INSERT INTO retweets VALUES (?, ?)",
        [("acct_1", "eigenrobot"), ("acct_1", "eigenrobot"), ("acct_1", "gwern")],
    )

    # Insert follower relationships
    # acct_2 (community member) follows acct_1
    seeded_db.execute("INSERT INTO account_followers VALUES ('acct_1', 'acct_2')")
    # acct_3 (community member) follows acct_1
    seeded_db.execute("INSERT INTO account_followers VALUES ('acct_1', 'acct_3')")

    seeded_db.commit()
    return seeded_db


def test_preview_returns_all_sections(preview_db):
    """get_account_preview returns all expected keys."""
    result = get_account_preview(preview_db, "acct_1")
    assert result["account_id"] == "acct_1"
    assert result["profile"]["username"] == "thezvi"
    assert len(result["communities"]) == 2
    assert len(result["recent_tweets"]) == 2
    assert len(result["top_tweets"]) == 2
    assert len(result["liked_tweets"]) == 1
    assert len(result["top_rt_targets"]) == 2
    assert result["tpot_score"] == 2  # acct_2 and acct_3 are community members
    assert result["tpot_score_max"] > 0
    assert result["note"] is None


def test_preview_with_note(preview_db):
    """Preview includes saved curator note."""
    upsert_account_note(preview_db, "acct_1", "Key community member")
    preview_db.commit()
    result = get_account_preview(preview_db, "acct_1")
    assert result["note"] == "Key community member"


def test_preview_followers_you_know_with_ego(preview_db):
    """Preview with ego returns followers you know."""
    # ego follows acct_2 and acct_3
    preview_db.executemany(
        "INSERT OR IGNORE INTO account_following VALUES (?, ?)",
        [("ego_1", "acct_2"), ("ego_1", "acct_3")],
    )
    # acct_2 also follows acct_1 (already set up)
    preview_db.commit()

    result = get_account_preview(preview_db, "acct_1", ego_account_id="ego_1")
    assert result["followers_you_know_count"] >= 1
    fk_ids = {f["account_id"] for f in result["followers_you_know"]}
    assert "acct_2" in fk_ids


def test_preview_notable_followees(preview_db):
    """Preview returns notable followees (high-TPOT accounts they follow)."""
    # acct_1 follows acct_3 (who is a community member)
    preview_db.execute(
        "INSERT OR IGNORE INTO account_following VALUES (?, ?)",
        ("acct_1", "acct_3"),
    )
    preview_db.commit()

    result = get_account_preview(preview_db, "acct_1")
    assert len(result["notable_followees"]) >= 1
    nf_ids = {f["account_id"] for f in result["notable_followees"]}
    assert "acct_3" in nf_ids
    # Should include tpot_score
    acct3 = next(f for f in result["notable_followees"] if f["account_id"] == "acct_3")
    assert "tpot_score" in acct3


def test_preview_unknown_account(preview_db):
    """Preview for non-existent account returns empty but doesn't crash."""
    result = get_account_preview(preview_db, "nobody")
    assert result["profile"]["username"] is None
    assert result["communities"] == []
    assert result["recent_tweets"] == []
    assert result["tpot_score"] == 0


# ── Branch & snapshot schema ──────────────────────────────────────────

def test_init_db_creates_branch_tables(db):
    """init_db creates community_branch, community_snapshot, community_snapshot_data tables."""
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "community_branch" in tables
    assert "community_snapshot" in tables
    assert "community_snapshot_data" in tables
