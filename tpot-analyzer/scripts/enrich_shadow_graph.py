"""CLI entrypoint for hybrid + API-based shadow enrichment."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

import logging
import logging.handlers

LOGGER = logging.getLogger(__name__)

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store
from src.graph.seeds import load_seed_candidates
from src.shadow import HybridShadowEnricher, SeedAccount, ShadowEnrichmentConfig, EnrichmentPolicy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich shadow nodes via Selenium + X API")
    parser.add_argument(
        "--cookies",
        type=Path,
        default=Path("secrets/twitter_cookies.pkl"),
        help="Path to Chrome cookies pickle (default: secrets/twitter_cookies.pkl). If the file is missing, you'll be prompted to choose from secrets/*.pkl.",
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
        default=Path("enrichment_summary.json"),
        help="Path to dump JSON summary (default: enrichment_summary.json).",
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
        default=5.0,
        help="Minimum delay (seconds) between scripted actions (default 5).",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=40.0,
        help="Maximum delay (seconds) between scripted actions (default 40).",
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
        "--profile-only",
        action="store_true",
        help="Refresh seed profile metadata only (defaults to backfilling seeds with existing edge data).",
    )
    parser.add_argument(
        "--profile-only-all",
        action="store_true",
        help="With --profile-only, refresh every seed instead of only those missing profile details.",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=10,
        help="Number of sample profiles to show during the confirmation preview (default 10).",
    )
    parser.add_argument(
        "--require-confirmation",
        action="store_true",
        help="Require user confirmation before each list refresh (default: auto-confirm based on policy).",
    )
    parser.add_argument(
        "--skip-if-ever-scraped",
        action="store_true",
        help="Skip seeds that have been successfully scraped before (even if stale). Re-scrapes seeds with incomplete metadata.",
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


def _resolve_cookie_path(args: argparse.Namespace) -> Path:
    """Determine which cookie file to use, prompting when multiple exist."""

    candidate = args.cookies
    if candidate.exists():
        return candidate

    default_path = Path("secrets/twitter_cookies.pkl")
    if candidate != default_path:
        raise FileNotFoundError(f"Cookie file not found at {candidate}.")

    secrets_dir = default_path.parent
    if not secrets_dir.exists():
        raise FileNotFoundError(
            "Default cookie path missing and secrets/ directory does not exist."
        )

    cookie_files = sorted(p for p in secrets_dir.glob("*.pkl") if p.is_file())
    if not cookie_files:
        raise FileNotFoundError(
            "No cookie files found in secrets/. Run scripts/setup_cookies.py first."
        )

    if args.quiet:
        chosen = cookie_files[0]
        print(f"[INFO] Using cookie file {chosen} (quiet mode).", file=sys.stderr)
        return chosen

    print("Multiple cookie files found in secrets/:")
    for idx, path in enumerate(cookie_files, start=1):
        print(f"  {idx}. {path.name}")

    while True:
        selection = input(
            f"Select cookie file [1-{len(cookie_files)}] (or press Enter to cancel): "
        ).strip()
        if not selection:
            raise SystemExit("No cookie file selected. Exiting.")
        if not selection.isdigit():
            print("Please enter a number.")
            continue
        index = int(selection)
        if 1 <= index <= len(cookie_files):
            chosen = cookie_files[index - 1]
            print(f"Using cookie file: {chosen.name}")
            return chosen
        print(f"Please enter a number between 1 and {len(cookie_files)}.")


def build_seed_accounts(fetcher: CachedDataFetcher, seed_usernames: List[str]) -> List[SeedAccount]:
    accounts = fetcher.fetch_accounts()
    id_to_username: dict[str, str] = {}
    for _, row in accounts.iterrows():
        account_id = str(row["account_id"])
        raw_username = row.get("username")
        if isinstance(raw_username, str):
            normalized = raw_username.strip().lower()
        else:
            normalized = ""
        id_to_username[account_id] = normalized

    username_to_id = {
        username: account_id for account_id, username in id_to_username.items() if username
    }

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
    args.cookies = _resolve_cookie_path(args)

    # Determine effective log level (--quiet overrides --log-level)
    if args.quiet:
        root_level = logging.DEBUG  # capture DEBUG events for disk
        console_level = logging.WARN
        file_level = logging.DEBUG
        # Suppress selenium and urllib3 console noise, keep errors visible
        logging.getLogger("selenium").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)
    else:
        resolved = getattr(logging, args.log_level.upper(), logging.INFO)
        root_level = resolved
        console_level = resolved
        file_level = resolved

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "enrichment.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)

    log_format = (
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        if not args.quiet
        else "%(levelname)s: %(message)s"
    )
    formatter = logging.Formatter(log_format)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(console_level)
    root_logger.addHandler(console_handler)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5  # 5MB per file
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(file_level)
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
            profile_only=args.profile_only,
            profile_only_all=args.profile_only_all,
        )

        # Build enrichment policy from CLI flags
        policy = EnrichmentPolicy.default()
        if args.require_confirmation:
            policy.require_user_confirmation = True
            policy.auto_confirm_rescrapes = False
        if args.skip_if_ever_scraped:
            policy.skip_if_ever_scraped = True

        enricher = HybridShadowEnricher(store, config, policy)
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
