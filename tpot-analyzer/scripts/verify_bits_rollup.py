#!/usr/bin/env python3
"""Verify bits rollup reproduces the current DB state.

Compares the computed rollup (from tweet_tags) against the existing
account_community_bits rows. Reports:
- total_bits mismatches (HARD FAILURE)
- missing keys in computed (HARD FAILURE — would lose data)
- extra keys in computed (expected — new tags discovered since last rollup)
- pct mismatches (expected if extra keys shift denominator)
- tweet_count migrations (0 → actual, expected — legacy field repair)

Exit 0 if total_bits match and no keys are missing. Exit 1 otherwise.

Usage:
    python scripts/verify_bits_rollup.py
    python scripts/verify_bits_rollup.py --db-path other.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rollup_bits import aggregate_bits, load_bits_tags, load_short_to_id

DEFAULT_DB_PATH = ROOT / "data" / "archive_tweets.db"
PCT_TOLERANCE = 0.5  # percent


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "\u2713" if ok else "\u2717"
    suffix = f"  ({detail})" if detail else ""
    print(f"  {status}  {label}{suffix}")
    return ok


def info(label: str, detail: str = "") -> None:
    """Informational note (not pass/fail)."""
    suffix = f"  ({detail})" if detail else ""
    print(f"  \u2139  {label}{suffix}")


def main():
    parser = argparse.ArgumentParser(description="Verify bits rollup against existing DB state")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"\u2717  Database not found: {args.db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    conn.row_factory = sqlite3.Row
    hard_ok = True  # only set to False for data-loss-risk issues

    # ── Load existing baseline ────────────────────────────────────────────────
    print("Loading existing account_community_bits...")
    existing_rows = conn.execute(
        "SELECT account_id, community_id, total_bits, tweet_count, pct FROM account_community_bits"
    ).fetchall()

    existing = {}
    for row in existing_rows:
        key = (row["account_id"], row["community_id"])
        existing[key] = {
            "total_bits": row["total_bits"],
            "tweet_count": row["tweet_count"],
            "pct": row["pct"],
        }
    existing_accounts = set(k[0] for k in existing)
    print(f"  Found {len(existing)} existing rows across {len(existing_accounts)} accounts\n")

    # ── Compute fresh rollup ──────────────────────────────────────────────────
    print("Computing fresh rollup from tweet_tags...")
    short_to_id = load_short_to_id(conn)
    tags = load_bits_tags(conn)
    computed = aggregate_bits(tags, short_to_id)
    print(f"  Computed {len(computed)} rows from {len(tags)} bits tags\n")

    # ── Compare ───────────────────────────────────────────────────────────────
    print("Comparison:")

    existing_keys = set(existing.keys())
    computed_keys = set(computed.keys())

    missing = existing_keys - computed_keys
    extra = computed_keys - existing_keys
    common = existing_keys & computed_keys

    # Missing keys = data loss risk → HARD FAILURE
    hard_ok &= check("No missing keys (would lose data)", len(missing) == 0,
                      f"{len(missing)} missing" if missing else "0")
    if missing:
        for key in sorted(missing):
            print(f"      MISSING: account={key[0]} community={key[1]} "
                  f"bits={existing[key]['total_bits']}")

    # Extra keys = new tags since last rollup → expected improvement
    if extra:
        accounts_with_extras = set(k[0] for k in extra)
        info(f"Extra keys (new tags discovered)", f"{len(extra)} new rows for {len(accounts_with_extras)} accounts")
        for key in sorted(extra):
            comm_short = next(
                (k for k, v in short_to_id.items() if v == key[1]),
                key[1][:8],
            )
            print(f"      NEW: account={key[0]} / {comm_short} bits={computed[key]['total_bits']}")
    else:
        check("No extra keys", True)

    # ── Check total_bits for common keys ──────────────────────────────────────
    bits_mismatches = []
    pct_mismatches = []
    pct_explained = []  # pct shifts explained by extra keys
    tweet_count_migrations = []

    # Which accounts have extra keys (their pct is expected to shift)
    accounts_with_extras = set(k[0] for k in extra)

    for key in sorted(common):
        e = existing[key]
        c = computed[key]

        if e["total_bits"] != c["total_bits"]:
            bits_mismatches.append((key, e["total_bits"], c["total_bits"]))

        pct_diff = abs(e["pct"] - c["pct"])
        if pct_diff > PCT_TOLERANCE:
            if key[0] in accounts_with_extras:
                # Shift explained by new communities in denominator
                pct_explained.append((key, e["pct"], c["pct"], pct_diff))
            else:
                pct_mismatches.append((key, e["pct"], c["pct"], pct_diff))

        # tweet_count: existing is 0 (legacy), computed is actual
        if e["tweet_count"] == 0 and c["tweet_count"] > 0:
            tweet_count_migrations.append((key, c["tweet_count"]))

    # total_bits mismatches → HARD FAILURE
    hard_ok &= check("total_bits match", len(bits_mismatches) == 0,
                      f"{len(bits_mismatches)} mismatches" if bits_mismatches else
                      f"all {len(common)} common keys match")
    if bits_mismatches:
        for key, existing_val, computed_val in bits_mismatches:
            print(f"      MISMATCH: {key} existing={existing_val} computed={computed_val}")

    # Unexplained pct mismatches → HARD FAILURE
    hard_ok &= check(f"pct match (tolerance {PCT_TOLERANCE}%)", len(pct_mismatches) == 0,
                      f"{len(pct_mismatches)} unexplained mismatches" if pct_mismatches else
                      f"all common keys within tolerance (excl. explained shifts)")
    if pct_mismatches:
        for key, existing_val, computed_val, diff in pct_mismatches:
            print(f"      MISMATCH: {key} existing={existing_val:.2f}% "
                  f"computed={computed_val:.2f}% diff={diff:.2f}%")

    # Explained pct shifts → informational
    if pct_explained:
        info(f"pct shifts explained by new communities",
             f"{len(pct_explained)} rows shifted (denominator changed)")
        for key, existing_val, computed_val, diff in pct_explained:
            comm_short = next(
                (k for k, v in short_to_id.items() if v == key[1]),
                key[1][:8],
            )
            print(f"      {key[0]} / {comm_short}: {existing_val:.2f}% → {computed_val:.2f}%")

    # ── tweet_count migration report (informational, not a failure) ───────────
    print(f"\ntweet_count migration (expected — legacy 0 → actual):")
    if tweet_count_migrations:
        check("tweet_count migrations detected", True,
              f"{len(tweet_count_migrations)} rows will gain tweet_count")
        for key, new_count in sorted(tweet_count_migrations, key=lambda x: -x[1])[:10]:
            comm_short = next(
                (k for k, v in short_to_id.items() if v == key[1]),
                key[1][:8],
            )
            print(f"      {key[0]} / {comm_short}: 0 \u2192 {new_count}")
        if len(tweet_count_migrations) > 10:
            print(f"      ... and {len(tweet_count_migrations) - 10} more")
    else:
        check("No tweet_count migrations needed", True)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if hard_ok:
        print("\u2713  PASS \u2014 rollup reproduces existing DB state")
        print(f"   {len(existing)} existing rows, {len(computed)} computed rows")
        delta = len(computed) - len(existing)
        if delta > 0:
            print(f"   +{delta} new rows from recently-added tags")
        print(f"   {len(tweet_count_migrations)} tweet_count fields will be repaired")
    else:
        print("\u2717  FAIL \u2014 rollup does NOT match existing DB state")
        print("   Review mismatches above before running rollup_bits.py")

    print()
    print("Next steps:")
    if hard_ok:
        print("  1. Run: python scripts/rollup_bits.py --dry-run")
        print("  2. Run: python scripts/rollup_bits.py")
        print("  3. Verify: python scripts/verify_bits_rollup.py")
    else:
        print("  1. Investigate mismatches listed above")
        print("  2. Check for manual edits to account_community_bits")

    conn.close()
    sys.exit(0 if hard_ok else 1)


if __name__ == "__main__":
    main()
