"""Profile/following/followers refresh actions + cached list-members fetch."""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Optional

from ...data.shadow_store import ScrapeRunMetrics, ShadowList
from ..selenium_worker import ListOverview, UserListCapture

LOGGER = logging.getLogger("src.shadow.enricher")


class RefreshActionsMixin:
    """Wraps the selenium fetches with policy checks + metrics recording.

    Required state on coordinator: self._store, self._config, self._policy,
    self._selenium. Cross-mixin: self._should_refresh_list, self._confirm_refresh
    (freshness), self._make_seed_account_record, self._make_list_member_records,
    self._list_capture_from_cache (record_builders), self._time_phase,
    self._phase_snapshot, self._log_phase_summary (observability).
    """

    def _refresh_profile(
        self,
        seed,
        has_edges: bool,
        has_profile: bool,
    ) -> Optional[dict]:
        """Refresh profile metadata only (no list scraping).

        Used in --profile-only mode to update bio, location, counts without scraping lists.

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

    def _refresh_following(self, seed, overview) -> Optional[UserListCapture]:
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

    def _refresh_followers(self, seed, overview) -> tuple:
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
