"""
assemble_context.py

Context assembly for the LLM labeling prompt in the active learning pipeline.

Provides:
  - get_graph_signal: which community seeds follow this account (inbound)
  - get_engagement_context: which classified accounts liked a specific tweet
  - get_community_descriptions: load community name→description map + short names
  - get_following_overlap: which classified accounts this account follows (outbound)
  - assemble_account_context: combines account-level signals into a dict
  - assemble_tweet_context: combines tweet-level signals into a dict
"""

import sqlite3
from collections import defaultdict


def get_graph_signal(conn: sqlite3.Connection, account_id: str) -> str:
    """
    Find seeds who follow this account, grouped by community.

    Joins account_following (following_account_id = account_id) with
    community_account and community to count inbound seeds per community.

    Returns a formatted string like:
        "Qualia Researchers: 40 seeds | Core TPOT: 38 seeds"
    or "No seed follows found in graph." if no results.
    """
    sql = """
        SELECT c.name, COUNT(DISTINCT af.account_id) AS seed_count
        FROM account_following af
        JOIN community_account ca ON ca.account_id = af.account_id
        JOIN community c ON c.id = ca.community_id
        WHERE af.following_account_id = ?
        GROUP BY c.id, c.name
        ORDER BY seed_count DESC
    """
    rows = conn.execute(sql, (account_id,)).fetchall()
    if not rows:
        return "No seed follows found in graph."
    parts = [f"{name}: {count} seeds" for name, count in rows]
    return " | ".join(parts)


def get_engagement_context(conn: sqlite3.Connection, tweet_id: str) -> str:
    """
    Find classified accounts who liked this specific tweet.

    Joins likes (tweet_id matches) with community_account and community.

    Returns a formatted string like:
        "Liked by: @user1 (Community1), @user2 (Community2)
         Breakdown: Community1: 3 | Community2: 2"
    or "No engagement data from classified accounts." if no results.
    """
    sql = """
        SELECT l.liker_username, c.name
        FROM likes l
        JOIN community_account ca ON ca.account_id = l.liker_account_id
        JOIN community c ON c.id = ca.community_id
        WHERE l.tweet_id = ?
        ORDER BY c.name, l.liker_username
    """
    rows = conn.execute(sql, (tweet_id,)).fetchall()
    if not rows:
        return "No engagement data from classified accounts."

    liked_by_parts = [f"@{username} ({community})" for username, community in rows]
    liked_by_line = "Liked by: " + ", ".join(liked_by_parts)

    community_counts: dict[str, int] = defaultdict(int)
    for _, community in rows:
        community_counts[community] += 1
    breakdown_parts = [f"{comm}: {cnt}" for comm, cnt in sorted(community_counts.items(), key=lambda x: -x[1])]
    breakdown_line = "Breakdown: " + " | ".join(breakdown_parts)

    return f"{liked_by_line}\n{breakdown_line}"


def get_community_descriptions(conn: sqlite3.Connection) -> tuple[dict[str, str], list[str]]:
    """
    Load all communities from the community table.

    Returns:
        (dict of community_name -> description, list of short_names)
    """
    rows = conn.execute(
        "SELECT name, short_name, description FROM community ORDER BY name"
    ).fetchall()
    descriptions: dict[str, str] = {}
    short_names: list[str] = []
    for name, short_name, description in rows:
        descriptions[name] = description or ""
        if short_name:
            short_names.append(short_name)
    return descriptions, short_names


def get_following_overlap(conn: sqlite3.Connection, account_id: str) -> str:
    """
    Check how many of this account's outbound follows are classified (in community_account).

    Joins account_following (account_id = our account) with community_account and community.

    Returns a formatted string like:
        "Follows 12 classified accounts: 5 Sensemaking Builders, 3 Regen, ..."
    or "No following data available." if the account has no outbound follows.
    """
    # First check if account has any outbound follows at all
    has_follows = conn.execute(
        "SELECT 1 FROM account_following WHERE account_id = ? LIMIT 1",
        (account_id,),
    ).fetchone()
    if not has_follows:
        return "No following data available."

    sql = """
        SELECT c.name, COUNT(DISTINCT af.following_account_id) AS classified_count
        FROM account_following af
        JOIN community_account ca ON ca.account_id = af.following_account_id
        JOIN community c ON c.id = ca.community_id
        WHERE af.account_id = ?
        GROUP BY c.id, c.name
        ORDER BY classified_count DESC
    """
    rows = conn.execute(sql, (account_id,)).fetchall()
    if not rows:
        # Account has follows but none are classified
        return "No following data available."

    total = sum(count for _, count in rows)
    community_parts = [f"{count} {name}" for name, count in rows]
    return f"Follows {total} classified accounts: {', '.join(community_parts)}"


def get_content_profile(conn: sqlite3.Connection, account_id: str, top_n: int = 5) -> str:
    """
    Load TF-IDF content profile for this account from account_content_profile.

    Returns a human-readable summary of the account's top liked-content topics,
    or empty string if no content profile exists.

    Example output:
        "Content interests (from liked tweets): rationalism/EA (23%), consciousness/qualia (18%), AI/ML tools (12%)"
    """
    try:
        rows = conn.execute(
            """SELECT acp.topic_idx, acp.weight, ct.top_words
               FROM account_content_profile acp
               JOIN content_topic ct ON ct.topic_idx = acp.topic_idx
               WHERE acp.account_id = ?
               ORDER BY acp.weight DESC
               LIMIT ?""",
            (account_id, top_n),
        ).fetchall()
    except sqlite3.OperationalError:
        return ""  # Tables don't exist yet
    if not rows:
        return ""

    # Filter to topics with meaningful weight (>3%)
    significant = [(idx, weight, words) for idx, weight, words in rows if weight > 0.03]
    if not significant:
        return ""

    # Build readable summary: use first 3-4 top_words as topic label
    parts = []
    for _, weight, top_words in significant:
        # top_words is comma-separated; take first 3 as a readable label
        word_list = [w.strip() for w in top_words.split(",")][:3]
        label = "/".join(word_list)
        parts.append(f"{label} ({weight:.0%})")

    return "Content interests (from liked tweets): " + ", ".join(parts)


def assemble_account_context(
    conn: sqlite3.Connection,
    account_id: str,
    username: str,
    bio: str,
) -> dict:
    """
    Assemble account-level context for the LLM labeling prompt.

    Combines:
      - graph_signal: inbound seed follows grouped by community
      - following_overlap: outbound follows toward classified accounts
      - content_profile: TF-IDF topic weights from liked tweets
      - community_descriptions: name→description mapping
      - community_short_names: list of community short names

    Returns a dict with keys: account_id, username, bio, graph_signal,
    following_overlap, content_profile, community_descriptions, community_short_names.
    """
    graph_signal = get_graph_signal(conn, account_id)
    following_overlap = get_following_overlap(conn, account_id)
    content_profile = get_content_profile(conn, account_id)
    community_descriptions, community_short_names = get_community_descriptions(conn)

    return {
        "account_id": account_id,
        "username": username,
        "bio": bio,
        "graph_signal": graph_signal,
        "following_overlap": following_overlap,
        "content_profile": content_profile,
        "community_descriptions": community_descriptions,
        "community_short_names": community_short_names,
    }


def assemble_tweet_context(
    conn: sqlite3.Connection,
    tweet_id: str,
    tweet_text: str,
    engagement_stats: str,
    mentions: str,
) -> dict:
    """
    Assemble tweet-level context for the LLM labeling prompt.

    Combines:
      - engagement_context: classified accounts who liked this tweet

    Returns a dict with keys: tweet_id, tweet_text, engagement_stats,
    mentions, engagement_context.
    """
    engagement_context = get_engagement_context(conn, tweet_id)

    return {
        "tweet_id": tweet_id,
        "tweet_text": tweet_text,
        "engagement_stats": engagement_stats,
        "mentions": mentions,
        "engagement_context": engagement_context,
    }
