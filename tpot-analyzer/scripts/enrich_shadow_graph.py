"""CLI entrypoint for hybrid + API-based shadow enrichment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

import logging
import logging.handlers

LOGGER = logging.getLogger(__name__)

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store
from src.graph.seeds import load_seed_candidates
from src.shadow import HybridShadowEnricher, SeedAccount, ShadowEnrichmentConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich shadow nodes via Selenium + X API")
    parser.add_argument(
        "--cookies",
        type=Path,
        default=Path("secrets/twitter_cookies.pkl"),
        help="Path to Chrome cookies pickle (default: secrets/twitter_cookies.pkl).",
    )
    parser.add_argument(
        "--seeds",
        nargs="*",
        default=[],
        help="Seed usernames (defaults merge with docs/seed_presets.json).",
    )
    parser.add_argument(
        "--bearer-token",
        type=str,
        default=None,
        help="Optional X API bearer token (falls back to X_BEARER_TOKEN env).",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=2.0,
        help="Seconds to pause between users to reduce scraping load.",
    )
    parser.add_argument(
        "--no-followers",
        action="store_false",
        dest="include_followers",
        help="Disable follower scraping (enabled by default).",
    )
    parser.add_argument(
        "--no-following",
        action="store_false",
        dest="include_following",
        help="Disable following scraping (enabled by default).",
    )
    parser.set_defaults(include_following=True, include_followers=True)
    parser.add_argument(
        "--no-followers-you-follow",
        action="store_false",
        dest="include_followers_you_follow",
        help="Skip the additional followers-you-follow list scrape (enabled by default).",
    )
    parser.set_defaults(include_followers_you_follow=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to dump JSON summary (stdout otherwise).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (default is visible window).",
    )
    parser.add_argument(
        "--chrome-binary",
        type=Path,
        default=None,
        help="Path to Chrome/Chromium binary to launch (defaults to Selenium Manager discovery).",
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=4.0,
        help="Minimum delay (seconds) between scripted actions (default 4).",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=9.0,
        help="Maximum delay (seconds) between scripted actions (default 9).",
    )
    parser.add_argument(
        "--auto-continue",
        action="store_true",
        help="Do not pause for manual login confirmation after cookies load.",
    )
    parser.add_argument(
        "--auto-confirm-first",
        action="store_true",
        help="Skip manual confirmation after the first scraped profile preview.",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=10,
        help="Number of sample profiles to show during the confirmation preview (default 10).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        help="Logging verbosity for enrichment routines.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all non-essential output (sets log level to WARN, skips preview).",
    )
    return parser.parse_args()


def build_seed_accounts(fetcher: CachedDataFetcher, seed_usernames: List[str]) -> List[SeedAccount]:
    accounts = fetcher.fetch_accounts()
    id_to_username = {
        str(row["account_id"]): (row.get("username") or '').lower()
        for _, row in accounts.iterrows()
    }
    username_to_id = {username: account_id for account_id, username in id_to_username.items() if username}

    seeds: List[SeedAccount] = []
    for seed in seed_usernames:
        normalized = seed.lower()
        account_id = username_to_id.get(normalized)
        username = normalized
        if account_id is None:
            account_id = f"shadow:{normalized}"
        seeds.append(SeedAccount(account_id=account_id, username=username))
    return seeds


def main() -> None:
    args = parse_args()

    # Determine effective log level (--quiet overrides --log-level)
    if args.quiet:
        log_level = logging.WARN
        # Suppress selenium and urllib3 noise
        logging.getLogger("selenium").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)
    else:
        log_level = getattr(logging, args.log_level.upper(), logging.INFO)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "enrichment.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    log_format = (
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        if not args.quiet
        else "%(levelname)s: %(message)s"
    )
    formatter = logging.Formatter(log_format)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5  # 5MB per file
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    cache_settings = get_cache_settings()
    bearer = args.bearer_token or os.getenv("X_BEARER_TOKEN")

    with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
        # Determine seed strategy: use ALL archive accounts by default,
        # or manual selection via --seeds (which merges with adi_tpot preset)
        if args.seeds:
            # Manual mode: use provided seeds + adi_tpot preset
            seed_usernames = sorted(load_seed_candidates(additional=args.seeds))
        else:
            # Default mode: use ALL archive accounts (275 nodes)
            accounts = fetcher.fetch_accounts()
            archive_usernames = [
                row.get("username").lower()
                for _, row in accounts.iterrows()
                if row.get("username")
            ]
            # Add adi_tpot preset to the front (prioritize these)
            preset_usernames = sorted(load_seed_candidates())
            seed_usernames = preset_usernames + [
                u for u in sorted(archive_usernames) if u not in preset_usernames
            ]
            LOGGER.info(
                "Using all %s archive accounts (%s from adi_tpot preset + %s additional)",
                len(seed_usernames),
                len(preset_usernames),
                len(seed_usernames) - len(preset_usernames),
            )
        store = get_shadow_store(fetcher.engine)
        seeds = build_seed_accounts(fetcher, seed_usernames)

        config = ShadowEnrichmentConfig(
            selenium_cookies_path=args.cookies,
            selenium_headless=args.headless,
            selenium_scroll_delay_min=args.delay_min,
            selenium_scroll_delay_max=args.delay_max,
            user_pause_seconds=args.pause,
            action_delay_min=args.delay_min,
            action_delay_max=args.delay_max,
            chrome_binary=args.chrome_binary,
            wait_for_manual_login=not args.auto_continue,
            include_followers=args.include_followers,
            include_following=args.include_following,
            include_followers_you_follow=args.include_followers_you_follow,
            bearer_token=bearer,
            confirm_first_scrape=not args.auto_confirm_first and not args.quiet,
            preview_sample_size=max(1, args.preview_count),
        )

        enricher = HybridShadowEnricher(store, config)
        try:
            summary = enricher.enrich(seeds)
        except KeyboardInterrupt:
            logging.getLogger(__name__).warning("Interrupted by user; shutting down enrichment cleanly")
            summary = {"status": "interrupted"}
        except RuntimeError as err:
            logging.getLogger(__name__).error(str(err))
            summary = {"status": "aborted", "reason": str(err)}

    payload = json.dumps(summary, indent=2)
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
