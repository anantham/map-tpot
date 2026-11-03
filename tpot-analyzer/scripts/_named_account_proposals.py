"""Shared read-only selection and validation for named-account proposals."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


APPROVED_MODELS = (
    "x-ai/grok-4.3",
    "deepseek/deepseek-v3.2",
    "google/gemini-3.1-flash-lite-preview",
)


def open_read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_account(conn: sqlite3.Connection, username: str, account_id: str) -> dict[str, Any]:
    row = conn.execute(
        """SELECT p.account_id, p.username, p.display_name,
                  COALESCE(upc.description, p.bio) AS bio,
                  upc.followers AS followers_count,
                  upc.following AS following_count,
                  upc.statuses AS statuses_count
           FROM profiles p
           LEFT JOIN user_profile_cache upc ON upc.account_id = p.account_id
           WHERE p.account_id = ? AND LOWER(p.username) = LOWER(?)""",
        (account_id, username),
    ).fetchone()
    if row is None:
        raise ValueError(f"canonical profile not found for @{username} / {account_id}")
    conflict = conn.execute(
        "SELECT COUNT(*) FROM profiles WHERE LOWER(username)=LOWER(?) AND account_id<>?",
        (username, account_id),
    ).fetchone()[0]
    if conflict:
        raise ValueError(f"username has {conflict} conflicting profile binding(s)")
    holdout = conn.execute(
        "SELECT COUNT(*) FROM tpot_directory_holdout WHERE account_id=? OR LOWER(handle)=LOWER(?)",
        (account_id, username),
    ).fetchone()[0]
    if holdout:
        raise ValueError("account is in the evaluation holdout")
    return dict(row)


def select_tweets(conn: sqlite3.Connection, account_id: str, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT tweet_id, account_id, username, text, like_count,
                  retweet_count, reply_count, view_count, created_at,
                  mentions_json, has_media, fetch_source, fetched_at
           FROM enriched_tweets
           WHERE account_id = ?
             AND COALESCE(is_reply, 0) = 0
             AND TRIM(COALESCE(text, '')) <> ''
             AND TRIM(COALESCE(text, '')) NOT LIKE 'RT @%'
           ORDER BY (COALESCE(like_count, 0) + COALESCE(retweet_count, 0)) DESC,
                    COALESCE(like_count, 0) DESC,
                    created_at DESC,
                    tweet_id
           LIMIT ?""",
        (account_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def source_receipt(account: dict[str, Any], tweets: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"account": account, "tweets": tweets}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "account": account,
        "tweets": tweets,
    }


def valid_communities(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT short_name FROM community WHERE short_name IS NOT NULL")
    }


def validate_label(label: Any, communities: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(label, dict):
        return ["label is not an object"]
    list_fields = {
        "bits": "bits:",
        "domains": "domain:",
        "themes": "theme:",
        "postures": "posture:",
        "new_community_signals": "new-community-signal:",
    }
    for field, prefix in list_fields.items():
        values = label.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            errors.append(f"{field} must be a list of strings")
            continue
        for value in values:
            if not value.startswith(prefix):
                errors.append(f"{field} value has wrong prefix: {value}")
    seen: set[str] = set()
    for tag in label.get("bits", []) if isinstance(label.get("bits"), list) else []:
        parts = tag.split(":")
        if len(parts) != 3:
            errors.append(f"malformed bits tag: {tag}")
            continue
        community = parts[1]
        if community not in communities:
            errors.append(f"unknown community in bits tag: {community}")
        if community in seen:
            errors.append(f"duplicate community in bits: {community}")
        seen.add(community)
        try:
            value = int(parts[2])
        except ValueError:
            errors.append(f"non-integer bits value: {tag}")
        else:
            if not 1 <= value <= 4:
                errors.append(f"bits value outside 1..4: {tag}")
    simulacrum = label.get("simulacrum")
    if not isinstance(simulacrum, dict) or set(simulacrum) != {"l1", "l2", "l3", "l4"}:
        errors.append("simulacrum must contain exactly l1,l2,l3,l4")
    else:
        values = list(simulacrum.values())
        if any(not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in values):
            errors.append("simulacrum values must be numeric in [0,1]")
        elif not 0.95 <= sum(values) <= 1.05:
            errors.append(f"simulacrum sum outside tolerance: {sum(values):.4f}")
    if label.get("signal_strength") not in {"low", "medium", "high"}:
        errors.append("signal_strength must be low, medium, or high")
    if not isinstance(label.get("note"), str):
        errors.append("note must be a string")
    return errors


def account_interpretation_counts(conn: sqlite3.Connection, account_id: str) -> dict[str, int]:
    return {
        "tweetTags": int(conn.execute(
            """SELECT COUNT(*) FROM tweet_tags tt JOIN enriched_tweets et
               ON et.tweet_id=tt.tweet_id WHERE et.account_id=?""",
            (account_id,),
        ).fetchone()[0]),
        "communityBits": int(conn.execute(
            "SELECT COUNT(*) FROM account_community_bits WHERE account_id=?", (account_id,)
        ).fetchone()[0]),
        "fingerprints": int(conn.execute(
            "SELECT COUNT(*) FROM account_fingerprint WHERE account_id=?", (account_id,)
        ).fetchone()[0]),
    }
