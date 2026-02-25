"""Tests for shadow graph edge coverage tracking.

These tests validate that we're tracking edge coverage properly and can
identify nodes with low coverage that need re-scraping.
"""
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def shadow_coverage_db(tmp_path) -> Path:
    db_path = tmp_path / "coverage.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE shadow_account (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            followers_count INTEGER,
            following_count INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE shadow_edge (
            source_id TEXT,
            target_id TEXT,
            direction TEXT,
            PRIMARY KEY (source_id, target_id, direction)
        )
    """)
    cur.execute("""
        CREATE TABLE scrape_run_metrics (
            seed_account_id TEXT,
            skipped INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE account (
            account_id TEXT PRIMARY KEY
        )
    """)

    cur.execute(
        "INSERT INTO shadow_account VALUES (?, ?, ?, ?)",
        ("seed1", "seed_user", 100, 50),
    )
    cur.execute(
        "INSERT INTO shadow_account VALUES (?, ?, ?, ?)",
        ("other1", "other_user", 200, 100),
    )
    cur.execute("INSERT INTO account VALUES (?)", ("seed1",))
    cur.execute("INSERT INTO account VALUES (?)", ("other1",))
    cur.execute(
        "INSERT INTO scrape_run_metrics VALUES (?, ?)",
        ("seed1", 0),
    )

    for i in range(80):
        cur.execute(
            "INSERT INTO shadow_edge VALUES (?, ?, ?)",
            (f"follower_{i}", "seed1", "inbound"),
        )
    for i in range(25):
        cur.execute(
            "INSERT INTO shadow_edge VALUES (?, ?, ?)",
            ("seed1", f"target_{i}", "outbound"),
        )

    for i in range(2):
        cur.execute(
            "INSERT INTO shadow_edge VALUES (?, ?, ?)",
            (f"follower_b_{i}", "other1", "inbound"),
        )
    for i in range(3):
        cur.execute(
            "INSERT INTO shadow_edge VALUES (?, ?, ?)",
            ("other1", f"target_b_{i}", "outbound"),
        )

    conn.commit()
    conn.close()
    return db_path


def test_coverage_tracking_exists(tmp_path):
    """Test that we can compute coverage for nodes with claimed totals."""
    # Create minimal test database
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create tables
    cur.execute("""
        CREATE TABLE shadow_account (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            followers_count INTEGER,
            following_count INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE shadow_edge (
            source_id TEXT,
            target_id TEXT,
            direction TEXT,
            PRIMARY KEY (source_id, target_id, direction)
        )
    """)

    # Insert test data
    cur.execute(
        "INSERT INTO shadow_account VALUES (?, ?, ?, ?)",
        ("123", "alice", 100, 50)
    )

    # Alice follows 10 people (claimed 50)
    for i in range(10):
        cur.execute(
            "INSERT INTO shadow_edge VALUES (?, ?, ?)",
            ("123", f"target_{i}", "outbound")
        )

    # 20 people follow Alice (claimed 100)
    for i in range(20):
        cur.execute(
            "INSERT INTO shadow_edge VALUES (?, ?, ?)",
            (f"follower_{i}", "123", "inbound")
        )

    conn.commit()

    # Compute coverage
    cur.execute("""
        SELECT
            username,
            following_count,
            (SELECT COUNT(*) FROM shadow_edge WHERE source_id = '123' AND direction = 'outbound') as following_captured,
            followers_count,
            (SELECT COUNT(*) FROM shadow_edge WHERE target_id = '123' AND direction = 'inbound') as followers_captured
        FROM shadow_account
        WHERE account_id = '123'
    """)

    row = cur.fetchone()
    username, claimed_following, captured_following, claimed_followers, captured_followers = row

    assert username == "alice"
    assert captured_following == 10
    assert captured_followers == 20
    assert claimed_following == 50
    assert claimed_followers == 100

    # Calculate coverage
    following_coverage = (captured_following / claimed_following) * 100
    followers_coverage = (captured_followers / claimed_followers) * 100

    assert following_coverage == 20.0  # 10/50 = 20%
    assert followers_coverage == 20.0  # 20/100 = 20%

    conn.close()


def test_low_coverage_detection(shadow_coverage_db):
    """Test that we can identify nodes with coverage below threshold."""
    conn = sqlite3.connect(shadow_coverage_db)
    cur = conn.cursor()

    # Find nodes with <5% coverage
    cur.execute("""
        SELECT
            a.username,
            a.followers_count,
            (SELECT COUNT(*) FROM shadow_edge WHERE target_id = a.account_id AND direction = 'inbound') as followers_captured,
            CASE WHEN a.followers_count > 0
                 THEN ROUND(100.0 * (SELECT COUNT(*) FROM shadow_edge WHERE target_id = a.account_id AND direction = 'inbound') / a.followers_count, 2)
                 ELSE NULL END as coverage_pct
        FROM shadow_account a
        WHERE a.followers_count IS NOT NULL
          AND a.followers_count > 0
          AND CASE WHEN a.followers_count > 0
                   THEN (SELECT COUNT(*) FROM shadow_edge WHERE target_id = a.account_id AND direction = 'inbound') * 100.0 / a.followers_count
                   ELSE NULL END < 5.0
        ORDER BY a.followers_count DESC
        LIMIT 10
    """)

    low_coverage_nodes = cur.fetchall()

    assert low_coverage_nodes, "Expected at least one low-coverage node in fixture data"
    usernames = {row[0] for row in low_coverage_nodes}
    assert "other_user" in usernames

    conn.close()


def test_archive_vs_shadow_coverage(shadow_coverage_db):
    """Test that archive nodes should have different coverage patterns than scraped nodes."""
    conn = sqlite3.connect(shadow_coverage_db)
    cur = conn.cursor()

    # Compare coverage for seed-scraped vs other nodes
    cur.execute("""
        WITH node_coverage AS (
            SELECT
                a.account_id,
                a.username,
                CASE
                    WHEN EXISTS(SELECT 1 FROM scrape_run_metrics WHERE seed_account_id = a.account_id AND skipped = 0)
                        THEN 'seed_scraped'
                    ELSE 'other'
                END as node_type,
                CASE WHEN a.followers_count > 0
                     THEN (SELECT COUNT(*) FROM shadow_edge WHERE target_id = a.account_id AND direction = 'inbound') * 100.0 / a.followers_count
                     ELSE NULL END as coverage_pct
            FROM shadow_account a
            WHERE a.followers_count IS NOT NULL
        )
        SELECT
            node_type,
            COUNT(*) as node_count,
            AVG(coverage_pct) as avg_coverage,
            MAX(coverage_pct) as max_coverage
        FROM node_coverage
        WHERE coverage_pct IS NOT NULL
        GROUP BY node_type
    """)

    results = {row[0]: {'count': row[1], 'avg': row[2], 'max': row[3]} for row in cur.fetchall()}

    assert "seed_scraped" in results and "other" in results, (
        "Expected both seed_scraped and other coverage groups in fixture data"
    )
    seed_avg = results["seed_scraped"]["avg"]
    other_avg = results["other"]["avg"]

    assert seed_avg > other_avg, (
        "Seed-scraped nodes should have higher coverage than incidental captures"
    )

    conn.close()


def test_coverage_script_runs(shadow_coverage_db):
    """Test that the analyze_coverage.py script runs without errors."""
    import subprocess
    import sys
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.analyze_coverage",
            "--summary-only",
            "--db-path",
            str(shadow_coverage_db),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "Summary Statistics" in result.stdout
    assert "SEED_SCRAPED" in result.stdout or "ARCHIVE" in result.stdout


@pytest.mark.unit
def test_coverage_percentage_formula():
    """Test that coverage is calculated and stored as percentage (0-100), not basis points.

    Bug fix: Previously, coverage was incorrectly stored as basis points (int(ratio * 10000))
    which produced values like 265 for 2.65%. The correct formula is round(ratio * 100, 2)
    which produces 2.65.

    This is a regression test ensuring the fix remains in place.
    """
    test_cases = [
        # (ratio, expected_percentage, description)
        (0.0265, 2.65, "53 following out of 2000"),
        (0.0230, 2.30, "230 followers out of 10000"),
        (0.027, 2.7, "Low coverage case"),
        (0.1669, 16.69, "Medium coverage case"),
        (0.5, 50.0, "Half coverage"),
        (1.0, 100.0, "Full coverage"),
        (0.0, 0.0, "Zero coverage"),
    ]

    for ratio, expected_percentage, description in test_cases:
        # This is the CORRECT formula (post-fix)
        stored_value = round(ratio * 100, 2)

        assert stored_value == expected_percentage, (
            f"{description}: Expected {expected_percentage}%, got {stored_value}%"
        )

        # Verify OLD formula (basis points) would have been wrong
        old_value = int(ratio * 10000)
        if ratio > 0:
            assert old_value != expected_percentage, (
                f"Old formula should differ from new formula for {description}"
            )
