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
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from scripts.active_learning_schema import create_tables
from scripts.fetch_tweets_for_account import (
    BudgetExhaustedError,
    assert_not_holdout,
    check_budget,
    fetch_last_tweets,
    log_api_call,
    parse_tweet,
    store_tweets,
)
from scripts.assemble_context import (
    assemble_account_context,
    assemble_tweet_context,
)
from scripts.label_tweets_ensemble import (
    MODELS,
    build_consensus,
    build_prompt,
    call_model,
    parse_label_json,
    store_labels,
    validate_bits,
    VALID_SHORT_NAMES,
    load_short_names_from_db,
)
from scripts.rollup_bits import (
    load_bits_tags,
    load_short_to_id,
    aggregate_bits,
    scoped_delete_bits,
    write_rollup,
    compute_discount,
)
from scripts.insert_seeds import insert_llm_seeds

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "archive_tweets.db"


# ═══════════════════════════════════════════════════════════════════════════
# Account selection
# ═══════════════════════════════════════════════════════════════════════════


def select_accounts(
    conn: sqlite3.Connection, top_n: int, round_num: int
) -> list[dict]:
    """Select top accounts from frontier_ranking for enrichment.

    Excludes:
      - holdout accounts (in_holdout=1 OR in tpot_directory_holdout)
      - already enriched (>=20 tweets in enriched_tweets)
      - accounts with no resolvable username (profiles OR resolved_accounts)

    Returns list of dicts sorted by info_value DESC.
    """
    sql = """
        SELECT fr.account_id, fr.info_value, fr.top_community,
               COALESCE(p.username, ra.username) as username
        FROM frontier_ranking fr
        LEFT JOIN profiles p ON fr.account_id = p.account_id
        LEFT JOIN resolved_accounts ra ON fr.account_id = ra.account_id
        WHERE fr.in_holdout = 0
        AND COALESCE(p.username, ra.username) IS NOT NULL
        AND fr.account_id NOT IN (
            SELECT account_id FROM tpot_directory_holdout
            WHERE account_id IS NOT NULL
        )
        AND fr.account_id NOT IN (
            SELECT account_id FROM enriched_tweets
            GROUP BY account_id HAVING COUNT(*) >= 20
        )
        ORDER BY fr.info_value DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (top_n,)).fetchall()
    return [
        {
            "account_id": row[0],
            "info_value": row[1],
            "top_community": row[2],
            "username": row[3],
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Triage
# ═══════════════════════════════════════════════════════════════════════════


def triage_results(bits: dict[str, float]) -> str:
    """Classify account labeling results by confidence.

    Returns:
      - "no_signal" if bits is empty
      - "high" if top community > 60% OR any community > 40%
      - "ambiguous" if no community > 40%
    """
    if not bits:
        return "no_signal"

    top_pct = max(bits.values())

    if top_pct > 60.0:
        return "high"
    if top_pct <= 40.0:
        return "ambiguous"
    return "high"


# ═══════════════════════════════════════════════════════════════════════════
# Model agreement diagnostic
# ═══════════════════════════════════════════════════════════════════════════


def _extract_top_community(label_dict: dict) -> str | None:
    """Extract the top community from a single model's label output."""
    bits = label_dict.get("bits", [])
    best_community = None
    best_value = -999

    for tag in bits:
        parts = tag.split(":")
        if len(parts) == 3 and parts[0] == "bits":
            try:
                val = int(parts[2])
                if val > best_value:
                    best_value = val
                    best_community = parts[1]
            except ValueError:
                continue

    return best_community


def log_model_agreement(all_labels: list[list[dict]]) -> None:
    """Log inter-model agreement across all labeled tweets.

    all_labels: list of per-tweet lists, where each inner list has one dict
    per model (up to 3).

    Prints the percentage of tweets where all models agree on the top community.
    """
    if not all_labels:
        print("Model agreement: no tweets labeled")
        return

    total = 0
    agreed = 0

    for tweet_labels in all_labels:
        if len(tweet_labels) < 2:
            continue
        total += 1

        tops = [_extract_top_community(ld) for ld in tweet_labels]
        tops = [t for t in tops if t is not None]

        if len(tops) >= 2 and len(set(tops)) == 1:
            agreed += 1

    if total == 0:
        print("Model agreement: no multi-model tweets to compare")
        return

    pct = agreed / total * 100
    print(f"Model agreement: {agreed}/{total} tweets ({pct:.1f}%) — all models agree on top community")


# ═══════════════════════════════════════════════════════════════════════════
# Round 1: Fetch + Label
# ═══════════════════════════════════════════════════════════════════════════


def _label_single_tweet(
    conn: sqlite3.Connection,
    openrouter_key: str,
    tweet: dict,
    account_ctx: dict,
) -> list[dict]:
    """Label a single tweet with all models, store consensus.

    Returns list of per-model label dicts (for agreement tracking).
    """
    tweet_ctx = assemble_tweet_context(
        conn,
        tweet_id=tweet["tweet_id"],
        tweet_text=tweet["text"],
        engagement_stats=f"likes={tweet.get('like_count', 0)} rt={tweet.get('retweet_count', 0)} replies={tweet.get('reply_count', 0)}",
        mentions=tweet.get("mentions_json", "[]"),
    )

    prompt_text = build_prompt(
        username=account_ctx["username"],
        bio=account_ctx.get("bio", ""),
        graph_signal=account_ctx["graph_signal"],
        other_tweets="",  # Could aggregate other tweets here in future
        tweet_text=tweet_ctx["tweet_text"],
        engagement=tweet_ctx["engagement_stats"],
        mentions=tweet_ctx["mentions"],
        engagement_context=tweet_ctx["engagement_context"],
        community_descriptions=account_ctx["community_descriptions"],
        community_short_names=account_ctx["community_short_names"],
    )

    # Split prompt into system + user at the --- delimiter
    parts = prompt_text.split("\n---\n\n", 1)
    system_prompt = parts[0] if len(parts) == 2 else prompt_text
    user_prompt = parts[1] if len(parts) == 2 else ""

    model_labels: list[dict] = []

    for model in MODELS:
        try:
            raw = call_model(openrouter_key, model, system_prompt, user_prompt)
            parsed = parse_label_json(raw)
            if parsed:
                model_labels.append(parsed)
            else:
                logger.warning(
                    "Failed to parse label from %s for tweet %s",
                    model, tweet["tweet_id"],
                )
        except Exception:
            logger.exception(
                "Error calling model %s for tweet %s",
                model, tweet["tweet_id"],
            )

    if len(model_labels) >= 2:
        consensus = build_consensus(model_labels)
        store_labels(conn, tweet["tweet_id"], consensus, reviewer="llm_ensemble")

    return model_labels


def run_round_1(
    conn: sqlite3.Connection,
    twitter_key: str,
    openrouter_key: str,
    accounts: list[dict],
    budget: float,
) -> dict:
    """Execute round 1: fetch tweets, label with ensemble, triage.

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
            # 1. Budget check
            check_budget(conn, limit=budget, raise_on_exceed=True)

            # 2. Holdout guard
            assert_not_holdout(conn, account_id)

            # 3. Fetch tweets
            raw_tweets, author_info = fetch_last_tweets(twitter_key, username)

            # 4. Parse + store
            parsed = [parse_tweet(t, username) for t in raw_tweets]
            inserted = store_tweets(conn, parsed, fetch_source="last_tweets")

            # 5. Log API call
            log_api_call(
                conn,
                account_id=account_id,
                username=username,
                round_num=1,
                action="last_tweets",
                tweets_fetched=len(parsed),
            )

            logger.info(
                "Fetched %d tweets for @%s (%d new), info_value=%.3f",
                len(parsed), username, inserted, acct["info_value"],
            )

            # 6. Label each tweet
            account_ctx = assemble_account_context(
                conn,
                account_id=account_id,
                username=username,
                bio=_resolve_bio(conn, account_id),
            )

            for tweet in parsed:
                try:
                    per_model = _label_single_tweet(
                        conn, openrouter_key, tweet, account_ctx
                    )
                    all_agreement_labels.append(per_model)
                except Exception:
                    logger.exception(
                        "Error labeling tweet %s for @%s",
                        tweet["tweet_id"], username,
                    )

            # 7. Triage — compute bits pct for this account
            bits_pct = _compute_account_bits_pct(conn, account_id)
            triage = triage_results(bits_pct)
            acct_result = {**acct, "triage": triage, "tweets_fetched": len(parsed)}
            results[triage].append(acct_result)

            logger.info(
                "  @%s triage=%s bits=%s",
                username, triage,
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


def _resolve_bio(conn: sqlite3.Connection, account_id: str) -> str:
    """Resolve bio from profiles or resolved_accounts."""
    row = conn.execute(
        "SELECT bio FROM profiles WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row and row[0]:
        return row[0]

    row = conn.execute(
        "SELECT bio FROM resolved_accounts WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row and row[0]:
        return row[0]

    return ""


def _compute_account_bits_pct(
    conn: sqlite3.Connection, account_id: str
) -> dict[str, float]:
    """Compute bits percentage distribution for an account from tweet_tags.

    Returns {community_short_name: pct} where pct sums to ~100.
    """
    rows = conn.execute(
        """
        SELECT tt.tag
        FROM tweet_tags tt
        JOIN enriched_tweets e ON e.tweet_id = tt.tweet_id
        WHERE e.account_id = ? AND tt.category = 'bits'
        """,
        (account_id,),
    ).fetchall()

    if not rows:
        return {}

    community_bits: dict[str, int] = defaultdict(int)
    for (tag,) in rows:
        parts = tag.split(":")
        if len(parts) == 3 and parts[0] == "bits":
            try:
                community_bits[parts[1]] += abs(int(parts[2]))
            except ValueError:
                continue

    total = sum(community_bits.values())
    if total == 0:
        return {}

    return {comm: (val / total * 100) for comm, val in community_bits.items()}


# ═══════════════════════════════════════════════════════════════════════════
# Measure: rollup + seed insertion
# ═══════════════════════════════════════════════════════════════════════════


def run_measure(conn: sqlite3.Connection) -> dict:
    """Rollup bits for newly labeled accounts, insert as propagation seeds.

    Steps:
      1. Find accounts with enriched tweets not yet in community_account
         with source='llm_ensemble'
      2. Run scoped rollup for those accounts
      3. Insert as seeds via insert_llm_seeds

    Returns metrics dict with account counts and rows inserted.
    """
    # 1. Find newly labeled accounts (have enriched_tweets + tweet_tags bits,
    #    but NOT in community_account with source='llm_ensemble')
    new_accounts_rows = conn.execute(
        """
        SELECT DISTINCT e.account_id
        FROM enriched_tweets e
        JOIN tweet_tags tt ON tt.tweet_id = e.tweet_id AND tt.category = 'bits'
        WHERE e.account_id NOT IN (
            SELECT account_id FROM community_account WHERE source = 'llm_ensemble'
        )
        """
    ).fetchall()
    new_account_ids = [r[0] for r in new_accounts_rows]

    if not new_account_ids:
        logger.info("No newly labeled accounts to measure")
        return {"new_accounts": 0, "rollup_rows": 0, "seeds_inserted": 0}

    logger.info("Found %d newly labeled accounts for measurement", len(new_account_ids))

    # 2. Run rollup — load tags, aggregate, write scoped
    short_to_id = load_short_to_id(conn)
    tags = load_bits_tags(conn)

    # Filter tags to only new accounts
    account_set = set(new_account_ids)
    filtered_tags = [(a, t, tag) for a, t, tag in tags if a in account_set]

    rollup = aggregate_bits(filtered_tags, short_to_id)

    # Apply informativeness discount
    for (account_id, community_id), data in rollup.items():
        discount = compute_discount(conn, account_id)
        data["total_bits"] = int(data["total_bits"] * discount)
        data["weighted_bits"] = data["weighted_bits"] * discount

    # Scoped delete + insert (don't wipe existing rollup for archive accounts)
    scoped_delete_bits(conn, new_account_ids)
    rollup_rows = write_rollup(conn, rollup)

    # 3. Insert as seeds
    seeds_inserted = insert_llm_seeds(conn, new_account_ids)

    print(
        "NOTE: Recall measured WITHOUT TF-IDF context — "
        "may underestimate pipeline potential"
    )

    metrics = {
        "new_accounts": len(new_account_ids),
        "rollup_rows": rollup_rows,
        "seeds_inserted": seeds_inserted,
    }
    logger.info("Measure complete: %s", metrics)
    return metrics


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


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

    conn = sqlite3.connect(str(args.db_path))
    create_tables(conn)

    if args.measure:
        metrics = run_measure(conn)
        print(f"\nMeasurement results: {json.dumps(metrics, indent=2)}")
        conn.close()
        return

    # Round execution
    round_num = args.round

    # Select accounts
    accounts = select_accounts(conn, top_n=args.top, round_num=round_num)
    logger.info(
        "Selected %d accounts for round %d (top_n=%d)",
        len(accounts), round_num, args.top,
    )

    if not accounts:
        logger.info("No accounts to process — all already enriched or excluded")
        conn.close()
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would process {len(accounts)} accounts:")
        for acct in accounts:
            print(
                f"  @{acct['username']} (id={acct['account_id']}, "
                f"info_value={acct['info_value']:.4f}, "
                f"top_community={acct['top_community']})"
            )
        conn.close()
        return

    # Resolve API keys
    from scripts.fetch_tweets_for_account import get_api_key

    twitter_key = get_api_key()
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        logger.error("OPENROUTER_API_KEY not set")
        sys.exit(1)

    if round_num == 1:
        results = run_round_1(
            conn, twitter_key, openrouter_key, accounts, args.budget
        )
        print(f"\nRound 1 complete:")
        print(f"  High confidence: {len(results['high'])} accounts")
        print(f"  Ambiguous:       {len(results['ambiguous'])} accounts")
        print(f"  No signal:       {len(results['no_signal'])} accounts")
        print(f"  Errors:          {len(results['errors'])} accounts")
    elif round_num == 2:
        # Round 2: targeted search for ambiguous accounts
        # For now, same flow as round 1 but could use advanced_search
        results = run_round_1(
            conn, twitter_key, openrouter_key, accounts, args.budget
        )
        print(f"\nRound 2 complete:")
        print(f"  High confidence: {len(results['high'])} accounts")
        print(f"  Ambiguous:       {len(results['ambiguous'])} accounts")
        print(f"  No signal:       {len(results['no_signal'])} accounts")
        print(f"  Errors:          {len(results['errors'])} accounts")

    conn.close()


if __name__ == "__main__":
    main()
