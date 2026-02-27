"""Account preview data assembly for the communities curator UI.

This module assembles rich per-account preview data by querying the archive DB.
It depends on Layer 2 community data from store.py (get_account_communities,
get_account_note) but does not modify any data.

Separated from store.py because:
- It contains volatile UI query logic (new data sources added frequently)
- It joins across both archive tables and communities tables
- It changes independently from the persistence layer
"""

import sqlite3
from typing import Optional

from src.communities.store import get_account_communities, get_account_note


def get_account_preview(
    conn: sqlite3.Connection,
    account_id: str,
    ego_account_id: Optional[str] = None,
) -> dict:
    """Assemble rich preview data for a single account.

    Returns dict with keys: profile, communities, followers_you_know,
    notable_followees, recent_tweets, top_tweets, liked_tweets,
    top_rt_targets, tpot_score, tpot_score_max, note.
    Does not commit.
    """
    # Profile
    profile = conn.execute(
        "SELECT username, display_name, bio, location, website FROM profiles WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    profile_dict = {
        "username": profile[0] if profile else None,
        "display_name": profile[1] if profile else None,
        "bio": profile[2] if profile else None,
        "location": profile[3] if profile else None,
        "website": profile[4] if profile else None,
    }

    # Community weights
    communities = []
    for cid, name, color, weight, source in get_account_communities(conn, account_id):
        communities.append({
            "community_id": cid, "name": name, "color": color,
            "weight": weight, "source": source,
        })

    # Followers you know: people you (ego) follow who also follow this account
    followers_you_know = []
    if ego_account_id:
        rows = conn.execute(
            """SELECT af.follower_account_id, p.username, p.bio
               FROM account_followers af
               JOIN account_following ego_f
                   ON ego_f.following_account_id = af.follower_account_id
                   AND ego_f.account_id = ?
               LEFT JOIN profiles p ON p.account_id = af.follower_account_id
               WHERE af.account_id = ?
               ORDER BY p.username""",
            (ego_account_id, account_id),
        ).fetchall()
        for fid, fusername, fbio in rows:
            fk_comms = []
            for cid, cname, ccolor, cw, csrc in get_account_communities(conn, fid):
                fk_comms.append({"community_id": cid, "name": cname, "color": ccolor})
            followers_you_know.append({
                "account_id": fid, "username": fusername, "bio": fbio,
                "communities": fk_comms,
            })

    # Notable followees: high-TPOT-score accounts that this person follows
    # (accounts they follow that are also community members, ranked by in-degree)
    notable_followees = []
    followee_rows = conn.execute(
        """SELECT af.following_account_id, p.username, p.bio,
                  COUNT(DISTINCT af2.follower_account_id) as tpot_score
           FROM account_following af
           JOIN community_account ca ON ca.account_id = af.following_account_id
           LEFT JOIN profiles p ON p.account_id = af.following_account_id
           LEFT JOIN account_followers af2
               ON af2.account_id = af.following_account_id
               AND af2.follower_account_id IN (
                   SELECT DISTINCT account_id FROM community_account
               )
           WHERE af.account_id = ?
             AND af.following_account_id != ?
           GROUP BY af.following_account_id
           ORDER BY tpot_score DESC
           LIMIT 30""",
        (account_id, account_id),
    ).fetchall()
    for fid, fusername, fbio, fscore in followee_rows:
        nf_comms = []
        for cid, cname, ccolor, cw, csrc in get_account_communities(conn, fid):
            nf_comms.append({"community_id": cid, "name": cname, "color": ccolor})
        notable_followees.append({
            "account_id": fid, "username": fusername, "bio": fbio,
            "tpot_score": fscore, "communities": nf_comms,
        })

    # Recent tweets (15)
    recent_tweets = []
    for tid, text, created, fav, rt_count in conn.execute(
        """SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
           FROM tweets WHERE account_id = ?
           ORDER BY created_at DESC LIMIT 15""",
        (account_id,),
    ).fetchall():
        recent_tweets.append({
            "tweet_id": tid, "text": text, "created_at": created,
            "favorites": fav, "retweets": rt_count,
        })

    # Top liked tweets (their most popular tweets by favorites)
    top_tweets = []
    for tid, text, created, fav, rt_count in conn.execute(
        """SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
           FROM tweets WHERE account_id = ?
           ORDER BY favorite_count DESC LIMIT 10""",
        (account_id,),
    ).fetchall():
        top_tweets.append({
            "tweet_id": tid, "text": text, "created_at": created,
            "favorites": fav, "retweets": rt_count,
        })

    # Tweets they liked (sample)
    liked_tweets = []
    for text, expanded_url in conn.execute(
        """SELECT full_text, expanded_url FROM likes
           WHERE liker_account_id = ?
           ORDER BY rowid DESC LIMIT 10""",
        (account_id,),
    ).fetchall():
        liked_tweets.append({"text": text, "url": expanded_url})

    # Top RT targets
    top_rt_targets = []
    for rt_username, count in conn.execute(
        """SELECT rt_of_username, COUNT(*) as cnt
           FROM retweets WHERE account_id = ?
           GROUP BY rt_of_username ORDER BY cnt DESC LIMIT 8""",
        (account_id,),
    ).fetchall():
        top_rt_targets.append({"username": rt_username, "count": count})

    # TPOT score: in-degree within the community member subgraph
    # = how many other community members follow this account
    tpot_score = conn.execute(
        """SELECT COUNT(DISTINCT af.follower_account_id)
           FROM account_followers af
           WHERE af.account_id = ?
             AND af.follower_account_id IN (
                 SELECT DISTINCT account_id FROM community_account
             )""",
        (account_id,),
    ).fetchone()[0]

    # Total community members for context
    total_community_members = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM community_account"
    ).fetchone()[0]

    # Note
    note = get_account_note(conn, account_id)

    return {
        "account_id": account_id,
        "profile": profile_dict,
        "communities": communities,
        "followers_you_know": followers_you_know,
        "followers_you_know_count": len(followers_you_know),
        "notable_followees": notable_followees,
        "recent_tweets": recent_tweets,
        "top_tweets": top_tweets,
        "liked_tweets": liked_tweets,
        "top_rt_targets": top_rt_targets,
        "tpot_score": tpot_score,
        "tpot_score_max": total_community_members,
        "note": note,
    }
