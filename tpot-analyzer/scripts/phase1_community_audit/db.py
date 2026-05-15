"""Database helpers for the Phase 1 community-correctness audit."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Sequence


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_community_lookup(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, short_name, name, description
        FROM community
        ORDER BY short_name COLLATE NOCASE
        """
    ).fetchall()
    return {
        str(row["short_name"]): {
            "id": str(row["id"]),
            "short_name": str(row["short_name"]),
            "name": str(row["name"] or row["short_name"]),
            "description": str(row["description"] or "").strip(),
        }
        for row in rows
    }


def resolve_profile(conn: sqlite3.Connection, *, username: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT p.account_id, p.username, p.display_name, p.bio,
               upc.followers, upc.following, upc.statuses
        FROM profiles p
        LEFT JOIN user_profile_cache upc ON upc.account_id = p.account_id
        WHERE lower(p.username) = lower(?)
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Profile not found for @{username}")
    return row


def load_sample_posts(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tweet_id, created_at, full_text AS text,
               favorite_count AS like_count,
               retweet_count,
               'tweets' AS source
        FROM tweets
        WHERE account_id = ? AND trim(full_text) != ''
        ORDER BY favorite_count DESC, retweet_count DESC, created_at DESC
        LIMIT ?
        """,
        (account_id, limit),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """
            SELECT tweet_id, created_at, text,
                   like_count,
                   retweet_count,
                   'enriched_tweets' AS source
            FROM enriched_tweets
            WHERE account_id = ? AND trim(text) != ''
            ORDER BY view_count DESC, like_count DESC, retweet_count DESC, created_at DESC
            LIMIT ?
            """,
            (account_id, limit),
        ).fetchall()
    return [
        {
            "tweet_id": str(row["tweet_id"]),
            "created_at": str(row["created_at"] or ""),
            "text": str(row["text"] or "").strip(),
            "like_count": int(row["like_count"] or 0),
            "retweet_count": int(row["retweet_count"] or 0),
            "source": str(row["source"]),
        }
        for row in rows
    ]


def load_memberships(conn: sqlite3.Connection, *, account_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.short_name, c.name, ca.weight, ca.source
        FROM community_account ca
        JOIN community c ON c.id = ca.community_id
        WHERE ca.account_id = ?
        ORDER BY ca.weight DESC, c.short_name COLLATE NOCASE
        """,
        (account_id,),
    ).fetchall()
    return [
        {
            "community_short_name": str(row["short_name"]),
            "community_name": str(row["name"] or row["short_name"]),
            "weight": round(float(row["weight"] or 0.0), 4),
            "source": str(row["source"]),
        }
        for row in rows
    ]


def load_post_counts(conn: sqlite3.Connection, *, account_id: str) -> Dict[str, int]:
    tweets_n = conn.execute(
        "SELECT COUNT(*) FROM tweets WHERE account_id = ?",
        (account_id,),
    ).fetchone()[0]
    enriched_n = conn.execute(
        "SELECT COUNT(*) FROM enriched_tweets WHERE account_id = ?",
        (account_id,),
    ).fetchone()[0]
    return {"tweets": int(tweets_n or 0), "enriched_tweets": int(enriched_n or 0)}


def build_manifest_item(
    conn: sqlite3.Connection,
    community_lookup: Dict[str, Dict[str, Any]],
    spec: Dict[str, Any],
    *,
    post_limit: int = 3,
) -> Dict[str, Any]:
    profile = resolve_profile(conn, username=str(spec["username"]))
    target_short_name = str(spec["target_community_short_name"])
    if target_short_name not in community_lookup:
        raise ValueError(f"Unknown community short_name '{target_short_name}' for {spec['review_id']}")
    target = community_lookup[target_short_name]
    account_id = str(profile["account_id"])
    posts = load_sample_posts(conn, account_id=account_id, limit=post_limit)
    memberships = load_memberships(conn, account_id=account_id)
    counts = load_post_counts(conn, account_id=account_id)
    return {
        **spec,
        "account_id": account_id,
        "display_name": str(profile["display_name"] or ""),
        "bio": str(profile["bio"] or ""),
        "target_community_id": target["id"],
        "target_community_name": target["name"],
        "followers": int(profile["followers"] or 0),
        "following": int(profile["following"] or 0),
        "statuses": int(profile["statuses"] or 0),
        "local_post_counts": counts,
        "sample_posts": posts,
        "current_memberships": memberships,
        "missing_local_posts": counts["tweets"] == 0 and counts["enriched_tweets"] == 0,
    }


def count_active_labels(
    conn: sqlite3.Connection,
    *,
    reviewer: str,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM account_community_gold_label_set
        WHERE reviewer = ? AND is_active = 1
        """,
        (reviewer,),
    ).fetchone()
    return int(row[0] or 0)


def list_active_label_breakdown(
    conn: sqlite3.Connection,
    *,
    reviewer: str,
) -> Sequence[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.short_name, ls.judgment, COUNT(*) AS n
        FROM account_community_gold_label_set ls
        JOIN community c ON c.id = ls.community_id
        WHERE ls.reviewer = ? AND ls.is_active = 1
        GROUP BY c.short_name, ls.judgment
        ORDER BY c.short_name COLLATE NOCASE, ls.judgment
        """,
        (reviewer,),
    ).fetchall()

