"""Hybrid enrichment orchestrator mixing Selenium scraping and X API lookups."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

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

    def __init__(self, store: ShadowStore, config: ShadowEnrichmentConfig) -> None:
        self._store = store
        self._config = config
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
    # Skip Logic Helpers
    # ------------------------------------------------------------------
    def _should_skip_seed(self, seed: SeedAccount) -> tuple[bool, Optional[str], dict]:
        """Check if seed should be skipped based on existing data.

        Skip conditions:
        - In normal mode: skip if we have both complete profile AND edges
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

        # Skip if not in profile-only mode and we have both edges and profile
        if not self._config.profile_only and has_edges and has_profile:
            return (True, "complete profile and edges exist", edge_summary)

        return (False, None, edge_summary)

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
            should_skip, skip_reason, edge_summary = self._should_skip_seed(seed)

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

            if self._config.profile_only:
                if not self._config.profile_only_all:
                    if not has_edges:
                        LOGGER.warning(
                            "Skipping profile-only @%s (%s) — no existing edge data",
                            seed.username,
                            seed.account_id,
                        )
                        summary[seed.account_id] = {
                            "username": seed.username,
                            "profile_only": True,
                            "skipped": True,
                            "reason": "no_edge_data",
                        }
                        continue
                    if has_profile:
                        LOGGER.warning(
                            "Skipping profile-only @%s (%s) — profile already complete",
                            seed.username,
                            seed.account_id,
                        )
                        summary[seed.account_id] = {
                            "username": seed.username,
                            "profile_only": True,
                            "skipped": True,
                            "reason": "profile_complete",
                        }
                        continue
                overview = self._selenium.fetch_profile_overview(seed.username)
                if not overview:
                    LOGGER.error(
                        "Profile-only update failed for @%s (%s); could not load profile page",
                        seed.username,
                        seed.account_id,
                    )
                    summary[seed.account_id] = {
                        "username": seed.username,
                        "profile_only": True,
                        "updated": False,
                        "error": "profile_overview_missing",
                    }
                    continue

                account_record = self._make_seed_account_record(seed, overview)
                inserted_accounts = self._store.upsert_accounts([account_record])
                summary[seed.account_id] = {
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
                LOGGER.warning(
                    "✓ profile-only @%s updated account (upserts=%s)",
                    seed.username,
                    inserted_accounts,
                )
                pause = random.uniform(
                    max(0.5, self._config.action_delay_min),
                    max(self._config.action_delay_min, self._config.action_delay_max),
                )
                time.sleep(pause)
                continue

            start = time.perf_counter()
            LOGGER.info("Enriching @%s...", seed.username)
            following_capture: Optional[UserListCapture] = (
                self._selenium.fetch_following(seed.username)
                if self._config.include_following
                else None
            )
            followers_capture: Optional[UserListCapture] = (
                self._selenium.fetch_followers(seed.username)
                if self._config.include_followers
                else None
            )
            followers_you_follow_capture: Optional[UserListCapture] = None
            if self._config.include_followers and self._config.include_followers_you_follow:
                followers_you_follow_capture = self._selenium.fetch_followers_you_follow(
                    seed.username
                )

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
            seed_profile_overview = self._profile_overview_from_captures(
                following_capture, followers_capture, followers_you_follow_capture
            )
            if seed_profile_overview:
                seed_account = self._make_seed_account_record(seed, seed_profile_overview)
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

            inserted_accounts = self._store.upsert_accounts(accounts)
            inserted_edges = self._store.upsert_edges(edges)
            inserted_discoveries = self._store.upsert_discoveries(discoveries)

            summary[seed.account_id] = {
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
                followers_you_follow_claimed_total=followers_you_follow_capture.claimed_total if followers_you_follow_capture else None,
                following_coverage=summary[seed.account_id]["coverage"]["following"],
                followers_coverage=summary[seed.account_id]["coverage"]["followers"],
                followers_you_follow_coverage=summary[seed.account_id]["coverage"]["followers_you_follow"],
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
                summary[seed.account_id]["following_claimed_total"],
                len(followers_entries),
                summary[seed.account_id]["followers_claimed_total"],
                len(followers_you_follow_entries),
                summary[seed.account_id]["followers_you_follow_claimed_total"],
            )

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

        if followers_total is None:
            LOGGER.warning(
                "Profile header missing followers total for @%s; storing NULL",
                seed.username,
            )
        if following_total is None:
            LOGGER.warning(
                "Profile header missing following total for @%s; storing NULL",
                seed.username,
            )

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
