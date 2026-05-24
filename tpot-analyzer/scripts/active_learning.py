"""Active learning orchestrator — ties together fetch, context, ensemble labeling, and rollup.

CLI entry point for running active learning rounds:
  Round 1: select top-N accounts by info_value, fetch tweets, label with 3-model ensemble
  Round 2: targeted search for ambiguous accounts from round 1
  Measure: rollup bits, insert as seeds, report metrics

Usage:
    .venv/bin/python3 -m scripts.active_learning --round 1 --top 50 --budget 2.50
    .venv/bin/python3 -m scripts.active_learning --round 2 --budget 5.0
    .venv/bin/python3 -m scripts.active_learning --measure
    .venv/bin/python3 -m scripts.active_learning --round 1 --top 3 --dry-run

This file is the ORCHESTRATOR. Phase-specific helpers live in
`scripts/_active_learning_helpers/`. They're re-exported below so existing
imports (`from scripts.active_learning import select_accounts`, etc.) keep working.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

from scripts.active_learning_schema import create_tables
from scripts.fetch_tweets_for_account import (
    BudgetExhaustedError,
    assert_not_holdout,
    check_budget,
    fetch_multi_scale,
)
from scripts.assemble_context import assemble_account_context
from scripts.label_tweets_ensemble import build_consensus

# Re-export helpers for backward compatibility (tests import via scripts.active_learning)
from scripts._active_learning_helpers._account_selection import (
    _load_ego_hops,
    select_accounts,
    select_accounts_by_handle,
)
from scripts._active_learning_helpers._labeling import (
    _compute_account_bits_pct,
    _enrich_low_text_tweet,
    _label_single_tweet,
    _resolve_bio,
)
from scripts._active_learning_helpers._measurement import run_measure
from scripts._active_learning_helpers._reporting import (
    _extract_top_community,
    log_model_agreement,
    profile_results,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "archive_tweets.db"


def run_round_1(
    conn: sqlite3.Connection,
    twitter_key: str | None,
    openrouter_key: str,
    accounts: list[dict],
    budget: float,
    archive_only: bool = False,
    archive_limit: int = 20,
    enabled_signals: set | None = None,
) -> dict:
    """Execute round 1: fetch tweets, label with ensemble, profile.

    For each account:
      1. Budget check
      2. Holdout guard
      3. Fetch last tweets
      4. Parse + store
      5. Log API call
      6. Label each tweet with 3-model ensemble
      7. Triage based on accumulated bits

    Returns dict with keys: high, ambiguous, no_signal, errors —
    each a list of account dicts.
    """
    results: dict[str, list] = {
        "high": [],
        "ambiguous": [],
        "no_signal": [],
        "errors": [],
    }
    all_agreement_labels: list[list[dict]] = []

    for acct in accounts:
        account_id = acct["account_id"]
        username = acct["username"]

        try:
            # 1. Budget check only applies when Twitter API calls are allowed.
            if not archive_only:
                check_budget(conn, limit=budget, raise_on_exceed=True)

            # 2. Holdout guard
            assert_not_holdout(conn, account_id)

            # 3. Fetch tweets — multi-scale strategy
            # Top tweets (most-engaged), recent timeline, latest search, older window
            parsed, total_new = fetch_multi_scale(
                twitter_key, username, account_id, conn,
                round_num=1, budget_limit=budget,
                archive_only=archive_only,
                archive_limit=archive_limit,
            )

            # Dedup across all sources
            seen_ids = set()
            unique_parsed = []
            for t in parsed:
                if t["tweet_id"] not in seen_ids:
                    unique_parsed.append(t)
                    seen_ids.add(t["tweet_id"])
            parsed = unique_parsed

            logger.info(
                "Fetched %d tweets for @%s (%d new), info_value=%.3f",
                len(parsed), username, total_new, acct["info_value"],
            )

            # 7. Label each tweet
            account_ctx = assemble_account_context(
                conn,
                account_id=account_id,
                username=username,
                bio=_resolve_bio(conn, account_id),
                enabled_signals=enabled_signals,
            )

            # Tag retweets — still label them but with context that it's an RT
            n_rts = sum(1 for t in parsed if t.get("text", "").startswith("RT @"))
            if n_rts:
                logger.info("  %d/%d tweets are retweets (labeled with RT context)", n_rts, len(parsed))

            # Build accumulating prior as we label tweets
            bits_accumulator: dict[str, int] = {}  # community → total bits so far

            # Pre-compute which tweets already have tags (skip re-labeling)
            already_labeled = set(
                r[0] for r in conn.execute(
                    "SELECT DISTINCT tweet_id FROM tweet_tags"
                ).fetchall()
            )

            for tweet in parsed:
                # Skip tweets that already have labels (avoid re-paying LLM calls)
                if tweet.get("tweet_id") in already_labeled:
                    logger.debug("Skipping already-labeled tweet %s", tweet["tweet_id"])
                    continue

                # Build prior string from accumulated bits
                if bits_accumulator:
                    total = sum(bits_accumulator.values())
                    prior_parts = sorted(bits_accumulator.items(), key=lambda x: -x[1])
                    current_prior = ", ".join(f"{c}:{b*100//total}%" for c, b in prior_parts[:4])
                else:
                    current_prior = ""

                try:
                    per_model = _label_single_tweet(
                        conn, openrouter_key, tweet, account_ctx,
                        current_prior=current_prior,
                        allow_paid_api=not archive_only,
                    )
                    all_agreement_labels.append(per_model)

                    # Update accumulator from consensus bits
                    if per_model:
                        consensus = build_consensus(per_model)
                        for bit_tag in consensus.get("bits", []):
                            parts = bit_tag.split(":")
                            if len(parts) == 3:
                                comm = parts[1]
                                try:
                                    val = int(parts[2])
                                    bits_accumulator[comm] = bits_accumulator.get(comm, 0) + val
                                except ValueError:
                                    pass

                except Exception:
                    logger.exception(
                        "Error labeling tweet %s for @%s",
                        tweet["tweet_id"], username,
                    )

            # 7. Profile — compute bits pct for this account
            bits_pct = _compute_account_bits_pct(conn, account_id)
            profile = profile_results(bits_pct)
            acct_result = {**acct, "profile": profile, "tweets_fetched": len(parsed)}
            results[profile].append(acct_result)

            logger.info(
                "  @%s profile=%s bits=%s",
                username, profile,
                {k: f"{v:.1f}%" for k, v in sorted(bits_pct.items(), key=lambda x: -x[1])[:3]},
            )

        except BudgetExhaustedError as e:
            logger.warning("Budget exhausted: %s", e)
            results["errors"].append({**acct, "error": str(e)})
            break
        except Exception as e:
            logger.exception("Error processing @%s: %s", username, e)
            results["errors"].append({**acct, "error": str(e)})

    # Diagnostic: model agreement
    log_model_agreement(all_agreement_labels)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Active learning orchestrator for TPOT community labeling"
    )
    parser.add_argument(
        "--round", type=int, choices=[1, 2],
        help="Round number (1=initial fetch+label, 2=targeted search)",
    )
    parser.add_argument(
        "--top", type=int, default=50,
        help="Number of top accounts to process (default: 50)",
    )
    parser.add_argument(
        "--budget", type=float, default=5.0,
        help="Budget limit in USD (default: 5.0)",
    )
    parser.add_argument(
        "--measure", action="store_true",
        help="Run measurement: rollup + seed insertion for newly labeled accounts",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Select accounts but don't fetch or label",
    )
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB_PATH,
        help="Path to archive_tweets.db",
    )
    parser.add_argument(
        "--accounts", type=str, default=None,
        help="Comma-separated handles to label (bypasses frontier_ranking)",
    )
    parser.add_argument(
        "--accounts-file", type=Path, default=None,
        help="File with one handle per line (bypasses frontier_ranking)",
    )
    parser.add_argument(
        "--ego", type=str, default=None,
        help="Ego username for proximity boosting (e.g., adityaarpitha). "
             "Accounts closer to ego in follow graph get prioritized.",
    )
    parser.add_argument(
        "--archive-only", action="store_true",
        help="Use only archive tweets for selected accounts. Do not spend Twitter API credits.",
    )
    parser.add_argument(
        "--archive-limit", type=int, default=20,
        help="When --archive-only is set, label only the top-N archive tweets by engagement (default: 20).",
    )
    parser.add_argument(
        "--context", type=str, default=None,
        help="Comma-separated context signals to enable (default: all defaults). "
             "Options: bio,graph_signal,following_overlap,content_profile,"
             "engagement_partners,cofollowed,mention_communities,rt_source,"
             "reply_communities. Use 'all' for everything, 'minimal' for "
             "bio+graph_signal only.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not args.round and not args.measure:
        parser.error("Must specify --round or --measure")

    if not args.db_path.exists():
        logger.error("Database not found: %s", args.db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    create_tables(conn)

    if args.measure:
        metrics = run_measure(conn)
        print(f"\nMeasurement results: {json.dumps(metrics, indent=2)}")
        conn.close()
        return

    # Round execution
    round_num = args.round

    # Select accounts — three modes: --accounts, --accounts-file, or frontier_ranking
    if args.accounts:
        handles = [h.strip().lstrip("@") for h in args.accounts.split(",") if h.strip()]
        accounts = select_accounts_by_handle(conn, handles)
        logger.info("Selected %d accounts by handle", len(accounts))
    elif args.accounts_file:
        if not args.accounts_file.exists():
            logger.error("Accounts file not found: %s", args.accounts_file)
            conn.close()
            sys.exit(1)
        handles = [
            line.strip().lstrip("@")
            for line in args.accounts_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        accounts = select_accounts_by_handle(conn, handles)
        logger.info("Selected %d accounts from file %s", len(accounts), args.accounts_file)
    else:
        # Resolve ego account_id if provided
        ego_id = None
        if args.ego:
            ego_row = conn.execute(
                "SELECT account_id FROM profiles WHERE LOWER(username) = LOWER(?)",
                (args.ego.lstrip("@"),),
            ).fetchone()
            if ego_row:
                ego_id = ego_row[0]
                logger.info("Ego: @%s (id=%s)", args.ego, ego_id)
            else:
                logger.warning("Ego @%s not found in profiles — using pure info_value", args.ego)

        accounts = select_accounts(conn, top_n=args.top, round_num=round_num, ego_account_id=ego_id)
        logger.info(
            "Selected %d accounts for round %d (top_n=%d%s)",
            len(accounts), round_num, args.top,
            f", ego=@{args.ego}" if ego_id else "",
        )

    if not accounts:
        logger.info("No accounts to process — all already enriched or excluded")
        conn.close()
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would process {len(accounts)} accounts:")
        for acct in accounts:
            prox = acct.get("proximity", "n/a")
            priority = acct.get("priority", acct["info_value"])
            print(
                f"  @{acct['username']} (id={acct['account_id']}, "
                f"info_value={acct['info_value']:.4f}, "
                f"priority={priority:.4f}, proximity={prox}, "
                f"top_community={acct['top_community']})"
            )
        conn.close()
        return

    # Resolve API keys
    twitter_key = None
    if not args.archive_only:
        from scripts.fetch_tweets_for_account import get_api_key
        twitter_key = get_api_key()
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        logger.error("OPENROUTER_API_KEY not set")
        sys.exit(1)

    # Parse context signals
    enabled_signals = None
    if args.context:
        from scripts.assemble_context import CONTEXT_SIGNALS
        if args.context == "all":
            enabled_signals = set(CONTEXT_SIGNALS.keys())
        elif args.context == "minimal":
            enabled_signals = {"bio", "graph_signal"}
        else:
            enabled_signals = set(args.context.split(","))
        logger.info("Context signals enabled: %s", enabled_signals)

    if round_num == 1:
        results = run_round_1(
            conn, twitter_key, openrouter_key, accounts, args.budget,
            archive_only=args.archive_only,
            archive_limit=args.archive_limit,
            enabled_signals=enabled_signals,
        )
        print(f"\nRound 1 complete:")
        print(f"  High confidence: {len(results['high'])} accounts")
        print(f"  Ambiguous:       {len(results['ambiguous'])} accounts")
        print(f"  No signal:       {len(results['no_signal'])} accounts")
        print(f"  Errors:          {len(results['errors'])} accounts")
    elif round_num == 2:
        # Round 2: targeted search for ambiguous accounts
        results = run_round_1(
            conn, twitter_key, openrouter_key, accounts, args.budget,
            archive_only=args.archive_only,
            archive_limit=args.archive_limit,
            enabled_signals=enabled_signals,
        )
        print(f"\nRound 2 complete:")
        print(f"  High confidence: {len(results['high'])} accounts")
        print(f"  Ambiguous:       {len(results['ambiguous'])} accounts")
        print(f"  No signal:       {len(results['no_signal'])} accounts")
        print(f"  Errors:          {len(results['errors'])} accounts")

    conn.close()


if __name__ == "__main__":
    main()
