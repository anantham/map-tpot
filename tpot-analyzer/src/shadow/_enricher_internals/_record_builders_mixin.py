"""Record constructors: turn captured users into ShadowAccount/Edge/Discovery/ListMember."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from ...data.shadow_store import (
    ShadowAccount,
    ShadowDiscovery,
    ShadowEdge,
    ShadowList,
    ShadowListMember,
)
from ..selenium_worker import CapturedUser, ListOverview, ProfileOverview, UserListCapture

LOGGER = logging.getLogger("src.shadow.enricher")


class RecordBuildersMixin:
    """Convert capture results into persistence records.

    Required state on coordinator: self._store, self._selenium.
    Cross-mixin: self._resolve_username (capture_helpers).
    """

    def _make_account_records(
        self,
        *,
        seed,
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

    def _make_seed_account_record(self, seed, overview: ProfileOverview) -> ShadowAccount:
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
        seed,
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
        seed,
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
