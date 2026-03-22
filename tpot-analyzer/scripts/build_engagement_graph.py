"""Build account_engagement_agg — aggregated pairwise engagement (Phase 1, no propagation).

Reads raw edges (likes, replies, retweets, follows) and produces per-account-pair
aggregated counts. No total_weight baked in — consumers apply their own weighting.
Self-edges excluded. Timestamps tracked for freshness reasoning.

This is aggregation only. Propagation comes later (Phase 2) after 10+ stable accounts.

Usage:
    .venv/bin/python3 -m scripts.build_engagement_graph
    .venv/bin/python3 -m scripts.build_engagement_graph --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_engagement_agg (
    source_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    follow_flag     INTEGER DEFAULT 0,
    like_count      INTEGER DEFAULT 0,
    reply_count     INTEGER DEFAULT 0,
    rt_count        INTEGER DEFAULT 0,
    first_seen      TEXT,
    last_seen       TEXT,
    source_opt_in   INTEGER DEFAULT 0,
    target_opt_in   INTEGER DEFAULT 0,
    PRIMARY KEY (source_id, target_id)
);
"""


def build_engagement_graph(db_path: Path, dry_run: bool = False) -> None:
    conn = sqlite3.connect(str(db_path))
    now = datetime.now(timezone.utc).isoformat()

    if not dry_run:
        conn.executescript(SCHEMA)

    # Determine opt-in accounts (those with tweets in archive = contributed data)
    opt_in = set(
        r[0] for r in conn.execute("SELECT DISTINCT account_id FROM tweets").fetchall()
    )
    print(f"Opt-in accounts (have tweets in archive): {len(opt_in):,}")

    # Collect edges: (source, target) -> {follow, likes, replies, rts, first_seen, last_seen}
    edges: dict[tuple[str, str], dict] = {}

    def ensure_edge(src: str, tgt: str) -> dict:
        if src == tgt:
            return None  # Exclude self-edges
        key = (src, tgt)
        if key not in edges:
            edges[key] = {"follow": 0, "likes": 0, "replies": 0, "rts": 0,
                          "first": None, "last": None}
        return edges[key]

    def update_time(edge: dict, ts: str | None) -> None:
        if not ts or not edge:
            return
        if edge["first"] is None or ts < edge["first"]:
            edge["first"] = ts
        if edge["last"] is None or ts > edge["last"]:
            edge["last"] = ts

    # 1. Follows
    print("Loading follows...")
    t0 = time.time()
    rows = conn.execute("SELECT account_id, following_account_id FROM account_following").fetchall()
    for src, tgt in rows:
        e = ensure_edge(src, tgt)
        if e:
            e["follow"] = 1
    print(f"  {len(rows):,} follow edges in {time.time()-t0:.1f}s")

    # 2. Likes (aggregated per account pair)
    print("Loading likes...")
    t0 = time.time()
    rows = conn.execute("""
        SELECT l.liker_account_id, t.account_id, COUNT(*) as cnt,
               MIN(t.created_at) as first_ts, MAX(t.created_at) as last_ts
        FROM likes l
        JOIN tweets t ON l.tweet_id = t.tweet_id
        WHERE l.liker_account_id != t.account_id
        GROUP BY l.liker_account_id, t.account_id
    """).fetchall()
    for src, tgt, cnt, first_ts, last_ts in rows:
        e = ensure_edge(src, tgt)
        if e:
            e["likes"] = cnt
            update_time(e, first_ts)
            update_time(e, last_ts)
    print(f"  {len(rows):,} like pairs in {time.time()-t0:.1f}s")

    # 3. Replies (aggregated per account pair)
    print("Loading replies...")
    t0 = time.time()
    rows = conn.execute("""
        SELECT t1.account_id, t2.account_id, COUNT(*) as cnt,
               MIN(t1.created_at) as first_ts, MAX(t1.created_at) as last_ts
        FROM tweets t1
        JOIN tweets t2 ON t1.reply_to_tweet_id = t2.tweet_id
        WHERE t1.account_id != t2.account_id
        GROUP BY t1.account_id, t2.account_id
    """).fetchall()
    for src, tgt, cnt, first_ts, last_ts in rows:
        e = ensure_edge(src, tgt)
        if e:
            e["replies"] = cnt
            update_time(e, first_ts)
            update_time(e, last_ts)
    print(f"  {len(rows):,} reply pairs in {time.time()-t0:.1f}s")

    # 4. Retweets (resolve via profiles for account_id)
    print("Loading retweets...")
    t0 = time.time()
    rows = conn.execute("""
        SELECT r.account_id, p.account_id, COUNT(*) as cnt,
               MIN(r.created_at) as first_ts, MAX(r.created_at) as last_ts
        FROM retweets r
        JOIN profiles p ON LOWER(p.username) = LOWER(r.rt_of_username)
        WHERE r.account_id != p.account_id
        GROUP BY r.account_id, p.account_id
    """).fetchall()
    for src, tgt, cnt, first_ts, last_ts in rows:
        e = ensure_edge(src, tgt)
        if e:
            e["rts"] = cnt
            update_time(e, first_ts)
            update_time(e, last_ts)
    print(f"  {len(rows):,} retweet pairs in {time.time()-t0:.1f}s")

    # Filter: only keep edges with at least some engagement
    significant = {k: v for k, v in edges.items()
                   if v["follow"] or v["likes"] or v["replies"] or v["rts"]}
    print(f"\nTotal unique account pairs: {len(significant):,}")

    if dry_run:
        # Show top edges by like count
        top = sorted(significant.items(), key=lambda x: -(x[1]["likes"] + x[1]["replies"]*3))[:20]
        print("\nTop 20 engagement edges (by likes + 3×replies):")
        for (src, tgt), e in top:
            src_name = conn.execute("SELECT username FROM profiles WHERE account_id = ?", (src,)).fetchone()
            tgt_name = conn.execute("SELECT username FROM profiles WHERE account_id = ?", (tgt,)).fetchone()
            sn = src_name[0] if src_name else src[:8]
            tn = tgt_name[0] if tgt_name else tgt[:8]
            opt = ("OPT" if src in opt_in else "   ") + "/" + ("OPT" if tgt in opt_in else "   ")
            print(f"  {sn:>20} → {tn:<20}  F={e['follow']} L={e['likes']:>4} R={e['replies']:>3} RT={e['rts']:>3}  [{opt}]")
        print("\nDRY RUN — no changes made.")
        conn.close()
        return

    # Write to DB
    print("\nWriting to account_engagement_agg...")
    conn.execute("DROP TABLE IF EXISTS account_engagement_agg")
    conn.executescript(SCHEMA)

    batch = []
    for (src, tgt), e in significant.items():
        batch.append((
            src, tgt,
            e["follow"], e["likes"], e["replies"], e["rts"],
            e["first"], e["last"],
            1 if src in opt_in else 0,
            1 if tgt in opt_in else 0,
        ))

    conn.executemany(
        "INSERT INTO account_engagement_agg "
        "(source_id, target_id, follow_flag, like_count, reply_count, rt_count, "
        "first_seen, last_seen, source_opt_in, target_opt_in) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        batch,
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM account_engagement_agg").fetchone()[0]
    both_opt = conn.execute(
        "SELECT COUNT(*) FROM account_engagement_agg WHERE source_opt_in = 1 AND target_opt_in = 1"
    ).fetchone()[0]
    print(f"Written {count:,} engagement edges ({both_opt:,} where both opt-in)")

    # Sanity check: adityaarpitha's top engagers
    aid = "261659859"
    print(f"\n=== Top engagers with @adityaarpitha ===")
    top = conn.execute("""
        SELECT ae.source_id, ae.like_count, ae.reply_count, ae.rt_count, ae.follow_flag,
               p.username
        FROM account_engagement_agg ae
        LEFT JOIN profiles p ON p.account_id = ae.source_id
        WHERE ae.target_id = ?
        ORDER BY ae.like_count + ae.reply_count * 3 DESC
        LIMIT 10
    """, (aid,)).fetchall()
    for src_id, likes, replies, rts, follow, username in top:
        print(f"  @{username or src_id[:8]:>20}  F={follow} L={likes:>3} R={replies:>2} RT={rts:>2}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build engagement aggregation graph")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    build_engagement_graph(args.db_path, dry_run=args.dry_run)
