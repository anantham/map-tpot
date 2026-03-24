"""
Labeling Context Generator

Run before a labeling session to produce a context blob for the labeling agent.
Outputs: account profile, thematic glossary, community exemplars, similar tweets.

Usage:
    python scripts/labeling_context.py <account_id_or_username>
    python scripts/labeling_context.py repligate
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

DB_PATH = DEFAULT_ARCHIVE_DB


def get_account_id(conn, identifier):
    """Resolve username or account_id."""
    row = conn.execute(
        "SELECT DISTINCT account_id FROM tweets WHERE LOWER(username) = LOWER(?) LIMIT 1",
        (identifier,),
    ).fetchone()
    if row:
        return row[0]
    # Try as account_id directly
    row = conn.execute(
        "SELECT DISTINCT account_id FROM tweets WHERE account_id = ? LIMIT 1",
        (identifier,),
    ).fetchone()
    return row[0] if row else None


def query_account_profile(conn, account_id):
    """Query 1: Account's current community profile from rollup table or raw bits."""
    # Try rollup table first (account_community_bits with community_id FK)
    try:
        rows = conn.execute(
            """
            SELECT c.short_name, acb.total_bits, acb.pct
            FROM account_community_bits acb
            JOIN community c ON c.id = acb.community_id
            WHERE acb.account_id = ?
            ORDER BY acb.total_bits DESC
            """,
            (account_id,),
        ).fetchall()
    except Exception:
        rows = []

    labeled_count = conn.execute(
        "SELECT COUNT(DISTINCT tweet_id) FROM tweet_label_set WHERE tweet_id IN "
        "(SELECT tweet_id FROM tweets WHERE account_id = ?)",
        (account_id,),
    ).fetchone()[0]

    if rows:
        total = sum(r[1] for r in rows)
        print(f"=== ACCOUNT PROFILE ({labeled_count} tweets labeled, {total} total bits) ===\n")
        for short_name, bits, pct in rows:
            bar = "█" * int(pct / 2)
            print(f"  {pct:5.1f}%  {bar}  {short_name} ({bits:+d} bits)")
        print()
        return

    # Fallback: compute from raw tweet_tags
    tag_rows = conn.execute(
        """
        SELECT tt.tag
        FROM tweet_tags tt
        JOIN tweets t ON t.tweet_id = tt.tweet_id
        WHERE tt.category = 'bits' AND t.account_id = ?
        """,
        (account_id,),
    ).fetchall()

    community_bits = defaultdict(int)
    for (tag,) in tag_rows:
        parts = tag.split(":")
        if len(parts) == 3:
            community_bits[parts[1]] += int(parts[2])

    total = sum(community_bits.values())
    print(f"=== ACCOUNT PROFILE ({labeled_count} tweets labeled, {total} total bits) ===\n")
    for comm, bits in sorted(community_bits.items(), key=lambda x: -x[1]):
        pct = bits / total * 100 if total else 0
        bar = "█" * int(pct / 2)
        print(f"  {pct:5.1f}%  {bar}  {comm} ({bits:+d} bits)")
    print()


def query_thematic_glossary(conn):
    """Query 2: Current thematic tag vocabulary with frequencies."""
    rows = conn.execute(
        """
        SELECT tag, COUNT(*) as cnt
        FROM tweet_tags
        WHERE category = 'thematic'
        GROUP BY tag
        ORDER BY cnt DESC
        """,
    ).fetchall()

    print("=== THEMATIC TAG GLOSSARY ===\n")
    for tag, cnt in rows:
        print(f"  {cnt:>2}x  {tag}")
    print()


def query_community_exemplars(conn, account_id):
    """Query 3: Top tweets per community (highest bits)."""
    # Get communities this account has bits for
    rows = conn.execute(
        """
        SELECT tt.tag, tt.tweet_id, t.full_text
        FROM tweet_tags tt
        JOIN tweets t ON t.tweet_id = tt.tweet_id
        WHERE tt.category = 'bits' AND t.account_id = ?
        ORDER BY tt.tag
        """,
        (account_id,),
    ).fetchall()

    # Group by community, sort by bits value
    community_tweets = defaultdict(list)
    for tag, tid, text in rows:
        parts = tag.split(":")
        if len(parts) == 3:
            comm = parts[1]
            bits_val = int(parts[2])
            community_tweets[comm].append((bits_val, tid, (text or "")[:80]))

    print("=== COMMUNITY EXEMPLARS (top tweets per community) ===\n")
    for comm in sorted(community_tweets.keys(), key=lambda c: -sum(b for b, _, _ in community_tweets[c])):
        tweets = sorted(community_tweets[comm], key=lambda x: -x[0])[:3]
        total = sum(b for b, _, _ in community_tweets[comm])
        print(f"  {comm} ({total:+d} total bits):")
        for bits_val, tid, text in tweets:
            print(f"    {bits_val:+d}b  {text}")
        print()


def query_similar_tweets(conn, tweet_id):
    """Query 4: Find tweets with similar thematic tags (for calibration)."""
    # Get themes of this tweet
    themes = conn.execute(
        "SELECT tag FROM tweet_tags WHERE tweet_id = ? AND category = 'thematic'",
        (tweet_id,),
    ).fetchall()

    if not themes:
        print(f"=== No thematic tags for tweet {tweet_id} ===\n")
        return

    theme_list = [t[0] for t in themes]
    placeholders = ",".join(["?"] * len(theme_list))

    # Find other tweets with overlapping themes
    rows = conn.execute(
        f"""
        SELECT tt.tweet_id, t.full_text, COUNT(*) as overlap,
               GROUP_CONCAT(tt.tag, ', ') as shared_themes
        FROM tweet_tags tt
        JOIN tweets t ON t.tweet_id = tt.tweet_id
        WHERE tt.tag IN ({placeholders})
          AND tt.category = 'thematic'
          AND tt.tweet_id != ?
        GROUP BY tt.tweet_id
        ORDER BY overlap DESC
        LIMIT 5
        """,
        theme_list + [tweet_id],
    ).fetchall()

    print(f"=== SIMILAR TWEETS (sharing themes with {tweet_id}) ===\n")
    for tid, text, overlap, shared in rows:
        print(f"  {overlap} shared themes: {shared}")
        print(f"    {(text or '')[:80]}")
        print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/labeling_context.py <username_or_account_id>")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    identifier = sys.argv[1]
    account_id = get_account_id(conn, identifier)

    if not account_id:
        print(f"Account '{identifier}' not found in DB.")
        sys.exit(1)

    username = conn.execute(
        "SELECT username FROM tweets WHERE account_id = ? LIMIT 1", (account_id,)
    ).fetchone()[0]

    print(f"LABELING CONTEXT for @{username} (account_id: {account_id})")
    print("=" * 60)
    print()

    query_account_profile(conn, account_id)
    query_thematic_glossary(conn)
    query_community_exemplars(conn, account_id)

    conn.close()


if __name__ == "__main__":
    main()
