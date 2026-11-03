"""Shared acceptance math and unrelated-state digests for named accounts."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
from collections import defaultdict
from typing import Any


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def majority_decisions(artifact: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    decisions: list[dict[str, Any]] = []
    positive_totals: dict[str, int] = defaultdict(int)
    for result in artifact.get("results", []):
        votes: dict[str, list[int]] = defaultdict(list)
        for model in result.get("models", []):
            for tag in model.get("label", {}).get("bits", []):
                _, community, raw_value = tag.split(":")
                votes[community].append(int(raw_value))
        majority: list[str] = []
        rejected: list[str] = []
        for community, values in sorted(votes.items()):
            if len(values) >= 2:
                value = int(statistics.median(values)) if len(values) == 3 else min(values)
                tag = f"bits:{community}:+{value}"
                if community == "None":
                    rejected.append(tag)
                else:
                    majority.append(tag)
                    positive_totals[community] += value
            else:
                rejected.append(f"bits:{community}:+{min(values[0], 1)}")
        new_signals = sorted({
            signal
            for model in result.get("models", [])
            for signal in model.get("label", {}).get("new_community_signals", [])
        })
        decisions.append({
            "rank": int(result["rank"]),
            "tweetId": str(result["tweet"]["tweet_id"]),
            "acceptedBits": majority,
            "rejectedBits": rejected,
            "rejectedNewCommunitySignals": new_signals,
        })
    return decisions, dict(sorted(positive_totals.items(), key=lambda item: -item[1]))


def table_digest(conn: sqlite3.Connection, query: str, params: tuple = ()) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for row in conn.execute(query, params):
        digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def unrelated_digests(conn: sqlite3.Connection, account_id: str) -> dict[str, dict[str, Any]]:
    target = "SELECT tweet_id FROM enriched_tweets WHERE account_id=?"
    return {
        "tweetTags": table_digest(
            conn,
            f"""SELECT tweet_id,tag,category,added_by,created_at FROM tweet_tags
                WHERE tweet_id NOT IN ({target}) ORDER BY tweet_id,tag""",
            (account_id,),
        ),
        "labelSets": table_digest(
            conn,
            f"""SELECT id,tweet_id,axis,reviewer,note,context_hash,context_snapshot_json,
                       is_active,created_at,supersedes_label_set_id FROM tweet_label_set
                WHERE tweet_id NOT IN ({target}) ORDER BY id""",
            (account_id,),
        ),
        "communityBits": table_digest(
            conn,
            """SELECT account_id,community_id,total_bits,tweet_count,pct,updated_at
               FROM account_community_bits WHERE account_id<>? ORDER BY account_id,community_id""",
            (account_id,),
        ),
        "fingerprints": table_digest(
            conn,
            "SELECT * FROM account_fingerprint WHERE account_id<>? ORDER BY account_id",
            (account_id,),
        ),
    }
