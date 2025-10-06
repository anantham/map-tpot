"""Check database quality without using X API.

Identifies potential data quality issues:
- Accounts with NULL followers/following counts
- Shadow IDs (never resolved via API)
- Accounts with 0 followers or following (suspicious)
- Accounts with no edge data captured
- Data age analysis

Usage:
    python -m scripts.check_db_quality [--show-all]
"""
import argparse
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check database quality without API calls"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/cache.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all accounts with issues (not just summary)",
    )
    return parser.parse_args()


def check_database_quality(db_path: str, show_all: bool):
    """Analyze database for data quality issues."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    print("=" * 80)
    print("DATABASE QUALITY REPORT")
    print("=" * 80)
    print()

    with engine.begin() as conn:
        # Total accounts
        total = conn.execute(text("SELECT COUNT(*) FROM shadow_account")).fetchone()[0]
        print(f"Total accounts: {total:,}")
        print()

        # 1. NULL count analysis
        print("1. INCOMPLETE METADATA (NULL counts)")
        print("-" * 80)
        null_followers = conn.execute(
            text("SELECT COUNT(*) FROM shadow_account WHERE followers_count IS NULL")
        ).fetchone()[0]
        null_following = conn.execute(
            text("SELECT COUNT(*) FROM shadow_account WHERE following_count IS NULL")
        ).fetchone()[0]
        null_both = conn.execute(
            text("""
                SELECT COUNT(*) FROM shadow_account
                WHERE followers_count IS NULL AND following_count IS NULL
            """)
        ).fetchone()[0]

        print(f"  NULL followers_count: {null_followers:,} ({null_followers/total*100:.1f}%)")
        print(f"  NULL following_count: {null_following:,} ({null_following/total*100:.1f}%)")
        print(f"  NULL both counts: {null_both:,} ({null_both/total*100:.1f}%)")

        if show_all and null_both > 0:
            print("\n  Examples:")
            rows = conn.execute(text("""
                SELECT username, account_id, source_channel, fetched_at
                FROM shadow_account
                WHERE followers_count IS NULL AND following_count IS NULL
                LIMIT 10
            """)).fetchall()
            for row in rows:
                print(f"    @{row.username or '(no username)'} | {row.account_id} | {row.source_channel}")
        print()

        # 2. Shadow ID analysis
        print("2. UNRESOLVED SHADOW IDs")
        print("-" * 80)
        shadow_ids = conn.execute(
            text("SELECT COUNT(*) FROM shadow_account WHERE account_id LIKE 'shadow:%'")
        ).fetchone()[0]
        print(f"  Shadow IDs: {shadow_ids:,} ({shadow_ids/total*100:.1f}%)")

        if show_all and shadow_ids > 0:
            print("\n  Examples:")
            rows = conn.execute(text("""
                SELECT username, account_id, followers_count, following_count
                FROM shadow_account
                WHERE account_id LIKE 'shadow:%'
                LIMIT 10
            """)).fetchall()
            for row in rows:
                print(f"    @{row.username} | followers={row.followers_count}, following={row.following_count}")
        print()

        # 3. Zero counts (suspicious)
        print("3. SUSPICIOUS ZERO COUNTS")
        print("-" * 80)
        zero_followers = conn.execute(
            text("SELECT COUNT(*) FROM shadow_account WHERE followers_count = 0")
        ).fetchone()[0]
        zero_following = conn.execute(
            text("SELECT COUNT(*) FROM shadow_account WHERE following_count = 0")
        ).fetchone()[0]

        print(f"  0 followers: {zero_followers:,}")
        print(f"  0 following: {zero_following:,}")

        if show_all and zero_followers > 0:
            print("\n  Accounts with 0 followers:")
            rows = conn.execute(text("""
                SELECT username, account_id, following_count, source_channel
                FROM shadow_account
                WHERE followers_count = 0
                LIMIT 10
            """)).fetchall()
            for row in rows:
                print(f"    @{row.username} | following={row.following_count} | {row.source_channel}")
        print()

        # 4. Edge coverage analysis
        print("4. EDGE COVERAGE")
        print("-" * 80)

        # Accounts with no edges captured
        no_edges = conn.execute(text("""
            SELECT COUNT(*) FROM shadow_account a
            WHERE NOT EXISTS (
                SELECT 1 FROM shadow_edge e
                WHERE e.source_id = a.account_id OR e.target_id = a.account_id
            )
        """)).fetchone()[0]
        print(f"  Accounts with no edges: {no_edges:,} ({no_edges/total*100:.1f}%)")

        # Seed-scraped vs discovered
        seed_scraped = conn.execute(text("""
            SELECT COUNT(DISTINCT seed_account_id)
            FROM scrape_run_metrics
            WHERE skipped = 0
        """)).fetchone()[0]
        print(f"  Successfully seed-scraped: {seed_scraped:,}")

        discovered = conn.execute(text("""
            SELECT COUNT(DISTINCT shadow_account_id)
            FROM shadow_discovery
        """)).fetchone()[0]
        print(f"  Discovered (in others' lists): {discovered:,}")
        print()

        # 5. Data age analysis
        print("5. DATA AGE")
        print("-" * 80)

        age_stats = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                AVG(JULIANDAY('now') - JULIANDAY(fetched_at)) as avg_age,
                MIN(fetched_at) as oldest,
                MAX(fetched_at) as newest
            FROM shadow_account
            WHERE fetched_at IS NOT NULL
        """)).fetchone()

        print(f"  Average age: {age_stats.avg_age:.1f} days")
        print(f"  Oldest: {age_stats.oldest}")
        print(f"  Newest: {age_stats.newest}")

        # Age distribution
        age_ranges = conn.execute(text("""
            SELECT
                CASE
                    WHEN JULIANDAY('now') - JULIANDAY(fetched_at) <= 1 THEN '< 1 day'
                    WHEN JULIANDAY('now') - JULIANDAY(fetched_at) <= 7 THEN '1-7 days'
                    WHEN JULIANDAY('now') - JULIANDAY(fetched_at) <= 30 THEN '1-4 weeks'
                    ELSE '> 1 month'
                END as age_range,
                COUNT(*) as count
            FROM shadow_account
            WHERE fetched_at IS NOT NULL
            GROUP BY age_range
            ORDER BY
                CASE age_range
                    WHEN '< 1 day' THEN 1
                    WHEN '1-7 days' THEN 2
                    WHEN '1-4 weeks' THEN 3
                    ELSE 4
                END
        """)).fetchall()

        print("\n  Age distribution:")
        for row in age_ranges:
            print(f"    {row.age_range}: {row.count:,}")
        print()

        # 6. Source channel breakdown
        print("6. DATA SOURCES")
        print("-" * 80)
        sources = conn.execute(text("""
            SELECT source_channel, COUNT(*) as count
            FROM shadow_account
            GROUP BY source_channel
            ORDER BY count DESC
        """)).fetchall()

        for row in sources:
            print(f"  {row.source_channel}: {row.count:,} ({row.count/total*100:.1f}%)")
        print()

        # 7. Scrape metrics summary
        print("7. SCRAPE RUN SUMMARY")
        print("-" * 80)

        scrape_stats = conn.execute(text("""
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) as skipped,
                SUM(CASE WHEN error_type IS NOT NULL THEN 1 ELSE 0 END) as errors
            FROM scrape_run_metrics
        """)).fetchone()

        print(f"  Total scrape runs: {scrape_stats.total_runs:,}")
        print(f"  Successful: {scrape_stats.successful:,}")
        print(f"  Skipped: {scrape_stats.skipped:,}")
        print(f"  Errors: {scrape_stats.errors:,}")

        # Error types
        if scrape_stats.errors > 0:
            error_types = conn.execute(text("""
                SELECT error_type, COUNT(*) as count
                FROM scrape_run_metrics
                WHERE error_type IS NOT NULL
                GROUP BY error_type
                ORDER BY count DESC
            """)).fetchall()
            print("\n  Error breakdown:")
            for row in error_types:
                print(f"    {row.error_type}: {row.count:,}")
        print()

        # Quality score
        print("=" * 80)
        print("QUALITY SCORE")
        print("=" * 80)

        complete_accounts = total - null_both
        complete_pct = (complete_accounts / total * 100) if total > 0 else 0
        resolved_pct = ((total - shadow_ids) / total * 100) if total > 0 else 0
        edge_pct = ((total - no_edges) / total * 100) if total > 0 else 0

        overall_score = (complete_pct + resolved_pct + edge_pct) / 3

        print(f"Completeness (non-NULL counts): {complete_pct:.1f}%")
        print(f"Resolution (non-shadow IDs): {resolved_pct:.1f}%")
        print(f"Connectivity (has edges): {edge_pct:.1f}%")
        print(f"\nOVERALL QUALITY: {overall_score:.1f}%")


def main():
    args = parse_args()
    check_database_quality(args.db_path, args.show_all)


if __name__ == "__main__":
    main()
