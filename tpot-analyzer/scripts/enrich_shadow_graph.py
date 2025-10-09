"""CLI entrypoint for hybrid + API-based shadow enrichment."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

import logging

LOGGER = logging.getLogger(__name__)

from src.config import get_cache_settings
from src.logging_utils import setup_enrichment_logging
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
        "--max-scrolls",
        type=int,
        default=6,
        help="Max consecutive scrolls with no height change before stopping (default 6). Applies to following, followers, verified_followers, and followers_you_follow lists. Increase to 20+ for accounts with 1000+ following/followers.",
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
        "--retry-attempts",
        type=int,
        default=5,
        help="Number of retry attempts for failed profile fetches (default 5). Set to 1 to disable retries.",
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
        default=True,
        help="Skip seeds that have been successfully scraped before (even if stale). Re-scrapes seeds with incomplete metadata. Enabled by default.",
    )
    parser.add_argument(
        "--no-skip-if-ever-scraped",
        dest="skip_if_ever_scraped",
        action="store_false",
        help="Disable the default skip behavior and re-scrape all seeds regardless of previous scrape status.",
    )
    parser.add_argument(
        "--center",
        type=str,
        default=None,
        help="Center username (e.g., 'adityaarpitha'). Fetches their /following list and prioritizes those accounts after the seed preset.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        help="Console logging verbosity (default INFO). File always logs DEBUG.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all non-essential output (sets log level to WARN, skips preview).",
    )
    parser.add_argument(
        "--enable-api-fallback",
        action="store_true",
        help="Enable X API fallback for enriching accounts with missing bios (requires --bearer-token or X_BEARER_TOKEN env). WARNING: May cause rate limiting.",
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

    # Setup colored and filtered logging
    console_log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    if args.quiet:
        console_log_level = logging.WARN
    setup_enrichment_logging(console_level=console_log_level, quiet=args.quiet)
    cache_settings = get_cache_settings()

    # Only enable X API fallback if explicitly requested
    bearer = None
    if args.enable_api_fallback:
        bearer = args.bearer_token or os.getenv("X_BEARER_TOKEN")
        if bearer:
            LOGGER.info("X API fallback enabled (--enable-api-fallback). May cause rate limiting.")
        else:
            LOGGER.warning("--enable-api-fallback specified but no bearer token found (check --bearer-token or X_BEARER_TOKEN env)")

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

        # If a center user is specified, enrich them FIRST then use their
        # following list from the DB to prioritize remaining seeds
        if args.center:
            center_username_lower = args.center.lower()
            LOGGER.info("Center user @%s specified - will enrich first, then prioritize their following list.", args.center)

            # Ensure center user is in the seed list (add if missing)
            if center_username_lower not in seed_usernames:
                seed_usernames.insert(0, center_username_lower)
            else:
                # Move to front if already present
                seed_usernames.remove(center_username_lower)
                seed_usernames.insert(0, center_username_lower)

        seeds = build_seed_accounts(fetcher, seed_usernames)

        # Calculate retry_delays from retry_attempts (attempts = delays + 1)
        retry_delays = [5.0, 15.0, 60.0][:max(0, args.retry_attempts - 1)]

        config = ShadowEnrichmentConfig(
            selenium_cookies_path=args.cookies,
            selenium_headless=args.headless,
            selenium_scroll_delay_min=args.delay_min,
            selenium_scroll_delay_max=args.delay_max,
            selenium_max_no_change_scrolls=args.max_scrolls,
            selenium_retry_delays=retry_delays,
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
            # If --center was specified, enrich just the center user first
            if args.center and len(seeds) > 0 and seeds[0].username == args.center.lower():
                center_seed = seeds[0]
                remaining_seeds = seeds[1:]

                LOGGER.info("Enriching center user @%s first...", args.center)
                enricher.enrich([center_seed])

                # Now query the DB for their following list to add as priority seeds
                center_following_usernames = set(store.get_following_usernames(args.center))

                if center_following_usernames:
                    LOGGER.info("Found %d accounts followed by @%s in DB cache.", len(center_following_usernames), args.center)

                    # Build seed priority: preset seeds first, then ALL center's following, then others
                    preset_usernames = set(load_seed_candidates())
                    remaining_usernames = {s.username for s in remaining_seeds}

                    # Priority groups
                    priority_seeds = remaining_usernames.intersection(preset_usernames)
                    center_following_not_in_archive = center_following_usernames - remaining_usernames - priority_seeds
                    center_following_in_archive = center_following_usernames.intersection(remaining_usernames) - priority_seeds
                    other_seeds = remaining_usernames - priority_seeds - center_following_in_archive

                    # Build reordered list: presets, then center's following (in archive), then center's following (not in archive), then others
                    reordered_usernames = (
                        sorted(list(priority_seeds)) +
                        sorted(list(center_following_in_archive)) +
                        sorted(list(center_following_not_in_archive)) +
                        sorted(list(other_seeds))
                    )

                    # Build seeds: use archive data where available, create shadow seeds for the rest
                    archive_based_seeds = build_seed_accounts(fetcher, reordered_usernames)

                    # Create shadow seeds for usernames not found in archive (these will get enriched from scratch)
                    archive_usernames = {s.username.lower() for s in archive_based_seeds if s.username}
                    shadow_seed_usernames = [u for u in reordered_usernames if u.lower() not in archive_usernames]
                    shadow_seeds = [
                        SeedAccount(account_id=f"shadow:{username}", username=username, trust=0.8)
                        for username in shadow_seed_usernames
                    ]

                    seeds = [center_seed] + archive_based_seeds + shadow_seeds

                    LOGGER.info(
                        "Reordered seeds: %d preset, %d from @%s's following (%d in archive, %d new shadow seeds), %d others. Total: %d seeds.",
                        len(priority_seeds),
                        len(center_following_in_archive) + len(shadow_seeds),
                        args.center,
                        len(center_following_in_archive),
                        len(shadow_seeds),
                        len(other_seeds),
                        len(seeds)
                    )
                else:
                    LOGGER.warning("No following data found for @%s in DB. Continuing with original seed order.", args.center)
                    # Restore full seeds list
                    seeds = [center_seed] + remaining_seeds

            # Run the main enrichment loop
            summary = enricher.enrich(seeds)
        except KeyboardInterrupt:
            logging.getLogger(__name__).warning("Interrupted by user; shutting down enrichment cleanly")
            summary = {"status": "interrupted"}
        except RuntimeError as err:
            logging.getLogger(__name__).error(str(err))
            summary = {"status": "aborted", "reason": str(err)}
        finally:
            # Ensure browser is closed
            enricher.quit()

    payload = json.dumps(summary, indent=2)
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
