#!/usr/bin/env python3
"""Debug script to scrape a single account with verbose logging.

This script provides maximum transparency for debugging enrichment issues:
- All actions logged to terminal (DEBUG level)
- DB reads/writes explicitly shown
- Scroll activity displayed
- Edge source tracking visible
- Stops after one account
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

from src.config import get_cache_settings
from src.data.shadow_store import ShadowStore
from src.shadow.enricher import EnrichmentPolicy, HybridShadowEnricher, SeedAccount, ShadowEnrichmentConfig
from src.shadow.selenium_worker import SeleniumConfig, SeleniumWorker


class DebugFormatter(logging.Formatter):
    """Colored formatter for terminal output."""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'

    def format(self, record):
        # Add color based on level
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{self.BOLD}{levelname}{self.RESET}"

        # Color the message based on keywords
        msg = str(record.msg)
        if 'DB READ' in msg or 'Found in DB' in msg:
            record.msg = f"{self.COLORS['DEBUG']}{msg}{self.RESET}"
        elif 'DB WRITE' in msg or 'Writing to DB' in msg or 'Inserted' in msg:
            record.msg = f"{self.BOLD}\033[35m{msg}{self.RESET}"  # Bold magenta
        elif 'scroll' in msg.lower():
            record.msg = f"\033[34m{msg}{self.RESET}"  # Blue
        elif 'Collected' in msg or 'Captured' in msg:
            record.msg = f"{self.BOLD}{self.COLORS['INFO']}{msg}{self.RESET}"  # Bold green

        return super().format(record)


def setup_debug_logging():
    """Configure logging for maximum visibility."""
    # Root logger to DEBUG
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Console handler with debug formatter
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(DebugFormatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    root.addHandler(console)

    # File handler for full trace
    file_handler = logging.FileHandler('logs/debug_single_account.log', mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
    ))
    root.addHandler(file_handler)

    # Suppress selenium noise in console (but keep in file)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def print_banner(text):
    """Print a banner for section separation."""
    width = 80
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Debug scrape for a single account with verbose logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape adityaarpitha with verbose output
  python -m scripts.debug_single_account adityaarpitha --cookies secrets/twitter_cookies.pkl

  # Force re-scrape even if fresh
  python -m scripts.debug_single_account adityaarpitha --force

  # Skip followers list, only scrape following
  python -m scripts.debug_single_account adityaarpitha --following-only
        """
    )

    parser.add_argument(
        'username',
        help='Username to scrape (without @)'
    )
    parser.add_argument(
        '--cookies',
        type=Path,
        help='Path to cookies file (will prompt to select if not provided)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-scrape even if data is fresh'
    )
    parser.add_argument(
        '--following-only',
        action='store_true',
        help='Only scrape following list (skip followers)'
    )
    parser.add_argument(
        '--followers-only',
        action='store_true',
        help='Only scrape followers list (skip following)'
    )
    parser.add_argument(
        '--max-scrolls',
        type=int,
        default=6,
        help='Max stagnant scrolls before stopping (default: 6)'
    )
    parser.add_argument(
        '--delay-min',
        type=float,
        default=5.0,
        help='Min delay between actions in seconds (default: 5.0)'
    )
    parser.add_argument(
        '--delay-max',
        type=float,
        default=10.0,
        help='Max delay between actions in seconds (default: 10.0, use lower for debugging)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )

    args = parser.parse_args()

    # Setup debug logging
    setup_debug_logging()
    logger = logging.getLogger(__name__)

    print_banner(f"DEBUG SCRAPE: @{args.username}")

    # Load config
    cache_settings = get_cache_settings()
    logger.info("✓ Config loaded")

    # Create database engine
    db_path = cache_settings.path
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    logger.info(f"✓ Database engine created: {db_path}")

    # Initialize store
    store = ShadowStore(engine)
    logger.info("✓ Shadow store initialized")

    # Check existing data
    print_banner("DATABASE STATUS CHECK")

    account_id = f"shadow:{args.username}"
    logger.info(f"DB READ: Checking for existing account: {account_id}")

    # Query account directly from DB
    with engine.begin() as conn:
        result = conn.execute(
            text(f"SELECT username, followers_count, following_count, fetched_at FROM shadow_account WHERE account_id = '{account_id}'")
        ).fetchone()

    if result:
        logger.info(f"✓ Found existing account in DB:")
        logger.info(f"  - Followers: {result[1]}")
        logger.info(f"  - Following: {result[2]}")
        logger.info(f"  - Last fetched: {result[3]}")
        existing = result
    else:
        logger.info(f"✗ No existing account record found")
        existing = None

    # Check metrics
    logger.info(f"DB READ: Checking scrape metrics for: {account_id}")
    metrics = store.get_last_scrape_metrics(account_id)
    if metrics:
        logger.info(f"✓ Found scrape metrics:")
        logger.info(f"  - Run at: {metrics.run_at}")
        logger.info(f"  - Following captured: {metrics.following_captured}")
        logger.info(f"  - Followers captured: {metrics.followers_captured}")
        logger.info(f"  - Skipped: {metrics.skipped}")

        if args.force:
            logger.warning("⚠️  --force flag set: Will re-scrape despite existing data")
    else:
        logger.info(f"✗ No scrape metrics found (first run)")

    # Check edges
    logger.info(f"DB READ: Counting edges for: {account_id}")

    # Count outbound (following)
    with engine.begin() as conn:
        result = conn.execute(
            text(f"SELECT COUNT(*) as c FROM shadow_edge WHERE source_id = '{account_id}' AND direction = 'outbound'")
        ).fetchone()
        outbound_count = result[0] if result else 0
    logger.info(f"  - Outbound edges (following): {outbound_count}")

    # Sample outbound edges with metadata
    if outbound_count > 0:
        with engine.begin() as conn:
            sample_out = conn.execute(text(f"""
                SELECT target_id, json_extract(metadata, '$.seed_username') as seed,
                       json_extract(metadata, '$.list_type') as list
                FROM shadow_edge
                WHERE source_id = '{account_id}' AND direction = 'outbound'
                LIMIT 3
            """)).fetchall()
        logger.info(f"  - Sample outbound edges:")
        for row in sample_out:
            logger.info(f"    → {row[0]} (from @{row[1]}'s {row[2]} list)")

    # Count inbound (followers)
    with engine.begin() as conn:
        result = conn.execute(
            text(f"SELECT COUNT(*) as c FROM shadow_edge WHERE target_id = '{account_id}' AND direction = 'inbound'")
        ).fetchone()
        inbound_count = result[0] if result else 0
    logger.info(f"  - Inbound edges (followers): {inbound_count}")

    # Sample inbound edges with metadata
    if inbound_count > 0:
        with engine.begin() as conn:
            sample_in = conn.execute(text(f"""
                SELECT source_id, json_extract(metadata, '$.seed_username') as seed,
                       json_extract(metadata, '$.list_type') as list
                FROM shadow_edge
                WHERE target_id = '{account_id}' AND direction = 'inbound'
                LIMIT 3
            """)).fetchall()
        logger.info(f"  - Sample inbound edges:")
        for row in sample_in:
            logger.info(f"    ← {row[0]} (from @{row[1]}'s {row[2]} list)")

    # Configure selenium
    print_banner("SELENIUM CONFIGURATION")

    if not args.cookies:
        # Look for cookie files in secrets/
        secrets_dir = Path("secrets")
        if not secrets_dir.exists():
            logger.error("No secrets/ directory found. Please create it and add cookie files.")
            return 1

        cookie_files = sorted(secrets_dir.glob("*.pkl"))
        if not cookie_files:
            logger.error("No .pkl cookie files found in secrets/")
            return 1

        if len(cookie_files) == 1:
            cookies_path = cookie_files[0]
            logger.info(f"Using only available cookie file: {cookies_path}")
        else:
            print("\nMultiple cookie files found:")
            for i, f in enumerate(cookie_files, 1):
                print(f"  {i}. {f.name}")

            try:
                choice = input(f"Select cookie file [1-{len(cookie_files)}]: ").strip()
                idx = int(choice) - 1
                if idx < 0 or idx >= len(cookie_files):
                    logger.error("Invalid selection")
                    return 1
                cookies_path = cookie_files[idx]
            except (ValueError, KeyboardInterrupt):
                logger.error("Invalid selection or cancelled")
                return 1
    else:
        cookies_path = args.cookies

    logger.info(f"Using cookies: {cookies_path}")

    # Create enrichment config (bundles selenium + policy settings)
    config = ShadowEnrichmentConfig(
        selenium_cookies_path=cookies_path,
        selenium_headless=args.headless,
        selenium_scroll_delay_min=args.delay_min,
        selenium_scroll_delay_max=args.delay_max,
        selenium_max_no_change_scrolls=args.max_scrolls,
        action_delay_min=args.delay_min,
        action_delay_max=args.delay_max,
        user_pause_seconds=0.5,  # Short pause between users in debug mode
        chrome_binary=None,
        wait_for_manual_login=True,  # Will prompt to verify session
        include_followers=not args.following_only,
        include_following=not args.followers_only,
        include_followers_you_follow=False,  # Skip this list in debug mode
        bearer_token=None,  # No API fallback in debug mode
        confirm_first_scrape=False,  # Auto-proceed in debug mode
        preview_sample_size=5,
        profile_only=False,
    )

    logger.info(f"Enrichment config:")
    logger.info(f"  - Headless: {args.headless}")
    logger.info(f"  - Delay range: {args.delay_min}s - {args.delay_max}s")
    logger.info(f"  - Max stagnant scrolls: {args.max_scrolls}")
    logger.info(f"  - Include following: {config.include_following}")
    logger.info(f"  - Include followers: {config.include_followers}")

    # Configure enrichment policy
    policy = EnrichmentPolicy(
        list_refresh_days=0 if args.force else 7,
        skip_if_ever_scraped=False,
        require_user_confirmation=False,
        auto_confirm_rescrapes=True,
    )

    # Create enricher
    enricher = HybridShadowEnricher(
        store=store,
        config=config,
        policy=policy,
    )

    # Create seed account
    seed = SeedAccount(
        account_id=account_id,
        username=args.username,
        trust=1.0,
    )

    # Determine which lists to scrape
    scrape_following = not args.followers_only
    scrape_followers = not args.following_only

    print_banner("STARTING SCRAPE")
    logger.info(f"Target: @{args.username}")
    logger.info(f"Lists to scrape:")
    logger.info(f"  - Following: {'YES' if scrape_following else 'NO'}")
    logger.info(f"  - Followers: {'YES' if scrape_followers else 'NO'}")

    try:
        # Enrich the account (single seed)
        results = enricher.enrich([seed])

        print_banner("SCRAPE COMPLETE")

        # Get result for our seed
        result = results.get(args.username)

        if result and not result.get('skipped'):
            logger.info("✓ Enrichment succeeded")
            logger.info(f"  - Result: {result}")

            # Show final edge counts
            logger.info("DB READ: Final edge counts")
            with engine.begin() as conn:
                result_out = conn.execute(
                    text(f"SELECT COUNT(*) as c FROM shadow_edge WHERE source_id = '{account_id}' AND direction = 'outbound'")
                ).fetchone()
                final_out = result_out[0] if result_out else 0

                result_in = conn.execute(
                    text(f"SELECT COUNT(*) as c FROM shadow_edge WHERE target_id = '{account_id}' AND direction = 'inbound'")
                ).fetchone()
                final_in = result_in[0] if result_in else 0

            logger.info(f"  - Outbound (following): {final_out} edges")
            logger.info(f"  - Inbound (followers): {final_in} edges")

            # Show final profile data
            logger.info("DB READ: Final profile data")
            with engine.begin() as conn:
                profile_data = conn.execute(
                    text(f"""
                        SELECT display_name, bio, location, website, profile_image_url, followers_count, following_count
                        FROM shadow_account
                        WHERE account_id = '{account_id}'
                    """)
                ).fetchone()

            if profile_data:
                logger.info(f"  - Display name: {profile_data[0]}")
                logger.info(f"  - Bio: {profile_data[1][:100] if profile_data[1] else None}...")
                logger.info(f"  - Location: {profile_data[2]}")
                logger.info(f"  - Website: {profile_data[3]}")
                logger.info(f"  - Profile image: {profile_data[4][:60] if profile_data[4] else None}...")
                logger.info(f"  - Followers: {profile_data[5]}")
                logger.info(f"  - Following: {profile_data[6]}")

            # Show NEW data added
            logger.info("DB READ: New data added in this run")

            # New outbound edges (following)
            new_out = final_out - outbound_count
            if new_out > 0:
                logger.info(f"  ✓ Added {new_out} new following edges ({outbound_count} → {final_out})")

                # Sample new accounts
                with engine.begin() as conn:
                    new_accounts = conn.execute(
                        text(f"""
                            SELECT s.username, s.display_name, s.bio
                            FROM shadow_edge e
                            JOIN shadow_account s ON e.target_id = s.account_id
                            WHERE e.source_id = '{account_id}'
                            AND e.direction = 'outbound'
                            ORDER BY e.fetched_at DESC
                            LIMIT 5
                        """)
                    ).fetchall()

                if new_accounts:
                    logger.info("  Sample newly added accounts:")
                    for acc in new_accounts:
                        bio_preview = (acc[2][:60] + "...") if acc[2] and len(acc[2]) > 60 else (acc[2] or "(no bio)")
                        logger.info(f"    • @{acc[0]} ({acc[1]}) - \"{bio_preview}\"")
            else:
                logger.info(f"  - No new following edges added (stayed at {outbound_count})")

            # New inbound edges (followers)
            new_in = final_in - inbound_count
            if new_in > 0:
                logger.info(f"  ✓ Added {new_in} new follower edges ({inbound_count} → {final_in})")
            else:
                logger.info(f"  - No new follower edges added (stayed at {inbound_count})")

            # Calculate coverage
            if existing:
                following_count = existing[2]  # following_count
                followers_count = existing[1]  # followers_count

                if following_count:
                    following_pct = (final_out / following_count) * 100
                    logger.info(f"  - Following coverage: {following_pct:.1f}% ({final_out}/{following_count})")
                if followers_count:
                    followers_pct = (final_in / followers_count) * 100
                    logger.info(f"  - Followers coverage: {followers_pct:.1f}% ({final_in}/{followers_count})")
        else:
            logger.warning("⚠️  Enrichment returned no result (possibly skipped)")

    except Exception as e:
        logger.exception(f"✗ Enrichment failed: {e}")
        return 1

    print_banner("DEBUG SESSION END")
    logger.info("Full trace saved to: logs/debug_single_account.log")

    return 0


if __name__ == '__main__':
    sys.exit(main())
