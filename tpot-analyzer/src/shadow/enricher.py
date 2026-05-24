"""Hybrid enrichment orchestrator mixing Selenium scraping and X API lookups.

Public surface (unchanged): SeedAccount, EnrichmentPolicy, ShadowEnrichmentConfig,
HybridShadowEnricher. ProfileOverview and ShadowAccount are re-exported for
back-compat with existing imports.

This file is the COORDINATOR. The heavy `enrich()` method stays here (it's the
orchestrator's single entry point and its 750 LOC of intertwined state, signal
handling, and per-seed loop don't decompose cleanly). All other behavior lives
in mixins under `_enricher_internals/`.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from sqlalchemy.exc import OperationalError

from ..data.shadow_store import (
    ScrapeRunMetrics,
    ShadowAccount,
    ShadowStore,
)
from ._enricher_internals._capture_helpers_mixin import CaptureHelpersMixin
from ._enricher_internals._freshness_mixin import FreshnessMixin
from ._enricher_internals._observability_mixin import ObservabilityMixin
from ._enricher_internals._record_builders_mixin import RecordBuildersMixin
from ._enricher_internals._refresh_actions_mixin import RefreshActionsMixin
from .selenium_worker import (
    CapturedUser,
    ProfileOverview,
    SeleniumConfig,
    SeleniumWorker,
)
from .x_api_client import XAPIClient, XAPIClientConfig


LOGGER = logging.getLogger(__name__)

__all__ = [
    "ACCOUNT_STATUS_RETRY_DAYS",
    "EnrichmentPolicy",
    "HybridShadowEnricher",
    "ProfileOverview",
    "SeedAccount",
    "ShadowAccount",
    "ShadowEnrichmentConfig",
]


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


class HybridShadowEnricher(
    ObservabilityMixin,
    FreshnessMixin,
    RefreshActionsMixin,
    RecordBuildersMixin,
    CaptureHelpersMixin,
):
    """Coordinates Selenium scraping with optional X API enrichment.

    Composes five behavior mixins under `_enricher_internals/`; this class
    owns the runtime state and the main `enrich()` loop.
    """

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
