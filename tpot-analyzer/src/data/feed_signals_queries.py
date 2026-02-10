"""Query helpers for extension feed signals."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]{2,}")
_STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "before", "being", "between",
    "but", "can", "could", "did", "does", "doing", "dont", "each", "for", "from", "had", "has",
    "have", "having", "her", "here", "hers", "him", "his", "how", "its", "just", "like", "more",
    "most", "not", "now", "our", "out", "over", "should", "some", "such", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "through", "too", "under", "until",
    "very", "was", "were", "what", "when", "where", "which", "while", "with", "would", "you", "your",
}


def window_cutoff(*, days: int) -> str:
    if days <= 0:
        raise ValueError("days must be > 0")
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _extract_keywords(texts: List[str], *, limit: int) -> List[Dict[str, int]]:
    counts: Counter[str] = Counter()
    for text in texts:
        for token in _TOKEN_RE.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            counts[token] += 1
    return [{"term": term, "count": count} for term, count in counts.most_common(limit)]


def build_account_summary(
    *,
    conn: sqlite3.Connection,
    workspace_id: str,
    ego: str,
    account_id: str,
    days: int,
    keyword_limit: int,
    sample_limit: int,
) -> Dict[str, object]:
    cutoff = window_cutoff(days=days)
    totals = conn.execute(
        """
        SELECT COUNT(*) AS impressions,
               COUNT(DISTINCT tweet_id) AS unique_tweets,
               MIN(seen_at) AS first_seen_at,
               MAX(seen_at) AS last_seen_at
        FROM feed_events
        WHERE workspace_id = ? AND ego = ? AND account_id = ? AND seen_at >= ?
        """,
        (workspace_id, ego, account_id, cutoff),
    ).fetchone()
    surface_rows = conn.execute(
        """
        SELECT surface, COUNT(*) AS c
        FROM feed_events
        WHERE workspace_id = ? AND ego = ? AND account_id = ? AND seen_at >= ?
        GROUP BY surface
        ORDER BY c DESC, surface ASC
        """,
        (workspace_id, ego, account_id, cutoff),
    ).fetchall()
    text_rows = conn.execute(
        """
        SELECT tweet_text
        FROM feed_events
        WHERE workspace_id = ? AND ego = ? AND account_id = ? AND seen_at >= ?
              AND tweet_text IS NOT NULL AND TRIM(tweet_text) != ''
        ORDER BY seen_at DESC
        LIMIT 3000
        """,
        (workspace_id, ego, account_id, cutoff),
    ).fetchall()
    sample_rows = conn.execute(
        """
        SELECT tweet_id, latest_text, last_seen_at, seen_count
        FROM feed_tweet_rollup
        WHERE workspace_id = ? AND ego = ? AND account_id = ? AND last_seen_at >= ?
        ORDER BY seen_count DESC, last_seen_at DESC
        LIMIT ?
        """,
        (workspace_id, ego, account_id, cutoff, max(1, sample_limit)),
    ).fetchall()
    texts = [str(row[0]) for row in text_rows if row and row[0]]
    return {
        "workspaceId": workspace_id,
        "ego": ego,
        "accountId": account_id,
        "lookbackDays": days,
        "impressions": int(totals[0] or 0) if totals else 0,
        "uniqueTweetsSeen": int(totals[1] or 0) if totals else 0,
        "firstSeenAt": totals[2] if totals else None,
        "lastSeenAt": totals[3] if totals else None,
        "surfaceCounts": [{"surface": row[0], "count": int(row[1])} for row in surface_rows],
        "topKeywords": _extract_keywords(texts, limit=max(1, keyword_limit)),
        "tweetSamples": [
            {
                "tweetId": row[0],
                "text": row[1],
                "lastSeenAt": row[2],
                "seenCount": int(row[3] or 0),
            }
            for row in sample_rows
        ],
    }


def build_top_exposed_accounts(
    *,
    conn: sqlite3.Connection,
    workspace_id: str,
    ego: str,
    days: int,
    limit: int,
) -> List[Dict[str, object]]:
    cutoff = window_cutoff(days=days)
    rows = conn.execute(
        """
        SELECT account_id,
               MAX(COALESCE(username, '')) AS username,
               COUNT(*) AS impressions,
               COUNT(DISTINCT tweet_id) AS unique_tweets,
               MAX(seen_at) AS last_seen_at
        FROM feed_events
        WHERE workspace_id = ? AND ego = ? AND seen_at >= ?
        GROUP BY account_id
        ORDER BY impressions DESC, unique_tweets DESC, last_seen_at DESC
        LIMIT ?
        """,
        (workspace_id, ego, cutoff, max(1, min(200, limit))),
    ).fetchall()
    return [
        {
            "accountId": row[0],
            "username": row[1] or None,
            "impressions": int(row[2] or 0),
            "uniqueTweetsSeen": int(row[3] or 0),
            "lastSeenAt": row[4],
        }
        for row in rows
    ]

