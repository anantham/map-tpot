#!/usr/bin/env python3
"""LLM tweet classification harness.

Classifies tweets on the simulacrum axis using few-shot prompting via
OpenRouter.  Results are ingested into the golden dataset pipeline and
evaluated against human labels when available.

Usage
-----
  # Pilot: 10 accounts, 50 tweets each, kimi-k2.5 (cheapest)
  python -m scripts.classify_tweets --accounts 10 --tweets-per-account 50

  # Full dev-split classification
  python -m scripts.classify_tweets --split dev

  # Multi-model benchmark
  python -m scripts.classify_tweets --model anthropic/claude-sonnet-4 --prompt-version v1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TAXONOMY_PATH = _PROJECT_ROOT / "data" / "golden" / "taxonomy.yaml"
_DB_PATH = _PROJECT_ROOT / "data" / "archive_tweets.db"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "moonshotai/kimi-k2.5"
PROMPT_VERSION = "v1"
AXIS = "simulacrum"
LABELS = ("l1", "l2", "l3", "l4")

# Rate-limiting
REQUESTS_PER_MINUTE = 30  # conservative default for OpenRouter free tier
REQUEST_INTERVAL = 60.0 / REQUESTS_PER_MINUTE

logger = logging.getLogger("classify_tweets")


# ═══════════════════════════════════════════════════════════════════════════
# Prompt building
# ═══════════════════════════════════════════════════════════════════════════

def load_taxonomy() -> dict:
    """Load taxonomy.yaml and return parsed dict."""
    if not _TAXONOMY_PATH.exists():
        logger.error("Taxonomy not found at %s", _TAXONOMY_PATH)
        sys.exit(1)
    with open(_TAXONOMY_PATH) as f:
        return yaml.safe_load(f) or {}


def build_prompt(taxonomy: dict, tweet_text: str) -> str:
    """Build a few-shot classification prompt from taxonomy + tweet.

    Mirrors the prompt structure in golden.py _build_interpret_prompt but
    streamlined for batch use (no thread context in V1).
    """
    sim = taxonomy.get("simulacrum", {})
    levels = sim.get("levels", {})

    lines = [
        "You are a tweet classification system. Classify the tweet below",
        "into the Simulacrum Level taxonomy. Output a probability",
        "distribution across four levels (l1, l2, l3, l4) summing to 1.0.",
        "",
        "TAXONOMY:",
    ]

    for key in LABELS:
        level = levels.get(key, {})
        name = level.get("name", key)
        defn = (level.get("definition") or "").strip().replace("\n", " ")
        test = (level.get("key_test") or "").strip()
        lines.append(f"  {key.upper()} ({name}): {defn}")
        if test:
            lines.append(f"    Key test: {test}")

    lines.append("\nGOLDEN EXAMPLES:")
    for key in LABELS:
        level = levels.get(key, {})
        for ex in (level.get("examples") or {}).get("positive", []):
            tweet = (ex.get("tweet") or "").strip()[:200]
            dist = ex.get("distribution", {})
            note = (ex.get("note") or "").strip()[:200]
            if tweet and dist:
                lines.append(f'  Tweet: "{tweet}"')
                lines.append(f"  Classification: {json.dumps(dist)}")
                if note:
                    lines.append(f"  Note: {note}")
                lines.append("")

    lines.append(f'NOW CLASSIFY THIS TWEET:\n"{tweet_text.strip()[:500]}"\n')
    lines.append(
        'Return ONLY valid JSON: {"distribution": {"l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.0}}\n'
        "Rules: values sum to 1.0. No extra keys, no markdown fences."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# OpenRouter API
# ═══════════════════════════════════════════════════════════════════════════

def call_openrouter(
    prompt: str,
    model: str,
    api_key: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 200,
    timeout: float = 30.0,
) -> dict:
    """Call OpenRouter and return the raw response JSON."""
    resp = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def parse_response(raw_response: dict) -> Optional[Dict[str, float]]:
    """Extract and validate the distribution from an OpenRouter response.

    Returns None if parsing fails (caller handles as skip).
    """
    content = (
        raw_response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    # Strip markdown fences
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Non-JSON response: %.100s", content)
        return None

    dist = parsed.get("distribution", parsed)  # allow flat dict too
    if not isinstance(dist, dict):
        logger.warning("No distribution in response: %s", type(dist))
        return None

    # Validate keys
    try:
        result = {k: float(dist.get(k, 0.0)) for k in LABELS}
    except (TypeError, ValueError):
        logger.warning("Non-numeric values in distribution: %s", dist)
        return None

    # Normalize
    total = sum(result.values())
    if total <= 0:
        logger.warning("Zero-sum distribution")
        return None
    if abs(total - 1.0) > 0.05:
        logger.info("Distribution sums to %.3f, normalizing", total)
    result = {k: round(v / total, 4) for k, v in result.items()}

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Tweet selection
# ═══════════════════════════════════════════════════════════════════════════

def _split_for_tweet(tweet_id: str) -> str:
    """Deterministic split assignment via SHA256 hash (mirrors schema.py)."""
    import hashlib
    bucket = int(hashlib.sha256(tweet_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "dev"
    return "test"


def select_tweets(
    db_path: Path,
    *,
    num_accounts: Optional[int] = None,
    tweets_per_account: int = 100,
    split: Optional[str] = None,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Select tweets to classify from the archive database.

    Picks a random sample of accounts, then selects tweets_per_account
    from each.  Uses client-side deterministic hash for split filtering
    instead of joining with curation_split (avoids scanning 5.5M rows).

    When split is specified, we over-fetch (~3x for dev/test which are 15%
    each) and filter in Python using the same SHA256 hash as the DB.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get distinct accounts
    accounts = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT account_id FROM tweets ORDER BY account_id"
        ).fetchall()
    ]
    if num_accounts and num_accounts < len(accounts):
        rng = random.Random(seed)
        accounts = rng.sample(accounts, num_accounts)

    logger.info("Selected %d accounts", len(accounts))

    # Over-fetch ratio: dev/test are ~15% each, so fetch 7x to get enough
    fetch_limit = tweets_per_account if not split else tweets_per_account * 7

    tweets = []
    for acct in accounts:
        rows = conn.execute(
            """
            SELECT tweet_id, account_id, username, full_text
            FROM tweets
            WHERE account_id = ?
              AND full_text IS NOT NULL AND length(full_text) > 20
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (acct, fetch_limit),
        ).fetchall()

        count = 0
        for r in rows:
            tid = r["tweet_id"]
            if split and _split_for_tweet(tid) != split:
                continue
            tweets.append({
                "tweet_id": tid,
                "account_id": r["account_id"],
                "username": r["username"],
                "text": r["full_text"],
            })
            count += 1
            if count >= tweets_per_account:
                break

    conn.close()
    logger.info("Selected %d tweets from %d accounts", len(tweets), len(accounts))
    return tweets


def get_already_classified(
    db_path: Path,
    model_name: str,
    prompt_version: str,
) -> set:
    """Return set of tweet_ids already classified by this model+prompt."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT p.tweet_id
            FROM model_prediction_set p
            WHERE p.model_name = ? AND p.prompt_version = ?
            """,
            (model_name, prompt_version),
        ).fetchall()
        return {r[0] for r in rows}
    except sqlite3.OperationalError:
        # Table may not exist yet
        return set()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Batch classification
# ═══════════════════════════════════════════════════════════════════════════

def classify_tweets(
    tweets: List[Dict[str, Any]],
    taxonomy: dict,
    model: str,
    api_key: str,
    *,
    budget_dollars: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Classify a list of tweets, returning prediction dicts.

    Respects rate limits and optional budget cap.
    """
    predictions = []
    total_cost = 0.0
    errors = 0
    skipped = 0

    for i, tweet in enumerate(tweets):
        # Budget check (rough estimate: ~500 tokens/call, kimi-k2.5 ~ $0.0003/call)
        if budget_dollars and total_cost >= budget_dollars:
            logger.info("Budget cap $%.2f reached after %d tweets", budget_dollars, i)
            break

        prompt = build_prompt(taxonomy, tweet["text"])

        try:
            raw = call_openrouter(prompt, model, api_key)
            dist = parse_response(raw)

            if dist is None:
                skipped += 1
                logger.warning(
                    "[%d/%d] SKIP %s — parse failure",
                    i + 1, len(tweets), tweet["tweet_id"],
                )
                continue

            predictions.append({
                "tweet_id": tweet["tweet_id"],
                "distribution": dist,
                "parse_status": "ok",
                "raw_response_json": raw,
            })

            # Rough cost tracking (kimi-k2.5: ~$0.14/M input, $0.28/M output)
            usage = raw.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 500)
            output_tokens = usage.get("completion_tokens", 50)
            call_cost = (input_tokens * 0.14 + output_tokens * 0.28) / 1_000_000
            total_cost += call_cost

            if (i + 1) % 10 == 0:
                logger.info(
                    "[%d/%d] %s → L%s (%.0f%%)  est_cost=$%.4f",
                    i + 1,
                    len(tweets),
                    tweet["username"],
                    max(dist, key=dist.get).replace("l", ""),
                    max(dist.values()) * 100,
                    total_cost,
                )

        except httpx.HTTPStatusError as exc:
            errors += 1
            logger.error(
                "[%d/%d] HTTP %s: %s",
                i + 1, len(tweets),
                exc.response.status_code,
                exc.response.text[:200],
            )
            if exc.response.status_code == 429:
                logger.info("Rate limited, sleeping 60s")
                time.sleep(60)
            elif exc.response.status_code >= 500:
                time.sleep(5)
            else:
                # Client error (auth, bad model) — stop
                logger.error("Fatal client error, stopping")
                break

        except httpx.TimeoutException:
            errors += 1
            logger.warning("[%d/%d] Timeout", i + 1, len(tweets))
            time.sleep(5)

        # Rate limiting
        time.sleep(REQUEST_INTERVAL)

    logger.info(
        "Classification complete: %d predictions, %d skipped, %d errors, est_cost=$%.4f",
        len(predictions), skipped, errors, total_cost,
    )
    return predictions


# ═══════════════════════════════════════════════════════════════════════════
# Ingestion & evaluation
# ═══════════════════════════════════════════════════════════════════════════

def ingest_predictions(
    predictions: List[Dict[str, Any]],
    *,
    model_name: str,
    model_version: Optional[str],
    prompt_version: str,
    run_id: str,
    api_base: str = "http://localhost:5001",
) -> dict:
    """POST predictions to the golden API for storage."""
    # Strip raw_response_json to keep payload small
    clean = []
    for p in predictions:
        clean.append({
            "tweet_id": p["tweet_id"],
            "distribution": p["distribution"],
            "parse_status": p.get("parse_status", "ok"),
        })

    resp = httpx.post(
        f"{api_base}/api/golden/predictions/run",
        json={
            "axis": AXIS,
            "model_name": model_name,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "run_id": run_id,
            "reviewer": "llm_classifier",
            "predictions": clean,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def run_evaluation(
    *,
    model_name: str,
    model_version: Optional[str],
    prompt_version: str,
    split: str = "dev",
    api_base: str = "http://localhost:5001",
) -> dict:
    """POST eval request and return Brier score results."""
    run_id = f"eval_{uuid4().hex[:12]}"
    resp = httpx.post(
        f"{api_base}/api/golden/eval/run",
        json={
            "axis": AXIS,
            "model_name": model_name,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "split": split,
            "threshold": 0.18,
            "reviewer": "human",
            "run_id": run_id,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Classify tweets on the simulacrum axis via LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"OpenRouter model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--model-version", default=None,
        help="Model version tag for tracking",
    )
    parser.add_argument(
        "--prompt-version", default=PROMPT_VERSION,
        help=f"Prompt version tag (default: {PROMPT_VERSION})",
    )
    parser.add_argument(
        "--accounts", type=int, default=None,
        help="Number of accounts to sample (default: all)",
    )
    parser.add_argument(
        "--tweets-per-account", type=int, default=100,
        help="Tweets per account (default: 100)",
    )
    parser.add_argument(
        "--split", default=None, choices=["train", "dev", "test"],
        help="Only classify tweets in this curation split",
    )
    parser.add_argument(
        "--budget", type=float, default=None,
        help="Max estimated spend in USD",
    )
    parser.add_argument(
        "--api-base", default="http://localhost:5001",
        help="Backend API base URL",
    )
    parser.add_argument(
        "--db", default=str(_DB_PATH),
        help=f"Path to archive_tweets.db (default: {_DB_PATH})",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for account sampling",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Select tweets and build prompt but don't call LLM",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key and not args.dry_run:
        logger.error("OPENROUTER_API_KEY not set. Export it or use --dry-run.")
        sys.exit(1)

    db_path = Path(args.db)
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    # Load taxonomy
    taxonomy = load_taxonomy()
    logger.info("Loaded taxonomy with %d levels", len(taxonomy.get("simulacrum", {}).get("levels", {})))

    # Select tweets
    tweets = select_tweets(
        db_path,
        num_accounts=args.accounts,
        tweets_per_account=args.tweets_per_account,
        split=args.split,
        seed=args.seed,
    )

    if not tweets:
        logger.error("No tweets selected. Check --accounts, --split, --tweets-per-account.")
        sys.exit(1)

    # Resume: skip already-classified tweets
    already = get_already_classified(db_path, args.model, args.prompt_version)
    if already:
        before = len(tweets)
        tweets = [t for t in tweets if t["tweet_id"] not in already]
        logger.info("Resume: skipping %d already-classified, %d remaining", before - len(tweets), len(tweets))

    if not tweets:
        logger.info("All selected tweets already classified. Nothing to do.")
        sys.exit(0)

    # Dry run
    if args.dry_run:
        sample = tweets[0]
        prompt = build_prompt(taxonomy, sample["text"])
        print(f"\n{'='*60}")
        print(f"DRY RUN: {len(tweets)} tweets selected")
        print(f"Model: {args.model}")
        print(f"Sample tweet ({sample['username']}): {sample['text'][:100]}...")
        print(f"\n--- PROMPT ({len(prompt)} chars) ---")
        print(prompt)
        print(f"{'='*60}")
        sys.exit(0)

    # Classify
    run_id = f"run_{uuid4().hex[:12]}"
    logger.info(
        "Starting classification: run=%s model=%s tweets=%d",
        run_id, args.model, len(tweets),
    )

    predictions = classify_tweets(
        tweets,
        taxonomy,
        args.model,
        api_key,
        budget_dollars=args.budget,
    )

    if not predictions:
        logger.error("No predictions produced. Check logs for errors.")
        sys.exit(1)

    # Ingest
    logger.info("Ingesting %d predictions via %s", len(predictions), args.api_base)
    result = ingest_predictions(
        predictions,
        model_name=args.model,
        model_version=args.model_version,
        prompt_version=args.prompt_version,
        run_id=run_id,
        api_base=args.api_base,
    )
    logger.info(
        "Ingested: %d inserted, mean_entropy=%.3f, mean_disagreement=%.3f",
        result.get("inserted", 0),
        result.get("meanEntropy", 0),
        result.get("meanDisagreement", 0),
    )

    # Evaluate
    print(f"\n{'='*60}")
    print(f"  CLASSIFICATION RESULTS — {args.model}")
    print(f"  Run: {run_id}")
    print(f"  Predictions: {len(predictions)}")
    print(f"{'='*60}")

    for split_name in ["dev", "test"]:
        try:
            ev = run_evaluation(
                model_name=args.model,
                model_version=args.model_version,
                prompt_version=args.prompt_version,
                split=split_name,
                api_base=args.api_base,
            )
            brier = ev.get("brierScore", "N/A")
            passed = ev.get("passed", False)
            n = ev.get("sampleSize", 0)
            status = "PASS" if passed else "FAIL"
            if n == 0:
                print(f"  {split_name:5s}: no human labels in this split yet")
            else:
                print(f"  {split_name:5s}: Brier={brier:.4f}  n={n}  [{status}]")
        except Exception as exc:
            print(f"  {split_name:5s}: eval error — {exc}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
