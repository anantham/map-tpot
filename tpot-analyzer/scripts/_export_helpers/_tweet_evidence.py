"""Tweet sampling + evidence + recommendation queries for the public site export."""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def get_sample_tweets(
    db_path: Path, account_id: str, limit: int = 3,
) -> list[str]:
    """Return top tweets by engagement (favorite_count + retweet_count).

    Args:
        db_path: Path to SQLite DB containing a ``tweets`` table.
        account_id: The account whose tweets to fetch.
        limit: Max number of tweets to return (default 3).

    Returns:
        List of tweet texts (each truncated to 280 chars), ordered by
        engagement descending. Returns ``[]`` when the account has no
        tweets or the ``tweets`` table does not exist.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """SELECT full_text FROM tweets
               WHERE account_id = ?
               ORDER BY (favorite_count + retweet_count) DESC
               LIMIT ?""",
            (account_id, limit),
        ).fetchall()
        return [row[0][:280] for row in rows]
    except sqlite3.OperationalError:
        # Table may not exist (e.g. test DBs without tweets)
        return []
    finally:
        conn.close()


def get_evidence(
    db_path: Path,
    account_id: str,
    community_names_map: dict[str, str],
    npz_snc_row: np.ndarray | None = None,
    npz_comm_names: list[str] | None = None,
) -> dict[str, Any]:
    """Build interpretable evidence for a single account.

    Returns dict with:
      - seed_neighbors_by_community: {community_name: count} (non-zero only)
      - notable_follows: [{handle, community}] — classified accounts this person follows
      - notable_followers: [{handle, community}] — classified accounts who follow this person
    """
    evidence: dict[str, Any] = {}

    # 1. Seed neighbors by community name (from propagation NPZ)
    if npz_snc_row is not None and npz_comm_names is not None:
        snc_dict = {}
        for i, name in enumerate(npz_comm_names):
            if i < len(npz_snc_row) and int(npz_snc_row[i]) > 0:
                snc_dict[name] = int(npz_snc_row[i])
        if snc_dict:
            # Sort by count descending, top 5
            evidence["seed_neighbors_by_community"] = dict(
                sorted(snc_dict.items(), key=lambda x: -x[1])[:5]
            )

    # 2. Notable follows (classified accounts this person follows)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("""
            SELECT af.following_account_id,
                   COALESCE(p.username, ra.username) as uname,
                   ca.community_id, ca.weight
            FROM account_following af
            LEFT JOIN profiles p ON p.account_id = af.following_account_id
            LEFT JOIN resolved_accounts ra ON ra.account_id = af.following_account_id
            JOIN community_account ca ON ca.account_id = af.following_account_id AND ca.weight >= 0.2
            WHERE af.account_id = ?
            AND (p.username IS NOT NULL OR ra.username IS NOT NULL)
            ORDER BY ca.weight DESC
            LIMIT 30
        """, (account_id,)).fetchall()

        # Deduplicate by account (pick highest-weight community)
        seen = set()
        notable = []
        for _fid, uname, cid, _w in rows:
            if uname and uname not in seen:
                seen.add(uname)
                cname = community_names_map.get(cid, "")
                if cname:
                    notable.append({"handle": uname, "community": cname})
            if len(notable) >= 8:
                break
        if notable:
            evidence["notable_follows"] = notable

        # 3. Notable followers (classified accounts who follow this person)
        try:
            frows = conn.execute("""
                SELECT af.follower_account_id,
                       COALESCE(p.username, ra.username) as uname,
                       ca.community_id, ca.weight
                FROM account_followers af
                LEFT JOIN profiles p ON p.account_id = af.follower_account_id
                LEFT JOIN resolved_accounts ra ON ra.account_id = af.follower_account_id
                JOIN community_account ca ON ca.account_id = af.follower_account_id AND ca.weight >= 0.2
                WHERE af.account_id = ?
                AND (p.username IS NOT NULL OR ra.username IS NOT NULL)
                ORDER BY ca.weight DESC
                LIMIT 30
            """, (account_id,)).fetchall()

            seen2 = set()
            notable_followers = []
            for _fid, uname, cid, _w in frows:
                if uname and uname not in seen2:
                    seen2.add(uname)
                    cname = community_names_map.get(cid, "")
                    if cname:
                        notable_followers.append({"handle": uname, "community": cname})
                if len(notable_followers) >= 8:
                    break
            if notable_followers:
                evidence["notable_followers"] = notable_followers
        except sqlite3.OperationalError:
            pass  # account_followers table may not exist

    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

    return evidence


def compute_recommendations(
    db_path: Path,
    all_accounts: list[dict[str, Any]],
    community_names_map: dict[str, str],
    max_per_community: int = 3,
    max_communities: int = 3,
) -> dict[str, list[dict]]:
    """Compute 'you might want to follow' recommendations for all accounts.

    For each account, finds high-weight classified accounts in their top
    communities that they don't already follow.

    Returns {account_id: [{"handle": ..., "community": ..., "weight": ...}, ...]}.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # 1. Load all follow edges (source → set of targets)
        logger.info("Loading follow graph for recommendations...")
        follow_sets: dict[str, set[str]] = {}
        for src, tgt in conn.execute("SELECT account_id, following_account_id FROM account_following"):
            if src not in follow_sets:
                follow_sets[src] = set()
            follow_sets[src].add(tgt)

        # 2. Load community members with usernames (the recommendation pool)
        # Only accounts with weight >= 0.3 (strong members)
        logger.info("Loading community member pool...")
        community_members: dict[str, list[tuple[str, str, float]]] = {}  # cid -> [(account_id, username, weight)]
        rows = conn.execute("""
            SELECT ca.community_id, ca.account_id,
                   COALESCE(p.username, ra.username) as uname, ca.weight
            FROM community_account ca
            LEFT JOIN profiles p ON p.account_id = ca.account_id
            LEFT JOIN resolved_accounts ra ON ra.account_id = ca.account_id
            WHERE ca.weight >= 0.3
            AND (p.username IS NOT NULL OR ra.username IS NOT NULL)
            ORDER BY ca.community_id, ca.weight DESC
        """).fetchall()
        for cid, aid, uname, w in rows:
            if cid not in community_members:
                community_members[cid] = []
            community_members[cid].append((aid, uname, w))

        # 3. For each account, compute recommendations
        logger.info("Computing recommendations for %d accounts...", len(all_accounts))
        results: dict[str, list[dict]] = {}

        for acct in all_accounts:
            aid = acct["id"]
            memberships = acct.get("memberships", [])
            if not memberships:
                continue

            following = follow_sets.get(aid, set())

            # Sort memberships by weight, take top communities
            sorted_m = sorted(memberships, key=lambda m: m.get("weight", 0), reverse=True)
            recs = []

            for m in sorted_m[:max_communities]:
                cid = m.get("community_id", "")
                cname = community_names_map.get(cid, "")
                if not cname:
                    continue
                members = community_members.get(cid, [])

                count = 0
                for member_aid, member_uname, member_w in members:
                    if member_aid == aid:
                        continue
                    if member_aid in following:
                        continue
                    recs.append({
                        "handle": member_uname,
                        "community": cname,
                    })
                    count += 1
                    if count >= max_per_community:
                        break

            if recs:
                results[aid] = recs

        return results

    finally:
        conn.close()


def _safe_followers(val: Any) -> int | None:
    """Convert num_followers (float64, may be NaN) to int or None."""
    if val is None:
        return None
    try:
        if math.isnan(val):
            return None
        return int(val)
    except (TypeError, ValueError):
        return None


def detect_tweet_types(db_path, account_id, tweet_ids):
    """Classify tweets as tweet/reply/retweet/thread."""
    if not tweet_ids:
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" for _ in tweet_ids)
        rows = conn.execute(f"""
            SELECT tweet_id, full_text, reply_to_tweet_id, created_at
            FROM tweets
            WHERE tweet_id IN ({placeholders}) AND account_id = ?
        """, [*tweet_ids, account_id]).fetchall()

        tweet_data = {}
        for row in rows:
            tweet_data[row[0]] = {
                "text": row[1] or "",
                "reply_to": row[2],
                "created_at": row[3],
            }

        timestamps = []
        for tid in tweet_ids:
            if tid in tweet_data and tweet_data[tid]["created_at"]:
                try:
                    dt = datetime.strptime(tweet_data[tid]["created_at"], "%Y-%m-%d %H:%M:%S")
                    timestamps.append((tid, dt))
                except ValueError:
                    pass
        timestamps.sort(key=lambda x: x[1])

        thread_ids = set()
        for i in range(len(timestamps) - 1):
            if timestamps[i + 1][1] - timestamps[i][1] <= timedelta(minutes=5):
                thread_ids.add(timestamps[i][0])
                thread_ids.add(timestamps[i + 1][0])

        result = {}
        for tid in tweet_ids:
            if tid not in tweet_data:
                result[tid] = "tweet"
            elif tweet_data[tid]["text"].startswith("RT @"):
                result[tid] = "retweet"
            elif tweet_data[tid]["reply_to"]:
                result[tid] = "reply"
            elif tid in thread_ids:
                result[tid] = "thread"
            else:
                result[tid] = "tweet"
    finally:
        conn.close()
    return result


def select_community_tweets(db_path, account_id, n=5):
    """Select top tweets by engagement (fav + rt*2) with type detection."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("""
            SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
            FROM tweets
            WHERE account_id = ?
            ORDER BY (favorite_count + retweet_count * 2) DESC
            LIMIT ?
        """, [account_id, n]).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()

    if not rows:
        return []

    tweet_ids = [r[0] for r in rows]
    types = detect_tweet_types(db_path, account_id, tweet_ids)

    return [
        {
            "id": r[0],
            "text": (r[1] or "")[:280],
            "created_at": r[2],
            "type": types.get(r[0], "tweet"),
            "favorite_count": r[3] or 0,
            "retweet_count": r[4] or 0,
        }
        for r in rows
    ]
