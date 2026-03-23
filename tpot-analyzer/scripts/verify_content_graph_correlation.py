#!/usr/bin/env python3
"""
CT3 — Content-graph correlation: do NMF communities align with content topics?

For each graph community, computes the weighted-average content-topic profile
across its members, then identifies the best-matching topic.  Also checks the
reverse: which content topics have NO strong community match.

Output: a printable report suitable for pasting into handover docs.

Usage:
    .venv/bin/python3 -m scripts.verify_content_graph_correlation
    .venv/bin/python3 -m scripts.verify_content_graph_correlation --min-weight 0.05
    .venv/bin/python3 -m scripts.verify_content_graph_correlation --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"

PASS = "\u2713"
FAIL = "\u2717"

# A topic is "strongly claimed" by a community if its average weight exceeds
# this fraction.  Topics below this threshold in ALL communities are orphans.
ORPHAN_THRESHOLD = 0.08

# A community is "validated" if its top content topic has average weight above
# this level — i.e., content and graph agree on at least one strong signal.
VALIDATION_THRESHOLD = 0.10


# ── data loading ──────────────────────────────────────────────────────────


def load_topics(conn: sqlite3.Connection) -> dict[int, str]:
    """topic_idx -> top_words string."""
    return dict(
        conn.execute("SELECT topic_idx, top_words FROM content_topic").fetchall()
    )


def load_content_profiles(
    conn: sqlite3.Connection,
) -> dict[str, dict[int, float]]:
    """account_id -> {topic_idx: weight}."""
    profiles: dict[str, dict[int, float]] = defaultdict(dict)
    for aid, tidx, w in conn.execute(
        "SELECT account_id, topic_idx, weight FROM account_content_profile"
    ):
        profiles[aid][tidx] = w
    return dict(profiles)


def load_communities(
    conn: sqlite3.Connection,
) -> dict[str, tuple[str, str]]:
    """community_id -> (name, short_name)."""
    return {
        r[0]: (r[1], r[2])
        for r in conn.execute("SELECT id, name, short_name FROM community")
    }


def load_community_members(
    conn: sqlite3.Connection, min_weight: float
) -> dict[str, list[tuple[str, float]]]:
    """community_id -> [(account_id, weight)] where weight > min_weight."""
    members: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for cid, aid, w in conn.execute(
        "SELECT community_id, account_id, weight FROM community_account "
        "WHERE weight > ?",
        (min_weight,),
    ):
        members[cid].append((aid, w))
    return dict(members)


# ── computation ───────────────────────────────────────────────────────────


def compute_community_topic_profile(
    member_ids: list[str],
    content_profiles: dict[str, dict[int, float]],
    n_topics: int,
) -> np.ndarray:
    """Return array of shape (n_topics,) with mean topic weight across members."""
    weights = np.zeros((len(member_ids), n_topics))
    valid = 0
    for i, aid in enumerate(member_ids):
        profile = content_profiles.get(aid)
        if profile is None:
            continue
        for tidx, w in profile.items():
            if tidx < n_topics:
                weights[valid, tidx] = w
        valid += 1

    if valid == 0:
        return np.zeros(n_topics)
    return weights[:valid].mean(axis=0)


def build_report(
    topics: dict[int, str],
    communities: dict[str, tuple[str, str]],
    comm_members: dict[str, list[tuple[str, float]]],
    content_profiles: dict[str, dict[int, float]],
    top_n: int = 3,
) -> dict[str, Any]:
    """Build the full correlation report as a structured dict."""

    n_topics = len(topics)
    community_results: list[dict[str, Any]] = []
    topic_best_community: dict[int, tuple[str, float]] = {}  # tidx -> (comm_name, weight)

    for cid, (cname, short) in sorted(communities.items(), key=lambda x: x[1][0]):
        members = comm_members.get(cid, [])
        member_ids = [aid for aid, _ in members]
        members_with_content = [
            aid for aid in member_ids if aid in content_profiles
        ]

        avg = compute_community_topic_profile(
            member_ids, content_profiles, n_topics
        )

        ranked = sorted(enumerate(avg), key=lambda x: -x[1])
        top_topics = []
        for tidx, w in ranked[:top_n]:
            words = topics.get(tidx, "???")
            short_words = ", ".join(words.split(", ")[:4])
            top_topics.append(
                {"topic_idx": tidx, "weight": float(w), "words": short_words}
            )

            # Track which community claims each topic most strongly
            prev = topic_best_community.get(tidx)
            if prev is None or w > prev[1]:
                topic_best_community[tidx] = (cname, float(w))

        community_results.append(
            {
                "name": cname,
                "short_name": short,
                "total_members": len(members),
                "members_with_content": len(members_with_content),
                "top_topics": top_topics,
                "validated": bool(ranked[0][1] >= VALIDATION_THRESHOLD),
            }
        )

    # Orphan topics: not claimed above ORPHAN_THRESHOLD by any community
    orphan_topics = []
    for tidx in sorted(topics.keys()):
        best = topic_best_community.get(tidx)
        if best is None or best[1] < ORPHAN_THRESHOLD:
            words = ", ".join(topics[tidx].split(", ")[:6])
            orphan_topics.append(
                {
                    "topic_idx": tidx,
                    "words": words,
                    "best_community": best[0] if best else None,
                    "best_weight": best[1] if best else 0.0,
                }
            )

    validated_count = sum(1 for c in community_results if c["validated"])

    return {
        "community_results": community_results,
        "orphan_topics": orphan_topics,
        "validated_count": validated_count,
        "total_communities": len(community_results),
        "total_topics": n_topics,
        "total_content_accounts": len(content_profiles),
        "validation_threshold": VALIDATION_THRESHOLD,
        "orphan_threshold": ORPHAN_THRESHOLD,
    }


# ── display ───────────────────────────────────────────────────────────────


def print_report(report: dict[str, Any]) -> None:
    """Pretty-print the correlation report."""

    print("\n" + "=" * 65)
    print("  COMMUNITY -> CONTENT TOPIC ALIGNMENT")
    print("=" * 65)

    for c in report["community_results"]:
        n_content = c["members_with_content"]
        n_total = c["total_members"]
        tag = PASS if c["validated"] else FAIL
        print(f"\n{tag} {c['name']} ({c['short_name']})")
        print(f"    [{n_content}/{n_total} members have content profiles]")
        for t in c["top_topics"]:
            bar = "#" * int(t["weight"] * 100)
            print(f"    T{t['topic_idx']:2d}={t['weight']:5.1%}  {bar}")
            print(f"          [{t['words']}]")

    # Orphan topics
    print("\n" + "-" * 65)
    print("  ORPHAN CONTENT TOPICS (no community claims above "
          f"{report['orphan_threshold']:.0%})")
    print("-" * 65)

    if report["orphan_topics"]:
        for o in report["orphan_topics"]:
            best = o["best_community"] or "none"
            print(
                f"  T{o['topic_idx']:2d}: [{o['words']}]"
                f"  (best: {best} @ {o['best_weight']:.1%})"
            )
    else:
        print("  (none found — every topic is claimed by at least one community)")

    # Validation summary
    v = report["validated_count"]
    t = report["total_communities"]
    print("\n" + "=" * 65)
    print("  VALIDATION SUMMARY")
    print("=" * 65)
    pct = v / t * 100 if t else 0
    print(f"  {v}/{t} communities validated by content vectors ({pct:.0f}%)")
    print(f"  Threshold: top content topic weight >= {report['validation_threshold']:.0%}")
    print(f"  Content accounts: {report['total_content_accounts']}")
    print(f"  Content topics: {report['total_topics']}")

    not_validated = [c["name"] for c in report["community_results"] if not c["validated"]]
    if not_validated:
        print(f"\n  Not validated:")
        for name in not_validated:
            print(f"    {FAIL} {name}")

    print()


# ── main ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CT3: Content-graph correlation report"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=ARCHIVE_DB,
        help="Path to archive_tweets.db",
    )
    parser.add_argument(
        "--min-weight",
        type=float,
        default=0.10,
        help="Minimum community_account weight to count as member (default: 0.10)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Number of top topics to show per community (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable report",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"  {FAIL} Database not found: {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(str(args.db))

    # Verify tables exist
    required = ["content_topic", "account_content_profile", "community_account", "community"]
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing = [t for t in required if t not in existing]
    if missing:
        print(f"  {FAIL} Missing tables: {', '.join(missing)}")
        print("  Run build_content_vectors.py and cluster_soft.py first.")
        conn.close()
        sys.exit(1)

    # Load data
    topics = load_topics(conn)
    content_profiles = load_content_profiles(conn)
    communities = load_communities(conn)
    comm_members = load_community_members(conn, args.min_weight)

    conn.close()

    # Build report
    report = build_report(
        topics, communities, comm_members, content_profiles, top_n=args.top_n
    )

    # Output
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    # Exit code: 0 if majority validated, 1 otherwise
    if report["validated_count"] < report["total_communities"] // 2:
        sys.exit(1)


if __name__ == "__main__":
    main()
