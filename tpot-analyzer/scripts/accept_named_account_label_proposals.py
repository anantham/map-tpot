#!/usr/bin/env python3
"""Apply an explicitly accepted named-account proposal and make local card data.

Test intent exception: this identity-sensitive operational CLI is verified by
an independent real-DB receipt verifier. It requires exact proposal and
accepted-bit hashes, checks zero-state preconditions, writes one transaction,
and proves unrelated table digests are unchanged before commit.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._named_account_acceptance import (  # noqa: E402
    canonical_sha256,
    file_sha256,
    majority_decisions,
    unrelated_digests,
)
from scripts._named_account_proposals import (  # noqa: E402
    load_account,
    select_tweets,
    source_receipt,
)
from scripts.rollup_bits import aggregate_bits, load_short_to_id  # noqa: E402
from scripts.rollup_fingerprints import rollup_account, store_fingerprint  # noqa: E402

DEFAULT_DB = ROOT / "data" / "archive_tweets.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Accept named-account label proposals")
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--accepted-bits-json", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--acceptance-output", type=Path, required=True)
    parser.add_argument("--card-output", type=Path, required=True)
    args = parser.parse_args()
    for output in (args.acceptance_output, args.card_output):
        if output.exists():
            raise FileExistsError(f"refusing to overwrite: {output}")

    proposal_sha = file_sha256(args.proposal)
    if proposal_sha != args.proposal_sha256:
        raise ValueError(f"proposal SHA mismatch: expected {args.proposal_sha256}, got {proposal_sha}")
    artifact = json.loads(args.proposal.read_text(encoding="utf-8"))
    if artifact.get("runStatus") != "complete" or artifact.get("goldStatus") != "not-gold":
        raise ValueError("proposal is not a complete non-gold receipt")
    decisions, positive_totals = majority_decisions(artifact)
    expected_totals = json.loads(args.accepted_bits_json)
    if positive_totals != expected_totals:
        raise ValueError(f"accepted bits mismatch: computed={positive_totals} expected={expected_totals}")
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    conn = sqlite3.connect(str(args.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        account = load_account(conn, args.username, args.account_id)
        current_source = source_receipt(account, select_tweets(conn, args.account_id, 20))
        if current_source["sha256"] != artifact.get("source", {}).get("sha256"):
            raise ValueError("current source no longer matches the accepted proposal")
        target_counts = {
            "tweetTags": conn.execute(
                """SELECT COUNT(*) FROM tweet_tags tt JOIN enriched_tweets et
                   ON et.tweet_id=tt.tweet_id WHERE et.account_id=?""", (args.account_id,)
            ).fetchone()[0],
            "labelSets": conn.execute(
                """SELECT COUNT(*) FROM tweet_label_set WHERE tweet_id IN
                   (SELECT tweet_id FROM enriched_tweets WHERE account_id=?)""", (args.account_id,)
            ).fetchone()[0],
            "communityBits": conn.execute(
                "SELECT COUNT(*) FROM account_community_bits WHERE account_id=?", (args.account_id,)
            ).fetchone()[0],
            "fingerprints": conn.execute(
                "SELECT COUNT(*) FROM account_fingerprint WHERE account_id=?", (args.account_id,)
            ).fetchone()[0],
        }
        if any(target_counts.values()):
            raise ValueError(f"target is not in the required zero state: {target_counts}")
        before = unrelated_digests(conn, args.account_id)
        conn.execute("BEGIN IMMEDIATE")
        tag_rows = []
        for decision in decisions:
            snapshot = {
                "proposalSha256": proposal_sha,
                "sourceSha256": current_source["sha256"],
                **decision,
            }
            conn.execute(
                """INSERT INTO tweet_label_set
                   (tweet_id,axis,reviewer,note,context_hash,context_snapshot_json,is_active,created_at)
                   VALUES (?,?,?,?,?,?,1,?)""",
                (
                    decision["tweetId"], "community_bits", args.reviewer,
                    "Human accepted the documented two-of-three positive community bits; None, one-model bits, and new-community signals rejected.",
                    current_source["sha256"], json.dumps(snapshot, sort_keys=True), now,
                ),
            )
            tag_rows.extend(
                (decision["tweetId"], tag, "bits", args.reviewer, now)
                for tag in decision["acceptedBits"]
            )
        conn.executemany(
            "INSERT INTO tweet_tags (tweet_id,tag,category,added_by,created_at) VALUES (?,?,?,?,?)",
            tag_rows,
        )
        rollup = aggregate_bits(
            [(args.account_id, tweet_id, tag) for tweet_id, tag, *_ in tag_rows],
            load_short_to_id(conn),
        )
        for (account_id, community_id), data in rollup.items():
            conn.execute(
                """INSERT INTO account_community_bits
                   (account_id,community_id,total_bits,tweet_count,pct,updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (account_id, community_id, data["total_bits"], data["tweet_count"], data["pct"], now),
            )
        fingerprint = rollup_account(conn, args.account_id)
        store_fingerprint(conn, fingerprint)
        after = unrelated_digests(conn, args.account_id)
        if after != before:
            raise RuntimeError("unrelated-state digest changed; rolling back")

        community_rows = conn.execute(
            """SELECT acb.community_id,c.name,c.short_name,c.color,c.description,
                      acb.total_bits,acb.tweet_count,acb.pct
               FROM account_community_bits acb JOIN community c ON c.id=acb.community_id
               WHERE acb.account_id=? ORDER BY acb.pct DESC""",
            (args.account_id,),
        ).fetchall()
        by_rank = {int(result["rank"]): result["tweet"]["text"] for result in artifact["results"]}
        card = {
            "schemaVersion": 1,
            "cardStatus": "local-human-accepted",
            "publicStatus": "not-exported",
            "handle": args.username,
            "accountId": args.account_id,
            "displayName": account.get("display_name"),
            "bio": account.get("bio"),
            "semantics": "Human-accepted relative content-evidence distribution; not calibrated membership probabilities.",
            "communities": [dict(row) for row in community_rows],
            "sampleTweets": [by_rank[rank] for rank in (12, 3, 14, 6, 1)],
            "reviewedTweets": len(decisions),
            "positiveTweets": sum(bool(item["acceptedBits"]) for item in decisions),
            "adjacentNoneBitsRejectedFromMembership": 20,
            "proposalSha256": proposal_sha,
            "sourceSha256": current_source["sha256"],
            "createdAt": now,
        }
        acceptance = {
            "schemaVersion": 1,
            "decisionStatus": "human-accepted",
            "reviewer": args.reviewer,
            "proposalSha256": proposal_sha,
            "sourceSha256": current_source["sha256"],
            "acceptedBits": positive_totals,
            "acceptedBitsSha256": canonical_sha256(positive_totals),
            "decisions": decisions,
            "unrelatedBefore": before,
            "unrelatedAfter": after,
            "cardPayloadSha256": canonical_sha256(card),
            "createdAt": now,
        }
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for output, payload in ((args.acceptance_output, acceptance), (args.card_output, card)):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✓ accepted review rows: {len(decisions)}")
    print(f"✓ accepted positive tags: {sum(len(item['acceptedBits']) for item in decisions)}")
    print(f"✓ local card communities: {len(card['communities'])}")
    print(f"Acceptance: {args.acceptance_output}")
    print(f"Card payload: {args.card_output}")
    print("Next: independently verify the acceptance and generate the local image; do not export or deploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
