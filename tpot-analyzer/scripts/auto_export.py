"""Auto-export: prepare local public-site candidates when enough new labeled data exists.

Checks how many accounts have been labeled since the last export. If the delta
exceeds a threshold, runs the local export pipeline. Publication requires separate review and an
explicit exact-digest approval in the upload command.

Usage:
    .venv/bin/python3 -m scripts.auto_export              # check + export if needed
    .venv/bin/python3 -m scripts.auto_export --force       # export regardless
    .venv/bin/python3 -m scripts.auto_export --dry-run     # check without exporting
    .venv/bin/python3 -m scripts.auto_export --threshold 5 # custom threshold
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

ARCHIVE_DB = DEFAULT_ARCHIVE_DB
MARKER_FILE = ROOT / "data" / ".last_export_state.json"
PUBLIC_SITE_DIR = ROOT / "data" / "publication_candidates"
DEFAULT_THRESHOLD = 10


def get_current_state(db_path: Path) -> dict:
    """Query DB for current labeling state."""
    conn = sqlite3.connect(str(db_path))
    try:
        # Accounts with bits rollup
        bits_accounts = conn.execute(
            "SELECT COUNT(DISTINCT account_id) FROM account_community_bits"
        ).fetchone()[0]

        # Total bits rows
        bits_rows = conn.execute(
            "SELECT COUNT(*) FROM account_community_bits"
        ).fetchone()[0]

        # Accounts with labeled tweets (tweet_tags with category='bits')
        labeled_accounts = conn.execute("""
            SELECT COUNT(DISTINCT t.account_id)
            FROM tweet_tags tt
            JOIN tweets t ON t.tweet_id = tt.tweet_id
            WHERE tt.category = 'bits'
        """).fetchone()[0]

        # Total labeled tweets
        labeled_tweets = conn.execute("""
            SELECT COUNT(DISTINCT tt.tweet_id)
            FROM tweet_tags tt
            WHERE tt.category = 'bits'
        """).fetchone()[0]

        # Accounts with >=20 labeled tweets (high-confidence)
        stable_accounts = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT t.account_id, COUNT(DISTINCT t.tweet_id) as cnt
                FROM tweet_tags tt
                JOIN tweets t ON t.tweet_id = tt.tweet_id
                WHERE tt.category = 'bits'
                GROUP BY t.account_id
                HAVING cnt >= 20
            )
        """).fetchone()[0]

        # Total classified accounts in community_account (NMF)
        nmf_accounts = conn.execute(
            "SELECT COUNT(DISTINCT account_id) FROM community_account"
        ).fetchone()[0]

        return {
            "bits_accounts": bits_accounts,
            "bits_rows": bits_rows,
            "labeled_accounts": labeled_accounts,
            "labeled_tweets": labeled_tweets,
            "stable_accounts": stable_accounts,
            "nmf_accounts": nmf_accounts,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def load_last_state() -> dict | None:
    """Load the last export state from marker file."""
    if not MARKER_FILE.exists():
        return None
    try:
        return json.loads(MARKER_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_state(state: dict) -> None:
    """Save current state as the last export marker."""
    state["exported_at"] = datetime.now(timezone.utc).isoformat()
    MARKER_FILE.write_text(json.dumps(state, indent=2) + "\n")


def should_export(current: dict, last: dict | None, threshold: int) -> tuple[bool, str]:
    """Decide whether to re-export based on delta."""
    if last is None:
        return True, "no previous export found"

    delta_accounts = current["bits_accounts"] - last.get("bits_accounts", 0)
    delta_tweets = current["labeled_tweets"] - last.get("labeled_tweets", 0)
    delta_stable = current["stable_accounts"] - last.get("stable_accounts", 0)

    reasons = []
    if delta_accounts >= threshold:
        reasons.append(f"{delta_accounts} new labeled accounts (threshold={threshold})")
    if delta_stable > 0:
        reasons.append(f"{delta_stable} new accounts with 20+ tweets")
    if delta_tweets >= threshold * 10:
        reasons.append(f"{delta_tweets} new labeled tweets")

    if reasons:
        return True, "; ".join(reasons)
    return False, (
        f"delta below threshold: {delta_accounts} new accounts, "
        f"{delta_tweets} new tweets, {delta_stable} newly stable"
    )


def run_export() -> bool:
    """Run the export pipeline."""
    logger.info("Running export pipeline...")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.export_public_site"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Export failed:\n%s", result.stderr)
        return False
    logger.info("Export completed successfully")
    if result.stdout.strip():
        # Print last few lines of output
        for line in result.stdout.strip().split("\n")[-5:]:
            logger.info("  %s", line)
    return True


def run_rollup() -> bool:
    """Run bits rollup before export to ensure DB is fresh."""
    logger.info("Running bits rollup...")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.rollup_bits"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Rollup failed:\n%s", result.stderr)
        return False
    logger.info("Rollup completed")
    return True


def main():
    parser = argparse.ArgumentParser(description="Auto-export public site when new data exists")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Min new labeled accounts to trigger export (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--force", action="store_true",
                        help="Export regardless of threshold")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check state without exporting")
    parser.add_argument("--no-push", action="store_true",
                        help="Compatibility flag: candidates are always local")
    parser.add_argument("--no-cards", action="store_true",
                        help="Compatibility flag: this script never generates paid cards")
    parser.add_argument("--db-path", type=Path, default=ARCHIVE_DB,
                        help="Path to archive_tweets.db")
    args = parser.parse_args()

    # 1. Check current state
    current = get_current_state(args.db_path)
    last = load_last_state()

    logger.info("=== Current labeling state ===")
    logger.info("  Accounts with bits rollup:  %d", current["bits_accounts"])
    logger.info("  Accounts with labeled tweets: %d", current["labeled_accounts"])
    logger.info("  Stable accounts (20+ tweets): %d", current["stable_accounts"])
    logger.info("  Total labeled tweets:         %d", current["labeled_tweets"])
    logger.info("  NMF classified accounts:      %d", current["nmf_accounts"])

    if last:
        logger.info("")
        logger.info("=== Last export ===")
        logger.info("  Exported at:     %s", last.get("exported_at", "unknown"))
        logger.info("  Bits accounts:   %d", last.get("bits_accounts", 0))
        logger.info("  Labeled tweets:  %d", last.get("labeled_tweets", 0))
        logger.info("  Stable accounts: %d", last.get("stable_accounts", 0))

    # 2. Decide
    if args.force:
        should, reason = True, "forced export"
    else:
        should, reason = should_export(current, last, args.threshold)

    logger.info("")
    if should:
        logger.info("✓ Export needed: %s", reason)
    else:
        logger.info("· No export needed: %s", reason)

    if args.dry_run:
        logger.info("(dry run — stopping here)")
        return

    if not should:
        return

    # 3. Rollup bits first
    if not run_rollup():
        sys.exit(1)

    # 4. Export
    if not run_export():
        sys.exit(1)

    # 5. Save marker
    save_state(current)

    logger.info("Local candidate prepared. Review publication-manifest.json and the exact bytes.")
    logger.info("Publication requires a separate approved digest; no Git push, deploy, or paid card request runs here.")

    logger.info("")
    logger.info("Done.")


if __name__ == "__main__":
    main()
