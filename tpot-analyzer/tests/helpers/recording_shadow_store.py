"""Stateful ShadowStore test double for enrichment tests."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from src.data.shadow_store import (
    ScrapeRunMetrics,
    ShadowAccount,
    ShadowDiscovery,
    ShadowEdge,
    ShadowList,
    ShadowListMember,
)


class RecordingShadowStore:
    """Record store interactions for behavior-focused tests."""

    def __init__(self) -> None:
        self.accounts: Dict[str, ShadowAccount] = {}
        self.edges: List[ShadowEdge] = []
        self.discoveries: List[ShadowDiscovery] = []
        self.metrics: List[ScrapeRunMetrics] = []
        self.lists: Dict[str, ShadowList] = {}
        self.list_members: Dict[str, List[ShadowListMember]] = {}
        self.edge_summary_overrides: Dict[str, Dict[str, int]] = {}
        self.profile_complete_overrides: Dict[str, bool] = {}
        self.last_scrape_overrides: Dict[str, ScrapeRunMetrics] = {}
        self.last_scrape_by_seed: Dict[str, ScrapeRunMetrics] = {}
        self.account_id_by_username: Dict[str, str] = {}

    def set_edge_summary(self, seed_account_id: str, following: int, followers: int) -> None:
        self.edge_summary_overrides[seed_account_id] = {
            "following": following,
            "followers": followers,
            "total": following + followers,
        }

    def set_profile_complete(self, seed_account_id: str, complete: bool) -> None:
        self.profile_complete_overrides[seed_account_id] = complete

    def set_last_scrape_metrics(self, seed_account_id: str, metrics: ScrapeRunMetrics) -> None:
        self.last_scrape_overrides[seed_account_id] = metrics

    def edge_summary_for_seed(self, seed_account_id: str) -> dict:
        override = self.edge_summary_overrides.get(seed_account_id)
        if override is not None:
            return override

        following = 0
        followers = 0
        for edge in self.edges:
            if not edge.metadata:
                continue
            list_type = edge.metadata.get("list_type")
            if list_type == "following" and edge.source_id == seed_account_id:
                following += 1
            elif list_type == "followers" and edge.target_id == seed_account_id:
                followers += 1
        return {
            "following": following,
            "followers": followers,
            "total": following + followers,
        }

    def is_seed_profile_complete(self, seed_account_id: str) -> bool:
        override = self.profile_complete_overrides.get(seed_account_id)
        if override is not None:
            return override
        return False

    def get_last_scrape_metrics(self, seed_account_id: str) -> Optional[ScrapeRunMetrics]:
        if seed_account_id in self.last_scrape_overrides:
            return self.last_scrape_overrides[seed_account_id]
        return self.last_scrape_by_seed.get(seed_account_id)

    def get_all_recent_scrape_metrics(self) -> List[ScrapeRunMetrics]:
        return list(self.metrics)

    def get_recent_scrape_runs(self, days: int) -> List[ScrapeRunMetrics]:
        _ = days
        return list(self.metrics)

    def get_shadow_account(self, account_id: str) -> Optional[ShadowAccount]:
        return self.accounts.get(account_id)

    def get_account_id_by_username(self, username: str) -> Optional[str]:
        return self.account_id_by_username.get(username)

    def upsert_accounts(self, accounts: Sequence[ShadowAccount]) -> int:
        total = 0
        for account in accounts:
            total += 1
            self.accounts[account.account_id] = account
            if account.username:
                self.account_id_by_username[account.username] = account.account_id
        return total

    def upsert_edges(self, edges: Sequence[ShadowEdge]) -> int:
        count = 0
        for edge in edges:
            count += 1
            self.edges.append(edge)
        return count

    def upsert_discoveries(self, discoveries: Sequence[ShadowDiscovery]) -> int:
        count = 0
        for discovery in discoveries:
            count += 1
            self.discoveries.append(discovery)
        return count

    def record_scrape_metrics(self, metrics: ScrapeRunMetrics) -> int:
        self.metrics.append(metrics)
        self.last_scrape_by_seed[metrics.seed_account_id] = metrics
        return 1

    def get_shadow_list(self, list_id: str) -> Optional[ShadowList]:
        return self.lists.get(list_id)

    def upsert_lists(self, lists: Sequence[ShadowList]) -> int:
        count = 0
        for entry in lists:
            count += 1
            self.lists[entry.list_id] = entry
        return count

    def replace_list_members(self, list_id: str, members: Sequence[ShadowListMember]) -> None:
        self.list_members[list_id] = list(members)

    def get_shadow_list_members(self, list_id: str) -> List[ShadowListMember]:
        return list(self.list_members.get(list_id, []))

    def fetch_accounts(self, account_ids: Sequence[str]) -> List[ShadowAccount]:
        return [self.accounts[account_id] for account_id in account_ids if account_id in self.accounts]

    def unresolved_accounts(self) -> List[ShadowAccount]:
        return []
