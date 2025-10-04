"""Persistence helpers for shadow (non-archive) account and edge data."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.sqlite import insert


@dataclass(frozen=True)
class ShadowAccount:
    """Represents metadata gathered from enrichment pipelines."""

    account_id: str
    username: Optional[str]
    display_name: Optional[str]
    bio: Optional[str]
    location: Optional[str]
    followers_count: Optional[int]
    following_count: Optional[int]
    source_channel: str
    fetched_at: datetime
    checked_at: Optional[datetime] = None
    scrape_stats: Optional[dict] = None


@dataclass(frozen=True)
class ShadowEdge:
    """Directed edge discovered during enrichment."""

    source_id: str
    target_id: str
    direction: str
    source_channel: str
    fetched_at: datetime
    checked_at: Optional[datetime] = None
    weight: Optional[float] = None
    metadata: Optional[dict] = None


@dataclass(frozen=True)
class ShadowDiscovery:
    """Tracks which seed led to discovering a shadow account."""

    shadow_account_id: str
    seed_account_id: str
    discovered_at: datetime
    discovery_method: str  # 'following', 'followers', 'followers_you_follow'


@dataclass(frozen=True)
class ScrapeRunMetrics:
    """Metrics for a single seed enrichment run."""

    seed_account_id: str
    seed_username: str
    run_at: datetime
    duration_seconds: float
    following_captured: int
    followers_captured: int
    followers_you_follow_captured: int
    following_claimed_total: Optional[int]
    followers_claimed_total: Optional[int]
    followers_you_follow_claimed_total: Optional[int]
    following_coverage: Optional[float]
    followers_coverage: Optional[float]
    followers_you_follow_coverage: Optional[float]
    accounts_upserted: int
    edges_upserted: int
    discoveries_upserted: int
    skipped: bool = False
    skip_reason: Optional[str] = None


class ShadowStore:
    """Typed wrapper around the analyzer cache for shadow data."""

    ACCOUNT_TABLE = "shadow_account"
    EDGE_TABLE = "shadow_edge"
    DISCOVERY_TABLE = "shadow_discovery"
    METRICS_TABLE = "scrape_run_metrics"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._metadata = MetaData()
        self._account_table = Table(
            self.ACCOUNT_TABLE,
            self._metadata,
            Column("account_id", String, primary_key=True),
            Column("username", String, nullable=True),
            Column("display_name", String, nullable=True),
            Column("bio", String, nullable=True),
            Column("location", String, nullable=True),
            Column("followers_count", Integer, nullable=True),
            Column("following_count", Integer, nullable=True),
            Column("source_channel", String, nullable=False),
            Column("fetched_at", DateTime(timezone=False), nullable=False),
            Column("checked_at", DateTime(timezone=False), nullable=True),
            Column("scrape_stats", JSON, nullable=True),
            Column("is_shadow", Boolean, nullable=False, default=True),
        )
        self._edge_table = Table(
            self.EDGE_TABLE,
            self._metadata,
            Column("source_id", String, nullable=False),
            Column("target_id", String, nullable=False),
            Column("direction", String, nullable=False),
            Column("source_channel", String, nullable=False),
            Column("fetched_at", DateTime(timezone=False), nullable=False),
            Column("checked_at", DateTime(timezone=False), nullable=True),
            Column("weight", Integer, nullable=True),
            Column("metadata", JSON, nullable=True),
            PrimaryKeyConstraint("source_id", "target_id", "direction", name="pk_shadow_edge"),
        )
        self._discovery_table = Table(
            self.DISCOVERY_TABLE,
            self._metadata,
            Column("shadow_account_id", String, nullable=False),
            Column("seed_account_id", String, nullable=False),
            Column("discovered_at", DateTime(timezone=False), nullable=False),
            Column("discovery_method", String, nullable=False),
            PrimaryKeyConstraint("shadow_account_id", "seed_account_id", name="pk_shadow_discovery"),
        )
        self._metrics_table = Table(
            self.METRICS_TABLE,
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("seed_account_id", String, nullable=False),
            Column("seed_username", String, nullable=False),
            Column("run_at", DateTime(timezone=False), nullable=False),
            Column("duration_seconds", Integer, nullable=False),
            Column("following_captured", Integer, nullable=False),
            Column("followers_captured", Integer, nullable=False),
            Column("followers_you_follow_captured", Integer, nullable=False),
            Column("following_claimed_total", Integer, nullable=True),
            Column("followers_claimed_total", Integer, nullable=True),
            Column("followers_you_follow_claimed_total", Integer, nullable=True),
            Column("following_coverage", Integer, nullable=True),  # Store as percentage * 10000 for precision
            Column("followers_coverage", Integer, nullable=True),
            Column("followers_you_follow_coverage", Integer, nullable=True),
            Column("accounts_upserted", Integer, nullable=False),
            Column("edges_upserted", Integer, nullable=False),
            Column("discoveries_upserted", Integer, nullable=False),
            Column("skipped", Boolean, nullable=False, default=False),
            Column("skip_reason", String, nullable=True),
        )
        self._metadata.create_all(self._engine)

    # ------------------------------------------------------------------
    # Account operations
    # ------------------------------------------------------------------
    def upsert_accounts(self, accounts: Sequence[ShadowAccount]) -> int:
        if not accounts:
            return 0
        rows = []
        for account in accounts:
            rows.append(
                {
                    "account_id": account.account_id,
                    "username": account.username,
                    "display_name": account.display_name,
                    "bio": account.bio,
                    "location": account.location,
                    "followers_count": account.followers_count,
                    "following_count": account.following_count,
                    "source_channel": account.source_channel,
                    "fetched_at": account.fetched_at,
                    "checked_at": account.checked_at,
                    "scrape_stats": account.scrape_stats,
                    "is_shadow": True,
                }
            )

        with self._engine.begin() as conn:
            stmt = insert(self._account_table).values(rows)
            # Smart upsert: only update fields with new non-null values (preserve existing data)
            # COALESCE(new_value, existing_value) = use new if not null, else keep existing
            update_cols = {
                col: func.coalesce(stmt.excluded[col], self._account_table.c[col])
                for col in rows[0].keys()
                if col != "account_id"
            }
            conn.execute(stmt.on_conflict_do_update(index_elements=[self._account_table.c.account_id], set_=update_cols))
        return len(rows)

    def fetch_accounts(self, account_ids: Optional[Iterable[str]] = None) -> List[dict]:
        with self._engine.connect() as conn:
            if account_ids is None:
                stmt = select(self._account_table)
            else:
                stmt = select(self._account_table).where(
                    self._account_table.c.account_id.in_(list(account_ids))
                )
            result = conn.execute(stmt)
            rows = [dict(row._mapping) for row in result]
        for row in rows:
            if isinstance(row.get("scrape_stats"), str):
                try:
                    row["scrape_stats"] = json.loads(row["scrape_stats"])
                except json.JSONDecodeError:
                    row["scrape_stats"] = None
        return rows

    def unresolved_accounts(self, account_ids: Iterable[str]) -> List[str]:
        ids = list(set(account_ids))
        if not ids:
            return []
        with self._engine.connect() as conn:
            stmt = select(self._account_table.c.account_id).where(self._account_table.c.account_id.in_(ids))
            resolved = {row.account_id for row in conn.execute(stmt)}
        return [account_id for account_id in ids if account_id not in resolved]

    def is_seed_profile_complete(self, account_id: str) -> bool:
        """Check if a seed account already has complete profile data (location, website, joined_date)."""
        with self._engine.connect() as conn:
            stmt = select(
                self._account_table.c.location,
                self._account_table.c.scrape_stats,
            ).where(self._account_table.c.account_id == account_id)
            result = conn.execute(stmt).fetchone()
            if not result:
                return False
            location, scrape_stats = result
            # Check if we have location AND (website or joined_date in scrape_stats)
            if location and scrape_stats:
                stats = scrape_stats if isinstance(scrape_stats, dict) else json.loads(scrape_stats)
                has_website = stats.get("website") is not None
                has_joined = stats.get("joined_date") is not None
                return has_website or has_joined
            return False

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------
    def upsert_edges(self, edges: Sequence[ShadowEdge]) -> int:
        if not edges:
            return 0
        rows = []
        for edge in edges:
            rows.append(
                {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "direction": edge.direction,
                    "source_channel": edge.source_channel,
                    "fetched_at": edge.fetched_at,
                    "checked_at": edge.checked_at,
                    "weight": edge.weight,
                    "metadata": edge.metadata,
                }
            )

        with self._engine.begin() as conn:
            stmt = insert(self._edge_table).values(rows)
            update_cols = {col: stmt.excluded[col] for col in rows[0].keys() if col not in {"source_id", "target_id", "direction"}}
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[
                        self._edge_table.c.source_id,
                        self._edge_table.c.target_id,
                        self._edge_table.c.direction,
                    ],
                    set_=update_cols,
                )
            )
        return len(rows)

    def fetch_edges(self, *, direction: Optional[str] = None) -> List[dict]:
        with self._engine.connect() as conn:
            stmt = select(self._edge_table)
            if direction:
                stmt = stmt.where(self._edge_table.c.direction == direction)
            result = conn.execute(stmt)
            rows = [dict(row._mapping) for row in result]
        for row in rows:
            metadata = row.get("metadata")
            if isinstance(metadata, str):
                try:
                    row["metadata"] = json.loads(metadata)
                except json.JSONDecodeError:
                    pass
        return rows

    def edge_summary_for_seed(self, account_id: str) -> Dict[str, int]:
        with self._engine.connect() as conn:
            stmt = select(self._edge_table).where(
                (self._edge_table.c.source_id == account_id)
                | (self._edge_table.c.target_id == account_id)
            )
            result = conn.execute(stmt)
            rows = [dict(row._mapping) for row in result]
        summary = {"following": 0, "followers": 0, "total": len(rows)}
        for row in rows:
            metadata = row.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = None
            list_type = (metadata or {}).get("list_type")
            if list_type == "following" and row["source_id"] == account_id:
                summary["following"] += 1
            elif list_type == "followers" and row["target_id"] == account_id:
                summary["followers"] += 1
        return summary

    # ------------------------------------------------------------------
    # Discovery operations
    # ------------------------------------------------------------------
    def upsert_discoveries(self, discoveries: Sequence[ShadowDiscovery]) -> int:
        if not discoveries:
            return 0
        rows = []
        for discovery in discoveries:
            rows.append(
                {
                    "shadow_account_id": discovery.shadow_account_id,
                    "seed_account_id": discovery.seed_account_id,
                    "discovered_at": discovery.discovered_at,
                    "discovery_method": discovery.discovery_method,
                }
            )

        with self._engine.begin() as conn:
            stmt = insert(self._discovery_table).values(rows)
            update_cols = {
                col: stmt.excluded[col]
                for col in rows[0].keys()
                if col not in {"shadow_account_id", "seed_account_id"}
            }
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[
                        self._discovery_table.c.shadow_account_id,
                        self._discovery_table.c.seed_account_id,
                    ],
                    set_=update_cols,
                )
            )
        return len(rows)

    def fetch_discoveries(
        self, *, shadow_account_id: Optional[str] = None, seed_account_id: Optional[str] = None
    ) -> List[dict]:
        with self._engine.connect() as conn:
            stmt = select(self._discovery_table)
            if shadow_account_id:
                stmt = stmt.where(self._discovery_table.c.shadow_account_id == shadow_account_id)
            if seed_account_id:
                stmt = stmt.where(self._discovery_table.c.seed_account_id == seed_account_id)
            result = conn.execute(stmt)
            return [dict(row._mapping) for row in result]

    # ------------------------------------------------------------------
    # Metrics operations
    # ------------------------------------------------------------------
    def record_scrape_metrics(self, metrics: ScrapeRunMetrics) -> int:
        """Record metrics for a single scrape run."""
        row = {
            "seed_account_id": metrics.seed_account_id,
            "seed_username": metrics.seed_username,
            "run_at": metrics.run_at,
            "duration_seconds": int(metrics.duration_seconds),
            "following_captured": metrics.following_captured,
            "followers_captured": metrics.followers_captured,
            "followers_you_follow_captured": metrics.followers_you_follow_captured,
            "following_claimed_total": metrics.following_claimed_total,
            "followers_claimed_total": metrics.followers_claimed_total,
            "followers_you_follow_claimed_total": metrics.followers_you_follow_claimed_total,
            "following_coverage": int(metrics.following_coverage * 10000) if metrics.following_coverage else None,
            "followers_coverage": int(metrics.followers_coverage * 10000) if metrics.followers_coverage else None,
            "followers_you_follow_coverage": int(metrics.followers_you_follow_coverage * 10000) if metrics.followers_you_follow_coverage else None,
            "accounts_upserted": metrics.accounts_upserted,
            "edges_upserted": metrics.edges_upserted,
            "discoveries_upserted": metrics.discoveries_upserted,
            "skipped": metrics.skipped,
            "skip_reason": metrics.skip_reason,
        }
        with self._engine.begin() as conn:
            result = conn.execute(insert(self._metrics_table).values(row))
            return result.lastrowid


def get_shadow_store(engine: Engine) -> ShadowStore:
    """Helper for one-line store construction."""

    return ShadowStore(engine)
