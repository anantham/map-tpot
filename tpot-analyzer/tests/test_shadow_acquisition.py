"""Unit tests for src/shadow/acquisition.py.

All tests use in-memory SQLite fixtures.  No Selenium, no real DB.
"""
from __future__ import annotations

import math
import sqlite3
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.shadow.acquisition import (
    AcquisitionWeights,
    CandidateSignals,
    _boundary_signal,
    _compute_novelty,
    _fetch_entropy_boundary,
    _multiclass_entropy,
    _mmr_select,
    score_candidates,
)
from src.shadow.enricher import SeedAccount


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _community_db(memberships: list | None = None, k: int = 3) -> sqlite3.Connection:
    """Build an in-memory archive_tweets.db with a single NMF run."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE community_run (
            run_id TEXT PRIMARY KEY,
            k      INTEGER NOT NULL,
            signal TEXT NOT NULL,
            threshold REAL NOT NULL,
            account_count INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE community_membership (
            run_id        TEXT NOT NULL,
            account_id    TEXT NOT NULL,
            community_idx INTEGER NOT NULL,
            weight        REAL NOT NULL,
            PRIMARY KEY (run_id, account_id, community_idx)
        );
        CREATE TABLE community_account (
            community_id TEXT NOT NULL,
            account_id   TEXT NOT NULL,
            weight       REAL NOT NULL,
            source       TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            PRIMARY KEY (community_id, account_id)
        );
    """)
    conn.execute(
        "INSERT INTO community_run VALUES (?,?,?,?,?,?,?)",
        ("run1", k, "retweet", 0.01, 10, None, "2025-01-01T00:00:00"),
    )
    if memberships:
        for row in memberships:
            conn.execute(
                "INSERT INTO community_membership VALUES (?,?,?,?)",
                ("run1", row[0], row[1], row[2]),
            )
    conn.commit()
    return conn


def _shadow_store_mock(
    followers: dict | None = None,
    scrape_times: dict | None = None,
) -> MagicMock:
    """Return a mock ShadowStore that delegates _execute_with_retry transparently."""
    followers = followers or {}
    scrape_times = scrape_times or {}

    store = MagicMock()

    def _retry(op_name, fn):
        # Build a minimal fake engine that returns canned results
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = lambda s: conn
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        if "followers" in op_name:
            conn.execute.return_value.fetchall.return_value = [
                (aid, cnt) for aid, cnt in followers.items()
            ]
        elif "scrape_times" in op_name:
            rows = []
            for aid, secs in scrape_times.items():
                rows.append((aid, secs))
            conn.execute.return_value.fetchall.return_value = rows
        else:
            conn.execute.return_value.fetchall.return_value = []

        return fn(engine)

    store._execute_with_retry.side_effect = _retry
    return store


def _seed(account_id: str, username: str | None = None) -> SeedAccount:
    return SeedAccount(account_id=account_id, username=username or account_id)


# ---------------------------------------------------------------------------
# Test 1: entropy — uniform membership → max entropy
# ---------------------------------------------------------------------------

def test_entropy_uniform_membership():
    """K equal weights should yield maximum normalised entropy = 1.0."""
    k = 4
    weights = [0.25, 0.25, 0.25, 0.25]
    h = _multiclass_entropy(weights, k)
    assert abs(h - 1.0) < 1e-6, f"Expected 1.0, got {h}"


# ---------------------------------------------------------------------------
# Test 2: entropy — concentrated membership → near-zero entropy
# ---------------------------------------------------------------------------

def test_entropy_concentrated_membership():
    """One dominant community should yield near-zero entropy."""
    k = 4
    weights = [0.97, 0.01, 0.01, 0.01]
    h = _multiclass_entropy(weights, k)
    assert h < 0.15, f"Expected low entropy, got {h}"


# ---------------------------------------------------------------------------
# Test 3: boundary — equal top-2 → boundary = 1.0
# ---------------------------------------------------------------------------

def test_boundary_bridge_account():
    """Equally split top-2 communities → boundary = 1.0."""
    weights = [0.5, 0.5, 0.0]  # already sorted DESC
    b = _boundary_signal(weights)
    assert abs(b - 1.0) < 1e-6, f"Expected 1.0, got {b}"


# ---------------------------------------------------------------------------
# Test 4: boundary — one dominant community → boundary near 0
# ---------------------------------------------------------------------------

def test_boundary_clear_member():
    """One community dominates → boundary close to 0."""
    weights = [0.95, 0.03, 0.02]
    b = _boundary_signal(weights)
    assert b < 0.2, f"Expected near-0 boundary, got {b}"


# ---------------------------------------------------------------------------
# Test 5: novelty — identical vector to scraped → novelty ≈ 0
# ---------------------------------------------------------------------------

def test_novelty_identical_to_scraped():
    """Candidate whose vector is identical to a scraped account → novelty ≈ 0."""
    k = 3
    vec = np.array([0.6, 0.3, 0.1])
    vec = vec / np.linalg.norm(vec)

    candidate_ids = ["A"]
    candidate_vectors = {"A": vec.copy()}
    scraped_ids = ["S"]
    scraped_vectors = {"S": vec.copy()}

    result = _compute_novelty(candidate_ids, candidate_vectors, scraped_ids, scraped_vectors, k)
    assert result["A"] < 0.01, f"Expected novelty ≈ 0, got {result['A']}"


# ---------------------------------------------------------------------------
# Test 6: novelty — orthogonal vector → novelty = 1.0
# ---------------------------------------------------------------------------

def test_novelty_orthogonal_to_scraped():
    """Candidate orthogonal to scraped set → novelty = 1.0."""
    k = 3
    cand_vec = np.array([1.0, 0.0, 0.0])  # already unit-length
    scr_vec = np.array([0.0, 1.0, 0.0])

    candidate_ids = ["B"]
    candidate_vectors = {"B": cand_vec}
    scraped_ids = ["S"]
    scraped_vectors = {"S": scr_vec}

    result = _compute_novelty(candidate_ids, candidate_vectors, scraped_ids, scraped_vectors, k)
    assert abs(result["B"] - 1.0) < 1e-6, f"Expected novelty=1.0, got {result['B']}"


# ---------------------------------------------------------------------------
# Test 7: MMR — two similar + one different → MMR picks diverse one first
# ---------------------------------------------------------------------------

def test_mmr_selects_diverse():
    """Given two near-identical candidates and one different one, MMR should
    prefer the diverse one to break redundancy after the first pick."""
    k = 3

    # A and B are similar; C is different
    vec_a = np.array([1.0, 0.0, 0.0])
    vec_b = np.array([0.99, 0.1, 0.0])
    vec_b = vec_b / np.linalg.norm(vec_b)
    vec_c = np.array([0.0, 0.0, 1.0])

    seeds = [_seed("A"), _seed("B"), _seed("C")]
    # Give A the highest score, then B, then C — but C is diverse
    scores = {"A": 1.0, "B": 0.9, "C": 0.5}
    membership_vectors = {"A": vec_a, "B": vec_b, "C": vec_c}

    result = _mmr_select(seeds, scores, membership_vectors, top_k=3, lambda_mmr=0.5, k=k)
    ids = [s.account_id for s in result]

    # A should be first (highest score), C should come before B (diversity)
    assert ids[0] == "A", f"Expected A first, got {ids[0]}"
    assert ids[1] == "C", f"Expected C second (diverse), got {ids[1]}"


# ---------------------------------------------------------------------------
# Test 8: score_candidates — accounts with more uncertainty ranked higher
# ---------------------------------------------------------------------------

def test_score_candidates_returns_ordered():
    """Full pipeline: account with max uncertainty (unknown community) should
    rank above a well-understood account that is always expensive to scrape."""
    # Two candidates:
    #   "uncertain" — no community membership data (gets default entropy=1)
    #   "known"     — clear member of community 0 (low entropy)

    k = 3
    conn = _community_db(
        memberships=[
            # known is firmly in community 0
            ("known", 0, 0.95),
            ("known", 1, 0.03),
            ("known", 2, 0.02),
            # uncertain has no entry → defaults to entropy=1
        ],
        k=k,
    )
    # Add community_account rows so coverage_boost works
    conn.execute(
        "INSERT INTO community_account VALUES (?,?,?,?,?)",
        ("comm0", "known", 0.95, "nmf", "2025-01-01"),
    )
    conn.commit()

    store = _shadow_store_mock(
        followers={"uncertain": 1000, "known": 1000},
        scrape_times={"uncertain": 60, "known": 60},
    )

    seeds = [_seed("uncertain"), _seed("known")]
    result = score_candidates(
        seeds,
        shadow_store=store,
        community_conn=conn,
        run_id="run1",
        top_k=None,
        lambda_mmr=1.0,  # pure relevance, no diversity adjustment
    )

    ids = [s.account_id for s in result]
    assert ids[0] == "uncertain", (
        f"Expected 'uncertain' to rank first, got {ids}"
    )
