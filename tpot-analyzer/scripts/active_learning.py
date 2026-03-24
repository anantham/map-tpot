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
    fetch_advanced_search,
    fetch_last_tweets,
    log_api_call,
    parse_tweet,
    store_tweets,
)
from scripts.assemble_context import (
    assemble_account_context,
    assemble_tweet_context,
)
from src.archive.thread_fetcher import get_thread_context, format_thread_for_prompt
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
    compute_discount,
)
from scripts.insert_seeds import insert_llm_seeds

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "archive_tweets.db"


# ═══════════════════════════════════════════════════════════════════════════
# Account selection
# ═══════════════════════════════════════════════════════════════════════════


def _load_ego_hops(conn: sqlite3.Connection, ego_account_id: str) -> tuple[set, set]:
    """Load hop-1 and hop-2 account sets from ego's follow graph.

    Returns (hop1_ids, hop2_ids) where:
      hop1 = accounts ego follows directly
      hop2 = accounts ego's follows follow (excluding hop1)
    """
    hop1 = set(
        r[0] for r in conn.execute(
            "SELECT following_account_id FROM account_following WHERE account_id = ?",
            (ego_account_id,),
        ).fetchall()
    )
    if not hop1:
        return hop1, set()

    # Hop 2: friends-of-friends, batched to avoid huge IN clause
    hop2 = set()
    hop1_list = list(hop1)
    batch_size = 500
    for i in range(0, len(hop1_list), batch_size):
        batch = hop1_list[i:i + batch_size]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"SELECT DISTINCT following_account_id FROM account_following WHERE account_id IN ({placeholders})",
            batch,
        ).fetchall()
        hop2.update(r[0] for r in rows)
    hop2 -= hop1  # don't double-count hop1
    hop2.discard(ego_account_id)  # don't include self

    return hop1, hop2


def select_accounts(
    conn: sqlite3.Connection,
    top_n: int,
    round_num: int,
    ego_account_id: str | None = None,
) -> list[dict]:
    """Select top accounts from frontier_ranking for enrichment.

    Excludes:
      - holdout accounts (in_holdout=1 OR in tpot_directory_holdout)
      - already enriched (any tweets in enriched_tweets)
      - accounts with no resolvable username (profiles OR resolved_accounts)

    If ego_account_id is provided, boosts accounts by proximity:
      - Hop 1 (ego follows them): 3x boost
      - Hop 2 (ego's follows follow them): 1.5x boost
      - Hop 3+: no boost

    Returns list of dicts sorted by priority DESC.
    """
    # Load more candidates than needed so proximity boost can re-rank
    fetch_limit = top_n * 5 if ego_account_id else top_n

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
            SELECT DISTINCT account_id FROM enriched_tweets
        )
        ORDER BY fr.info_value DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (fetch_limit,)).fetchall()

    accounts = [
        {
            "account_id": row[0],
            "info_value": row[1],
            "top_community": row[2],
            "username": row[3],
        }
        for row in rows
    ]

    # Apply ego proximity boost
    if ego_account_id and accounts:
        hop1, hop2 = _load_ego_hops(conn, ego_account_id)
        for acct in accounts:
            aid = acct["account_id"]
            if aid in hop1:
                acct["proximity"] = "hop1"
                acct["priority"] = acct["info_value"] * 3.0
            elif aid in hop2:
                acct["proximity"] = "hop2"
                acct["priority"] = acct["info_value"] * 1.5
            else:
                acct["proximity"] = "hop3+"
                acct["priority"] = acct["info_value"]
        accounts.sort(key=lambda a: a["priority"], reverse=True)
        logger.info(
            "Ego boost applied: %d hop1, %d hop2, %d hop3+",
            sum(1 for a in accounts if a["proximity"] == "hop1"),
            sum(1 for a in accounts if a["proximity"] == "hop2"),
            sum(1 for a in accounts if a["proximity"] == "hop3+"),
        )
    else:
        for acct in accounts:
            acct["proximity"] = "n/a"
            acct["priority"] = acct["info_value"]

    return accounts[:top_n]


def select_accounts_by_handle(
    conn: sqlite3.Connection, handles: list[str]
) -> list[dict]:
    """Select specific accounts by handle, bypassing frontier_ranking.

    Resolves handles to account_ids via profiles/resolved_accounts.
    Skips holdout accounts and already-enriched accounts.
    Does NOT require accounts to be in frontier_ranking.
    """
    holdout_ids = set(
        r[0] for r in conn.execute(
            "SELECT account_id FROM tpot_directory_holdout WHERE account_id IS NOT NULL"
        ).fetchall()
    )
    enriched_ids = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM enriched_tweets"
        ).fetchall()
    )

    accounts = []
    for handle in handles:
        # Resolve handle → account_id
        row = conn.execute(
            "SELECT account_id, username FROM profiles WHERE LOWER(username) = LOWER(?)",
            (handle,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT account_id, username FROM resolved_accounts WHERE LOWER(username) = LOWER(?)",
                (handle,),
            ).fetchone()
        if not row:
            logger.warning("Could not resolve handle: @%s — skipping", handle)
            continue

        aid, username = row[0], row[1]

        if aid in holdout_ids:
            logger.warning("@%s is a holdout account — skipping", handle)
            continue

        if aid in enriched_ids:
            logger.warning("@%s already enriched — skipping", handle)
            continue

        # Get info_value if available (might not be in frontier_ranking)
        iv_row = conn.execute(
            "SELECT info_value, top_community FROM frontier_ranking WHERE account_id = ?",
            (aid,),
        ).fetchone()

        accounts.append({
            "account_id": aid,
            "info_value": iv_row[0] if iv_row else 0.0,
            "top_community": iv_row[1] if iv_row else "unknown",
            "username": username,
            "proximity": "manual",
            "priority": 999.0,  # manual picks always highest priority
        })

    return accounts


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


def _enrich_low_text_tweet(tweet_text: str, context_json: str) -> str:
    """Enrich tweets with minimal text by fetching linked content.

    For URL-only or image-only tweets, the LLM has nothing to tag.
    This fetches article titles/descriptions from URLs to provide
    actual content for labeling.
    """
    import json as _json
    import re

    # Extract URLs from tweet text
    urls = re.findall(r'https?://\S+', tweet_text)

    # Also check context_json for URLs
    try:
        context_items = _json.loads(context_json) if context_json else []
    except (ValueError, TypeError):
        context_items = []

    for item in context_items:
        if isinstance(item, str):
            urls.extend(re.findall(r'https?://\S+', item))

    # Strip text to check if it's "low text" (only URLs, no real content)
    stripped = re.sub(r'https?://\S+', '', tweet_text).strip()
    if len(stripped) >= 30:
        # Enough real text — no enrichment needed
        return tweet_text

    # Try to fetch article metadata for each URL
    enrichments = []
    for url in urls[:2]:  # max 2 URLs to keep costs down
        # Skip t.co, image URLs, and media
        if 't.co/' in url or 'pbs.twimg.com' in url or 'video.twimg.com' in url:
            continue
        try:
            import httpx
            resp = httpx.get(
                url, follow_redirects=True, timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            )
            if resp.status_code == 200:
                html = resp.text[:5000]  # first 5KB
                # Extract title
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                # Extract og:description
                desc_match = re.search(
                    r'<meta[^>]+(?:property|name)=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                    html, re.IGNORECASE,
                )
                parts = []
                if title_match:
                    parts.append(f"[Article: {title_match.group(1).strip()[:150]}]")
                if desc_match:
                    parts.append(f"[Description: {desc_match.group(1).strip()[:200]}]")
                if parts:
                    enrichments.append("\n".join(parts))
        except Exception:
            pass  # network errors are fine — we just lose enrichment

    if enrichments:
        return tweet_text + "\n" + "\n".join(enrichments)

    # If we couldn't enrich, add a cue so the LLM knows to be cautious
    if len(stripped) < 10:
        return tweet_text + "\n[This tweet has minimal text — only links/media. Assign 0 bits unless the linked content is clearly community-specific.]"

    return tweet_text


def _label_single_tweet(
    conn: sqlite3.Connection,
    openrouter_key: str,
    tweet: dict,
    account_ctx: dict,
    current_prior: str = "",
) -> list[dict]:
    """Label a single tweet with all models, store consensus.

    Args:
        current_prior: accumulating bits profile so far, e.g.
            "LLM-Whisperers:40%, Qualia-Research:30%, AI-Safety:20%"
            The LLM uses this to focus on surprising/extending evidence.

    Returns list of per-model label dicts (for agreement tracking).
    """
    # Build enriched tweet text: original text + context (quotes, images, links)
    tweet_text = tweet["text"]
    context_json = tweet.get("context_json", "[]")
    if context_json and context_json != "[]":
        import json as _json
        try:
            context_items = _json.loads(context_json)
            if context_items:
                tweet_text += "\n" + "\n".join(context_items)
        except (ValueError, TypeError):
            pass

    # Enrich reply tweets with thread context (parent tweets)
    if tweet.get("is_reply") and tweet.get("tweet_id"):
        try:
            from src.config import DEFAULT_ARCHIVE_DB
            thread = get_thread_context(tweet["tweet_id"], DEFAULT_ARCHIVE_DB)
            if thread and len(thread) > 1:
                thread_text = format_thread_for_prompt(thread, tweet["tweet_id"])
                tweet_text = f"[Thread context]\n{thread_text}\n[End thread]"
        except Exception as e:
            logger.debug("Thread fetch failed for %s: %s", tweet["tweet_id"], e)

    # Enrich low-text tweets by fetching linked content (#1: bias leak fix)
    tweet_text = _enrich_low_text_tweet(tweet_text, context_json)

    tweet_ctx = assemble_tweet_context(
        conn,
        tweet_id=tweet["tweet_id"],
        tweet_text=tweet_text,
        engagement_stats=f"likes={tweet.get('like_count', 0)} rt={tweet.get('retweet_count', 0)} replies={tweet.get('reply_count', 0)}",
        mentions=tweet.get("mentions_json", "[]"),
    )

    prompt_text = build_prompt(
        username=account_ctx["username"],
        bio=account_ctx.get("bio", ""),
        graph_signal=account_ctx["graph_signal"],
        other_tweets=current_prior,
        tweet_text=tweet_ctx["tweet_text"],
        engagement=tweet_ctx["engagement_stats"],
        mentions=tweet_ctx["mentions"],
        engagement_context=tweet_ctx["engagement_context"],
        community_descriptions=account_ctx["community_descriptions"],
        community_short_names=account_ctx["community_short_names"],
        content_profile=account_ctx.get("content_profile", ""),
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

            # 3. Fetch tweets — two calls for diverse sampling
            # Call 1: recent tweets (current state)
            raw_tweets, author_info = fetch_last_tweets(twitter_key, username)
            parsed = [parse_tweet(t, username) for t in raw_tweets]
            inserted = store_tweets(conn, parsed, fetch_source="last_tweets")

            # Call 2: most-liked tweets (best/most representative content)
            check_budget(conn, limit=budget, raise_on_exceed=True)
            top_query = f"from:{username}"
            raw_top = fetch_advanced_search(twitter_key, top_query)
            parsed_top = [parse_tweet(t, username) for t in raw_top]
            inserted_top = store_tweets(conn, parsed_top, fetch_source="advanced_search", fetch_query=top_query)
            log_api_call(
                conn, account_id=account_id, username=username,
                round_num=1, action="advanced_search",
                tweets_fetched=len(parsed_top), query=top_query,
            )

            # Merge: label all unique tweets (dedup by tweet_id)
            seen_ids = set()
            all_parsed = []
            for t in parsed + parsed_top:
                if t["tweet_id"] not in seen_ids:
                    all_parsed.append(t)
                    seen_ids.add(t["tweet_id"])
            parsed = all_parsed

            # 5. Store bio from API response (if not already in DB)
            if author_info:
                api_bio = author_info.get("description", "")
                if api_bio:
                    # Update resolved_accounts with bio from API
                    conn.execute(
                        "INSERT OR IGNORE INTO resolved_accounts (account_id, username, bio) VALUES (?, ?, ?)",
                        (account_id, username, api_bio),
                    )
                    conn.execute(
                        "UPDATE resolved_accounts SET bio = ? WHERE account_id = ? AND (bio IS NULL OR bio = '')",
                        (api_bio, account_id),
                    )
                    conn.commit()

            # 6. Log API call
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

            # 7. Label each tweet
            account_ctx = assemble_account_context(
                conn,
                account_id=account_id,
                username=username,
                bio=_resolve_bio(conn, account_id),
            )

            # Tag retweets — still label them but with context that it's an RT
            n_rts = sum(1 for t in parsed if t.get("text", "").startswith("RT @"))
            if n_rts:
                logger.info("  %d/%d tweets are retweets (labeled with RT context)", n_rts, len(parsed))

            # Build accumulating prior as we label tweets
            bits_accumulator: dict[str, int] = {}  # community → total bits so far

            for tweet in parsed:
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
    # NOTE: Do NOT call write_rollup here — it does a global DELETE that wipes
    # all accounts, not just the ones being measured. Use scoped_delete + manual insert.
    scoped_delete_bits(conn, new_account_ids)
    now_str = __import__('datetime').datetime.now(
        __import__('datetime').timezone.utc
    ).isoformat()
    rollup_rows = 0
    for (account_id, community_id), data in sorted(rollup.items()):
        conn.execute(
            """INSERT OR REPLACE INTO account_community_bits
               (account_id, community_id, total_bits, tweet_count, pct, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, community_id, data["total_bits"],
             data["tweet_count"], data["pct"], now_str),
        )
        rollup_rows += 1
    conn.commit()

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
