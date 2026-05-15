"""Auto-export: re-export + deploy public site when enough new labeled data exists.

Checks how many accounts have been labeled since the last export. If the delta
exceeds a threshold, runs the full export pipeline, commits, and pushes
(which triggers Vercel auto-deploy).

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
PUBLIC_SITE_DIR = ROOT / "public-site" / "public"
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


def git_commit_and_push(reason: str) -> bool:
    """Commit updated export files and push."""
    data_json = PUBLIC_SITE_DIR / "data.json"
    search_json = PUBLIC_SITE_DIR / "search.json"

    if not data_json.exists():
        logger.error("data.json not found at %s", data_json)
        return False

    # Check if files actually changed
    status = subprocess.run(
        ["git", "status", "--porcelain", str(data_json), str(search_json)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if not status.stdout.strip():
        logger.info("No changes to data.json / search.json — skipping commit")
        return True

    # Stage
    subprocess.run(
        ["git", "add", str(data_json), str(search_json)],
        cwd=str(ROOT),
        check=True,
    )

    # Commit
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"chore(export): auto-export {now}\n\n{reason}"
    subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(ROOT),
        check=True,
    )

    # Push
    logger.info("Pushing to origin...")
    result = subprocess.run(
        ["git", "push"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Push failed:\n%s", result.stderr)
        return False
    logger.info("Pushed — Vercel will auto-deploy")
    return True


SITE_URL = "https://maptpot.vercel.app"


def pre_generate_cards(db_path: Path, site_url: str = SITE_URL) -> None:
    """Hit /api/generate-card for each labeled account to pre-cache cards.

    Reads the exported data.json to build card payloads with resolved community
    names/colors, then POSTs to the deployed Vercel endpoint. Cards are cached
    permanently in Vercel KV, so subsequent visits are instant.
    """
    import time
    try:
        import urllib.request
    except ImportError:
        logger.warning("urllib not available — skipping card pre-generation")
        return

    data_json = PUBLIC_SITE_DIR / "data.json"
    if not data_json.exists():
        logger.warning("data.json not found — skipping card pre-generation")
        return

    data = json.loads(data_json.read_text())
    community_map = {c["id"]: c for c in data.get("communities", [])}

    # Find labeled accounts (those with bits data)
    conn = sqlite3.connect(str(db_path))
    labeled_ids = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM account_community_bits"
        ).fetchall()
    )
    conn.close()

    # Build payloads from exported data
    accounts_to_generate = []
    for acct in data.get("classified_accounts", []):
        if acct["id"] not in labeled_ids:
            continue
        memberships = acct.get("memberships", [])
        communities = []
        for m in sorted(memberships, key=lambda x: -x["weight"]):
            comm = community_map.get(m["community_id"], {})
            communities.append({
                "name": comm.get("name", "Unknown"),
                "color": comm.get("color", "#666"),
                "weight": m["weight"],
                "description": comm.get("description", ""),
            })
        if communities:
            accounts_to_generate.append({
                "handle": acct.get("username", acct["id"]),
                "bio": acct.get("bio"),
                "communities": communities,
                "tweets": [],  # API will generate without tweets
            })

    if not accounts_to_generate:
        logger.info("No labeled accounts to pre-generate cards for")
        return

    logger.info("Pre-generating cards for %d labeled accounts...", len(accounts_to_generate))
    endpoint = f"{site_url}/api/generate-card"
    success = 0
    for payload in accounts_to_generate:
        handle = payload["handle"]
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if result.get("cached"):
                    logger.info("  @%-20s already cached", handle)
                else:
                    logger.info("  @%-20s card generated", handle)
                success += 1
        except Exception as e:
            logger.warning("  @%-20s failed: %s", handle, e)
        time.sleep(1)  # Rate limit — 1 card/sec

    logger.info("Cards: %d/%d generated", success, len(accounts_to_generate))


def main():
    parser = argparse.ArgumentParser(description="Auto-export public site when new data exists")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Min new labeled accounts to trigger export (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--force", action="store_true",
                        help="Export regardless of threshold")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check state without exporting")
    parser.add_argument("--no-push", action="store_true",
                        help="Export and commit but don't push")
    parser.add_argument("--no-cards", action="store_true",
                        help="Skip card pre-generation after deploy")
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

    # 6. Commit + push
    if not args.no_push:
        if not git_commit_and_push(reason):
            logger.error("Commit/push failed — export files are ready but not deployed")
            sys.exit(1)
    else:
        logger.info("--no-push: skipping git commit and push")

    # 7. Pre-generate cards for labeled accounts
    if not args.no_cards and not args.no_push:
        logger.info("")
        logger.info("Waiting 30s for Vercel deploy to start...")
        import time
        time.sleep(30)
        pre_generate_cards(args.db_path)
    elif args.no_cards:
        logger.info("--no-cards: skipping card pre-generation")

    logger.info("")
    logger.info("Done.")


if __name__ == "__main__":
    main()
