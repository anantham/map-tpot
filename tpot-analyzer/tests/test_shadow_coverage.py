"""Tests for shadow graph edge coverage tracking.

These tests validate that we're tracking edge coverage properly and can
identify nodes with low coverage that need re-scraping.
"""
import sqlite3
from pathlib import Path

import pytest


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


def test_low_coverage_detection():
    """Test that we can identify nodes with coverage below threshold."""
    db_path = Path("data/cache.db")
    if not db_path.exists():
        pytest.skip("Database not found")

    conn = sqlite3.connect(db_path)
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

    # We should have some nodes with low coverage
    # (This is informational, not a strict assertion)
    if low_coverage_nodes:
        print("\nNodes with <5% follower coverage (need re-scraping):")
        for username, claimed, captured, pct in low_coverage_nodes:
            print(f"  @{username}: {captured}/{claimed} ({pct}%)")

    conn.close()


def test_archive_vs_shadow_coverage():
    """Test that archive nodes should have different coverage patterns than scraped nodes."""
    db_path = Path("data/cache.db")
    if not db_path.exists():
        pytest.skip("Database not found")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if we have scrape_run_metrics table
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scrape_run_metrics'")
    if not cur.fetchone():
        pytest.skip("scrape_run_metrics table not found")

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

    # Seed-scraped nodes should have higher average coverage than others
    if 'seed_scraped' in results and 'other' in results:
        seed_avg = results['seed_scraped']['avg']
        other_avg = results['other']['avg']

        print(f"\nCoverage comparison:")
        print(f"  Seed-scraped: {seed_avg:.2f}% avg (n={results['seed_scraped']['count']})")
        print(f"  Other nodes: {other_avg:.2f}% avg (n={results['other']['count']})")

        # Seed-scraped should have better coverage
        assert seed_avg > other_avg, \
            f"Seed-scraped nodes should have higher coverage than incidental captures"

    conn.close()


def test_coverage_script_runs():
    """Test that the analyze_coverage.py script runs without errors."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "scripts.analyze_coverage", "--summary-only"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "Summary Statistics" in result.stdout
    assert "SEED_SCRAPED" in result.stdout or "ARCHIVE" in result.stdout
