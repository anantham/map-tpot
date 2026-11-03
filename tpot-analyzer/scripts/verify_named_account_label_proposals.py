#!/usr/bin/env python3
"""Verify a private named-account proposal receipt and unchanged DB boundary.

Test intent exception: this operational verifier exercises public CLI behavior
against the real receipt and read-only DB, printing pasteable checks and next
steps instead of adding implementation-coupled unit tests.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._named_account_proposals import (  # noqa: E402
    APPROVED_MODELS,
    account_interpretation_counts,
    load_account,
    open_read_only,
    select_tweets,
    source_receipt,
    valid_communities,
    validate_label,
)

DEFAULT_DB = ROOT / "data" / "archive_tweets.db"


class Checks:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str) -> None:
        print(f"{'✓' if ok else '✗'} {name}: {detail}")
        if not ok:
            self.failures += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify named-account label proposals")
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--username", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--expected-results", type=int, default=20)
    args = parser.parse_args()
    checks = Checks()
    checks.check("proposal receipt exists", args.receipt.is_file(), str(args.receipt))
    if not args.receipt.is_file():
        return 1
    try:
        artifact: dict[str, Any] = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        checks.check("proposal receipt parses", False, str(error))
        return 1

    checks.check(
        "proposal-only envelope",
        artifact.get("schemaVersion") == 1
        and artifact.get("proposalStatus") == "model-proposed"
        and artifact.get("goldStatus") == "not-gold"
        and artifact.get("permissions") == {
            "writeLabels": False, "measure": False, "export": False, "deploy": False,
        },
        f"status={artifact.get('proposalStatus')} gold={artifact.get('goldStatus')} permissions={artifact.get('permissions')}",
    )
    checks.check(
        "approved exact ensemble",
        artifact.get("models") == list(APPROVED_MODELS),
        ", ".join(artifact.get("models") or []),
    )
    results = artifact.get("results")
    results = results if isinstance(results, list) else []
    checks.check(
        "complete proposal batch",
        artifact.get("runStatus") == "complete" and len(results) == args.expected_results and not artifact.get("errors"),
        f"runStatus={artifact.get('runStatus')} results={len(results)} errors={artifact.get('errors')}",
    )

    conn = open_read_only(args.db_path)
    try:
        account = load_account(conn, args.username, args.account_id)
        current_tweets = select_tweets(conn, args.account_id, args.expected_results)
        current_source = source_receipt(account, current_tweets)
        stored_source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
        checks.check(
            "source receipt still matches",
            stored_source.get("sha256") == current_source["sha256"],
            f"stored={stored_source.get('sha256')} current={current_source['sha256']}",
        )
        communities = valid_communities(conn)
        validation_errors: list[str] = []
        seen_tweets: set[str] = set()
        proposed_bits: dict[str, int] = defaultdict(int)
        response_key_shapes: set[tuple[str, ...]] = set()
        usage_key_shapes: set[tuple[str, ...]] = set()
        calls = 0
        receipt_cost = 0.0
        for result in results:
            tweet = result.get("tweet") if isinstance(result, dict) else None
            tweet_id = str(tweet.get("tweet_id")) if isinstance(tweet, dict) else ""
            if not tweet_id or tweet_id in seen_tweets:
                validation_errors.append(f"missing or duplicate tweet_id: {tweet_id}")
            seen_tweets.add(tweet_id)
            model_rows = result.get("models") if isinstance(result, dict) else None
            if not isinstance(model_rows, list) or [row.get("model") for row in model_rows] != list(APPROVED_MODELS):
                validation_errors.append(f"tweet {tweet_id} model order/identity mismatch")
                model_rows = model_rows if isinstance(model_rows, list) else []
            for row in model_rows:
                calls += 1
                validation_errors.extend(
                    f"tweet {tweet_id} {row.get('model')}: {error}"
                    for error in validate_label(row.get("label"), communities)
                )
                receipt = row.get("receipt") if isinstance(row.get("receipt"), dict) else {}
                response_key_shapes.add(tuple(receipt.get("topLevelKeys") or []))
                usage_key_shapes.add(tuple(receipt.get("usageKeys") or []))
                if not receipt.get("responseId") or not isinstance(receipt.get("costUsd"), (int, float)):
                    validation_errors.append(f"tweet {tweet_id} {row.get('model')}: incomplete call receipt")
                else:
                    receipt_cost += float(receipt["costUsd"])
                if receipt.get("responseModel") != row.get("model"):
                    validation_errors.append(
                        f"tweet {tweet_id} requested {row.get('model')} but received {receipt.get('responseModel')}"
                    )
            consensus = result.get("consensus") if isinstance(result, dict) else None
            validation_errors.extend(
                f"tweet {tweet_id} consensus: {error}" for error in validate_label(consensus, communities)
            )
            if isinstance(consensus, dict):
                for tag in consensus.get("bits", []):
                    _, community, value = tag.split(":")
                    proposed_bits[community] += int(value)
        checks.check(
            "model and consensus validation",
            not validation_errors and calls == args.expected_results * len(APPROVED_MODELS),
            f"calls={calls} errors={len(validation_errors)}",
        )
        if validation_errors:
            for error in validation_errors[:10]:
                print(f"    ✗ {error}")
        checks.check(
            "response schemas were recorded",
            len(response_key_shapes) >= 1 and all("choices" in shape for shape in response_key_shapes)
            and len(usage_key_shapes) >= 1 and all("prompt_tokens" in shape for shape in usage_key_shapes),
            f"response_shapes={len(response_key_shapes)} usage_shapes={len(usage_key_shapes)}",
        )
        stored_bits = artifact.get("proposedBits")
        checks.check(
            "proposed bit rollup reconciles",
            stored_bits == dict(sorted(proposed_bits.items(), key=lambda item: -item[1])),
            json.dumps(stored_bits, sort_keys=True),
        )
        cost = artifact.get("observedCostUsd")
        cap = artifact.get("maxUsd")
        checks.check(
            "per-call costs reconcile",
            isinstance(cost, (int, float)) and abs(receipt_cost - float(cost)) < 1e-8,
            f"receipt_sum=${receipt_cost:.10f} artifact=${cost}",
        )
        checks.check(
            "cost stayed within cap",
            isinstance(cost, (int, float)) and isinstance(cap, (int, float)) and 0 < cost <= cap,
            f"observed=${cost} cap=${cap}",
        )
        counts = account_interpretation_counts(conn, args.account_id)
        checks.check(
            "accepted-label and card boundary unchanged",
            not any(counts.values()),
            json.dumps(counts, sort_keys=True),
        )
    finally:
        conn.close()

    print(f"\nSummary: {checks.failures} failed check(s).")
    if checks.failures:
        print("Next: do not accept or measure these proposals; inspect the failed receipt checks.")
    else:
        print("Next: review the proposed communities and evidence; acceptance remains a separate write gate.")
        print("Do not measure, export, upload, or deploy until the human accepts the proposals.")
    return 1 if checks.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
