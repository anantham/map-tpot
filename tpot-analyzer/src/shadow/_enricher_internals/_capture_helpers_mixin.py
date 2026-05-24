"""Capture-resolution + first-scrape confirmation + small numeric/text helpers."""
from __future__ import annotations

import logging
import select
import sys
from typing import Dict, List, Optional, Sequence

from ..selenium_worker import CapturedUser, ProfileOverview, UserListCapture

LOGGER = logging.getLogger("src.shadow.enricher")


class CaptureHelpersMixin:
    """Username resolution + timed input + capture statistics.

    Required state on coordinator: self._resolution_cache, self._api,
    self._config, self._selenium, self._first_scrape_confirmed.
    """

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

        sample_sources: List[tuple] = []
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
