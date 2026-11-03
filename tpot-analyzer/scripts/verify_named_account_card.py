#!/usr/bin/env python3
"""Verify accepted named-account labels, scoped rollups, and local card data."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._named_account_acceptance import (  # noqa: E402
    canonical_sha256,
    unrelated_digests,
)

DEFAULT_DB = ROOT / "data" / "archive_tweets.db"
EXPECTED_BITS = {
    "Core-TPOT": 13,
    "highbies": 5,
    "LLM-Whisperers": 3,
    "Tech-Intellectuals": 2,
    "Relational-Explorers": 1,
}


class Checks:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str) -> None:
        print(f"{'✓' if ok else '✗'} {name}: {detail}")
        if not ok:
            self.failures += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a local named-account card")
    parser.add_argument("acceptance", type=Path)
    parser.add_argument("card", type=Path)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    checks = Checks()
    for name, path in (("acceptance receipt", args.acceptance), ("card payload", args.card)):
        checks.check(f"{name} exists", path.is_file(), str(path))
    if checks.failures:
        return 1
    acceptance = json.loads(args.acceptance.read_text(encoding="utf-8"))
    card = json.loads(args.card.read_text(encoding="utf-8"))
    checks.check(
        "human acceptance envelope",
        acceptance.get("decisionStatus") == "human-accepted"
        and acceptance.get("reviewer") == args.reviewer
        and acceptance.get("acceptedBits") == EXPECTED_BITS,
        f"reviewer={acceptance.get('reviewer')} bits={acceptance.get('acceptedBits')}",
    )
    checks.check(
        "card receipt binding",
        acceptance.get("cardPayloadSha256") == canonical_sha256(card),
        f"stored={acceptance.get('cardPayloadSha256')} current={canonical_sha256(card)}",
    )
    checks.check(
        "local-only card envelope",
        card.get("cardStatus") == "local-human-accepted"
        and card.get("publicStatus") == "not-exported"
        and card.get("handle") == args.username
        and card.get("accountId") == args.account_id,
        f"cardStatus={card.get('cardStatus')} publicStatus={card.get('publicStatus')}",
    )

    conn = sqlite3.connect(f"file:{args.db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tags = conn.execute(
            """SELECT tt.tweet_id,tt.tag,tt.category,tt.added_by FROM tweet_tags tt
               JOIN enriched_tweets et ON et.tweet_id=tt.tweet_id
               WHERE et.account_id=? ORDER BY tt.tweet_id,tt.tag""",
            (args.account_id,),
        ).fetchall()
        checks.check(
            "accepted tags only",
            len(tags) == 12 and all(row["category"] == "bits" and row["added_by"] == args.reviewer for row in tags)
            and all(":None:" not in row["tag"] for row in tags),
            f"rows={len(tags)} none_rows={sum(':None:' in row['tag'] for row in tags)}",
        )
        label_sets = conn.execute(
            """SELECT axis,reviewer,context_hash,context_snapshot_json FROM tweet_label_set
               WHERE tweet_id IN (SELECT tweet_id FROM enriched_tweets WHERE account_id=?)""",
            (args.account_id,),
        ).fetchall()
        checks.check(
            "twenty human review receipts",
            len(label_sets) == 20
            and all(row["axis"] == "community_bits" and row["reviewer"] == args.reviewer for row in label_sets)
            and all(row["context_hash"] == acceptance.get("sourceSha256") for row in label_sets),
            f"rows={len(label_sets)}",
        )
        rollup_rows = conn.execute(
            """SELECT c.short_name,acb.total_bits,acb.tweet_count,acb.pct
               FROM account_community_bits acb JOIN community c ON c.id=acb.community_id
               WHERE acb.account_id=? ORDER BY acb.pct DESC""",
            (args.account_id,),
        ).fetchall()
        rolled = {row["short_name"]: row["total_bits"] for row in rollup_rows}
        checks.check(
            "scoped community rollup",
            rolled == EXPECTED_BITS and abs(sum(row["pct"] for row in rollup_rows) - 100.0) < 1e-8,
            f"bits={rolled} pct_sum={sum(row['pct'] for row in rollup_rows):.6f}",
        )
        fp = conn.execute(
            """SELECT username,n_tweets_labeled,n_tweets_total,sample_method,evidence_ring,
                      simulacrum_json,posture_json,theme_json,domain_json,cadence_json
               FROM account_fingerprint WHERE account_id=?""",
            (args.account_id,),
        ).fetchone()
        checks.check(
            "scoped enriched fingerprint",
            fp is not None and fp["username"] == args.username and fp["n_tweets_labeled"] == 10
            and fp["n_tweets_total"] == 48 and fp["sample_method"] == "api_recent"
            and fp["evidence_ring"] == "enriched"
            and all(fp[name] is None for name in ("simulacrum_json", "posture_json", "theme_json", "domain_json")),
            f"username={fp['username'] if fp else None} labeled={fp['n_tweets_labeled'] if fp else None} total={fp['n_tweets_total'] if fp else None}",
        )
        current_unrelated = unrelated_digests(conn, args.account_id)
        checks.check(
            "unrelated state unchanged",
            acceptance.get("unrelatedBefore") == acceptance.get("unrelatedAfter") == current_unrelated,
            "all four unrelated table digests match",
        )
    finally:
        conn.close()

    communities = card.get("communities") if isinstance(card.get("communities"), list) else []
    checks.check(
        "card community payload",
        [row.get("short_name") for row in communities] == list(EXPECTED_BITS)
        and abs(sum(float(row.get("pct", 0)) for row in communities) - 100.0) < 1e-8
        and card.get("adjacentNoneBitsRejectedFromMembership") == 20,
        f"communities={[row.get('short_name') for row in communities]} sampleTweets={len(card.get('sampleTweets') or [])}",
    )
    checks.check(
        "card evidence sample",
        card.get("reviewedTweets") == 20 and card.get("positiveTweets") == 10
        and len(card.get("sampleTweets") or []) == 5,
        f"reviewed={card.get('reviewedTweets')} positive={card.get('positiveTweets')} samples={len(card.get('sampleTweets') or [])}",
    )
    if args.image:
        try:
            import struct
            with args.image.open("rb") as handle:
                signature = handle.read(8)
                length, chunk = struct.unpack(">I4s", handle.read(8))
                width, height = struct.unpack(">II", handle.read(8))
            valid = (
                signature == b"\x89PNG\r\n\x1a\n" and chunk == b"IHDR" and length == 13
                and width > 0 and height > width and abs((width / height) - (2 / 3)) < 0.08
            )
            checks.check("local card image", valid, f"{args.image} {width}x{height} PNG")
        except Exception as error:
            checks.check("local card image", False, str(error))

    print(f"\nSummary: {checks.failures} failed check(s).")
    if checks.failures:
        print("Next: stop before export/deployment and inspect the failed card check.")
    elif args.image:
        print("Next: review the local image; public export and deployment remain separate gates.")
    else:
        print("Next: generate the local image from this verified payload; do not export or deploy.")
    return 1 if checks.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
