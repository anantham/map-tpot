"""Tests for scripts/rollup_bits.py — bits tag parsing and aggregation."""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so we can import scripts.rollup_bits
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rollup_bits import aggregate_bits, parse_bits_tag


# ── parse_bits_tag ────────────────────────────────────────────────────────────


class TestParseBitsTag:
    def test_positive_tag(self):
        assert parse_bits_tag("bits:LLM-Whisperers:+3") == ("LLM-Whisperers", 3)

    def test_negative_tag(self):
        assert parse_bits_tag("bits:Qualia-Research:-2") == ("Qualia-Research", -2)

    def test_zero_bits(self):
        assert parse_bits_tag("bits:highbies:+0") == ("highbies", 0)

    def test_malformed_no_prefix(self):
        assert parse_bits_tag("LLM-Whisperers:+3") is None

    def test_malformed_missing_value(self):
        assert parse_bits_tag("bits:LLM-Whisperers") is None

    def test_malformed_non_numeric(self):
        assert parse_bits_tag("bits:LLM-Whisperers:abc") is None

    def test_extra_colons(self):
        assert parse_bits_tag("bits:AI-Safety:+1:extra") is None

    def test_empty_string(self):
        assert parse_bits_tag("") is None

    def test_wrong_prefix(self):
        assert parse_bits_tag("domain:AI-Safety:+1") is None

    def test_bare_number_without_sign(self):
        """Tags like bits:X:3 (no +/-) should still parse — int('3') works."""
        assert parse_bits_tag("bits:highbies:3") == ("highbies", 3)


# ── aggregate_bits ────────────────────────────────────────────────────────────


class TestAggregateBits:
    """Test the aggregation logic that converts (account, tweet, tag) triples
    into per-(account, community) rollup dicts."""

    SHORT_TO_ID = {
        "LLM-Whisperers": "comm-llm",
        "Qualia-Research": "comm-qualia",
        "AI-Safety": "comm-ai",
    }

    def test_basic_aggregation_same_community(self):
        """Two tags for same community on different tweets → sum bits, tweet_count=2."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:LLM-Whisperers:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        key = ("acct1", "comm-llm")
        assert key in result
        assert result[key]["total_bits"] == 5
        assert result[key]["tweet_count"] == 2
        assert result[key]["pct"] == 100.0  # only community for this account

    def test_negative_bits_subtract(self):
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:LLM-Whisperers:-1"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert result[("acct1", "comm-llm")]["total_bits"] == 2

    def test_unknown_community_skipped(self):
        tags = [
            ("acct1", "tweet1", "bits:Unknown-Comm:+5"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert len(result) == 0

    def test_pct_calculation(self):
        """30/70 split: abs(3)/(abs(3)+abs(7)) = 30%, abs(7)/(abs(3)+abs(7)) = 70%."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:Qualia-Research:+7"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert abs(result[("acct1", "comm-llm")]["pct"] - 30.0) < 0.01
        assert abs(result[("acct1", "comm-qualia")]["pct"] - 70.0) < 0.01

    def test_pct_with_negative_bits(self):
        """pct uses abs(total_bits) — negative communities still get proportional share."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+6"),
            ("acct1", "tweet2", "bits:Qualia-Research:-4"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        # abs(6) + abs(-4) = 10
        assert abs(result[("acct1", "comm-llm")]["pct"] - 60.0) < 0.01
        assert abs(result[("acct1", "comm-qualia")]["pct"] - 40.0) < 0.01

    def test_multiple_accounts_separate(self):
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct2", "tweet2", "bits:LLM-Whisperers:+5"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert result[("acct1", "comm-llm")]["total_bits"] == 3
        assert result[("acct2", "comm-llm")]["total_bits"] == 5
        # Each is 100% for their single-community account
        assert result[("acct1", "comm-llm")]["pct"] == 100.0
        assert result[("acct2", "comm-llm")]["pct"] == 100.0

    def test_same_tweet_same_community_multiple_tags_tweet_count_1(self):
        """Multiple bits tags for same (tweet, community) → tweet_count still 1."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet1", "bits:LLM-Whisperers:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == 5
        assert result[key]["tweet_count"] == 1  # same tweet, same community

    def test_same_tweet_different_communities(self):
        """One tweet with tags for two communities → each community gets tweet_count=1."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet1", "bits:Qualia-Research:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert result[("acct1", "comm-llm")]["tweet_count"] == 1
        assert result[("acct1", "comm-qualia")]["tweet_count"] == 1

    def test_malformed_tags_skipped(self):
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "not-a-bits-tag"),
            ("acct1", "tweet3", "bits:LLM-Whisperers:abc"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        # Only the first valid tag contributes
        assert result[("acct1", "comm-llm")]["total_bits"] == 3
        assert result[("acct1", "comm-llm")]["tweet_count"] == 1

    def test_empty_input(self):
        result = aggregate_bits([], self.SHORT_TO_ID)
        assert result == {}

    def test_case_insensitive_short_name_lookup(self):
        """Tags may be lowercased by the tag system; lookup should be case-insensitive."""
        tags = [
            ("acct1", "tweet1", "bits:llm-whisperers:+3"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert ("acct1", "comm-llm") in result
        assert result[("acct1", "comm-llm")]["total_bits"] == 3


# ── DB integration tests for rollup_bits.py ──────────────────────────────────

import sqlite3
from datetime import datetime, timezone

from rollup_bits import load_bits_tags, load_short_to_id, write_rollup


def _create_fixture_db():
    """Create an in-memory SQLite DB with realistic fixture data.

    Communities:
        comm-llm  (short_name='llm-whisperers')
        comm-qual (short_name='qualia-research')

    Accounts / tweets:
        acct-A: tweet-A1, tweet-A2, tweet-A3  (3 tweets)
        acct-B: tweet-B1, tweet-B2             (2 tweets)

    Tags (all category='bits'):
        tweet-A1: bits:llm-whisperers:+3
        tweet-A1: bits:llm-whisperers:+2   (duplicate tweet, same community — tests dedup)
        tweet-A2: bits:qualia-research:+4
        tweet-A3: bits:llm-whisperers:-1   (negative)
        tweet-B1: bits:qualia-research:+5
        tweet-B2: bits:llm-whisperers:+2

    Expected rollup (manual calculation):
        acct-A / comm-llm:  total_bits = +3 +2 -1 = 4, tweets={A1, A3} → tweet_count=2
        acct-A / comm-qual:  total_bits = +4,           tweets={A2}    → tweet_count=1
            acct-A abs_sum = |4| + |4| = 8
            pct: llm = 4/8*100 = 50.0, qual = 4/8*100 = 50.0

        acct-B / comm-qual:  total_bits = +5,           tweets={B1}    → tweet_count=1
        acct-B / comm-llm:   total_bits = +2,           tweets={B2}    → tweet_count=1
            acct-B abs_sum = |5| + |2| = 7
            pct: qual = 5/7*100 ≈ 71.429, llm = 2/7*100 ≈ 28.571
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()

    conn.executescript("""
        CREATE TABLE community (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            short_name      TEXT,
            description     TEXT,
            color           TEXT,
            seeded_from_run TEXT,
            seeded_from_idx INTEGER,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE tweets (
            tweet_id          TEXT PRIMARY KEY,
            account_id        TEXT NOT NULL,
            username          TEXT NOT NULL,
            full_text         TEXT NOT NULL,
            created_at        TEXT,
            reply_to_tweet_id TEXT,
            reply_to_username TEXT,
            favorite_count    INTEGER DEFAULT 0,
            retweet_count     INTEGER DEFAULT 0,
            lang              TEXT,
            is_note_tweet     INTEGER DEFAULT 0,
            fetched_at        TEXT
        );

        CREATE TABLE tweet_tags (
            tweet_id   TEXT NOT NULL,
            tag        TEXT NOT NULL,
            category   TEXT,
            added_by   TEXT NOT NULL DEFAULT 'human',
            created_at TEXT NOT NULL,
            PRIMARY KEY (tweet_id, tag)
        );

        CREATE TABLE account_community_bits (
            account_id   TEXT NOT NULL,
            community_id TEXT NOT NULL,
            total_bits   INTEGER NOT NULL DEFAULT 0,
            tweet_count  INTEGER NOT NULL DEFAULT 0,
            pct          REAL NOT NULL DEFAULT 0.0,
            updated_at   TEXT NOT NULL,
            PRIMARY KEY (account_id, community_id),
            FOREIGN KEY (community_id) REFERENCES community(id)
        );
    """)

    # Communities
    conn.execute(
        "INSERT INTO community (id, name, short_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("comm-llm", "LLM Whisperers", "llm-whisperers", now, now),
    )
    conn.execute(
        "INSERT INTO community (id, name, short_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("comm-qual", "Qualia Research", "qualia-research", now, now),
    )

    # Tweets — acct-A (3 tweets)
    for tid, acct in [("tweet-A1", "acct-A"), ("tweet-A2", "acct-A"), ("tweet-A3", "acct-A"),
                       ("tweet-B1", "acct-B"), ("tweet-B2", "acct-B")]:
        conn.execute(
            "INSERT INTO tweets (tweet_id, account_id, username, full_text) VALUES (?, ?, ?, ?)",
            (tid, acct, acct.lower(), f"text of {tid}"),
        )

    # Bits tags
    tag_rows = [
        ("tweet-A1", "bits:llm-whisperers:+3",    "bits", now),
        ("tweet-A1", "bits:llm-whisperers:+2",     None, now),  # dup tweet/community — BUT unique tag text
        # Note: tweet_tags PK is (tweet_id, tag), so "+3" and "+2" are different tags.
        ("tweet-A2", "bits:qualia-research:+4",    "bits", now),
        ("tweet-A3", "bits:llm-whisperers:-1",     "bits", now),
        ("tweet-B1", "bits:qualia-research:+5",    "bits", now),
        ("tweet-B2", "bits:llm-whisperers:+2",    "bits", now),
    ]
    conn.executemany(
        "INSERT INTO tweet_tags (tweet_id, tag, category, created_at) VALUES (?, ?, ?, ?)",
        tag_rows,
    )

    conn.commit()
    return conn


# Expected values from manual calculation (see _create_fixture_db docstring).
# Note: tweet-A1 has TWO bits tags for llm-whisperers (+3 and +2). However,
# load_bits_tags filters WHERE category = 'bits'. The second tag has category=NULL,
# so it will NOT be loaded. Therefore:
#   acct-A / comm-llm: +3 (from A1) + -1 (from A3) = 2, tweets={A1, A3}, count=2
#   acct-A / comm-qual: +4 (from A2), tweets={A2}, count=1
#   acct-A abs_sum = |2| + |4| = 6
#   pct: llm = 2/6*100 ≈ 33.333, qual = 4/6*100 ≈ 66.667
#
#   acct-B / comm-qual: +5 (from B1), tweets={B1}, count=1
#   acct-B / comm-llm:  +2 (from B2), tweets={B2}, count=1
#   acct-B abs_sum = |5| + |2| = 7
#   pct: qual = 5/7*100 ≈ 71.429, llm = 2/7*100 ≈ 28.571

EXPECTED = {
    ("acct-A", "comm-llm"):  {"total_bits": 2, "tweet_count": 2, "pct": 2 / 6 * 100},
    ("acct-A", "comm-qual"): {"total_bits": 4, "tweet_count": 1, "pct": 4 / 6 * 100},
    ("acct-B", "comm-qual"): {"total_bits": 5, "tweet_count": 1, "pct": 5 / 7 * 100},
    ("acct-B", "comm-llm"):  {"total_bits": 2, "tweet_count": 1, "pct": 2 / 7 * 100},
}


def _run_full_rollup(conn, dry_run=False):
    """Run the full rollup pipeline against the given connection."""
    short_to_id = load_short_to_id(conn)
    tags = load_bits_tags(conn)
    rollup = aggregate_bits(tags, short_to_id)
    count = write_rollup(conn, rollup, dry_run=dry_run)
    return rollup, count


class TestRollupBitsDB:
    """Integration tests: rollup_bits functions against a real in-memory SQLite DB."""

    def test_dry_run_does_not_write(self):
        """dry_run=True computes the rollup but leaves account_community_bits empty."""
        conn = _create_fixture_db()
        _run_full_rollup(conn, dry_run=True)

        rows = conn.execute("SELECT COUNT(*) FROM account_community_bits").fetchone()[0]
        assert rows == 0, f"Expected 0 rows after dry run, got {rows}"
        conn.close()

    def test_live_run_writes_correct_rows(self):
        """Live rollup writes the expected (account_id, community_id) rows."""
        conn = _create_fixture_db()
        _run_full_rollup(conn, dry_run=False)

        rows = conn.execute(
            "SELECT account_id, community_id, total_bits, pct FROM account_community_bits"
        ).fetchall()
        db_keys = {(r["account_id"], r["community_id"]) for r in rows}

        assert db_keys == set(EXPECTED.keys()), (
            f"Key mismatch: expected {set(EXPECTED.keys())}, got {db_keys}"
        )

        # Verify total_bits match for every row
        for r in rows:
            key = (r["account_id"], r["community_id"])
            assert r["total_bits"] == EXPECTED[key]["total_bits"], (
                f"{key}: total_bits expected {EXPECTED[key]['total_bits']}, got {r['total_bits']}"
            )
        conn.close()

    def test_live_run_replaces_existing(self):
        """Running rollup again replaces stale rows with fresh computation."""
        conn = _create_fixture_db()
        now = datetime.now(timezone.utc).isoformat()

        # Pre-populate with stale data
        conn.execute(
            """INSERT INTO account_community_bits
               (account_id, community_id, total_bits, tweet_count, pct, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("acct-STALE", "comm-llm", 999, 99, 100.0, now),
        )
        conn.commit()

        # Verify stale row exists
        stale_count = conn.execute(
            "SELECT COUNT(*) FROM account_community_bits WHERE account_id = 'acct-STALE'"
        ).fetchone()[0]
        assert stale_count == 1

        # Run rollup
        _run_full_rollup(conn, dry_run=False)

        # Stale row should be gone
        stale_count = conn.execute(
            "SELECT COUNT(*) FROM account_community_bits WHERE account_id = 'acct-STALE'"
        ).fetchone()[0]
        assert stale_count == 0, "Stale row should be deleted by rollup"

        # Correct rows should be present
        total_rows = conn.execute("SELECT COUNT(*) FROM account_community_bits").fetchone()[0]
        assert total_rows == len(EXPECTED)
        conn.close()

    def test_total_bits_matches_exactly(self):
        """Verify every total_bits value matches manual calculation from fixture tags."""
        conn = _create_fixture_db()
        _run_full_rollup(conn, dry_run=False)

        rows = conn.execute(
            "SELECT account_id, community_id, total_bits FROM account_community_bits"
        ).fetchall()
        for r in rows:
            key = (r["account_id"], r["community_id"])
            assert key in EXPECTED, f"Unexpected key {key} in DB"
            assert r["total_bits"] == EXPECTED[key]["total_bits"], (
                f"{key}: expected total_bits={EXPECTED[key]['total_bits']}, got {r['total_bits']}"
            )
        conn.close()

    def test_pct_within_tolerance(self):
        """Verify pct = abs(total_bits) / sum(abs(total_bits)) * 100 per account, within 0.001."""
        conn = _create_fixture_db()
        _run_full_rollup(conn, dry_run=False)

        rows = conn.execute(
            "SELECT account_id, community_id, pct FROM account_community_bits"
        ).fetchall()
        for r in rows:
            key = (r["account_id"], r["community_id"])
            expected_pct = EXPECTED[key]["pct"]
            assert abs(r["pct"] - expected_pct) < 0.001, (
                f"{key}: expected pct={expected_pct:.4f}, got {r['pct']:.4f}"
            )
        conn.close()

    def test_tweet_count_populated(self):
        """Verify tweet_count > 0 for all rows (not left as 0)."""
        conn = _create_fixture_db()
        _run_full_rollup(conn, dry_run=False)

        rows = conn.execute(
            "SELECT account_id, community_id, tweet_count FROM account_community_bits"
        ).fetchall()
        for r in rows:
            key = (r["account_id"], r["community_id"])
            assert r["tweet_count"] == EXPECTED[key]["tweet_count"], (
                f"{key}: expected tweet_count={EXPECTED[key]['tweet_count']}, got {r['tweet_count']}"
            )
            assert r["tweet_count"] > 0, f"{key}: tweet_count should be > 0"
        conn.close()


# ── Verify script integration tests ──────────────────────────────────────────

# verify_bits_rollup.main() uses argparse + sys.exit, so we invoke it by
# monkeypatching sys.argv and catching SystemExit.

import tempfile
import os

# Import verify_bits_rollup.main
sys.path.insert(0, str(ROOT / "scripts"))
from verify_bits_rollup import main as verify_main


def _create_synced_db_file():
    """Create a temporary DB file with fixture data AND a completed rollup.

    Returns the path to the temp DB (caller must clean up).
    verify_bits_rollup.main() requires a real file path (checks .exists()).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    # Build the fixture in-memory, then copy to file
    mem_conn = _create_fixture_db()
    _run_full_rollup(mem_conn, dry_run=False)

    # Copy in-memory DB to file via backup API
    file_conn = sqlite3.connect(db_path)
    mem_conn.backup(file_conn)
    file_conn.close()
    mem_conn.close()

    return db_path


class TestVerifyBitsRollup:
    """Integration tests for scripts/verify_bits_rollup.py verification logic."""

    def test_verify_passes_when_synced(self, monkeypatch):
        """When DB is synced, verify returns 0 (all checks pass)."""
        db_path = _create_synced_db_file()
        try:
            monkeypatch.setattr("sys.argv", ["verify_bits_rollup.py", "--db-path", db_path])
            with pytest.raises(SystemExit) as exc_info:
                verify_main()
            assert exc_info.value.code == 0, (
                f"verify should exit 0 when synced, got {exc_info.value.code}"
            )
        finally:
            os.unlink(db_path)

    def test_verify_detects_missing_keys(self, monkeypatch):
        """A row in account_community_bits with no matching bits tags → HARD FAILURE.

        'missing' = existing_keys - computed_keys: a key in DB that the tag scan
        can't reproduce. This signals data loss risk if we re-run the rollup.
        """
        db_path = _create_synced_db_file()
        try:
            # Insert a phantom row that has no corresponding bits tags
            conn = sqlite3.connect(db_path)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO account_community_bits
                   (account_id, community_id, total_bits, tweet_count, pct, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("acct-PHANTOM", "comm-llm", 10, 2, 100.0, now),
            )
            conn.commit()
            conn.close()

            monkeypatch.setattr("sys.argv", ["verify_bits_rollup.py", "--db-path", db_path])
            with pytest.raises(SystemExit) as exc_info:
                verify_main()
            assert exc_info.value.code == 1, (
                f"verify should exit 1 when missing keys detected, got {exc_info.value.code}"
            )
        finally:
            os.unlink(db_path)

    def test_verify_detects_total_bits_mismatch(self, monkeypatch):
        """Corrupting a total_bits value → HARD FAILURE."""
        db_path = _create_synced_db_file()
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE account_community_bits SET total_bits = 999 "
                "WHERE account_id = 'acct-A' AND community_id = 'comm-llm'"
            )
            conn.commit()
            conn.close()

            monkeypatch.setattr("sys.argv", ["verify_bits_rollup.py", "--db-path", db_path])
            with pytest.raises(SystemExit) as exc_info:
                verify_main()
            assert exc_info.value.code == 1, (
                f"verify should exit 1 on total_bits mismatch, got {exc_info.value.code}"
            )
        finally:
            os.unlink(db_path)

    def test_verify_reports_extra_keys(self, monkeypatch, capsys):
        """Adding a new bits tag without re-running rollup → verify reports extra keys (not failure)."""
        db_path = _create_synced_db_file()
        try:
            # Add a new bits tag that will create an extra computed key
            conn = sqlite3.connect(db_path)
            now = datetime.now(timezone.utc).isoformat()
            # Add a new tweet for a new account
            conn.execute(
                "INSERT INTO tweets (tweet_id, account_id, username, full_text) VALUES (?, ?, ?, ?)",
                ("tweet-C1", "acct-C", "acct-c", "text of tweet-C1"),
            )
            conn.execute(
                "INSERT INTO tweet_tags (tweet_id, tag, category, created_at) VALUES (?, ?, ?, ?)",
                ("tweet-C1", "bits:llm-whisperers:+7", "bits", now),
            )
            conn.commit()
            conn.close()

            monkeypatch.setattr("sys.argv", ["verify_bits_rollup.py", "--db-path", db_path])
            with pytest.raises(SystemExit) as exc_info:
                verify_main()
            # Extra keys are expected improvements, not failures → exit 0
            assert exc_info.value.code == 0, (
                f"verify should exit 0 for extra keys only, got {exc_info.value.code}"
            )
            captured = capsys.readouterr()
            assert "Extra keys" in captured.out or "new rows" in captured.out.lower() or "NEW" in captured.out, (
                "Output should mention extra/new keys"
            )
        finally:
            os.unlink(db_path)
