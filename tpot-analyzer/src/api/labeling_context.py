"""Labeling context gatherer — enriches tweets with DB context for AI interpretation.

Queries the archive DB to build rich context for the LLM labeling prompt:
- Account profile (bits-derived or NMF community memberships)
- Engagement context (who replied/liked/RT'd + their communities)
- Similar already-labeled tweets (thematic tag overlap + their full labels)
- Community profiles (names + descriptions)
- Thematic tag glossary

All data comes from the archive DB — no external API calls needed.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "archive_tweets.db"


def _get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_account_profile(conn: sqlite3.Connection, account_id: str) -> dict:
    """Get account's community profile — bits (posterior) if available, else NMF (prior)."""
    # Try bits first
    rows = conn.execute("""
        SELECT c.short_name, c.name, acb.total_bits, acb.pct
        FROM account_community_bits acb
        JOIN community c ON c.id = acb.community_id
        WHERE acb.account_id = ?
        ORDER BY acb.total_bits DESC
    """, (account_id,)).fetchall()

    if rows:
        return {
            "source": "bits",
            "communities": [
                {"short_name": r["short_name"], "name": r["name"],
                 "bits": r["total_bits"], "pct": round(r["pct"], 1)}
                for r in rows
            ],
        }

    # Fallback to NMF
    rows = conn.execute("""
        SELECT c.short_name, c.name, ca.weight
        FROM community_account ca
        JOIN community c ON c.id = ca.community_id
        WHERE ca.account_id = ? AND ca.weight >= 0.05
        ORDER BY ca.weight DESC
    """, (account_id,)).fetchall()

    return {
        "source": "nmf",
        "communities": [
            {"short_name": r["short_name"], "name": r["name"],
             "weight": round(r["weight"], 3)}
            for r in rows
        ],
    }


def get_engagement_context(conn: sqlite3.Connection, tweet_id: str) -> dict:
    """Get TPOT engagement on a tweet — who replied/liked/RT'd and their communities."""
    result = {"replies": [], "likes": [], "retweets": []}

    # Replies from classified accounts
    replies = conn.execute("""
        SELECT t.username, t.account_id, t.full_text, t.favorite_count,
               c.short_name, ca.weight
        FROM tweets t
        LEFT JOIN community_account ca ON ca.account_id = t.account_id
        LEFT JOIN community c ON c.id = ca.community_id
            AND ca.weight = (SELECT MAX(ca2.weight) FROM community_account ca2
                             WHERE ca2.account_id = t.account_id)
        WHERE t.reply_to_tweet_id = ?
        ORDER BY t.favorite_count DESC
        LIMIT 10
    """, (tweet_id,)).fetchall()

    for r in replies:
        result["replies"].append({
            "username": r["username"],
            "text": (r["full_text"] or "")[:120],
            "likes": r["favorite_count"] or 0,
            "community": r["short_name"],
            "weight": round(r["weight"], 2) if r["weight"] else None,
        })

    # Likes from classified accounts (who liked this tweet)
    likes = conn.execute("""
        SELECT l.liker_username, l.liker_account_id,
               c.short_name, ca.weight
        FROM likes l
        LEFT JOIN community_account ca ON ca.account_id = l.liker_account_id
        LEFT JOIN community c ON c.id = ca.community_id
            AND ca.weight = (SELECT MAX(ca2.weight) FROM community_account ca2
                             WHERE ca2.account_id = l.liker_account_id)
        WHERE l.tweet_id = ?
        ORDER BY ca.weight DESC NULLS LAST
        LIMIT 15
    """, (tweet_id,)).fetchall()

    for l in likes:
        if l["short_name"]:  # Only include classified likers
            result["likes"].append({
                "username": l["liker_username"],
                "community": l["short_name"],
                "weight": round(l["weight"], 2) if l["weight"] else None,
            })

    return result


def get_similar_labeled_tweets(conn: sqlite3.Connection, tweet_id: str, limit: int = 5) -> list:
    """Find already-labeled tweets with overlapping thematic tags."""
    # Get this tweet's themes
    themes = conn.execute(
        "SELECT tag FROM tweet_tags WHERE tweet_id = ? AND category = 'thematic'",
        (tweet_id,),
    ).fetchall()

    if not themes:
        return []

    theme_list = [t["tag"] for t in themes]
    placeholders = ",".join(["?"] * len(theme_list))

    # Find tweets with overlapping themes that have been labeled
    rows = conn.execute(f"""
        SELECT tt.tweet_id, t.full_text, t.username,
               COUNT(DISTINCT tt.tag) as overlap,
               GROUP_CONCAT(DISTINCT tt.tag) as shared_themes
        FROM tweet_tags tt
        JOIN tweets t ON t.tweet_id = tt.tweet_id
        JOIN tweet_label_set tls ON tls.tweet_id = tt.tweet_id
        WHERE tt.tag IN ({placeholders})
          AND tt.category = 'thematic'
          AND tt.tweet_id != ?
        GROUP BY tt.tweet_id
        ORDER BY overlap DESC
        LIMIT ?
    """, theme_list + [tweet_id, limit]).fetchall()

    result = []
    for r in rows:
        tid = r["tweet_id"]
        # Get full labels for this tweet
        tags = conn.execute("""
            SELECT tag, category FROM tweet_tags WHERE tweet_id = ?
        """, (tid,)).fetchall()

        bits = {}
        themes_list = []
        domains = []
        postures = []
        for tag_row in tags:
            tag, cat = tag_row["tag"], tag_row["category"]
            if cat == "bits":
                parts = tag.split(":")
                if len(parts) == 3:
                    bits[parts[1]] = int(parts[2])
            elif cat == "thematic":
                themes_list.append(tag)
            elif cat == "domain":
                domains.append(tag)
            elif cat == "posture":
                postures.append(tag)

        # Get simulacrum
        sim_row = conn.execute("""
            SELECT tls.note, GROUP_CONCAT(tlp.label || ':' || tlp.probability)
            FROM tweet_label_set tls
            JOIN tweet_label_prob tlp ON tlp.label_set_id = tls.id
            WHERE tls.tweet_id = ?
            GROUP BY tls.id
            ORDER BY tls.id DESC LIMIT 1
        """, (tid,)).fetchone()

        result.append({
            "tweet_id": tid,
            "username": r["username"],
            "text": (r["full_text"] or "")[:200],
            "overlap": r["overlap"],
            "shared_themes": r["shared_themes"],
            "domains": domains,
            "themes": themes_list,
            "postures": postures,
            "bits": bits,
            "note": sim_row["note"] if sim_row else None,
        })

    return result


def get_community_profiles(conn: sqlite3.Connection) -> list:
    """Get all community names + descriptions."""
    rows = conn.execute("""
        SELECT short_name, name, description FROM community
        WHERE short_name IS NOT NULL
        ORDER BY name
    """).fetchall()
    return [{"short_name": r["short_name"], "name": r["name"],
             "description": (r["description"] or "")[:300]}
            for r in rows]


def get_thematic_glossary(conn: sqlite3.Connection) -> list:
    """Get current thematic tag vocabulary with frequencies."""
    rows = conn.execute("""
        SELECT tag, COUNT(*) as cnt
        FROM tweet_tags WHERE category = 'thematic'
        GROUP BY tag ORDER BY cnt DESC
    """).fetchall()
    return [{"tag": r["tag"], "count": r["cnt"]} for r in rows]


def gather_labeling_context(
    tweet_id: str | None = None,
    tweet_text: str | None = None,
    account_id: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """Gather all context needed for AI-assisted labeling.

    Returns a dict with all context sections that can be injected into the prompt.
    """
    conn = _get_conn(db_path)

    # Resolve tweet info if we have tweet_id
    username = None
    created_at = None
    if tweet_id:
        row = conn.execute(
            "SELECT full_text, account_id, username, created_at FROM tweets WHERE tweet_id = ?",
            (tweet_id,),
        ).fetchone()
        if row:
            tweet_text = tweet_text or row["full_text"]
            account_id = account_id or row["account_id"]
            username = row["username"]
            created_at = row["created_at"]

    # Resolve account_id from tweet if needed
    if tweet_id and not account_id:
        row = conn.execute(
            "SELECT account_id FROM tweets WHERE tweet_id = ?", (tweet_id,),
        ).fetchone()
        if row:
            account_id = row["account_id"]

    # Get account bio/display_name from profiles table if available
    account_meta = {}
    if account_id:
        profile_row = conn.execute(
            "SELECT bio, display_name FROM profiles WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if profile_row:
            account_meta = {
                "bio": profile_row["bio"],
                "display_name": profile_row["display_name"],
            }

    ctx = {
        "tweet_text": tweet_text,
        "tweet_id": tweet_id,
        "account_id": account_id,
        "username": username,
        "created_at": created_at,
        "account_meta": account_meta,
    }

    if account_id:
        ctx["account_profile"] = get_account_profile(conn, account_id)

    if tweet_id:
        ctx["engagement"] = get_engagement_context(conn, tweet_id)
        ctx["similar_tweets"] = get_similar_labeled_tweets(conn, tweet_id)

    ctx["communities"] = get_community_profiles(conn)
    ctx["thematic_glossary"] = get_thematic_glossary(conn)

    conn.close()
    return ctx
