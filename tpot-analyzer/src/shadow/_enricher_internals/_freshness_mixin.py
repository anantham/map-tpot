"""Freshness + skip-gating logic for HybridShadowEnricher."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from ...data.shadow_store import ScrapeRunMetrics

LOGGER = logging.getLogger("src.shadow.enricher")


class FreshnessMixin:
    """Decides whether to skip seeds or refresh lists based on policy + history.

    Required state on coordinator: self._store, self._config, self._policy,
    self._selenium, plus cross-mixin: self._make_seed_account_record (record_builders).
    """

    def _should_skip_seed(self, seed) -> tuple:
        """Check if seed should be skipped based on existing data and policy.

        Skip conditions:
        - In normal mode: skip if we have complete profile AND edges AND policy says data is fresh
        - In profile-only mode: never skip here (handled separately)

        Returns:
            tuple of (should_skip, skip_reason, edge_summary, cached_overview)
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

    def _check_list_freshness_across_runs(
        self,
        account_id: str,
        list_type: str,  # "following" or "followers"
        username: Optional[str] = None,
    ) -> tuple:
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
        seed,
        list_type: str,  # "following" or "followers"
        current_total: Optional[int],
    ) -> tuple:
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
        seed,
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
