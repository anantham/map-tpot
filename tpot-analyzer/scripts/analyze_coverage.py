"""Analyze and report edge coverage for all nodes in the shadow graph.

This script computes what percentage of each account's followers/following
we've actually captured via scraping, compared to their claimed totals.

Usage:
    python -m scripts.analyze_coverage [--min-coverage 10] [--format table|json|csv]
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine, text


@dataclass
class NodeCoverage:
    """Coverage statistics for a single node."""
    account_id: str
    username: str
    claimed_followers: Optional[int]
    claimed_following: Optional[int]
    followers_captured: int
    following_captured: int
    followers_coverage_pct: Optional[float]
    following_coverage_pct: Optional[float]
    data_source: str  # 'seed_scraped', 'archive', 'discovered'


def compute_summary_only(db_path: str) -> dict:
    """Compute coverage summary without per-node subqueries (fast path)."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    query = text(
        """
        WITH inbound_counts AS (
            SELECT target_id AS account_id, COUNT(*) AS followers_captured
            FROM shadow_edge
            WHERE direction = 'inbound'
            GROUP BY target_id
        ),
        outbound_counts AS (
            SELECT source_id AS account_id, COUNT(*) AS following_captured
            FROM shadow_edge
            WHERE direction = 'outbound'
            GROUP BY source_id
        ),
        base AS (
            SELECT
                a.account_id,
                a.username,
                a.followers_count AS claimed_followers,
                a.following_count AS claimed_following,
                COALESCE(ic.followers_captured, 0) AS followers_captured,
                COALESCE(oc.following_captured, 0) AS following_captured,
                CASE
                    WHEN EXISTS(SELECT 1 FROM scrape_run_metrics WHERE seed_account_id = a.account_id AND skipped = 0)
                        THEN 'seed_scraped'
                    WHEN EXISTS(SELECT 1 FROM account WHERE account_id = a.account_id)
                        THEN 'archive'
                    ELSE 'discovered'
                END AS data_source
            FROM shadow_account a
            LEFT JOIN inbound_counts ic ON ic.account_id = a.account_id
            LEFT JOIN outbound_counts oc ON oc.account_id = a.account_id
            WHERE a.followers_count IS NOT NULL OR a.following_count IS NOT NULL
        )
        SELECT
            data_source,
            COUNT(*) AS total_nodes,
            AVG(CASE WHEN claimed_followers > 0 THEN 100.0 * followers_captured / claimed_followers END) AS avg_follower_coverage,
            AVG(CASE WHEN claimed_following > 0 THEN 100.0 * following_captured / claimed_following END) AS avg_following_coverage,
            MAX(CASE WHEN claimed_followers > 0 THEN 100.0 * followers_captured / claimed_followers END) AS max_follower_coverage,
            MAX(CASE WHEN claimed_following > 0 THEN 100.0 * following_captured / claimed_following END) AS max_following_coverage,
            SUM(CASE WHEN claimed_followers > 0 THEN 1 ELSE 0 END) AS nodes_with_followers,
            SUM(CASE WHEN claimed_following > 0 THEN 1 ELSE 0 END) AS nodes_with_following
        FROM base
        GROUP BY data_source
        """
    )

    stats: dict = {}
    with engine.begin() as conn:
        for row in conn.execute(query):
            stats[row.data_source] = {
                "total_nodes": int(row.total_nodes),
                "avg_follower_coverage": float(row.avg_follower_coverage or 0.0),
                "avg_following_coverage": float(row.avg_following_coverage or 0.0),
                "max_follower_coverage": float(row.max_follower_coverage or 0.0),
                "max_following_coverage": float(row.max_following_coverage or 0.0),
                "nodes_with_data": {
                    "followers": int(row.nodes_with_followers or 0),
                    "following": int(row.nodes_with_following or 0),
                },
            }

    return stats


def compute_node_coverage(db_path: str) -> List[NodeCoverage]:
    """Compute edge coverage for all accounts with claimed totals."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    query = text("""
    SELECT
        a.account_id,
        a.username,
        a.followers_count as claimed_followers,
        a.following_count as claimed_following,
        -- Count outbound edges (who they follow)
        (SELECT COUNT(*)
         FROM shadow_edge
         WHERE source_id = a.account_id AND direction = 'outbound') as following_captured,
        -- Count inbound edges (who follows them)
        (SELECT COUNT(*)
         FROM shadow_edge
         WHERE target_id = a.account_id AND direction = 'inbound') as followers_captured,
        -- Calculate coverage
        CASE WHEN a.following_count > 0
             THEN ROUND(100.0 * (SELECT COUNT(*) FROM shadow_edge WHERE source_id = a.account_id AND direction = 'outbound') / a.following_count, 2)
             ELSE NULL END as following_coverage_pct,
        CASE WHEN a.followers_count > 0
             THEN ROUND(100.0 * (SELECT COUNT(*) FROM shadow_edge WHERE target_id = a.account_id AND direction = 'inbound') / a.followers_count, 2)
             ELSE NULL END as followers_coverage_pct,
        -- Determine data source
        CASE
            WHEN EXISTS(SELECT 1 FROM scrape_run_metrics WHERE seed_account_id = a.account_id AND skipped = 0)
                THEN 'seed_scraped'
            WHEN EXISTS(SELECT 1 FROM account WHERE account_id = a.account_id)
                THEN 'archive'
            ELSE 'discovered'
        END as data_source
    FROM shadow_account a
    WHERE a.followers_count IS NOT NULL OR a.following_count IS NOT NULL
    ORDER BY
        CASE data_source
            WHEN 'archive' THEN 1
            WHEN 'seed_scraped' THEN 2
            ELSE 3
        END,
        followers_coverage_pct DESC NULLS LAST
    """)

    results = []
    with engine.begin() as conn:
        for row in conn.execute(query):
            results.append(NodeCoverage(
                account_id=row.account_id,
                username=row.username,
                claimed_followers=row.claimed_followers,
                claimed_following=row.claimed_following,
                followers_captured=row.followers_captured,
                following_captured=row.following_captured,
                followers_coverage_pct=row.followers_coverage_pct,
                following_coverage_pct=row.following_coverage_pct,
                data_source=row.data_source,
            ))

    return results


def compute_summary_stats(nodes: List[NodeCoverage]) -> dict:
    """Compute summary statistics across all nodes."""
    by_source = {}

    for source in ['archive', 'seed_scraped', 'discovered']:
        source_nodes = [n for n in nodes if n.data_source == source]
        if not source_nodes:
            continue

        follower_coverages = [n.followers_coverage_pct for n in source_nodes if n.followers_coverage_pct is not None]
        following_coverages = [n.following_coverage_pct for n in source_nodes if n.following_coverage_pct is not None]

        by_source[source] = {
            'total_nodes': len(source_nodes),
            'avg_follower_coverage': sum(follower_coverages) / len(follower_coverages) if follower_coverages else 0,
            'avg_following_coverage': sum(following_coverages) / len(following_coverages) if following_coverages else 0,
            'max_follower_coverage': max(follower_coverages) if follower_coverages else 0,
            'max_following_coverage': max(following_coverages) if following_coverages else 0,
            'nodes_with_data': {
                'followers': len(follower_coverages),
                'following': len(following_coverages),
            }
        }

    return by_source


def print_table(nodes: List[NodeCoverage], min_coverage: Optional[float] = None) -> None:
    """Print coverage data as a formatted table."""
    # Filter by minimum coverage if specified
    if min_coverage is not None:
        nodes = [n for n in nodes if
                 (n.followers_coverage_pct and n.followers_coverage_pct >= min_coverage) or
                 (n.following_coverage_pct and n.following_coverage_pct >= min_coverage)]

    print("\nNode Coverage Report")
    print("=" * 120)
    print(f"{'Username':<20} {'Source':<15} {'Followers':<25} {'Following':<25}")
    print(f"{'':20} {'':15} {'Captured/Claimed (%)':25} {'Captured/Claimed (%)':25}")
    print("-" * 120)

    for node in nodes:
        followers_str = f"{node.followers_captured}/{node.claimed_followers or '?'}"
        if node.followers_coverage_pct is not None:
            followers_str += f" ({node.followers_coverage_pct:.1f}%)"
        else:
            followers_str += " (—)"

        following_str = f"{node.following_captured}/{node.claimed_following or '?'}"
        if node.following_coverage_pct is not None:
            following_str += f" ({node.following_coverage_pct:.1f}%)"
        else:
            following_str += " (—)"

        print(f"{node.username:<20} {node.data_source:<15} {followers_str:<25} {following_str:<25}")

    print("-" * 120)
    print(f"Total nodes: {len(nodes)}")


def print_summary(stats: dict) -> None:
    """Print summary statistics."""
    print("\nSummary Statistics")
    print("=" * 80)

    for source, data in stats.items():
        print(f"\n{source.upper()}:")
        print(f"  Total nodes: {data['total_nodes']}")
        print(f"  Avg follower coverage: {data['avg_follower_coverage']:.2f}%")
        print(f"  Avg following coverage: {data['avg_following_coverage']:.2f}%")
        print(f"  Max follower coverage: {data['max_follower_coverage']:.2f}%")
        print(f"  Max following coverage: {data['max_following_coverage']:.2f}%")
        print(f"  Nodes with follower data: {data['nodes_with_data']['followers']}")
        print(f"  Nodes with following data: {data['nodes_with_data']['following']}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze edge coverage for all nodes in the shadow graph"
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        help="Only show nodes with at least this coverage percentage (0-100)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/cache.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only show summary statistics, not per-node details",
    )

    args = parser.parse_args()

    # Compute coverage
    if args.summary_only:
        stats = compute_summary_only(args.db_path)
        if not stats:
            print("No nodes with claimed follower/following counts found.", file=sys.stderr)
            sys.exit(1)
        nodes: List[NodeCoverage] = []
    else:
        nodes = compute_node_coverage(args.db_path)
        if not nodes:
            print("No nodes with claimed follower/following counts found.", file=sys.stderr)
            sys.exit(1)
        stats = compute_summary_stats(nodes)

    # Output based on format
    if args.format == "table":
        if not args.summary_only:
            print_table(nodes, min_coverage=args.min_coverage)
        print_summary(stats)

    elif args.format == "json":
        output = {
            'nodes': [
                {
                    'account_id': n.account_id,
                    'username': n.username,
                    'claimed_followers': n.claimed_followers,
                    'claimed_following': n.claimed_following,
                    'followers_captured': n.followers_captured,
                    'following_captured': n.following_captured,
                    'followers_coverage_pct': n.followers_coverage_pct,
                    'following_coverage_pct': n.following_coverage_pct,
                    'data_source': n.data_source,
                }
                for n in nodes
                if args.min_coverage is None or
                   (n.followers_coverage_pct and n.followers_coverage_pct >= args.min_coverage) or
                   (n.following_coverage_pct and n.following_coverage_pct >= args.min_coverage)
            ],
            'summary': stats,
        }
        print(json.dumps(output, indent=2))

    elif args.format == "csv":
        print("account_id,username,data_source,claimed_followers,claimed_following,"
              "followers_captured,following_captured,followers_coverage_pct,following_coverage_pct")
        for n in nodes:
            if args.min_coverage is None or \
               (n.followers_coverage_pct and n.followers_coverage_pct >= args.min_coverage) or \
               (n.following_coverage_pct and n.following_coverage_pct >= args.min_coverage):
                print(f"{n.account_id},{n.username},{n.data_source},"
                      f"{n.claimed_followers or ''},{n.claimed_following or ''},"
                      f"{n.followers_captured},{n.following_captured},"
                      f"{n.followers_coverage_pct or ''},{n.following_coverage_pct or ''}")


if __name__ == "__main__":
    main()
