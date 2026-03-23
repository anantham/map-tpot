"""Tests for scripts/rollup_bits.py — bits tag parsing and aggregation."""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so we can import scripts.rollup_bits
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rollup_bits import (
    DEFAULT_SIMULACRUM_WEIGHT,
    SIMULACRUM_WEIGHTS,
    aggregate_bits,
    get_dominant_simulacrum,
    parse_bits_tag,
    simulacrum_weight_for_tweet,
)


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

    def test_weighted_bits_equals_unweighted_when_no_weights(self):
        """Without tweet_weights, weighted_bits should equal total_bits as float."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:LLM-Whisperers:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        key = ("acct1", "comm-llm")
        assert result[key]["weighted_bits"] == 5.0
        assert result[key]["total_bits"] == 5

    def test_weighted_bits_with_l3_tweet(self):
        """L3 tweet (2.0x weight) should double the weighted bits."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
        ]
        tweet_weights = {"tweet1": SIMULACRUM_WEIGHTS["l3"]}  # 2.0
        result = aggregate_bits(tags, self.SHORT_TO_ID, tweet_weights=tweet_weights)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == 3  # unweighted preserved
        assert result[key]["weighted_bits"] == 6.0  # 3 * 2.0

    def test_weighted_bits_with_l4_tweet(self):
        """L4 tweet (0.5x weight) should halve the weighted bits."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+4"),
        ]
        tweet_weights = {"tweet1": SIMULACRUM_WEIGHTS["l4"]}  # 0.5
        result = aggregate_bits(tags, self.SHORT_TO_ID, tweet_weights=tweet_weights)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == 4
        assert result[key]["weighted_bits"] == 2.0  # 4 * 0.5

    def test_weighted_bits_mixed_levels(self):
        """Two tweets with different simulacrum levels produce correct weighted sum."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),  # L3 → 2.0x → 6.0
            ("acct1", "tweet2", "bits:LLM-Whisperers:+2"),  # L1 → 1.5x → 3.0
        ]
        tweet_weights = {
            "tweet1": SIMULACRUM_WEIGHTS["l3"],  # 2.0
            "tweet2": SIMULACRUM_WEIGHTS["l1"],  # 1.5
        }
        result = aggregate_bits(tags, self.SHORT_TO_ID, tweet_weights=tweet_weights)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == 5
        assert abs(result[key]["weighted_bits"] - 9.0) < 0.001  # 3*2.0 + 2*1.5

    def test_weighted_bits_missing_tweet_gets_default_weight(self):
        """Tweets not in tweet_weights dict get DEFAULT_SIMULACRUM_WEIGHT (1.0)."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet-unlabeled", "bits:LLM-Whisperers:+2"),
        ]
        tweet_weights = {"tweet1": 2.0}  # only tweet1 has a weight
        result = aggregate_bits(tags, self.SHORT_TO_ID, tweet_weights=tweet_weights)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == 5
        # 3*2.0 + 2*1.0 = 8.0
        assert abs(result[key]["weighted_bits"] - 8.0) < 0.001

    def test_weighted_bits_negative_tags(self):
        """Negative bits tags are also weighted correctly."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:-3"),
        ]
        tweet_weights = {"tweet1": SIMULACRUM_WEIGHTS["l3"]}  # 2.0
        result = aggregate_bits(tags, self.SHORT_TO_ID, tweet_weights=tweet_weights)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == -3
        assert result[key]["weighted_bits"] == -6.0  # -3 * 2.0


# ── get_dominant_simulacrum ──────────────────────────────────────────────────


class TestGetDominantSimulacrum:
    """Tests for dominant simulacrum level extraction from probability distributions."""

    def test_clear_dominant_l1(self):
        assert get_dominant_simulacrum({"l1": 0.8, "l2": 0.05, "l3": 0.1, "l4": 0.05}) == "l1"

    def test_clear_dominant_l3(self):
        assert get_dominant_simulacrum({"l1": 0.1, "l2": 0.1, "l3": 0.6, "l4": 0.2}) == "l3"

    def test_clear_dominant_l4(self):
        assert get_dominant_simulacrum({"l1": 0.1, "l2": 0.0, "l3": 0.2, "l4": 0.7}) == "l4"

    def test_all_zero_returns_none(self):
        """All-zero distribution has no signal → None."""
        assert get_dominant_simulacrum({"l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.0}) is None

    def test_empty_dict_returns_none(self):
        assert get_dominant_simulacrum({}) is None

    def test_tie_broken_alphabetically(self):
        """When two levels tie, the earlier one (alphabetically) wins.

        max(sorted(keys), key=f) returns the first element with the max value
        from the sorted iteration, so l1 < l3 means l1 wins the tie.
        """
        result = get_dominant_simulacrum({"l1": 0.4, "l2": 0.1, "l3": 0.4, "l4": 0.1})
        assert result == "l1"

    def test_non_normalized_distribution(self):
        """Distributions with sums != 1.0 should still work (normalize internally)."""
        # l2=1.0, l3=1.0 → normalized l2=0.5, l3=0.5 → tie → l2 wins (earlier alphabetically)
        result = get_dominant_simulacrum({"l1": 0.0, "l2": 1.0, "l3": 1.0, "l4": 0.0})
        assert result == "l2"

    def test_single_nonzero_label(self):
        """Only one label has probability → that's the dominant one."""
        assert get_dominant_simulacrum({"l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 1.0}) == "l4"


# ── simulacrum_weight_for_tweet ──────────────────────────────────────────────


class TestSimulacrumWeightForTweet:
    """Tests for computing the weight multiplier from a distribution."""

    def test_l1_dominant_weight(self):
        dist = {"l1": 0.7, "l2": 0.1, "l3": 0.1, "l4": 0.1}
        assert simulacrum_weight_for_tweet(dist) == SIMULACRUM_WEIGHTS["l1"]  # 1.5

    def test_l2_dominant_weight(self):
        dist = {"l1": 0.1, "l2": 0.7, "l3": 0.1, "l4": 0.1}
        assert simulacrum_weight_for_tweet(dist) == SIMULACRUM_WEIGHTS["l2"]  # 1.0

    def test_l3_dominant_weight(self):
        dist = {"l1": 0.1, "l2": 0.1, "l3": 0.7, "l4": 0.1}
        assert simulacrum_weight_for_tweet(dist) == SIMULACRUM_WEIGHTS["l3"]  # 2.0

    def test_l4_dominant_weight(self):
        dist = {"l1": 0.1, "l2": 0.1, "l3": 0.1, "l4": 0.7}
        assert simulacrum_weight_for_tweet(dist) == SIMULACRUM_WEIGHTS["l4"]  # 0.5

    def test_all_zero_returns_default(self):
        dist = {"l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.0}
        assert simulacrum_weight_for_tweet(dist) == DEFAULT_SIMULACRUM_WEIGHT  # 1.0

    def test_empty_returns_default(self):
        assert simulacrum_weight_for_tweet({}) == DEFAULT_SIMULACRUM_WEIGHT


# ── DB integration tests for rollup_bits.py ──────────────────────────────────

import sqlite3
from datetime import datetime, timezone

from rollup_bits import (
    load_bits_tags,
    load_short_to_id,
    load_simulacrum_weights,
    write_rollup,
)


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


# ── Simulacrum-weighted DB integration tests ─────────────────────────────────


def _add_simulacrum_tables(conn):
    """Add tweet_label_set and tweet_label_prob tables to an existing fixture DB."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tweet_label_set (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT NOT NULL,
            axis TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            note TEXT,
            context_hash TEXT,
            context_snapshot_json TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL,
            supersedes_label_set_id INTEGER,
            FOREIGN KEY(supersedes_label_set_id) REFERENCES tweet_label_set(id)
        );

        CREATE TABLE IF NOT EXISTS tweet_label_prob (
            label_set_id INTEGER NOT NULL,
            label TEXT NOT NULL CHECK (label IN ('l1','l2','l3','l4')),
            probability REAL NOT NULL CHECK (probability >= 0.0 AND probability <= 1.0),
            PRIMARY KEY (label_set_id, label),
            FOREIGN KEY(label_set_id) REFERENCES tweet_label_set(id) ON DELETE CASCADE
        );
    """)


def _create_fixture_db_with_simulacrum():
    """Create fixture DB with bits tags AND simulacrum labels.

    Simulacrum labels assigned:
        tweet-A1: L3 dominant (0.1, 0.1, 0.6, 0.2) → weight 2.0
        tweet-A2: L1 dominant (0.7, 0.1, 0.1, 0.1) → weight 1.5
        tweet-A3: L4 dominant (0.1, 0.0, 0.2, 0.7) → weight 0.5
        tweet-B1: L2 dominant (0.2, 0.5, 0.2, 0.1) → weight 1.0
        tweet-B2: (no simulacrum label)              → weight 1.0 (default)

    Bits tags (category='bits' only, same as base fixture):
        tweet-A1: bits:llm-whisperers:+3
        tweet-A2: bits:qualia-research:+4
        tweet-A3: bits:llm-whisperers:-1
        tweet-B1: bits:qualia-research:+5
        tweet-B2: bits:llm-whisperers:+2

    Weighted rollup (manual calculation):
        acct-A / comm-llm:  unweighted=+3-1=2, weighted=3*2.0+(-1)*0.5=5.5
        acct-A / comm-qual: unweighted=+4,      weighted=4*1.5=6.0
        acct-B / comm-qual: unweighted=+5,      weighted=5*1.0=5.0
        acct-B / comm-llm:  unweighted=+2,      weighted=2*1.0=2.0  (no label → default)
    """
    conn = _create_fixture_db()
    _add_simulacrum_tables(conn)

    now = datetime.now(timezone.utc).isoformat()

    # tweet-A1: L3 dominant
    conn.execute(
        "INSERT INTO tweet_label_set (tweet_id, axis, reviewer, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        ("tweet-A1", "simulacrum", "test", 1, now),
    )
    ls_a1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for label, prob in [("l1", 0.1), ("l2", 0.1), ("l3", 0.6), ("l4", 0.2)]:
        conn.execute(
            "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
            (ls_a1, label, prob),
        )

    # tweet-A2: L1 dominant
    conn.execute(
        "INSERT INTO tweet_label_set (tweet_id, axis, reviewer, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        ("tweet-A2", "simulacrum", "test", 1, now),
    )
    ls_a2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for label, prob in [("l1", 0.7), ("l2", 0.1), ("l3", 0.1), ("l4", 0.1)]:
        conn.execute(
            "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
            (ls_a2, label, prob),
        )

    # tweet-A3: L4 dominant
    conn.execute(
        "INSERT INTO tweet_label_set (tweet_id, axis, reviewer, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        ("tweet-A3", "simulacrum", "test", 1, now),
    )
    ls_a3 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for label, prob in [("l1", 0.1), ("l2", 0.0), ("l3", 0.2), ("l4", 0.7)]:
        conn.execute(
            "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
            (ls_a3, label, prob),
        )

    # tweet-B1: L2 dominant
    conn.execute(
        "INSERT INTO tweet_label_set (tweet_id, axis, reviewer, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        ("tweet-B1", "simulacrum", "test", 1, now),
    )
    ls_b1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for label, prob in [("l1", 0.2), ("l2", 0.5), ("l3", 0.2), ("l4", 0.1)]:
        conn.execute(
            "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
            (ls_b1, label, prob),
        )

    # tweet-B2: intentionally NO simulacrum label → will get default weight

    conn.commit()
    return conn


EXPECTED_WEIGHTED = {
    # acct-A / comm-llm:  +3 (A1, L3→2.0) + -1 (A3, L4→0.5) = 3*2.0 + (-1)*0.5 = 5.5
    ("acct-A", "comm-llm"):  {"total_bits": 2, "weighted_bits": 5.5},
    # acct-A / comm-qual: +4 (A2, L1→1.5) = 4*1.5 = 6.0
    ("acct-A", "comm-qual"): {"total_bits": 4, "weighted_bits": 6.0},
    # acct-B / comm-qual: +5 (B1, L2→1.0) = 5*1.0 = 5.0
    ("acct-B", "comm-qual"): {"total_bits": 5, "weighted_bits": 5.0},
    # acct-B / comm-llm:  +2 (B2, no label→1.0) = 2*1.0 = 2.0
    ("acct-B", "comm-llm"):  {"total_bits": 2, "weighted_bits": 2.0},
}


class TestSimulacrumWeightedRollup:
    """Integration tests for simulacrum-weighted bits rollup."""

    def test_load_simulacrum_weights_returns_correct_weights(self):
        """load_simulacrum_weights returns correct weight per tweet."""
        conn = _create_fixture_db_with_simulacrum()
        weights = load_simulacrum_weights(conn)

        assert weights["tweet-A1"] == SIMULACRUM_WEIGHTS["l3"]  # 2.0
        assert weights["tweet-A2"] == SIMULACRUM_WEIGHTS["l1"]  # 1.5
        assert weights["tweet-A3"] == SIMULACRUM_WEIGHTS["l4"]  # 0.5
        assert weights["tweet-B1"] == SIMULACRUM_WEIGHTS["l2"]  # 1.0
        assert "tweet-B2" not in weights  # no label → not in dict
        conn.close()

    def test_weighted_rollup_total_bits_unchanged(self):
        """Simulacrum weighting should NOT change total_bits (unweighted)."""
        conn = _create_fixture_db_with_simulacrum()
        short_to_id = load_short_to_id(conn)
        tags = load_bits_tags(conn)
        tweet_weights = load_simulacrum_weights(conn)

        rollup = aggregate_bits(tags, short_to_id, tweet_weights=tweet_weights)

        for key, expected in EXPECTED_WEIGHTED.items():
            assert key in rollup, f"Missing key {key} in rollup"
            assert rollup[key]["total_bits"] == expected["total_bits"], (
                f"{key}: total_bits expected {expected['total_bits']}, got {rollup[key]['total_bits']}"
            )
        conn.close()

    def test_weighted_rollup_weighted_bits_correct(self):
        """weighted_bits should reflect simulacrum level multipliers."""
        conn = _create_fixture_db_with_simulacrum()
        short_to_id = load_short_to_id(conn)
        tags = load_bits_tags(conn)
        tweet_weights = load_simulacrum_weights(conn)

        rollup = aggregate_bits(tags, short_to_id, tweet_weights=tweet_weights)

        for key, expected in EXPECTED_WEIGHTED.items():
            assert abs(rollup[key]["weighted_bits"] - expected["weighted_bits"]) < 0.001, (
                f"{key}: weighted_bits expected {expected['weighted_bits']}, "
                f"got {rollup[key]['weighted_bits']}"
            )
        conn.close()

    def test_weighted_rollup_shifts_community_profile(self):
        """L3 in-group tweets should amplify community membership signal.

        acct-A unweighted: llm=2, qual=4 → llm=33%, qual=67%
        acct-A weighted:   llm=5.5, qual=6.0 → llm=47.8%, qual=52.2%

        The L3 tweet on LLM-Whisperers boosted it from 33% to 48%.
        """
        conn = _create_fixture_db_with_simulacrum()
        short_to_id = load_short_to_id(conn)
        tags = load_bits_tags(conn)
        tweet_weights = load_simulacrum_weights(conn)

        rollup = aggregate_bits(tags, short_to_id, tweet_weights=tweet_weights)

        # Unweighted pct should still be based on total_bits
        assert abs(rollup[("acct-A", "comm-llm")]["pct"] - (2 / 6 * 100)) < 0.01

        # Weighted bits should show L3 amplification
        weighted_llm = rollup[("acct-A", "comm-llm")]["weighted_bits"]
        weighted_qual = rollup[("acct-A", "comm-qual")]["weighted_bits"]
        weighted_pct_llm = abs(weighted_llm) / (abs(weighted_llm) + abs(weighted_qual)) * 100
        # 5.5 / (5.5 + 6.0) * 100 ≈ 47.83%
        assert abs(weighted_pct_llm - 47.83) < 0.1

    def test_write_rollup_with_weighted_bits_column(self):
        """write_rollup with simulacrum_weighted=True should write weighted_bits to DB."""
        conn = _create_fixture_db_with_simulacrum()
        short_to_id = load_short_to_id(conn)
        tags = load_bits_tags(conn)
        tweet_weights = load_simulacrum_weights(conn)

        rollup = aggregate_bits(tags, short_to_id, tweet_weights=tweet_weights)
        write_rollup(conn, rollup, simulacrum_weighted=True)

        # Check column exists
        cols = conn.execute("PRAGMA table_info(account_community_bits)").fetchall()
        col_names = {row[1] for row in cols}
        assert "weighted_bits" in col_names

        # Check values
        rows = conn.execute(
            "SELECT account_id, community_id, total_bits, weighted_bits "
            "FROM account_community_bits"
        ).fetchall()
        for r in rows:
            key = (r["account_id"], r["community_id"])
            assert key in EXPECTED_WEIGHTED
            assert r["total_bits"] == EXPECTED_WEIGHTED[key]["total_bits"]
            assert abs(r["weighted_bits"] - EXPECTED_WEIGHTED[key]["weighted_bits"]) < 0.001
        conn.close()

    def test_write_rollup_without_weighted_does_not_add_column(self):
        """Unweighted rollup should NOT add weighted_bits column."""
        conn = _create_fixture_db_with_simulacrum()
        short_to_id = load_short_to_id(conn)
        tags = load_bits_tags(conn)

        rollup = aggregate_bits(tags, short_to_id)  # no tweet_weights
        write_rollup(conn, rollup, simulacrum_weighted=False)

        cols = conn.execute("PRAGMA table_info(account_community_bits)").fetchall()
        col_names = {row[1] for row in cols}
        assert "weighted_bits" not in col_names
        conn.close()

    def test_all_zero_simulacrum_gets_default_weight(self):
        """Tweet with all-zero simulacrum probs → default weight 1.0."""
        conn = _create_fixture_db()
        _add_simulacrum_tables(conn)
        now = datetime.now(timezone.utc).isoformat()

        # Add a label set with all zeros for tweet-A1
        conn.execute(
            "INSERT INTO tweet_label_set (tweet_id, axis, reviewer, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("tweet-A1", "simulacrum", "test", 1, now),
        )
        ls_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for label in ("l1", "l2", "l3", "l4"):
            conn.execute(
                "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
                (ls_id, label, 0.0),
            )
        conn.commit()

        weights = load_simulacrum_weights(conn)
        # All-zero → should get DEFAULT_SIMULACRUM_WEIGHT
        assert weights["tweet-A1"] == DEFAULT_SIMULACRUM_WEIGHT
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
