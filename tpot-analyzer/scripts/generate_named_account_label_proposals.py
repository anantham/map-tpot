#!/usr/bin/env python3
"""Generate private model proposals without writing accepted-label tables.

Test intent exception: this is a bounded operational CLI, so the repository's
one-shot-script convention uses an independent real-receipt verifier instead
of pre-written unit tests. The DB is opened read-only and output is restricted
to an ignored private artifact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

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
from scripts.assemble_context import (  # noqa: E402
    assemble_account_context,
    get_engagement_context,
    resolve_mention_communities,
)
from scripts.label_tweets_ensemble import (  # noqa: E402
    build_consensus,
    build_prompt,
)
from scripts._openrouter_proposals import (  # noqa: E402
    actual_cost,
    call_model,
    estimated_cost,
    load_catalog,
    pricing_for,
)

DEFAULT_DB = ROOT / "data" / "archive_tweets.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "private" / "label_proposals"


def render_prompt(account_ctx: dict[str, Any], tweet: dict[str, Any], prior: str) -> tuple[str, str]:
    prompt = build_prompt(
        username=account_ctx["username"],
        bio=account_ctx.get("bio", ""),
        graph_signal=account_ctx.get("graph_signal", ""),
        other_tweets=prior,
        tweet_text=tweet["text"],
        engagement=f"likes={tweet.get('like_count', 0)} rt={tweet.get('retweet_count', 0)} replies={tweet.get('reply_count', 0)}",
        mentions=tweet.get("mentions_json") or "[]",
        engagement_context=account_ctx["engagementByTweet"].get(tweet["tweet_id"], ""),
        community_descriptions=account_ctx["community_descriptions"],
        community_short_names=account_ctx["community_short_names"],
        content_profile=account_ctx.get("content_profile", ""),
        engagement_partners=account_ctx.get("engagement_partners", ""),
        mention_communities=resolve_mention_communities(account_ctx["conn"], tweet.get("mentions_json") or "[]"),
        cofollowed=account_ctx.get("cofollowed", ""),
    )
    parts = prompt.split("\n---\n\n", 1)
    return (parts[0], parts[1] if len(parts) == 2 else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate private named-account label proposals")
    parser.add_argument("--username", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-usd", type=float, default=0.50)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be in 1..20")
    output = args.output or DEFAULT_OUTPUT_DIR / f"{args.username.lower()}-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.json"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite proposal receipt: {output}")
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    conn = open_read_only(args.db_path)
    artifact: dict[str, Any] = {
        "schemaVersion": 1,
        "proposalStatus": "model-proposed",
        "goldStatus": "not-gold",
        "runStatus": "preflight",
        "permissions": {"writeLabels": False, "measure": False, "export": False, "deploy": False},
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "models": list(APPROVED_MODELS),
        "maxUsd": args.max_usd,
        "results": [],
        "errors": [],
    }
    try:
        account = load_account(conn, args.username, args.account_id)
        tweets = select_tweets(conn, args.account_id, args.limit)
        if len(tweets) != args.limit:
            raise ValueError(f"expected {args.limit} eligible tweets, found {len(tweets)}")
        source = source_receipt(account, tweets)
        artifact["source"] = source
        artifact["interpretationCountsBefore"] = account_interpretation_counts(conn, args.account_id)
        if any(artifact["interpretationCountsBefore"].values()):
            raise ValueError(f"account already has interpreted rows: {artifact['interpretationCountsBefore']}")
        account_ctx = assemble_account_context(conn, args.account_id, args.username, account.get("bio") or "")
        account_ctx["conn"] = conn
        account_ctx["engagementByTweet"] = {
            tweet["tweet_id"]: get_engagement_context(conn, tweet["tweet_id"]) for tweet in tweets
        }
        prompts = [render_prompt(account_ctx, tweet, "") for tweet in tweets]

        with httpx.Client(timeout=90.0) as client:
            catalog = load_catalog(client, APPROVED_MODELS)
            artifact["modelCatalog"] = {
                model: {"id": item["id"], "name": item.get("name"), "pricing": pricing_for(item)}
                for model, item in catalog.items()
            }
            projected = estimated_cost(prompts, catalog)
            artifact["projectedMaxUsd"] = round(projected, 8)
            if projected > args.max_usd:
                raise ValueError(f"projected maximum ${projected:.6f} exceeds cap ${args.max_usd:.6f}")
            print(f"✓ preflight: tweets={len(tweets)} models={len(APPROVED_MODELS)} projected_max=${projected:.6f}")
            communities = valid_communities(conn)
            bits: dict[str, int] = defaultdict(int)
            observed_cost = 0.0
            for index, tweet in enumerate(tweets, start=1):
                prior_total = sum(bits.values())
                prior = ", ".join(
                    f"{name}:{value * 100 // prior_total}%"
                    for name, value in sorted(bits.items(), key=lambda item: -item[1])[:4]
                ) if prior_total else ""
                system_prompt, user_prompt = render_prompt(account_ctx, tweet, prior)
                per_model = []
                model_receipts = []
                for model in APPROVED_MODELS:
                    parsed, receipt = call_model(client, api_key, model, system_prompt, user_prompt)
                    errors = validate_label(parsed, communities)
                    if errors:
                        raise ValueError(f"{model} invalid label for tweet {tweet['tweet_id']}: {errors}")
                    cost = actual_cost(receipt, pricing_for(catalog[model]))
                    observed_cost += cost
                    receipt["costUsd"] = round(cost, 10)
                    model_receipts.append({"model": model, "label": parsed, "receipt": receipt})
                    per_model.append(parsed)
                    if observed_cost > args.max_usd:
                        raise ValueError(f"observed cost ${observed_cost:.6f} exceeded cap ${args.max_usd:.6f}")
                consensus = build_consensus(per_model)
                errors = validate_label(consensus, communities)
                if errors:
                    raise ValueError(f"invalid consensus for tweet {tweet['tweet_id']}: {errors}")
                for tag in consensus["bits"]:
                    _, community, value = tag.split(":")
                    bits[community] += int(value)
                artifact["results"].append({
                    "rank": index,
                    "tweet": tweet,
                    "models": model_receipts,
                    "consensus": consensus,
                })
                print(f"✓ tweet {index}/{len(tweets)}: models=3 consensus_bits={len(consensus['bits'])} cost_so_far=${observed_cost:.6f}", flush=True)
            artifact["observedCostUsd"] = round(observed_cost, 10)
            artifact["proposedBits"] = dict(sorted(bits.items(), key=lambda item: -item[1]))
            artifact["runStatus"] = "complete"
    except Exception as error:
        artifact["runStatus"] = "partial" if artifact["results"] else "failed"
        artifact["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        conn.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Receipt: {output}")
    if artifact["runStatus"] != "complete":
        print(f"✗ proposal run {artifact['runStatus']}: {artifact['errors'][-1]}")
        return 1
    print(f"✓ proposal run complete: results={len(artifact['results'])} observed_cost=${artifact['observedCostUsd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
