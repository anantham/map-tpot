#!/usr/bin/env python3
"""Fetch recent post activity for selected accounts via X recent search."""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv


LOGGER = logging.getLogger("fetch_recent_activity")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_FILE = PROJECT_ROOT / "docs" / "seed_presets.json"
DEFAULT_JSON = PROJECT_ROOT / "data" / "outputs" / "recent_activity" / "activity_latest.json"
DEFAULT_CSV = PROJECT_ROOT / "data" / "outputs" / "recent_activity" / "activity_latest.csv"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch recent account activity using search/recent batching.")
    parser.add_argument("--usernames", nargs="*", default=[], help="Explicit usernames (without @).")
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED_FILE, help="Seed preset file fallback.")
    parser.add_argument("--seed-preset", type=str, default="adi_tpot", help="Seed preset key.")
    parser.add_argument("--batch-size", type=int, default=8, help="Handles per OR query.")
    parser.add_argument("--max-results", type=int, default=100, help="Tweets per request (1..100).")
    parser.add_argument("--pages-per-batch", type=int, default=1, help="Pages per query batch.")
    parser.add_argument("--exclude-retweets", action="store_true", default=True, help="Exclude retweets (default).")
    parser.add_argument("--include-retweets", dest="exclude_retweets", action="store_false", help="Include retweets.")
    parser.add_argument("--exclude-replies", action="store_true", default=False, help="Exclude replies.")
    parser.add_argument("--wait-on-rate-limit", action="store_true", default=False, help="Sleep and retry on 429.")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="HTTP timeout.")
    parser.add_argument("--post-read-unit-cost", type=float, default=0.005, help="Estimated $ per post read.")
    parser.add_argument("--base-url", type=str, default="https://api.x.com/2/tweets/search/recent", help="Endpoint URL.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON, help="JSON output path.")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV, help="CSV output path.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Print queries only.")
    parser.add_argument("--verbose", action="store_true", default=False, help="Debug logs.")
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def iso_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_usernames(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        candidate = raw.strip().lstrip("@").lower()
        if not candidate or not USERNAME_RE.match(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def load_usernames(args: argparse.Namespace) -> List[str]:
    if args.usernames:
        usernames = normalize_usernames(args.usernames)
    else:
        payload = json.loads(args.seed_file.read_text())
        usernames = normalize_usernames(payload.get(args.seed_preset, []))
    if not usernames:
        raise ValueError("No valid usernames found.")
    return usernames


def build_batches(usernames: Sequence[str], batch_size: int, exclude_retweets: bool, exclude_replies: bool) -> List[Tuple[List[str], str]]:
    suffixes = []
    if exclude_retweets:
        suffixes.append("-is:retweet")
    if exclude_replies:
        suffixes.append("-is:reply")
    suffix = " ".join(suffixes).strip()
    batches: List[Tuple[List[str], str]] = []
    for i in range(0, len(usernames), max(1, batch_size)):
        handles = list(usernames[i : i + batch_size])
        query = "(" + " OR ".join(f"from:{u}" for u in handles) + ")"
        if suffix:
            query = f"{query} {suffix}"
        batches.append((handles, query))
    return batches


def maybe_sleep_on_429(headers: Dict[str, str], enabled: bool) -> bool:
    if not enabled:
        return False
    reset = headers.get("x-rate-limit-reset")
    retry_after = headers.get("retry-after")
    sleep_seconds = 0
    if retry_after and retry_after.isdigit():
        sleep_seconds = int(retry_after)
    elif reset and reset.isdigit():
        sleep_seconds = max(int(reset) - int(time.time()) + 1, 1)
    if sleep_seconds <= 0:
        return False
    LOGGER.warning("429 received; sleeping %ss", sleep_seconds)
    time.sleep(sleep_seconds)
    return True


def compute_account_metrics(username: str, tweets: List[dict], user_meta: dict, now: datetime) -> Dict[str, object]:
    timestamps = sorted((parse_ts(t.get("created_at")) for t in tweets), reverse=True)
    timestamps = [ts for ts in timestamps if ts]
    likes = [int((t.get("public_metrics") or {}).get("like_count", 0)) for t in tweets]
    replies = [int((t.get("public_metrics") or {}).get("reply_count", 0)) for t in tweets]
    retweets = [int((t.get("public_metrics") or {}).get("retweet_count", 0)) for t in tweets]
    impressions = [int((t.get("public_metrics") or {}).get("impression_count", 0)) for t in tweets]
    last_tweet = timestamps[0] if timestamps else None
    oldest_tweet = timestamps[-1] if timestamps else None
    gaps = [(timestamps[i] - timestamps[i + 1]).total_seconds() / 3600 for i in range(len(timestamps) - 1)]
    obs_days = ((last_tweet - oldest_tweet).total_seconds() / 86400) if last_tweet and oldest_tweet else None
    obs_days = max(obs_days, 1 / 24) if obs_days else None
    ranked = sorted(tweets, key=lambda t: int((t.get("public_metrics") or {}).get("like_count", 0)), reverse=True)
    top = ranked[0] if ranked else {}
    top_text = (top.get("text") or "").replace("\n", " ").strip()
    return {
        "username": username,
        "user_id": user_meta.get("id"),
        "verified": user_meta.get("verified"),
        "followers_count": (user_meta.get("public_metrics") or {}).get("followers_count"),
        "following_count": (user_meta.get("public_metrics") or {}).get("following_count"),
        "tweets_observed": len(tweets),
        "last_tweet_at": iso_utc(last_tweet) if last_tweet else None,
        "oldest_tweet_at": iso_utc(oldest_tweet) if oldest_tweet else None,
        "hours_since_last_tweet": round((now - last_tweet).total_seconds() / 3600, 3) if last_tweet else None,
        "tweets_observed_7d": sum(1 for ts in timestamps if ts >= now - timedelta(days=7)),
        "tweets_observed_30d": sum(1 for ts in timestamps if ts >= now - timedelta(days=30)),
        "observed_tweets_per_day": round(len(timestamps) / obs_days, 3) if obs_days else None,
        "median_hours_between_posts": round(statistics.median(gaps), 3) if gaps else None,
        "mean_hours_between_posts": round(statistics.mean(gaps), 3) if gaps else None,
        "avg_like_count": round(statistics.mean(likes), 3) if likes else None,
        "avg_reply_count": round(statistics.mean(replies), 3) if replies else None,
        "avg_retweet_count": round(statistics.mean(retweets), 3) if retweets else None,
        "avg_impression_count": round(statistics.mean(impressions), 3) if impressions else None,
        "top_recent_by_likes": {
            "tweet_id": top.get("id"),
            "created_at": top.get("created_at"),
            "like_count": int((top.get("public_metrics") or {}).get("like_count", 0)) if top else 0,
            "text_preview": top_text[:180] + ("..." if len(top_text) > 180 else ""),
        },
    }


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    fields = [
        "username", "user_id", "tweets_observed", "last_tweet_at", "hours_since_last_tweet",
        "tweets_observed_7d", "tweets_observed_30d", "observed_tweets_per_day",
        "median_hours_between_posts", "mean_hours_between_posts", "avg_like_count",
        "avg_reply_count", "avg_retweet_count", "avg_impression_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        LOGGER.error("X_BEARER_TOKEN not found in %s/.env", PROJECT_ROOT)
        return 2

    usernames = load_usernames(args)
    batches = build_batches(usernames, args.batch_size, args.exclude_retweets, args.exclude_replies)
    LOGGER.info("Prepared %d usernames into %d batch queries.", len(usernames), len(batches))
    if args.dry_run:
        print("DRY RUN: batched queries")
        for i, (handles, query) in enumerate(batches, 1):
            print(f"[{i}] handles={len(handles)} query={query}")
        return 0

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "User-Agent": "TPOTRecentActivity/1.0"})
    tweets_by_user = {u: [] for u in usernames}
    meta_by_user = {u: {} for u in usernames}
    request_log: List[Dict[str, object]] = []
    total_tweets = 0

    for batch_idx, (handles, query) in enumerate(batches, 1):
        cursor: Optional[str] = None
        for page in range(1, max(1, args.pages_per_batch) + 1):
            params = {
                "query": query,
                "max_results": str(max(1, min(args.max_results, 100))),
                "tweet.fields": "id,author_id,text,created_at,lang,public_metrics",
                "expansions": "author_id",
                "user.fields": "id,username,name,verified,public_metrics",
            }
            if cursor:
                params["next_token"] = cursor
            response = session.get(args.base_url, params=params, timeout=args.timeout_seconds)
            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text[:1000]}
            if response.status_code == 429 and maybe_sleep_on_429(response.headers, args.wait_on_rate_limit):
                continue
            request_log.append(
                {
                    "batch_index": batch_idx,
                    "page": page,
                    "status_code": response.status_code,
                    "result_count": payload.get("meta", {}).get("result_count") if isinstance(payload, dict) else None,
                    "rate_limit_remaining": response.headers.get("x-rate-limit-remaining"),
                    "rate_limit_reset": response.headers.get("x-rate-limit-reset"),
                    "request_url": response.url,
                }
            )
            if response.status_code != 200:
                LOGGER.error("Batch %d page %d failed: %s", batch_idx, page, payload)
                break
            users = {str(u.get("id")): u for u in payload.get("includes", {}).get("users", [])}
            data = payload.get("data", [])
            for tweet in data:
                author = users.get(str(tweet.get("author_id")))
                if not author:
                    continue
                uname = normalize_usernames([str(author.get("username", ""))])
                if not uname:
                    continue
                key = uname[0]
                if key in tweets_by_user:
                    tweets_by_user[key].append(tweet)
                    meta_by_user[key] = author
            total_tweets += len(data)
            cursor = payload.get("meta", {}).get("next_token")
            if not cursor:
                break

    now = datetime.now(timezone.utc)
    rows = [compute_account_metrics(u, tweets_by_user.get(u, []), meta_by_user.get(u, {}), now) for u in usernames]
    rows.sort(key=lambda r: str(r["username"]))
    est_cost = round(total_tweets * max(args.post_read_unit_cost, 0.0), 6)
    report = {
        "generated_at": iso_utc(now),
        "request_parameters": vars(args),
        "summary": {
            "accounts_requested": len(usernames),
            "accounts_with_observed_tweets": sum(1 for row in rows if int(row["tweets_observed"]) > 0),
            "requests_made": len(request_log),
            "tweets_returned_total": total_tweets,
            "estimated_post_read_cost_usd": est_cost,
        },
        "request_log": request_log,
        "accounts": rows,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2))
    write_csv(args.output_csv, rows)

    print("=" * 72)
    print("RECENT ACTIVITY FETCH SUMMARY")
    print("=" * 72)
    print(f"Accounts requested: {len(usernames)}")
    print(f"Accounts with observed tweets: {report['summary']['accounts_with_observed_tweets']}")
    print(f"API requests made: {len(request_log)}")
    print(f"Tweets returned: {total_tweets}")
    print(f"Estimated Post:Read cost (USD): {est_cost:.6f}")
    print(f"JSON output: {args.output_json}")
    print(f"CSV output: {args.output_csv}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
