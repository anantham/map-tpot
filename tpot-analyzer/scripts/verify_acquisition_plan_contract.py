"""Verify zero-credential acquisition plans and optionally freeze one privately."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.evaluation.acquisition_plan_contract import (
    hash_plan_manifest,
    worst_case_request_credits,
)
from src.evaluation.dossier_acquisition_plan import (
    build_dossier_acquisition_plan,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRICE_CARD = (
    ROOT / "data" / "manifests" / "twitterapiio_price_card_20260730.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load {field} at {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object: {path}")
    return value


def _panel_targets(panel: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = panel.get("accounts")
    if not isinstance(accounts, list) or len(accounts) != 12:
        raise ValueError("private panel must contain exactly 12 accounts")
    counts: dict[str, int] = {}
    targets = []
    for account in accounts:
        if not isinstance(account, dict):
            raise ValueError("each private panel account must be an object")
        stratum = account.get("stratum")
        counts[stratum] = counts.get(stratum, 0) + 1
        targets.append(
            {
                "handle": account.get("handle"),
                "fetch_profile": account.get("fetch_profile"),
                "recent_tweets_limit": account.get("recent_tweets_limit"),
            }
        )
    expected = {"likely_positive": 4, "boundary": 6, "likely_negative": 2}
    if counts != expected:
        raise ValueError(
            f"private panel strata mismatch: expected={expected}, observed={counts}"
        )
    return targets


def _holdout_and_coverage(
    db_path: Path,
    targets: list[dict[str, Any]],
) -> dict[str, int]:
    if not db_path.is_file():
        raise ValueError(f"archive DB does not exist: {db_path}")
    handles = [str(target["handle"]).lower() for target in targets]
    placeholders = ",".join("?" for _ in handles)
    uri = f"file:{db_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        holdout = conn.execute(
            f"""
            SELECT COUNT(DISTINCT lower(handle))
            FROM tpot_directory_holdout
            WHERE lower(handle) IN ({placeholders})
            """,
            handles,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT lower(p.username), COUNT(t.tweet_id)
            FROM profiles p
            LEFT JOIN tweets t ON t.account_id = p.account_id
            WHERE lower(p.username) IN ({placeholders})
            GROUP BY lower(p.username)
            """,
            handles,
        ).fetchall()
    return {
        "holdout_accounts": int(holdout),
        "profiles_present": len(rows),
        "accounts_with_tweets": sum(int(count) > 0 for _, count in rows),
    }


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as destination:
        destination.write(serialized)
    path.chmod(0o600)


def _check(label: str, passed: bool, detail: str) -> bool:
    print(f"{'✓' if passed else '✗'} {label}: {detail}")
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--price-card", type=Path, default=DEFAULT_PRICE_CARD)
    parser.add_argument("--panel", type=Path)
    parser.add_argument("--archive-db", type=Path)
    parser.add_argument("--write-plan", type=Path)
    parser.add_argument("--hard-cap-usd", default="0.05")
    parser.add_argument(
        "--planned-at",
        default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args(argv)
    if args.write_plan and not args.panel:
        parser.error("--write-plan requires --panel")

    checks = []
    try:
        price_card = _load_object(args.price_card, "price card")
        panel = _load_object(args.panel, "private panel") if args.panel else None
        targets = _panel_targets(panel) if panel else [
            {
                "handle": f"pilotacct{index:02d}",
                "fetch_profile": True,
                "recent_tweets_limit": 20,
            }
            for index in range(12)
        ]
        selection_hash = _sha256(args.panel) if args.panel else "0" * 64
        plan = build_dossier_acquisition_plan(
            targets=targets,
            price_card=price_card,
            selection_manifest_sha256=selection_hash,
            planned_at=args.planned_at,
            hard_cap_usd=args.hard_cap_usd,
            max_price_age_days=7,
        )
        checks.append(_check(
            "Followings reserve",
            worst_case_request_credits(price_card) == 398,
            f"{worst_case_request_credits(price_card)} credits/page worst case",
        ))
        reservation = plan["reservation"]
        checks.append(_check(
            "Dossier reserve",
            reservation["total_credits"] == 3846,
            f"{reservation['request_count']} calls; "
            f"{reservation['maximum_tweet_count']} tweets max; "
            f"${reservation['total_usd']}",
        ))
        checks.append(_check(
            "Balance telemetry reserve",
            plan["telemetry"]["pricing_status"] == "conservative_unverified"
            and reservation["telemetry_reserve_credits"] == 30,
            "2 calls; 30-credit conservative reserve; price unverified",
        ))
        checks.append(_check(
            "Plan cannot execute",
            plan["authorizes_execution"] is False,
            "authorizes_execution=false",
        ))
        checks.append(_check(
            "Plan self-hash",
            plan["plan_sha256"] == hash_plan_manifest(plan),
            plan["plan_sha256"],
        ))
        if panel:
            checks.append(_check(
                "Private panel",
                len(targets) == 12,
                f"12 accounts; selection_sha256={selection_hash}",
            ))
        if args.archive_db:
            coverage = _holdout_and_coverage(args.archive_db, targets)
            checks.append(_check(
                "Historical holdout exclusion",
                coverage["holdout_accounts"] == 0,
                f"overlap={coverage['holdout_accounts']}",
            ))
            print(
                "  local coverage: "
                f"profiles={coverage['profiles_present']}/12; "
                f"accounts_with_tweets={coverage['accounts_with_tweets']}/12"
            )
        if args.write_plan:
            _write_exclusive(args.write_plan, plan)
            print(f"  wrote private plan: {args.write_plan} (mode 0600)")
    except (ValueError, OSError, sqlite3.DatabaseError) as error:
        _check("Acquisition contract", False, str(error))
        print("Next: correct the manifest, price card, cap, or local DB; do not call the API.")
        return 1

    passed = sum(checks)
    print(f"\nchecks_passed={passed}/{len(checks)}")
    if passed != len(checks):
        print("Next: repair failed safety checks; do not authorize execution.")
        return 1
    print("Next: accept only the revised private plan hash in a fail-closed executor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
