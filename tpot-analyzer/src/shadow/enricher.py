"""Hybrid enrichment orchestrator mixing Selenium scraping and X API lookups."""
from __future__ import annotations

import json
import logging
import random
import time
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
    ShadowStore,
)
from .selenium_worker import (
    CapturedUser,
    ProfileOverview,
    SeleniumConfig,
    SeleniumWorker,
    UserListCapture,
)
from .x_api_client import XAPIClient, XAPIClientConfig


LOGGER = logging.getLogger(__name__)


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
        self._policy = policy or EnrichmentPolicy.default()
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
        )
        self._selenium = SeleniumWorker(selenium_config)
        self._api: Optional[XAPIClient] = None
        if config.bearer_token:
            api_config = XAPIClientConfig(
                bearer_token=config.bearer_token,
                rate_state_path=config.rate_state_path,
            )
            self._api = XAPIClient(api_config)
        self._resolution_cache: Dict[str, Dict[str, object]] = {}
        self._first_scrape_confirmed = not config.confirm_first_scrape

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
                following_claimed_total=None,
                followers_claimed_total=None,
                followers_you_follow_claimed_total=None,
                following_coverage=None,
                followers_coverage=None,
                followers_you_follow_coverage=None,
                accounts_upserted=0,
                edges_upserted=0,
                discoveries_upserted=0,
                skipped=False,
                skip_reason=None,
                error_type="profile_overview_missing",
                error_details=f"Profile-only mode: Failed to fetch profile overview for @{seed.username}",
            )
            self._store.record_scrape_metrics(error_metrics)
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

    def _should_refresh_list(
        self,
        seed: SeedAccount,
        list_type: str,  # "following" or "followers"
        current_total: Optional[int],
    ) -> tuple[bool, Optional[str]]:
        """Check if a list should be refreshed based on policy.

        Returns:
            tuple of (should_refresh: bool, reason: Optional[str])

        Notes:
            When should_refresh is True, ``reason`` indicates which policy trigger fired
            (e.g. ``first_run``, ``age_threshold``, ``delta_threshold``). When False,
            ``reason`` explains why the list is considered fresh.
        """
        # Get last scrape metrics
        last_metrics = self._store.get_last_scrape_metrics(seed.account_id)

        if not last_metrics:
            # No previous scrape - always refresh
            LOGGER.info(
                "@%s %s list has no historical metrics; performing initial scrape",
                seed.username,
                list_type,
            )
            return (True, "first_run")

        # Calculate age in days
        age_days = (datetime.utcnow() - last_metrics.run_at).days

        # Get old count for delta calculation
        if list_type == "following":
            old_total = last_metrics.following_claimed_total
        else:  # "followers"
            old_total = last_metrics.followers_claimed_total

        # Check age trigger
        if age_days > self._policy.list_refresh_days:
            LOGGER.info(
                "@%s %s list is %d days old (threshold: %d days) - refresh needed",
                seed.username,
                list_type,
                age_days,
                self._policy.list_refresh_days,
            )
            return (True, "age_threshold")

        # Check percentage delta trigger
        if old_total is not None and current_total is not None:
            pct_delta = abs(current_total - old_total) / max(old_total, 1)
            if pct_delta > self._policy.pct_delta_threshold:
                LOGGER.info(
                    "@%s %s count changed from %d to %d (%.1f%% delta, threshold: %.1f%%) - refresh needed",
                    seed.username,
                    list_type,
                    old_total,
                    current_total,
                    pct_delta * 100,
                    self._policy.pct_delta_threshold * 100,
                )
                return (True, "delta_threshold")

        # No refresh needed
        LOGGER.info(
            "@%s %s list is fresh (age: %d days, old: %s, current: %s) - skipping",
            seed.username,
            list_type,
            age_days,
            old_total,
            current_total,
        )
        return (False, f"{list_type}_fresh")

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
        return self._selenium.fetch_following(seed.username)

    def _refresh_followers(
        self,
        seed: SeedAccount,
        overview: ProfileOverview,
    ) -> tuple[Optional[UserListCapture], Optional[UserListCapture]]:
        """Refresh followers lists with policy-driven caching.

        Returns:
            tuple of (followers_capture, followers_you_follow_capture)
        """
        if not self._config.include_followers:
            LOGGER.info(
                "Skipping @%s followers list: include_followers disabled in config",
                seed.username,
            )
            return (None, None)

        # Check if refresh is needed based on policy
        should_refresh, reason = self._should_refresh_list(
            seed, "followers", overview.followers_total
        )

        if not should_refresh:
            LOGGER.info("Skipping @%s followers list: %s", seed.username, reason)
            return (None, None)

        # Prompt user if needed
        if not self._confirm_refresh(seed, "followers", reason):
            LOGGER.warning("Skipping @%s followers list: user declined", seed.username)
            return (None, None)

        # Scrape followers
        followers_capture = self._selenium.fetch_followers(seed.username)

        # Scrape followers_you_follow if enabled
        followers_you_follow_capture = None
        if self._config.include_followers_you_follow:
            followers_you_follow_capture = self._selenium.fetch_followers_you_follow(
                seed.username
            )
        else:
            LOGGER.info(
                "Skipping followers-you-follow list for @%s: include_followers_you_follow disabled",
                seed.username,
            )

        return (followers_capture, followers_you_follow_capture)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enrich(self, seeds: Sequence[SeedAccount]) -> Dict[str, Dict[str, object]]:
        """Enrich the graph starting from provided seed accounts."""

        summary: Dict[str, Dict[str, object]] = {}
        for seed in seeds:
            if not seed.username:
                LOGGER.warning("Seed %s missing username; skipping", seed.account_id)
                continue

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
                skip_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=0.0,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    skipped=True,
                    skip_reason=skip_reason,
                )
                self._store.record_scrape_metrics(skip_metrics)
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

            # Fetch profile overview first to check counts for policy
            overview = cached_overview or self._selenium.fetch_profile_overview(seed.username)
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
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
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

            # Use policy-driven refresh helpers
            following_capture = self._refresh_following(seed, overview)
            followers_capture, followers_you_follow_capture = self._refresh_followers(seed, overview)

            # Check if policy skipped all lists (preserve baseline, don't corrupt metrics)
            policy_skipped_all = (following_capture is None and followers_capture is None)

            if policy_skipped_all:
                # Even if lists are fresh, refresh seed profile metadata for canonical counts
                self._store.upsert_accounts([self._make_seed_account_record(seed, overview)])
                # Record that we checked but policy skipped everything
                skip_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=0.0,
                    following_captured=0,
                    followers_captured=0,
                    followers_you_follow_captured=0,
                    following_claimed_total=None,
                    followers_claimed_total=None,
                    followers_you_follow_claimed_total=None,
                    following_coverage=None,
                    followers_coverage=None,
                    followers_you_follow_coverage=None,
                    accounts_upserted=0,
                    edges_upserted=0,
                    discoveries_upserted=0,
                    skipped=True,
                    skip_reason="policy_fresh_data",
                )
                self._store.record_scrape_metrics(skip_metrics)

                LOGGER.info(
                    "✓ Skipped @%s (policy: data is fresh, baseline preserved)",
                    seed.username,
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
                [capture for capture in (followers_capture, followers_you_follow_capture) if capture]
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

            edges = self._make_edge_records(
                seed=seed,
                following=following_entries,
                followers=followers_entries,
            )
            discoveries = self._make_discovery_records(
                seed=seed,
                following=following_entries,
                followers=followers_entries,
                followers_you_follow=followers_you_follow_entries,
            )

            try:
                inserted_accounts = self._store.upsert_accounts(accounts)
                inserted_edges = self._store.upsert_edges(edges)
                inserted_discoveries = self._store.upsert_discoveries(discoveries)

                seed_summary = {
                    "username": seed.username,
                    "accounts_upserted": inserted_accounts,
                    "edges_upserted": inserted_edges,
                    "discoveries_upserted": inserted_discoveries,
                    "following_captured": len(following_entries),
                    "followers_captured": len(followers_entries),
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

                # Record scrape metrics
                run_metrics = ScrapeRunMetrics(
                    seed_account_id=seed.account_id,
                    seed_username=seed.username or "",
                    run_at=datetime.utcnow(),
                    duration_seconds=scrape_duration,
                    following_captured=len(following_entries),
                    followers_captured=len(followers_entries),
                    followers_you_follow_captured=len(followers_you_follow_entries),
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
                    skipped=False,
                    skip_reason=None,
                )
                self._store.record_scrape_metrics(run_metrics)

                LOGGER.warning(
                    "✓ @%s: accounts=%s edges=%s discoveries=%s following=%s/%s followers=%s/%s followers_you_follow=%s/%s",
                    seed.username,
                    inserted_accounts,
                    inserted_edges,
                    inserted_discoveries,
                    len(following_entries),
                    seed_summary["following_claimed_total"],
                    len(followers_entries),
                    seed_summary["followers_claimed_total"],
                    len(followers_you_follow_entries),
                    seed_summary["followers_you_follow_claimed_total"],
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
                    skipped=False,
                    skip_reason=None,
                    error_type="persistence_failure",
                    error_details=f"SQLite OperationalError: {str(getattr(exc, 'orig', exc))}",
                )
                self._store.record_scrape_metrics(error_metrics)
                continue

            if self._config.user_pause_seconds > 0:
                time.sleep(self._config.user_pause_seconds)

        self._selenium.quit()
        return summary

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
            resolved = self._resolve_username(username)
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
            resolved = self._resolve_username(captured.username)
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
            resolved = self._resolve_username(captured.username)
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
            resolved = self._resolve_username(captured.username)
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
            if captured.username not in pure_followers:
                continue
            resolved = self._resolve_username(captured.username)
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
            resolved = self._resolve_username(captured.username)
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

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------
    def _resolve_username(self, username: Optional[str]) -> Dict[str, object]:
        if not username:
            return {}
        username = username.strip().lstrip("@")
        cache_key = username.lower()
        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]

        fallback_id = f"shadow:{cache_key}"
        record: Dict[str, object] = {
            "account_id": fallback_id,
            "username": username,
            "display_name": username,
            "source_channel": "hybrid_selenium",
            "resolution": "selenium",
        }
        if not self._api:
            self._resolution_cache[cache_key] = record
            return record

        info = self._api.get_user_info_by_username(username)
        if not info:
            self._resolution_cache[cache_key] = record
            return record

        metrics = info.get("public_metrics") or {}
        record.update(
            {
                "account_id": str(info.get("id", fallback_id)),
                "display_name": info.get("name") or username,
                "bio": info.get("description"),
                "location": info.get("location"),
                "followers_count": metrics.get("followers_count"),
                "following_count": metrics.get("following_count"),
                "source_channel": "x_api",
                "resolution": "x_api",
            }
        )
        self._resolution_cache[cache_key] = record
        return record

    # ------------------------------------------------------------------
    # Human confirmation helper
    # ------------------------------------------------------------------
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
            response = input("Proceed with enrichment? [Y/n]: ").strip().lower()
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
