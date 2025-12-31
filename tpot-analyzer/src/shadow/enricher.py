"""Hybrid enrichment orchestrator mixing Selenium scraping and X API lookups."""
from __future__ import annotations

import json
import logging
import random
import select
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy.exc import OperationalError

from ..data.shadow_store import (
    ScrapeRunMetrics,
    ShadowAccount,
    ShadowDiscovery,
    ShadowEdge,
    ShadowList,
    ShadowListMember,
    ShadowStore,
)
from .selenium_worker import (
    CapturedUser,
    ListOverview,
    ProfileOverview,
    SeleniumConfig,
    SeleniumWorker,
    UserListCapture,
)
from .x_api_client import XAPIClient, XAPIClientConfig


LOGGER = logging.getLogger(__name__)


# Account status retry periods (in days)
ACCOUNT_STATUS_RETRY_DAYS = {
    "protected": 90,    # Protected accounts may become public
    "deleted": 365,     # Usernames rarely recycled, but check yearly
    "suspended": 365,   # Suspended accounts may be reinstated
}


def _shorten_text(value: Optional[str], limit: int = 160) -> str:
    """Return a condensed representation for log output."""

    if value is None:
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    if len(text) <= limit:
        return text

    return text[: max(0, limit - 3)] + "..."


@dataclass(frozen=True)
class SeedAccount:
    account_id: str
    username: Optional[str]
    trust: float = 1.0


@dataclass
class EnrichmentPolicy:
    """Policy for cache-aware enrichment refresh decisions."""
    list_refresh_days: int = 180
    profile_refresh_days: int = 30
    pct_delta_threshold: float = 0.5
    require_user_confirmation: bool = False  # Non-blocking default (use --require-confirmation to enable)
    auto_confirm_rescrapes: bool = True  # Auto-proceed by default
    skip_if_ever_scraped: bool = False  # Skip accounts that have been scraped before (even if stale)

    @classmethod
    def from_file(cls, path: Path) -> "EnrichmentPolicy":
        """Load policy from JSON file."""
        with open(path) as f:
            data = json.load(f)
        # Filter out comments and unknown fields
        valid_fields = {k: v for k, v in data.items() if not k.startswith("_")}
        return cls(**valid_fields)

    @classmethod
    def default(cls) -> "EnrichmentPolicy":
        """Return default policy."""
        return cls()


@dataclass
class ShadowEnrichmentConfig:
    selenium_cookies_path: Path
    selenium_headless: bool = False
    selenium_scroll_delay_min: float = 5.0
    selenium_scroll_delay_max: float = 40.0
    selenium_max_no_change_scrolls: int = 6
    selenium_retry_delays: List[float] = None
    user_pause_seconds: float = 5.0
    action_delay_min: float = 5.0
    action_delay_max: float = 40.0
    chrome_binary: Optional[Path] = None
    include_following: bool = True
    include_followers: bool = True
    include_followers_you_follow: bool = True
    bearer_token: Optional[str] = None
    rate_state_path: Path = Path("data/x_api_rate_state.json")
    wait_for_manual_login: bool = True
    confirm_first_scrape: bool = True
    preview_sample_size: int = 10
    profile_only: bool = False
    profile_only_all: bool = False

    def __post_init__(self):
        """Set default retry delays if not provided."""
        if self.selenium_retry_delays is None:
            self.selenium_retry_delays = [5.0, 15.0, 60.0]


class HybridShadowEnricher:
    """Coordinates Selenium scraping with optional X API enrichment."""

    def __init__(
        self,
        store: ShadowStore,
        config: ShadowEnrichmentConfig,
        policy: Optional[EnrichmentPolicy] = None
    ) -> None:
        self._store = store
        self._config = config
        if policy is None:
            self._policy = EnrichmentPolicy.default()
        elif not isinstance(policy, EnrichmentPolicy):
            raise TypeError(f"policy must be EnrichmentPolicy or None, got {type(policy)!r}")
        else:
            self._policy = policy
        selenium_config = SeleniumConfig(
            cookies_path=config.selenium_cookies_path,
            headless=config.selenium_headless,
            scroll_delay_min=config.selenium_scroll_delay_min,
            scroll_delay_max=config.selenium_scroll_delay_max,
            max_no_change_scrolls=config.selenium_max_no_change_scrolls,
            action_delay_min=config.action_delay_min,
            action_delay_max=config.action_delay_max,
            chrome_binary=config.chrome_binary,
            require_confirmation=config.wait_for_manual_login,
            retry_delays=config.selenium_retry_delays,
        )
        self._selenium = SeleniumWorker(selenium_config)
        # Wire up pause/shutdown callbacks so selenium worker can respond to Ctrl+C
        self._selenium.set_pause_callback(lambda: self._pause_requested)
        self._selenium.set_shutdown_callback(lambda: self._shutdown_requested)
        self._api: Optional[XAPIClient] = None
        if config.bearer_token:
            api_config = XAPIClientConfig(
                bearer_token=config.bearer_token,
                rate_state_path=config.rate_state_path,
            )
            self._api = XAPIClient(api_config)
        self._resolution_cache: Dict[str, Dict[str, object]] = {}
        self._first_scrape_confirmed = not config.confirm_first_scrape
        self._current_phase_timings: dict[str, dict[str, float]] = {}

        # Pause/resume state
        self._pause_requested = False
        self._shutdown_requested = False
        self._original_sigint_handler = None

    def _log_pre_run_summary(self, seed: SeedAccount):
        logger = logging.getLogger(__name__)
        logger.info(f"--- Pre-run DB status for @{seed.username} ---")

        # Get account info
        account = self._store.get_shadow_account(seed.account_id)
        if account:
            logger.info(f"  Account found: followers={account.followers_count}, following={account.following_count}, fetched_at={account.fetched_at}")
        else:
            logger.info("  Account not found in DB.")

        # Get last scrape metrics
        metrics = self._store.get_last_scrape_metrics(seed.account_id)
        if metrics:
            logger.info(f"  Last scrape: run_at={metrics.run_at}, following_captured={metrics.following_captured}, followers_captured={metrics.followers_captured}")
        else:
            logger.info("  No previous scrape metrics found.")

        # Get edge summary
        edge_summary = self._store.edge_summary_for_seed(seed.account_id)
        logger.info(f"  Edge counts: following={edge_summary['following']}, followers={edge_summary['followers']}")
        logger.info("-------------------------------------------------")

    @contextmanager
    def _time_phase(self, group: str, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            bucket = self._current_phase_timings.setdefault(group, {})
            bucket[name] = bucket.get(name, 0.0) + duration
            LOGGER.debug("[timing] %-15s %-24s %.3fs", group, name, duration)

    def _phase_snapshot(self) -> Optional[dict[str, dict[str, float]]]:
        if not self._current_phase_timings:
            return None
        return {
            group: {phase: round(duration, 4) for phase, duration in phases.items()}
            for group, phases in self._current_phase_timings.items()
        }

    def _log_phase_summary(self, identifier: str) -> None:
        snapshot = self._phase_snapshot()
        if not snapshot:
            return
        LOGGER.debug("[timing] summary for %s: %s", identifier, snapshot)

    # ------------------------------------------------------------------
    # Pause/Resume Helpers
    # ------------------------------------------------------------------
    def _setup_signal_handler(self) -> None:
        """Setup signal handler for graceful pause on Ctrl+C."""
        def signal_handler(signum, frame):
            if self._pause_requested:
                # Second Ctrl+C - immediate shutdown
                LOGGER.warning("\n⚠️  Second Ctrl+C detected - forcing shutdown...")
                self._shutdown_requested = True
                # Restore original handler and re-raise to trigger immediate exit
                signal.signal(signal.SIGINT, self._original_sigint_handler)
                raise KeyboardInterrupt
            else:
                # First Ctrl+C - request pause after current seed
                LOGGER.warning("\n⏸️  Pause requested (Ctrl+C). Will pause after current seed completes...")
                LOGGER.warning("   Press Ctrl+C again to force immediate shutdown.")
                self._pause_requested = True

        self._original_sigint_handler = signal.signal(signal.SIGINT, signal_handler)

    def _restore_signal_handler(self) -> None:
        """Restore original signal handler."""
        if self._original_sigint_handler:
            signal.signal(signal.SIGINT, self._original_sigint_handler)

    def _handle_pause_menu(self, current_seed_idx: int, total_seeds: int) -> str:
        """Show pause menu and return user choice.

        Returns:
            'resume' - Continue enrichment
            'shutdown' - Exit cleanly
            'skip' - Skip remaining seeds
        """
        print("\n" + "=" * 80)
        print("⏸️  ENRICHMENT PAUSED")
        print("=" * 80)
        print(f"Progress: {current_seed_idx}/{total_seeds} seeds completed")
        print(f"Remaining: {total_seeds - current_seed_idx} seeds")
        print("\nOptions:")
        print("  [r] Resume enrichment")
        print("  [s] Shutdown and save progress")
        print("  [q] Quit (same as shutdown)")
        print("=" * 80)

        while True:
            try:
                response = input("\nYour choice [r/s/q]: ").strip().lower()
                if response in ('r', 'resume'):
                    print("▶️  Resuming enrichment...\n")
                    return 'resume'
                elif response in ('s', 'shutdown', 'q', 'quit'):
                    print("🛑 Shutting down gracefully...\n")
                    return 'shutdown'
                else:
                    print("Invalid choice. Please enter 'r' (resume) or 's' (shutdown).")
            except (KeyboardInterrupt, EOFError):
                # Handle Ctrl+C or Ctrl+D during menu
                print("\n🛑 Shutdown requested during pause menu...\n")
                return 'shutdown'

    # ------------------------------------------------------------------
    # Enrichment Workflow Helpers
    # ------------------------------------------------------------------
    def _should_skip_seed(
        self, seed: SeedAccount
    ) -> tuple[bool, Optional[str], dict, Optional[ProfileOverview]]:
        """Check if seed should be skipped based on existing data and policy.

        Skip conditions:
        - In normal mode: skip if we have complete profile AND edges AND policy says data is fresh
        - In profile-only mode: never skip here (handled separately)

        Returns:
            tuple of (should_skip, skip_reason, edge_summary)
            - should_skip: True if seed can be skipped entirely
            - skip_reason: Human-readable reason for skip (or None)
            - edge_summary: Dict with following/followers counts for logging
        """
        edge_summary = self._store.edge_summary_for_seed(seed.account_id)
        has_edges = edge_summary["following"] > 0 and edge_summary["followers"] > 0
        has_profile = self._store.is_seed_profile_complete(seed.account_id)

        # If --skip-if-ever-scraped is enabled, skip this policy check entirely
        # (it was already handled earlier in the enrich() method)
        if self._policy.skip_if_ever_scraped:
            return (False, None, edge_summary, None)

        # Check if we have complete data
        if not self._config.profile_only and has_edges and has_profile:
            # Fetch current profile to check policy (age/delta triggers)
            overview = self._selenium.fetch_profile_overview(seed.username)
            if not overview:
                LOGGER.warning(
                    "Could not fetch profile overview for @%s to check policy; skipping as complete",
                    seed.username,
                )
                return (
                    True,
                    "complete profile and edges exist (could not verify freshness)",
                    edge_summary,
                    None,
                )

            # Check if policy requires refresh despite complete data
            following_needs_refresh, following_skip_reason = self._should_refresh_list(
                seed, "following", overview.following_total
            )
            followers_needs_refresh, followers_skip_reason = self._should_refresh_list(
                seed, "followers", overview.followers_total
            )

            # Always refresh seed profile metadata so counts stay current
            self._store.upsert_accounts([self._make_seed_account_record(seed, overview)])

            if following_needs_refresh or followers_needs_refresh:
                # Policy says data is stale or changed significantly, don't skip
                reasons = []
                if following_needs_refresh:
                    reasons.append("following needs refresh")
                if followers_needs_refresh:
                    reasons.append("followers needs refresh")
                LOGGER.info(
                    "@%s has complete data but policy requires refresh (%s)",
                    seed.username,
                    ", ".join(reasons),
                )
                return (False, None, edge_summary, overview)

            # Complete data AND policy says it's fresh - safe to skip
            return (
                True,
                "complete profile and edges exist (policy confirms fresh)",
                edge_summary,
                overview,
            )

        return (False, None, edge_summary, None)

    def _refresh_profile(
        self,
        seed: SeedAccount,
        has_edges: bool,
        has_profile: bool
    ) -> Optional[dict]:
        """Refresh profile metadata only (no list scraping).

        Used in --profile-only mode to update bio, location, counts without scraping lists.

        Args:
            seed: The seed account to refresh
            has_edges: Whether seed already has edge data in store
            has_profile: Whether seed already has complete profile in store

        Returns:
            Summary dict with refresh results, or None to skip profile refresh
        """
        # Skip if not in profile-only-all mode and no edges exist
        if not self._config.profile_only_all:
            if not has_edges:
                LOGGER.warning(
                    "Skipping profile-only @%s (%s) — no existing edge data",
                    seed.username,
                    seed.account_id,
                )
                return {
                    "username": seed.username,
                    "profile_only": True,
                    "skipped": True,
                    "reason": "no_edge_data",
                }
            if has_profile:
                LOGGER.warning(
                    "Skipping profile-only @%s (%s) — profile already complete",
                    seed.username,
                    seed.account_id,
                )
                return {
                    "username": seed.username,
                    "profile_only": True,
                    "skipped": True,
                    "reason": "profile_complete",
                }

        # Fetch profile overview from Selenium
        start = time.perf_counter()
        with self._time_phase("profile", "fetch_overview"):
            overview = self._selenium.fetch_profile_overview(seed.username)
        if not overview:
            LOGGER.error(
                "Profile-only update failed for @%s (%s); could not load profile page",
                seed.username,
                seed.account_id,
            )
            # Record error metrics for profile-only failures
            error_metrics = ScrapeRunMetrics(
                seed_account_id=seed.account_id,
                seed_username=seed.username or "",
                run_at=datetime.utcnow(),
                duration_seconds=time.perf_counter() - start,
                following_captured=0,
                followers_captured=0,
                followers_you_follow_captured=0,
                list_members_captured=0,
                following_claimed_total=None,
                followers_claimed_total=None,
                followers_you_follow_claimed_total=None,
                following_coverage=None,
                followers_coverage=None,
                followers_you_follow_coverage=None,
                accounts_upserted=0,
                edges_upserted=0,
                discoveries_upserted=0,
                phase_timings=self._phase_snapshot(),
                skipped=False,
                skip_reason=None,
                error_type="profile_overview_missing",
                error_details=f"Profile-only mode: Failed to fetch profile overview for @{seed.username}",
            )
            self._store.record_scrape_metrics(error_metrics)
            self._log_phase_summary(f"@{seed.username}")
            return {
                "username": seed.username,
                "profile_only": True,
                "updated": False,
                "error": "profile_overview_missing",
            }

        # Update store with profile data
        account_record = self._make_seed_account_record(seed, overview)
        inserted_accounts = self._store.upsert_accounts([account_record])

        LOGGER.warning(
            "✓ profile-only @%s updated account (upserts=%s)",
            seed.username,
            inserted_accounts,
        )

        # Apply delay before next seed
        pause = random.uniform(
            max(0.5, self._config.action_delay_min),
            max(self._config.action_delay_min, self._config.action_delay_max),
        )
        time.sleep(pause)

        return {
            "username": seed.username,
            "profile_only": True,
            "updated": inserted_accounts > 0,
            "profile_overview": {
                "username": overview.username,
                "display_name": overview.display_name,
                "bio": overview.bio,
                "location": overview.location,
                "website": overview.website,
                "followers_total": overview.followers_total,
                "following_total": overview.following_total,
                "joined_date": overview.joined_date,
                "profile_image_url": overview.profile_image_url,
            },
        }

    def _check_list_freshness_across_runs(
        self,
        account_id: str,
        list_type: str,  # "following" or "followers"
        username: Optional[str] = None,
    ) -> tuple[bool, int, int]:
        """Check if a list has fresh data across ANY recent run, not just the last one.

        This is smarter than checking only the last run, because different lists might
        have been scraped in different runs (e.g., following in run #1, followers in run #2).

        Also handles account ID migration from shadow IDs to real IDs by checking both.

        Returns:
            tuple of (would_skip: bool, days_ago: int, captured_count: int)
        """
        # Prefer store-level APIs so this logic is mockable in unit tests.
        account_id_variants = {account_id}
        if username:
            shadow_id = f"shadow:{username.lower()}"
            if shadow_id != account_id:
                account_id_variants.add(shadow_id)

        recent_metrics = []
        if hasattr(self._store, "get_all_recent_scrape_metrics"):
            try:
                recent_metrics = self._store.get_all_recent_scrape_metrics() or []
            except Exception as exc:
                LOGGER.warning(
                    "Failed to retrieve recent scrape metrics via get_all_recent_scrape_metrics "
                    "(seed=%s list=%s); proceeding without history: %s",
                    account_id,
                    list_type,
                    exc,
                )
                recent_metrics = []
        elif hasattr(self._store, "get_recent_scrape_runs"):
            try:
                recent_metrics = self._store.get_recent_scrape_runs(days=self._policy.list_refresh_days) or []
            except TypeError:
                # Backwards-compatible call signature
                recent_metrics = self._store.get_recent_scrape_runs(self._policy.list_refresh_days) or []
            except Exception as exc:
                LOGGER.warning(
                    "Failed to retrieve recent scrape metrics via get_recent_scrape_runs "
                    "(seed=%s list=%s); proceeding without history: %s",
                    account_id,
                    list_type,
                    exc,
                )
                recent_metrics = []
        else:
            # Fallback: real ShadowStore instance (legacy internal query path).
            try:
                from datetime import timedelta
                from sqlalchemy import desc, select

                cutoff_date = datetime.utcnow() - timedelta(days=self._policy.list_refresh_days)

                def _query(engine):
                    with engine.begin() as conn:
                        query = select(self._store._metrics_table).where(
                            self._store._metrics_table.c.seed_account_id.in_(list(account_id_variants)),
                            self._store._metrics_table.c.run_at >= cutoff_date,
                        ).order_by(desc(self._store._metrics_table.c.run_at))
                        return conn.execute(query).fetchall()

                recent_metrics = self._store._execute_with_retry("check_list_freshness", _query)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to retrieve recent scrape metrics via ShadowStore fallback query "
                    "(seed=%s list=%s); proceeding without history: %s",
                    account_id,
                    list_type,
                    exc,
                )
                recent_metrics = []

        try:
            recent_metrics = [
                m for m in recent_metrics
                if getattr(m, "seed_account_id", None) in account_id_variants
            ]
            recent_metrics.sort(key=lambda m: getattr(m, "run_at", datetime.min), reverse=True)
        except Exception as exc:
            LOGGER.warning(
                "Failed to normalize recent scrape metrics (seed=%s list=%s); proceeding without history: %s",
                account_id,
                list_type,
                exc,
            )
            recent_metrics = []

        # Look for the most recent run where this list was successfully scraped
        MIN_RAW_TO_SKIP = 13
        for metrics_row in recent_metrics:
            if list_type == "following":
                captured = metrics_row.following_captured
            else:  # "followers"
                captured = metrics_row.followers_captured

            # Found a run with meaningful data for this list
            if captured is not None and captured > MIN_RAW_TO_SKIP:
                age_days = (datetime.utcnow() - metrics_row.run_at).days
                return (True, age_days, captured)  # Would skip (fresh data exists)

        # No recent run with good data for this list
        return (False, 0, 0)  # Would NOT skip (needs refresh)

    def _would_skip_list_by_history(
        self,
        last_metrics: ScrapeRunMetrics,
        list_type: str,  # "following" or "followers"
    ) -> bool:
        """Check if a list would be skipped based ONLY on historical data (no profile fetch needed).

        Returns:
            True if the list would be skipped, False otherwise
        """
        # Get captured count from last run
        if list_type == "following":
            last_captured = last_metrics.following_captured
        else:  # "followers"
            last_captured = last_metrics.followers_captured

        # Rule: If we have very few captured accounts, it's worth trying again.
        MIN_RAW_TO_RETRY = 13
        if last_captured is None or last_captured <= MIN_RAW_TO_RETRY:
            return False  # Would NOT skip (would refresh)

        # Rule: If we have a decent number of accounts, only refresh if the data is very old.
        age_days = (datetime.utcnow() - last_metrics.run_at).days
        if age_days > self._policy.list_refresh_days:
            return False  # Would NOT skip (would refresh)

        # Otherwise, skip
        return True

    def _should_refresh_list(
        self,
        seed: SeedAccount,
        list_type: str,  # "following" or "followers"
        current_total: Optional[int],
    ) -> tuple[bool, Optional[str]]:
        """Check if a list should be refreshed based on policy.

        Returns:
            tuple of (should_refresh: bool, reason: Optional[str])
        """
        last_metrics = self._store.get_last_scrape_metrics(seed.account_id)

        if not last_metrics:
            LOGGER.info(
                "@%s %s list has no historical metrics; performing initial scrape",
                seed.username,
                list_type,
            )
            return (True, "first_run")

        # Get captured count from last run metrics
        if list_type == "following":
            last_captured = last_metrics.following_captured
        else:  # "followers"
            last_captured = last_metrics.followers_captured

        # CRITICAL: Also check actual edges in DB to detect corruption
        # Metrics might say we captured 95, but DB could have corrupted/incomplete data
        edge_summary = self._store.edge_summary_for_seed(seed.account_id)
        actual_edge_count = edge_summary.get(list_type, 0)

        MIN_RAW_TO_RETRY = 13
        observed_total = (
            current_total if current_total is not None and current_total >= 0 else None
        )
        small_account_total = (
            observed_total if observed_total is not None and observed_total <= MIN_RAW_TO_RETRY else None
        )

        # Rule 1: If profile totals indicate a small list, require full coverage
        if small_account_total is not None:
            if last_captured is None or last_captured < small_account_total:
                LOGGER.info(
                    "@%s %s list captured %s but profile reports %s accounts; refresh needed to match observed total (<= %d threshold).",
                    seed.username,
                    list_type,
                    last_captured,
                    small_account_total,
                    MIN_RAW_TO_RETRY,
                )
                return (True, "profile_total_not_met")
        else:
            # Rule 1 (legacy): If metrics show low captured count, retry
            if last_captured is None or last_captured <= MIN_RAW_TO_RETRY:
                LOGGER.info(
                    "@%s %s list has low captured count in metrics (%s <= %d); refresh needed.",
                    seed.username,
                    list_type,
                    last_captured,
                    MIN_RAW_TO_RETRY,
                )
                return (True, "low_captured_count_in_metrics")

        # Rule 2: CRITICAL - Verify DB actually has edges matching the metrics
        # If metrics say we captured data but DB is empty/sparse, that's corruption!
        if small_account_total is not None:
            if actual_edge_count < small_account_total:
                LOGGER.warning(
                    "⚠️  DATA INTEGRITY CHECK: @%s %s profile total=%d but DB only has %d edges (metrics recorded %s).",
                    seed.username,
                    list_type,
                    small_account_total,
                    actual_edge_count,
                    last_captured,
                )
                LOGGER.warning(
                    "   └─ Small-account data mismatch detected - forcing re-scrape to repair data"
                )
                return (True, "metrics_db_mismatch_corruption_detected")
        else:
            if actual_edge_count <= MIN_RAW_TO_RETRY:
                LOGGER.warning(
                    "⚠️  DATA INTEGRITY CHECK: @%s %s metrics show %d captured, but DB only has %d edges!",
                    seed.username,
                    list_type,
                    last_captured,
                    actual_edge_count,
                )
                LOGGER.warning(
                    "   └─ Likely data corruption or partial write - forcing re-scrape to repair data"
                )
                return (True, "metrics_db_mismatch_corruption_detected")

        # Rule 3: If we have sufficient edges, only refresh if data is very old
        age_days = (datetime.utcnow() - last_metrics.run_at).days
        if age_days > self._policy.list_refresh_days:
            LOGGER.info(
                "@%s %s list is %d days old (threshold: %d days) - refresh needed despite sufficient data (metrics: %d captured, DB: %d edges).",
                seed.username,
                list_type,
                age_days,
                self._policy.list_refresh_days,
                last_captured,
                actual_edge_count,
            )
            return (True, "age_threshold")

        # Rule 4: Refresh if the observed total has changed substantially since last run.
        # This catches fast-growing accounts that need re-scrape despite recent runs.
        baseline_total = (
            last_metrics.following_claimed_total
            if list_type == "following"
            else last_metrics.followers_claimed_total
        )
        if (
            baseline_total is not None
            and baseline_total > 0
            and observed_total is not None
            and observed_total > 0
        ):
            pct_delta = abs(observed_total - baseline_total) / float(baseline_total)
            if pct_delta > self._policy.pct_delta_threshold:
                LOGGER.info(
                    "@%s %s list changed by %.1f%% vs baseline %d (observed %d); refresh needed (threshold %.1f%%).",
                    seed.username,
                    list_type,
                    pct_delta * 100.0,
                    baseline_total,
                    observed_total,
                    self._policy.pct_delta_threshold * 100.0,
                )
                return (True, "pct_delta_threshold")

        # Otherwise, the data is considered fresh enough.
        LOGGER.info(
            "@%s %s list is considered fresh (age: %d days, metrics: %d captured, DB: %d edges, profile_total=%s) - skipping",
            seed.username,
            list_type,
            age_days,
            last_captured,
            actual_edge_count,
            observed_total if observed_total is not None else "-",
        )
        return (False, f"{list_type}_fresh_sufficient_capture")

    def _confirm_refresh(
        self,
        seed: SeedAccount,
        list_type: str,
        reason: Optional[str],
    ) -> bool:
        """Prompt user to confirm list refresh if policy requires it.

        Returns:
            True if refresh should proceed, False otherwise
        """
        def describe(reason_code: Optional[str]) -> Optional[str]:
            if reason_code is None:
                return None
            if reason_code == "first_run":
                return "no historical metrics"
            if reason_code == "age_threshold":
                return f"age exceeded {self._policy.list_refresh_days} day threshold"
            if reason_code == "delta_threshold":
                pct = self._policy.pct_delta_threshold * 100
                return f"count delta exceeded {pct:.1f}% threshold"
            return reason_code

        human_reason = describe(reason)
        reason_note = f" (trigger: {human_reason})" if human_reason else ""
        if self._policy.auto_confirm_rescrapes:
            LOGGER.info(
                "Auto-confirming refresh for @%s %s%s (--auto-confirm-rescrapes enabled)",
                seed.username,
                list_type,
                reason_note,
            )
            return True

        if not self._policy.require_user_confirmation:
            return True

        # Prompt user
        print(f"\n⚠️  Policy check: @{seed.username} {list_type} list needs refresh")
        trigger_text = human_reason or (
            f"age > {self._policy.list_refresh_days} days OR delta > {self._policy.pct_delta_threshold * 100:.0f}%"
        )
        print(f"   Trigger: {trigger_text}")
        response = input(f"   Proceed with scraping {list_type}? [y/n]: ").strip().lower()

        if response == "y":
            LOGGER.info("User confirmed refresh for @%s %s", seed.username, list_type)
            return True
        else:
            LOGGER.warning("User declined refresh for @%s %s", seed.username, list_type)
            return False

    def _refresh_following(
        self,
        seed: SeedAccount,
        overview: ProfileOverview,
    ) -> Optional[UserListCapture]:
        """Refresh following list with policy-driven caching.

        Returns:
            UserListCapture if scraped, None if skipped
        """
        if not self._config.include_following:
            LOGGER.info(
                "Skipping @%s following list: include_following disabled in config",
                seed.username,
            )
            return None

        # Check if refresh is needed based on policy
        should_refresh, reason = self._should_refresh_list(
            seed, "following", overview.following_total
        )

        if not should_refresh:
            LOGGER.info("Skipping @%s following list: %s", seed.username, reason)
            return None

        # Prompt user if needed
        if not self._confirm_refresh(seed, "following", reason):
            LOGGER.warning("Skipping @%s following list: user declined", seed.username)
            return None

        # Scrape the list
        LOGGER.info("Scraping @%s following list (reason: %s)...", seed.username, reason)
        with self._time_phase("list_following", "selenium_fetch"):
            capture = self._selenium.fetch_following(seed.username)
        if capture:
            LOGGER.info(
                "✓ Scraped @%s following: captured %d/%s accounts",
                seed.username,
                len(capture.entries),
                capture.claimed_total if capture.claimed_total else "?",
            )
        else:
            LOGGER.warning("✗ Failed to scrape @%s following list", seed.username)
        return capture

    def _refresh_followers(
        self,
        seed: SeedAccount,
        overview: ProfileOverview,
    ) -> tuple[Optional[UserListCapture], Optional[UserListCapture], Optional[UserListCapture]]:
        """Refresh followers lists with policy-driven caching.

        Returns:
            tuple of (followers_capture, followers_you_follow_capture, verified_followers_capture)
        """
        def _normalize_capture(capture: Optional[UserListCapture]) -> Optional[UserListCapture]:
            if capture is None:
                return None
            entries = getattr(capture, "entries", None)
            return capture if isinstance(entries, list) else None

        if not self._config.include_followers:
            LOGGER.info(
                "Skipping @%s followers list: include_followers disabled in config",
                seed.username,
            )
            return (None, None, None)

        # Check if refresh is needed based on policy
        should_refresh, reason = self._should_refresh_list(
            seed, "followers", overview.followers_total
        )

        if not should_refresh:
            LOGGER.info("Skipping @%s followers list: %s", seed.username, reason)
            return (None, None, None)

        # Prompt user if needed
        if not self._confirm_refresh(seed, "followers", reason):
            LOGGER.warning("Skipping @%s followers list: user declined", seed.username)
            return (None, None, None)

        # Scrape followers
        LOGGER.info("Scraping @%s followers list (reason: %s)...", seed.username, reason)
        with self._time_phase("list_followers", "selenium_fetch"):
            followers_capture = self._selenium.fetch_followers(seed.username)
        followers_capture = _normalize_capture(followers_capture)
        if followers_capture:
            LOGGER.info(
                "✓ Scraped @%s followers: captured %d/%s accounts",
                seed.username,
                len(followers_capture.entries),
                followers_capture.claimed_total if followers_capture.claimed_total else "?",
            )
        else:
            LOGGER.warning("✗ Failed to scrape @%s followers list", seed.username)

        # Scrape verified_followers
        LOGGER.info("Scraping @%s verified-followers list...", seed.username)
        with self._time_phase("list_verified_followers", "selenium_fetch"):
            verified_followers_capture = self._selenium.fetch_verified_followers(seed.username)
        verified_followers_capture = _normalize_capture(verified_followers_capture)
        if verified_followers_capture:
            LOGGER.info(
                "✓ Scraped @%s verified-followers: captured %d/%s accounts",
                seed.username,
                len(verified_followers_capture.entries),
                verified_followers_capture.claimed_total if verified_followers_capture.claimed_total else "?",
            )
        else:
            LOGGER.warning("✗ Failed to scrape @%s verified-followers list", seed.username)

        # Scrape followers_you_follow if enabled
        followers_you_follow_capture = None
        if self._config.include_followers_you_follow:
            LOGGER.info("Scraping @%s followers-you-follow list...", seed.username)
            with self._time_phase("list_followers_you_follow", "selenium_fetch"):
                followers_you_follow_capture = self._selenium.fetch_followers_you_follow(
                    seed.username
                )
            followers_you_follow_capture = _normalize_capture(followers_you_follow_capture)
            if followers_you_follow_capture:
                LOGGER.info(
                    "✓ Scraped @%s followers-you-follow: captured %d/%s accounts",
                    seed.username,
                    len(followers_you_follow_capture.entries),
                    followers_you_follow_capture.claimed_total if followers_you_follow_capture.claimed_total else "?",
                )
            else:
                LOGGER.warning("✗ Failed to scrape @%s followers-you-follow list", seed.username)
        else:
            LOGGER.info(
                "Skipping followers-you-follow list for @%s: include_followers_you_follow disabled",
                seed.username,
            )

        return (followers_capture, followers_you_follow_capture, verified_followers_capture)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_list_members_with_cache(
        self,
        list_id: str,
        *,
        force_refresh: bool = False,
    ) -> UserListCapture:
        """Fetch list members, using cached snapshots when fresh."""
        list_meta = None if force_refresh else self._store.get_shadow_list(list_id)
        if list_meta and not force_refresh:
            age_days = (datetime.utcnow() - list_meta.fetched_at).days
            if age_days <= self._policy.list_refresh_days:
                members = self._store.get_shadow_list_members(list_id)
                if members:
                    LOGGER.info(
                        "Using cached snapshot for list %s — %d members captured %d days ago",
                        list_id,
                        len(members),
                        age_days,
                    )
                    return self._list_capture_from_cache(
                        list_id=list_id,
                        list_meta=list_meta,
                        members=members,
                    )
                LOGGER.warning(
                    "Cached list %s metadata found but no members persisted; forcing refresh.",
                    list_id,
                )

        LOGGER.info("Refreshing list members for list %s via Selenium…", list_id)
        start = time.perf_counter()
        capture = self._selenium.fetch_list_members(list_id)
        duration = time.perf_counter() - start

        entries = capture.entries if capture else []
        member_records = self._make_list_member_records(list_id=list_id, captures=entries)
        now = datetime.utcnow()

        overview: Optional[ListOverview] = capture.list_overview if capture else None
        owner_account_id = None
        if overview and overview.owner_username:
            owner_account_id = self._store.get_account_id_by_username(overview.owner_username) or None
        metadata: dict = {}
        if overview and overview.owner_profile_url:
            metadata["owner_profile_url"] = overview.owner_profile_url
        if overview and overview.members_total is not None:
            metadata["claimed_total"] = overview.members_total
        elif capture and capture.claimed_total is not None:
            metadata["claimed_total"] = capture.claimed_total

        list_record = ShadowList(
            list_id=list_id,
            name=overview.name if overview else None,
            description=overview.description if overview else None,
            owner_account_id=owner_account_id,
            owner_username=overview.owner_username if overview else None,
            owner_display_name=overview.owner_display_name if overview else None,
            member_count=len(entries),
            claimed_member_total=overview.members_total if overview else (capture.claimed_total if capture else None),
            followers_count=overview.followers_total if overview else None,
            fetched_at=now,
            source_channel="selenium_list_members",
            metadata=metadata or None,
        )
        self._store.upsert_lists([list_record])
        self._store.replace_list_members(list_id, member_records)

        list_metrics = ScrapeRunMetrics(
            seed_account_id=f"list:{list_id}",
            seed_username=f"list:{list_id}",
            run_at=now,
            duration_seconds=duration,
            following_captured=0,
            followers_captured=0,
            followers_you_follow_captured=0,
            list_members_captured=len(entries),
            following_claimed_total=None,
            followers_claimed_total=overview.followers_total if overview else None,
            followers_you_follow_claimed_total=None,
            following_coverage=None,
            followers_coverage=None,
            followers_you_follow_coverage=None,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
            phase_timings=self._phase_snapshot(),
            skipped=False,
            skip_reason=None,
        )
        self._store.record_scrape_metrics(list_metrics)

        return capture

    def enrich(self, seeds: Sequence[SeedAccount]) -> Dict[str, Dict[str, object]]:
        """Enrich the graph starting from provided seed accounts."""

        # Setup signal handler for graceful pause/resume
        self._setup_signal_handler()

        total_seeds = len(seeds)
        LOGGER.info("=" * 80)
        LOGGER.info("Starting enrichment run: %d seeds total", total_seeds)
        LOGGER.info("=" * 80)

        summary: Dict[str, Dict[str, object]] = {}
        for seed_idx, seed in enumerate(seeds, start=1):
            if not seed.username:
                LOGGER.warning("Seed %s missing username; skipping", seed.account_id)
                continue

            self._current_phase_timings = {}

            LOGGER.info("\n" + "━" * 80)
            LOGGER.info("🔹 SEED #%d/%d: @%s", seed_idx, total_seeds, seed.username)
            LOGGER.info("━" * 80)

            self._log_pre_run_summary(seed)

            # Check if --skip-if-ever-scraped flag is enabled
            if self._policy.skip_if_ever_scraped:
                last_scrape = self._store.get_last_scrape_metrics(seed.account_id)

                # Check account status from database with time-based retry
                if last_scrape and last_scrape.skipped:
                    account = self._store.get_shadow_account(seed.account_id)

                    if account and account.scrape_stats:
                        status = account.scrape_stats.get("account_status")
                        status_detected_at = account.scrape_stats.get("status_detected_at")

                        # Backward compatibility for old deleted accounts
                        if not status and account.scrape_stats.get("deleted"):
                            status = "deleted"
                            status_detected_at = status_detected_at or (last_scrape.run_at.isoformat() if last_scrape.run_at else None)

                        if status and status != "active" and status_detected_at:
                            # Calculate age of status
                            try:
                                detected_date = datetime.fromisoformat(status_detected_at)
                                days_since = (datetime.utcnow() - detected_date).days
                                retry_after = ACCOUNT_STATUS_RETRY_DAYS.get(status, 0)

                                # Skip if status is still within retry period
                                if days_since < retry_after:
                                    LOGGER.info(
                                        "⏭️  SKIPPED — account status: %s (detected %d days ago, retry after %d days)",
                                        status, days_since, retry_after
                                    )
                                    summary[seed.account_id] = {
                                        "username": seed.username,
                                        "skipped": True,
                                        "reason": f"account_status_{status}_within_retry_period",
                                        "status": status,
                                        "days_since_detected": days_since,
                                        "retry_after_days": retry_after,
                                    }
                                    # Record skip metrics
                                    skip_metrics = ScrapeRunMetrics(
                                        seed_account_id=seed.account_id,
                                        seed_username=seed.username or "",
                                        run_at=datetime.utcnow(),
                                        duration_seconds=0.0,
                                        following_captured=0,
                                        followers_captured=0,
                                        followers_you_follow_captured=0,
                                        list_members_captured=0,
                                        following_claimed_total=None,
                                        followers_claimed_total=None,
                                        followers_you_follow_claimed_total=None,
                                        following_coverage=None,
                                        followers_coverage=None,
                                        followers_you_follow_coverage=None,
                                        accounts_upserted=0,
                                        edges_upserted=0,
                                        discoveries_upserted=0,
                                        phase_timings=self._phase_snapshot(),
                                        skipped=True,
                                        skip_reason=f"account_status_{status}_retry_pending",
                                    )
                                    self._store.record_scrape_metrics(skip_metrics)
                                    continue  # Skip to next seed
                                else:
                                    LOGGER.info(
                                        "♻️  RETRY — account status: %s is %d days old (>%d days), will re-check",
                                        status, days_since, retry_after
                                    )
                                    # Continue with scraping to re-check status

                            except (ValueError, TypeError) as e:
                                LOGGER.warning(
                                    "Could not parse status_detected_at for @%s: %s",
                                    seed.username, e
                                )
                                # Continue with scraping (treat as new check)

                if last_scrape and not last_scrape.skipped:
                    # Check if we have complete metadata AND sufficient edge coverage
                    account = self._store.get_shadow_account(seed.account_id)
                    has_complete_metadata = (
                        account is not None and
                        account.followers_count is not None and
                        account.following_count is not None
                    )

                    # Calculate edge coverage from last scrape
                    # Special case: 0/0 means we captured all 0 items = 100% coverage
                    following_coverage = self._compute_skip_coverage_percent(
                        account.following_count if account else None,
                        last_scrape.following_captured,
                    )
                    followers_coverage = self._compute_skip_coverage_percent(
                        account.followers_count if account else None,
                        last_scrape.followers_captured,
                    )

                    # Only skip if we have complete metadata AND sufficient edge coverage (by percent or raw count)
                    MIN_COVERAGE_PCT = 10.0
                    MIN_RAW_COUNT = 20
                    has_sufficient_following = (following_coverage >= MIN_COVERAGE_PCT or (last_scrape.following_captured or 0) > MIN_RAW_COUNT)
                    has_sufficient_followers = (followers_coverage >= MIN_COVERAGE_PCT or (last_scrape.followers_captured or 0) > MIN_RAW_COUNT)
                    has_sufficient_coverage = has_sufficient_following and has_sufficient_followers

                    if has_complete_metadata and has_sufficient_coverage:
                        days_since = (datetime.utcnow() - last_scrape.run_at).days
                        LOGGER.info("⏭️  SKIPPED — complete profile and edge data found in DB")
                        LOGGER.info("   └─ Last scraped: %d days ago", days_since)
                        LOGGER.info("   └─ Following coverage: %.1f%% (%s/%s)",
                                    following_coverage,
                                    last_scrape.following_captured or 0,
                                    account.following_count if account else "?")
                        LOGGER.info("   └─ Followers coverage: %.1f%% (%s/%s)",
                                    followers_coverage,
                                    last_scrape.followers_captured or 0,
                                    account.followers_count if account else "?")
                        summary[seed.account_id] = {
                            "username": seed.username,
                            "skipped": True,
                            "reason": "already_scraped_sufficient_coverage",
                        }
                        continue
                    else:
                        skip_reason_parts = []
                        if not has_complete_metadata:
                            skip_reason_parts.append(f"incomplete metadata (followers: {account.followers_count if account else None}, following: {account.following_count if account else None})")
                        if not has_sufficient_coverage:
                            reasons = []
                            if not has_sufficient_following:
                                reasons.append(f"following: {following_coverage:.1f}% < {MIN_COVERAGE_PCT}% and {(last_scrape.following_captured or 0)} <= {MIN_RAW_COUNT}")
                            if not has_sufficient_followers:
                                reasons.append(f"followers: {followers_coverage:.1f}% < {MIN_COVERAGE_PCT}% and {(last_scrape.followers_captured or 0)} <= {MIN_RAW_COUNT}")
                            skip_reason_parts.append(f"low coverage ({'; '.join(reasons)})")

                        LOGGER.info(
                            "Re-scraping @%s (%s) despite prior scrape — %s",
                            seed.username,
                            seed.account_id,
                            " AND ".join(skip_reason_parts),
                        )

            # Check if we should skip this seed
            should_skip, skip_reason, edge_summary, cached_overview = self._should_skip_seed(seed)

            if should_skip:
                LOGGER.warning(
                    "Skipping @%s (%s) — %s (following: %s, followers: %s)",
                    seed.username,
                    seed.account_id,
                    skip_reason,
                    edge_summary["following"],
                    edge_summary["followers"],
                )
                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": skip_reason,
                    "edge_summary": edge_summary,
                }
                # Record skip metrics
                phase_snapshot = self._phase_snapshot()
                skip_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=0.0,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    list_members_captured=0,
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    phase_timings=phase_snapshot,
                    skipped=True,
                    skip_reason=skip_reason,
                )
                self._store.record_scrape_metrics(skip_metrics)
                self._log_phase_summary(f"@{seed.username}")
                continue

            # Compute edge/profile status for profile-only mode check
            has_edges = edge_summary["following"] > 0 and edge_summary["followers"] > 0
            has_profile = self._store.is_seed_profile_complete(seed.account_id)

            # Handle profile-only mode
            if self._config.profile_only:
                profile_result = self._refresh_profile(seed, has_edges, has_profile)
                if profile_result:
                    summary[seed.account_id] = profile_result
                    continue

            start = time.perf_counter()
            LOGGER.info("Enriching @%s...", seed.username)

            # Optimization: If --skip-if-ever-scraped is enabled, check if we can skip profile fetch entirely
            # by checking if policy would skip both edge lists based on historical data alone
            # IMPROVEMENT: Check multiple recent runs, not just the last one
            if self._policy.skip_if_ever_scraped and not cached_overview:
                following_would_skip, following_days_ago, following_captured = self._check_list_freshness_across_runs(seed.account_id, "following", seed.username)
                followers_would_skip, followers_days_ago, followers_captured = self._check_list_freshness_across_runs(seed.account_id, "followers", seed.username)

                if following_would_skip and followers_would_skip:
                        LOGGER.info("⏭️  SKIPPED — both edge lists are fresh (no profile visit needed)")
                        LOGGER.info("   └─ Following: %s accounts captured %d days ago", following_captured, following_days_ago)
                        LOGGER.info("   └─ Followers: %s accounts captured %d days ago", followers_captured, followers_days_ago)
                        phase_snapshot = self._phase_snapshot()
                        skip_metrics = ScrapeRunMetrics(
                            seed_account_id=seed.account_id,
                            seed_username=seed.username or "",
                            run_at=datetime.utcnow(),
                            duration_seconds=0.0,
                            following_captured=0,
                            followers_captured=0,
                            followers_you_follow_captured=0,
                            list_members_captured=0,
                            following_claimed_total=None,
                            followers_claimed_total=None,
                            followers_you_follow_claimed_total=None,
                            following_coverage=None,
                            followers_coverage=None,
                            followers_you_follow_coverage=None,
                            accounts_upserted=0,
                            edges_upserted=0,
                            discoveries_upserted=0,
                            phase_timings=phase_snapshot,
                            skipped=True,
                            skip_reason="both_lists_fresh_and_skip_if_ever_scraped_enabled",
                            error_type=None,
                            error_details=None,
                        )
                        self._store.record_scrape_metrics(skip_metrics)
                        self._log_phase_summary(f"@{seed.username}")
                        summary[seed.account_id] = {
                            "username": seed.username,
                            "skipped": True,
                            "reason": "both_lists_fresh_and_skip_if_ever_scraped_enabled",
                        }
                        continue

            # Fetch profile overview first to check counts for policy
            if not cached_overview:
                LOGGER.info("📍 Visiting profile page for @%s...", seed.username)
            if cached_overview:
                overview = cached_overview
            else:
                with self._time_phase("profile", "fetch_overview"):
                    overview = self._selenium.fetch_profile_overview(seed.username)
            if not overview:
                LOGGER.error("Failed to fetch profile overview for @%s - skipping", seed.username)
                error_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=time.perf_counter() - start,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    list_members_captured=0,
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    phase_timings=self._phase_snapshot(),
                    skipped=True,
                    skip_reason="profile_overview_missing",
                    error_type="profile_overview_missing",
                    error_details=f"Failed to fetch profile overview for @{seed.username}",
                )
                self._store.record_scrape_metrics(error_metrics)
                summary[seed.account_id] = {
                    "username": seed.username,
                    "error": "profile_overview_missing",
                }
                continue

            # Check if account has status marker (deleted/suspended/protected)
            if overview.bio and overview.bio.startswith("[ACCOUNT"):
                # Extract status from marker: "[ACCOUNT DELETED]" -> "deleted"
                status = overview.bio.replace("[ACCOUNT ", "").replace("]", "").lower()

                LOGGER.warning("⏭️  SKIPPED — account status: %s", status)
                LOGGER.info("   └─ Saving account record with status marker")

                # Save the account record to DB
                # Ensure display_name isn't also the marker (defensive)
                display_name = (
                    None
                    if overview.display_name and overview.display_name.startswith("[")
                    else overview.display_name
                )
                status_account = ShadowAccount(
                    account_id=seed.account_id,
                    username=seed.username,
                    display_name=display_name,
                    bio=overview.bio,
                    location=overview.location,
                    website=overview.website,
                    profile_image_url=overview.profile_image_url,
                    followers_count=0,
                    following_count=0,
                    source_channel="selenium",
                    fetched_at=datetime.utcnow(),
                    checked_at=None,
                    scrape_stats={
                        "account_status": status,
                        "status_detected_at": datetime.utcnow().isoformat(),
                        "status_checked_at": datetime.utcnow().isoformat(),
                        # Keep existing deleted flag for backward compatibility
                        "deleted": (status in ["deleted", "suspended"]),
                    },
                )
                self._store.upsert_accounts([status_account])
                status_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=time.perf_counter() - start,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    list_members_captured=0,
                    following_claimed_total=0,
                    followers_claimed_total=0,
                    followers_you_follow_claimed_total=0,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=1,  # We upserted the deleted account marker
                    edges_upserted=0,
                    discoveries_upserted=0,
                    phase_timings=self._phase_snapshot(),
                    skipped=True,
                    skip_reason=f"account_{status}",
                    error_type=None,
                    error_details=None,
                )
                self._store.record_scrape_metrics(status_metrics)
                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": f"account_{status}",
                    "status": status,
                }
                continue

            # Use policy-driven refresh helpers
            following_capture = self._refresh_following(seed, overview)
            followers_capture, followers_you_follow_capture, verified_followers_capture = self._refresh_followers(seed, overview)

            # Check if policy skipped all lists (preserve baseline, don't corrupt metrics)
            policy_skipped_all = (following_capture is None and followers_capture is None)

            if policy_skipped_all:
                # If --skip-if-ever-scraped is enabled, don't waste time on metadata-only updates
                if self._policy.skip_if_ever_scraped:
                    LOGGER.info(
                        "Skipping @%s — policy skipped all edge lists and --skip-if-ever-scraped is enabled (metadata update skipped)",
                        seed.username,
                    )
                skip_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=0.0,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    list_members_captured=0,
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    phase_timings=self._phase_snapshot(),
                    skipped=True,
                    skip_reason="policy_skipped_all_lists_and_skip_if_ever_scraped_enabled",
                    error_type=None,
                    error_details=None,
                )
                self._store.record_scrape_metrics(skip_metrics)
                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": "policy_skipped_all_lists_and_skip_if_ever_scraped_enabled",
                }
                continue

                # Even if lists are fresh, refresh seed profile metadata for canonical counts
                account_record = self._make_seed_account_record(seed, overview)
                LOGGER.info(
                    "Writing metadata-only update to DB for @%s (followers: %s, following: %s)...",
                    seed.username,
                    overview.followers_total,
                    overview.following_total,
                )
                upserted = self._store.upsert_accounts([account_record])
                LOGGER.info("✓ DB write complete for @%s: %d account record updated", seed.username, upserted)
                # Record that we checked but policy skipped everything
                skip_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=0.0,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    list_members_captured=0,
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    phase_timings=self._phase_snapshot(),
                    skipped=True,
                    skip_reason="policy_fresh_data",
                )
                self._store.record_scrape_metrics(skip_metrics)

                LOGGER.info(
                    "✓ Skipped @%s (policy: data is fresh) — updated metadata: %s followers, %s following",
                    seed.username,
                    overview.followers_total,
                    overview.following_total,
                )

                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": "policy_fresh_data",
                    "edge_summary": self._store.edge_summary_for_seed(seed.account_id),
                }
                continue

            following_entries: List[CapturedUser] = (
                list(following_capture.entries)
                if following_capture is not None
                else []
            )
            followers_entries: List[CapturedUser] = self._combine_captures(
                [capture for capture in (followers_capture, followers_you_follow_capture, verified_followers_capture) if capture]
            )
            followers_you_follow_entries: List[CapturedUser] = (
                list(followers_you_follow_capture.entries)
                if followers_you_follow_capture is not None
                else []
            )
            all_entries = following_entries + followers_entries
            scrape_duration = time.perf_counter() - start
            LOGGER.debug(
                "Scraped @%s: %s following, %s followers in %.1fs",
                seed.username,
                len(following_entries),
                len(followers_entries),
                scrape_duration,
            )

            self._confirm_first_scrape(
                seed_username=seed.username,
                following_capture=following_capture,
                followers_capture=followers_capture,
                followers_you_follow_capture=followers_you_follow_capture,
                following_entries=following_entries,
                followers_entries=followers_entries,
                followers_you_follow_entries=followers_you_follow_entries,
            )

            accounts = self._make_account_records(seed=seed, captures=all_entries)

            # Store seed's own profile metadata from ProfileOverview
            # (we already fetched it earlier for policy checks)
            seed_account = self._make_seed_account_record(seed, overview)
            accounts.append(seed_account)

            # Create and upsert edges by type to get per-list metrics
            following_edges = self._make_edge_records(seed=seed, following=following_entries, followers=[])
            followers_edges = self._make_edge_records(seed=seed, following=[], followers=followers_entries)
            
            discoveries = self._make_discovery_records(
                seed=seed,
                following=following_entries,
                followers=followers_entries,
                followers_you_follow=followers_you_follow_entries,
            )

            try:
                LOGGER.info(
                    "Writing to DB for @%s: %d accounts, %d following edges, %d followers edges, %d discoveries...",
                    seed.username,
                    len(accounts),
                    len(following_edges),
                    len(followers_edges),
                    len(discoveries),
                )
                inserted_accounts = self._store.upsert_accounts(accounts)
                
                # Upsert separately to get per-list metrics
                inserted_following_edges = self._store.upsert_edges(following_edges)
                inserted_followers_edges = self._store.upsert_edges(followers_edges)
                inserted_edges = inserted_following_edges + inserted_followers_edges

                inserted_discoveries = self._store.upsert_discoveries(discoveries)
                
                LOGGER.info(
                    "✓ DB write complete for @%s: %d accounts, %d edges (%d following, %d followers), %d discoveries upserted",
                    seed.username,
                    inserted_accounts,
                    inserted_edges,
                    inserted_following_edges,
                    inserted_followers_edges,
                    inserted_discoveries,
                )

                # Calculate new/duplicate counts for summary
                new_following_count = inserted_following_edges
                duplicate_following_count = len(following_entries) - new_following_count
                new_followers_count = inserted_followers_edges
                duplicate_followers_count = len(followers_entries) - new_followers_count

                seed_summary = {
                    "username": seed.username,
                    "accounts_upserted": inserted_accounts,
                    "edges_upserted": inserted_edges,
                    "discoveries_upserted": inserted_discoveries,
                    "following_captured": len(following_entries),
                    "following_new": new_following_count,
                    "following_duplicates": duplicate_following_count,
                    "followers_captured": len(followers_entries),
                    "followers_new": new_followers_count,
                    "followers_duplicates": duplicate_followers_count,
                    "followers_you_follow_captured": len(followers_you_follow_entries),
                    "following_claimed_total": (
                        following_capture.claimed_total if following_capture else None
                    ),
                    "followers_claimed_total": (
                        followers_capture.claimed_total if followers_capture else None
                    ),
                    "followers_you_follow_claimed_total": (
                        followers_you_follow_capture.claimed_total
                        if followers_you_follow_capture
                        else None
                    ),
                    "coverage": {
                        "following": self._compute_coverage(
                            len(following_entries),
                            following_capture.claimed_total if following_capture else None,
                        ),
                        "followers": self._compute_coverage(
                            len(followers_entries),
                            followers_capture.claimed_total if followers_capture else None,
                        ),
                        "followers_you_follow": self._compute_coverage(
                            len(followers_you_follow_entries),
                            followers_you_follow_capture.claimed_total
                            if followers_you_follow_capture
                            else None,
                        ),
                    },
                    "scrape_duration_seconds": round(scrape_duration, 2),
                    "timestamp": datetime.utcnow().isoformat(),
                    "edge_summary": self._store.edge_summary_for_seed(seed.account_id),
                    "profile_overview": self._profile_overview_as_dict(
                        following_capture,
                        followers_capture,
                        followers_you_follow_capture,
                    ),
                }
                summary[seed.account_id] = seed_summary

                profile_snapshot = seed_summary.get("profile_overview") or {}
                LOGGER.info(
                    "   Profile snapshot for @%s: display=\"%s\", followers=%s, following=%s, location=\"%s\", website=%s",
                    seed.username,
                    _shorten_text(
                        profile_snapshot.get("display_name")
                        or profile_snapshot.get("username"),
                        80,
                    ),
                    profile_snapshot.get("followers_total"),
                    profile_snapshot.get("following_total"),
                    _shorten_text(profile_snapshot.get("location"), 60),
                    _shorten_text(profile_snapshot.get("website"), 80),
                )

                if profile_snapshot.get("bio"):
                    LOGGER.info(
                        "   Profile bio for @%s: %s",
                        seed.username,
                        _shorten_text(profile_snapshot.get("bio"), 200),
                    )

                # Record scrape metrics
                run_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=scrape_duration,
                    following_captured=len(following_entries),
                    followers_captured=len(followers_entries),
                    followers_you_follow_captured=len(followers_you_follow_entries),
                    list_members_captured=0,
                    following_claimed_total=following_capture.claimed_total if following_capture else None,
                    followers_claimed_total=followers_capture.claimed_total if followers_capture else None,
                    followers_you_follow_claimed_total=(
                        followers_you_follow_capture.claimed_total
                        if followers_you_follow_capture
                        else None
                    ),
                    following_coverage=seed_summary["coverage"]["following"],
                    followers_coverage=seed_summary["coverage"]["followers"],
                    followers_you_follow_coverage=seed_summary["coverage"]["followers_you_follow"],
                    accounts_upserted=inserted_accounts,
                    edges_upserted=inserted_edges,
                    discoveries_upserted=inserted_discoveries,
                    phase_timings=self._phase_snapshot(),
                    skipped=False,
                    skip_reason=None,
                )
                self._store.record_scrape_metrics(run_metrics)

                # Log summary with new/duplicate counts
                LOGGER.warning(
                    "✓ @%s COMPLETE. Following: %d captured (%d new, %d duplicates). Followers: %d captured (%d new, %d duplicates). DB writes: %d accounts, %d total edges.",
                    seed.username,
                    len(following_entries),
                    new_following_count,
                    duplicate_following_count,
                    len(followers_entries),
                    new_followers_count,
                    duplicate_followers_count,
                    inserted_accounts,
                    inserted_edges,
                )
            except OperationalError as exc:
                LOGGER.error(
                    "SQLite persistence failed for @%s after retries; capturing summary and continuing.",
                    seed.username,
                    exc_info=exc,
                )
                summary[seed.account_id] = {
                    "username": seed.username,
                    "error": "persistence_failure",
                    "reason": str(getattr(exc, "orig", exc)),
                    "accounts_captured": len(all_entries),
                    "following_captured": len(following_entries),
                    "followers_captured": len(followers_entries),
                    "followers_you_follow_captured": len(followers_you_follow_entries),
                }

                # Record persistence failure in metrics
                error_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=time.perf_counter() - start,
                    following_captured=len(following_entries),
                    followers_captured=len(followers_entries),
                    followers_you_follow_captured=len(followers_you_follow_entries),
                    list_members_captured=0,
                    following_claimed_total=following_capture.claimed_total if following_capture else None,
                    followers_claimed_total=followers_capture.claimed_total if followers_capture else None,
                    followers_you_follow_claimed_total=(
                        followers_you_follow_capture.claimed_total
                        if followers_you_follow_capture
                        else None
                    ),
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    phase_timings=self._phase_snapshot(),
                    skipped=False,
                    skip_reason=None,
                    error_type="persistence_failure",
                    error_details=f"SQLite OperationalError: {str(getattr(exc, 'orig', exc))}",
                )
                self._store.record_scrape_metrics(error_metrics)
                continue

            # Check if pause was requested (Ctrl+C)
            if self._pause_requested:
                choice = self._handle_pause_menu(seed_idx, total_seeds)
                if choice == 'shutdown':
                    LOGGER.info("Enrichment shutdown by user. Progress saved.")
                    self._restore_signal_handler()
                    return summary
                elif choice == 'resume':
                    # Clear pause flag and continue
                    self._pause_requested = False
                    LOGGER.info("Resuming enrichment from seed #%d/%d...", seed_idx + 1, total_seeds)

            # Check if shutdown was forced (second Ctrl+C)
            if self._shutdown_requested:
                LOGGER.warning("Forced shutdown detected. Exiting immediately.")
                self._restore_signal_handler()
                return summary

            if self._config.user_pause_seconds > 0:
                time.sleep(self._config.user_pause_seconds)

        # Restore original signal handler at the end
        self._restore_signal_handler()
        return summary

    def quit(self):
        """Safely quits the underlying Selenium browser instance."""
        self._restore_signal_handler()
        self._selenium.quit()

    # ------------------------------------------------------------------
    # Record constructors
    # ------------------------------------------------------------------
    def _make_account_records(
        self,
        *,
        seed: SeedAccount,
        captures: Iterable[CapturedUser],
    ) -> List[ShadowAccount]:
        now = datetime.utcnow()
        aggregated: Dict[str, Dict[str, object]] = {}

        def update_account(captured: CapturedUser) -> None:
            username = captured.username
            if not username:
                return
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                return
            entry = aggregated.setdefault(
                account_id,
                {
                    "data": resolved,
                    "sources": set(),
                    "seeds": set(),
                    "canonical_username": username,
                    "profile_urls": set(),
                    "website": resolved.get("website"),
                    "profile_image_url": resolved.get("profile_image_url"),
                },
            )
            entry["sources"].update(captured.list_types or {"unknown"})
            entry["seeds"].add(seed.username)
            if captured.display_name and not resolved.get("display_name"):
                resolved["display_name"] = captured.display_name
            if captured.bio and not resolved.get("bio"):
                resolved["bio"] = captured.bio
            if captured.profile_url:
                entry["profile_urls"].add(captured.profile_url)
            if captured.website:
                if not resolved.get("website"):
                    resolved["website"] = captured.website
                if not entry.get("website"):
                    entry["website"] = captured.website
            if captured.profile_image_url:
                if not resolved.get("profile_image_url"):
                    resolved["profile_image_url"] = captured.profile_image_url
                if not entry.get("profile_image_url"):
                    entry["profile_image_url"] = captured.profile_image_url

        for captured in captures:
            update_account(captured)

        records: List[ShadowAccount] = []
        for account_id, entry in aggregated.items():
            resolved = entry["data"]
            records.append(
                ShadowAccount(
                    account_id=account_id,
                    username=resolved.get("username"),
                    display_name=resolved.get("display_name"),
                    bio=resolved.get("bio"),
                    location=resolved.get("location"),
                    website=resolved.get("website") or entry.get("website"),
                    profile_image_url=entry.get("profile_image_url"),
                    followers_count=resolved.get("followers_count"),
                    following_count=resolved.get("following_count"),
                    source_channel=resolved.get("source_channel", "hybrid_selenium"),
                    fetched_at=now,
                    checked_at=now,
                    scrape_stats={
                        "resolution": resolved.get("resolution"),
                        "canonical_username": entry["canonical_username"],
                        "sources": sorted(entry["sources"]),
                        "seed_usernames": sorted(s for s in entry["seeds"] if s),
                        "profile_urls": sorted(entry["profile_urls"]),
                    },
                )
            )
        return records

    def _make_seed_account_record(
        self, seed: SeedAccount, overview: ProfileOverview
    ) -> ShadowAccount:
        """Create a shadow account record for the seed itself using profile overview data."""
        now = datetime.utcnow()

        followers_total = overview.followers_total
        following_total = overview.following_total

        if not overview.followers_total:
            LOGGER.warning(
                "Profile header missing followers total for @%s; storing NULL", seed.username
            )
            self._selenium._save_page_snapshot(seed.username, "profile-header-missing")
        if not overview.following_total:
            LOGGER.warning(
                "Profile header missing following total for @%s; storing NULL", seed.username
            )
            self._selenium._save_page_snapshot(seed.username, "profile-header-missing")

        return ShadowAccount(
            account_id=seed.account_id,
            username=overview.username,
            display_name=overview.display_name,
            bio=overview.bio,
            location=overview.location,
            website=overview.website,
            profile_image_url=overview.profile_image_url,
            followers_count=followers_total,
            following_count=following_total,
            source_channel="selenium_profile_scrape",
            fetched_at=now,
            checked_at=now,
            scrape_stats={
                "resolution": "seed_profile",
                "canonical_username": overview.username,
                "sources": ["seed_profile_page"],
                "seed_usernames": [seed.username],
                "profile_urls": [f"https://x.com/{overview.username}"],
                "website": overview.website,
                "joined_date": overview.joined_date,
            },
        )

    def _make_edge_records(
        self,
        *,
        seed: SeedAccount,
        following: Sequence[CapturedUser],
        followers: Sequence[CapturedUser],
    ) -> List[ShadowEdge]:
        edges: List[ShadowEdge] = []
        now = datetime.utcnow()

        for captured in following:
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                continue
            edges.append(
                ShadowEdge(
                    source_id=seed.account_id,
                    target_id=account_id,
                    direction="outbound",
                    source_channel=resolved.get("source_channel", "hybrid_selenium"),
                    fetched_at=now,
                    checked_at=now,
                    weight=1,
                    metadata={
                        "list_type": "following",
                        "list_types": sorted(captured.list_types or {"following"}),
                        "seed_username": seed.username,
                        "resolution": resolved.get("resolution"),
                    },
                )
            )

        for captured in followers:
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                continue
            list_types = captured.list_types or {"followers"}
            edges.append(
                ShadowEdge(
                    source_id=account_id,
                    target_id=seed.account_id,
                    direction="inbound",
                    source_channel=resolved.get("source_channel", "hybrid_selenium"),
                    fetched_at=now,
                    checked_at=now,
                    weight=1,
                    metadata={
                        "list_type": "followers",
                        "list_types": sorted(list_types),
                        "seed_username": seed.username,
                        "resolution": resolved.get("resolution"),
                    },
                )
            )

        return edges

    def _make_discovery_records(
        self,
        *,
        seed: SeedAccount,
        following: Sequence[CapturedUser],
        followers: Sequence[CapturedUser],
        followers_you_follow: Sequence[CapturedUser],
    ) -> List[ShadowDiscovery]:
        discoveries: List[ShadowDiscovery] = []
        now = datetime.utcnow()

        # Track discoveries from following list
        for captured in following:
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                continue
            discoveries.append(
                ShadowDiscovery(
                    shadow_account_id=account_id,
                    seed_account_id=seed.account_id,
                    discovered_at=now,
                    discovery_method="following",
                )
            )

        # Track discoveries from followers list (excluding followers_you_follow to avoid duplicates)
        followers_usernames = {c.username for c in followers}
        followers_you_follow_usernames = {c.username for c in followers_you_follow}
        pure_followers = followers_usernames - followers_you_follow_usernames

        for captured in followers:
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                continue
            discoveries.append(
                ShadowDiscovery(
                    shadow_account_id=account_id,
                    seed_account_id=seed.account_id,
                    discovered_at=now,
                    discovery_method="followers",
                )
            )

        # Track discoveries from followers_you_follow list
        for captured in followers_you_follow:
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                continue
            discoveries.append(
                ShadowDiscovery(
                    shadow_account_id=account_id,
                    seed_account_id=seed.account_id,
                    discovered_at=now,
                    discovery_method="followers_you_follow",
                )
            )

        return discoveries

    def _make_list_member_records(
        self,
        *,
        list_id: str,
        captures: Sequence[CapturedUser],
    ) -> List[ShadowListMember]:
        """Convert captured list members into persistent list member records."""
        records: List[ShadowListMember] = []
        now = datetime.utcnow()

        for captured in captures:
            resolved = self._resolve_username(captured)
            account_id = resolved.get("account_id")
            if not account_id:
                continue

            username = (captured.username or resolved.get("username") or "").strip("@")
            list_types = captured.list_types or {"list_members"}
            metadata: dict = {"list_types": sorted(list_types)}
            if captured.profile_url:
                metadata["profile_url"] = captured.profile_url

            records.append(
                ShadowListMember(
                    list_id=list_id,
                    member_account_id=account_id,
                    member_username=username or None,
                    member_display_name=captured.display_name or resolved.get("display_name"),
                    bio=captured.bio or resolved.get("bio"),
                    website=captured.website or resolved.get("website"),
                    profile_image_url=captured.profile_image_url or resolved.get("profile_image_url"),
                    fetched_at=now,
                    source_channel=resolved.get("source_channel", "hybrid_selenium"),
                    metadata=metadata if metadata else None,
                )
            )

        return records

    def _list_capture_from_cache(
        self,
        *,
        list_id: str,
        list_meta: ShadowList,
        members: Sequence[ShadowListMember],
    ) -> UserListCapture:
        """Convert cached list members into a UserListCapture."""
        entries: List[CapturedUser] = []
        for member in members:
            list_types = {"list_members"}
            if member.metadata:
                meta_types = member.metadata.get("list_types")
                if isinstance(meta_types, (list, tuple, set)):
                    list_types = set(meta_types)

            profile_url = None
            if member.metadata and member.metadata.get("profile_url"):
                profile_url = member.metadata["profile_url"]
            elif member.member_username:
                profile_url = f"https://x.com/{member.member_username}"

            entries.append(
                CapturedUser(
                    username=member.member_username,
                    display_name=member.member_display_name,
                    bio=member.bio,
                    profile_url=profile_url,
                    website=member.website,
                    profile_image_url=member.profile_image_url,
                    list_types=set(list_types),
                )
            )

        claimed_total = list_meta.claimed_member_total if list_meta.claimed_member_total is not None else list_meta.member_count if list_meta.member_count is not None else len(entries)
        overview = ListOverview(
            list_id=list_id,
            name=list_meta.name,
            description=list_meta.description,
            owner_username=list_meta.owner_username,
            owner_display_name=list_meta.owner_display_name,
            owner_profile_url=(
                list_meta.metadata.get("owner_profile_url")
                if list_meta.metadata and isinstance(list_meta.metadata, dict)
                else (f"https://x.com/{list_meta.owner_username}" if list_meta.owner_username else None)
            ),
            members_total=list_meta.claimed_member_total,
            followers_total=list_meta.followers_count,
        )
        return UserListCapture(
            list_type="list_members",
            entries=entries,
            claimed_total=claimed_total,
            page_url=f"https://twitter.com/i/lists/{list_id}/members",
            profile_overview=None,
            list_overview=overview,
        )

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------
    def _resolve_username(self, captured: CapturedUser) -> Dict[str, object]:
        username = captured.username
        if not username:
            return {}
        username = username.strip().lstrip("@")
        cache_key = username.lower()
        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]

        # Use API as fallback only if basic info (bio) is missing from Selenium
        has_basic_info = captured.bio is not None and captured.bio.strip() != ""
        fallback_id = f"shadow:{cache_key}"

        if has_basic_info or not self._api:
            record: Dict[str, object] = {
                "account_id": fallback_id,
                "username": username,
                "display_name": captured.display_name or username,
                "bio": captured.bio,
                "source_channel": "hybrid_selenium",
                "resolution": "selenium",
            }
            self._resolution_cache[cache_key] = record
            return record

        # Fallback to API
        LOGGER.debug("Selenium data for @%s is missing bio; falling back to X API.", username)
        info = self._api.get_user_info_by_username(username)

        if not info:
            # API failed, use Selenium data anyway
            record: Dict[str, object] = {
                "account_id": fallback_id,
                "username": username,
                "display_name": captured.display_name or username,
                "bio": captured.bio,
                "source_channel": "hybrid_selenium",
                "resolution": "selenium_api_failed",
            }
            self._resolution_cache[cache_key] = record
            return record

        # API succeeded, use the rich data
        metrics = info.get("public_metrics") or {}
        record = {
            "account_id": str(info.get("id", fallback_id)),
            "display_name": info.get("name") or username,
            "bio": info.get("description"),
            "location": info.get("location"),
            "followers_count": metrics.get("followers_count"),
            "following_count": metrics.get("following_count"),
            "source_channel": "x_api",
            "resolution": "x_api",
        }
        self._resolution_cache[cache_key] = record
        return record

    # ------------------------------------------------------------------
    # Human confirmation helper
    # ------------------------------------------------------------------
    @staticmethod
    def _input_with_timeout(prompt: str, timeout_seconds: int = 30) -> Optional[str]:
        """Get user input with a timeout. Auto-accepts after timeout.

        Args:
            prompt: The prompt to display to the user
            timeout_seconds: Seconds to wait before auto-accepting (default 30)

        Returns:
            User input string, or None if timeout occurred (auto-accept)
        """
        print(prompt, end='', flush=True)

        # Use select to wait for input with timeout (Unix/macOS only)
        # On Windows, this will fall back to regular input (no timeout)
        if sys.platform == 'win32':
            # Windows doesn't support select on stdin, fall back to regular input
            return input()

        # Print countdown timer
        print(f" (auto-accepting in {timeout_seconds}s)", flush=True)

        ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)

        if ready:
            # User provided input before timeout
            return sys.stdin.readline().strip()
        else:
            # Timeout occurred - auto-accept
            print("\n⏱️  Timeout - auto-accepting...")
            return None  # None signals auto-accept

    def _confirm_first_scrape(
        self,
        seed_username: str,
        following_capture: Optional[UserListCapture],
        followers_capture: Optional[UserListCapture],
        followers_you_follow_capture: Optional[UserListCapture],
        following_entries: Sequence[CapturedUser],
        followers_entries: Sequence[CapturedUser],
        followers_you_follow_entries: Sequence[CapturedUser],
    ) -> None:
        if self._first_scrape_confirmed:
            return

        overview = self._profile_overview_from_captures(
            following_capture, followers_capture, followers_you_follow_capture
        )

        print("\n=== First scraped profile preview ===")
        print(f"Seed handle      : @{seed_username}")
        if overview:
            print(f"Seed display     : {overview.display_name or '?'}")
            print(f"Seed bio         : {self._truncate_text(overview.bio) or '?'}")
            print(f"Seed location    : {overview.location or '?'}")
            print(f"Seed website     : {overview.website or '?'}")
            totals = []
            if overview.following_total is not None:
                totals.append(f"following≈{overview.following_total:,}")
            if overview.followers_total is not None:
                totals.append(f"followers≈{overview.followers_total:,}")
            if totals:
                print(f"Seed totals     : {', '.join(totals)}")

        self._print_capture_summary("Following", following_capture, following_entries)
        self._print_capture_summary("Followers", followers_capture, followers_entries)
        self._print_capture_summary(
            "Followers you follow",
            followers_you_follow_capture,
            followers_you_follow_entries,
        )

        sample_sources: List[tuple[str, Sequence[CapturedUser]]] = []
        if following_entries:
            sample_sources.append(("Following", following_entries))
        if followers_entries:
            sample_sources.append(("Followers", followers_entries))
        if followers_you_follow_entries:
            sample_sources.append(("Followers you follow", followers_you_follow_entries))

        preview_limit = max(1, self._config.preview_sample_size)
        detailed_shown = False
        for label, entries in sample_sources:
            if not entries:
                continue
            detailed_shown = True
            print(f"\nTop {min(preview_limit, len(entries))} from {label}:")
            for idx, entry in enumerate(entries[:preview_limit], start=1):
                bio_snippet = f" — {self._truncate_text(entry.bio)}" if entry.bio else ""
                list_tags = (
                    f" [{', '.join(sorted(entry.list_types))}]" if entry.list_types else ""
                )
                print(
                    f"  {idx:>2}. @{entry.username} — {entry.display_name or '<no name>'}{bio_snippet}{list_tags}"
                )

        if not detailed_shown:
            LOGGER.warning(
                "No profiles captured for @%s during confirmation gate; continuing.",
                seed_username,
            )
            self._first_scrape_confirmed = True
            return

        while True:
            response = self._input_with_timeout("Proceed with enrichment? [Y/n]:", timeout_seconds=30)

            # None means timeout occurred - auto-accept
            if response is None:
                self._first_scrape_confirmed = True
                print("Continuing enrichment…\n")
                return

            response = response.strip().lower()
            if response in ("", "y", "yes"):
                self._first_scrape_confirmed = True
                print("Continuing enrichment…\n")
                return
            if response in ("n", "no"):
                LOGGER.error("User aborted after reviewing first scraped profile; stopping run.")
                self._selenium.quit()
                raise RuntimeError("First scraped profile was rejected by user confirmation.")
            print("Please respond with 'y' or 'n'.")

    @staticmethod
    def _combine_captures(captures: Sequence[UserListCapture]) -> List[CapturedUser]:
        combined: Dict[str, CapturedUser] = {}
        for capture in captures:
            for entry in capture.entries:
                existing = combined.get(entry.username)
                if existing:
                    existing.list_types.update(entry.list_types)
                    if not existing.display_name and entry.display_name:
                        existing.display_name = entry.display_name
                    if not existing.bio and entry.bio:
                        existing.bio = entry.bio
                    if not existing.website and entry.website:
                        existing.website = entry.website
                    if not existing.profile_image_url and entry.profile_image_url:
                        existing.profile_image_url = entry.profile_image_url
                    continue
                combined[entry.username] = CapturedUser(
                    username=entry.username,
                    display_name=entry.display_name,
                    bio=entry.bio,
                    profile_url=entry.profile_url,
                    website=entry.website,
                    profile_image_url=entry.profile_image_url,
                    list_types=set(entry.list_types),
                )
        return list(combined.values())

    @staticmethod
    def _compute_skip_coverage_percent(claimed_total: Optional[int], captured: Optional[int]) -> float:
        """Compute coverage percent used for skip gating (0/0 treated as 100%)."""
        if claimed_total is not None and claimed_total > 0 and captured is not None:
            return (captured / claimed_total) * 100
        if claimed_total == 0 and (captured or 0) == 0:
            return 100.0
        return 0.0

    @staticmethod
    def _compute_coverage(captured: int, claimed_total: Optional[int]) -> Optional[float]:
        if not claimed_total or claimed_total <= 0:
            return None
        return round(captured / claimed_total, 6)

    def _profile_overview_from_captures(
        self,
        following_capture: Optional[UserListCapture],
        followers_capture: Optional[UserListCapture],
        followers_you_follow_capture: Optional[UserListCapture],
    ) -> Optional[ProfileOverview]:
        for capture in (
            following_capture,
            followers_capture,
            followers_you_follow_capture,
        ):
            if capture and capture.profile_overview:
                return capture.profile_overview
        return None

    def _profile_overview_as_dict(
        self,
        following_capture: Optional[UserListCapture],
        followers_capture: Optional[UserListCapture],
        followers_you_follow_capture: Optional[UserListCapture],
    ) -> Optional[Dict[str, object]]:
        overview = self._profile_overview_from_captures(
            following_capture, followers_capture, followers_you_follow_capture
        )
        if not overview:
            return None
        return {
            "username": overview.username,
            "display_name": overview.display_name,
            "bio": overview.bio,
            "location": overview.location,
            "website": overview.website,
            "followers_total": overview.followers_total,
            "following_total": overview.following_total,
            "joined_date": overview.joined_date,
            "profile_image_url": overview.profile_image_url,
        }

    def _print_capture_summary(
        self,
        label: str,
        capture: Optional[UserListCapture],
        entries: Sequence[CapturedUser],
    ) -> None:
        captured_count = len(entries)
        claimed_total = capture.claimed_total if capture else None

        # Per user request: Assume "followers you follow" is always fully captured.
        if claimed_total is None and label == "Followers you follow":
            claimed_total = captured_count

        coverage = self._compute_coverage(captured_count, claimed_total)
        coverage_str = (
            f" ({coverage * 100:.3f}% of claimed)" if coverage is not None else ""
        )
        claimed_str = f"{claimed_total:,}" if claimed_total is not None else "?"
        print(f"{label:<20}: captured {captured_count} / {claimed_str}{coverage_str}")

    @staticmethod
    def _truncate_text(value: Optional[str], limit: int = 160) -> str:
        if not value:
            return ""
        text = value.strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"
