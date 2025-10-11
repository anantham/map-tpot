"""Persistence helpers for shadow (non-archive) account and edge data."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence, TypeVar

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
    tuple_,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.sqlite import insert


LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class ShadowAccount:
    """Represents metadata gathered from enrichment pipelines."""

    account_id: str
    username: Optional[str]
    display_name: Optional[str]
    bio: Optional[str]
    location: Optional[str]
    website: Optional[str]
    profile_image_url: Optional[str]
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
    error_type: Optional[str] = None  # "404", "timeout", "rate_limit", "private", "suspended"
    error_details: Optional[str] = None


class ShadowStore:
    """Typed wrapper around the analyzer cache for shadow data."""

    ACCOUNT_TABLE = "shadow_account"
    EDGE_TABLE = "shadow_edge"
    DISCOVERY_TABLE = "shadow_discovery"
    METRICS_TABLE = "scrape_run_metrics"
    _RETRYABLE_SQLITE_ERRORS = ("disk i/o error", "database is locked")

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
            Column("website", String, nullable=True),
            Column("profile_image_url", String, nullable=True),
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
            Column("error_type", String, nullable=True),
            Column("error_details", String, nullable=True),
        )
        self._metadata.create_all(self._engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _execute_with_retry(
        self,
        op_name: str,
        fn: Callable[[Engine], T],
        *,
        max_attempts: int = 3,
        base_delay_seconds: float = 1.0,
    ) -> T:
        last_exc: Optional[OperationalError] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn(self._engine)
            except OperationalError as exc:
                message = ""
                if getattr(exc, "orig", None) is not None:
                    message = str(exc.orig).lower()
                else:
                    message = str(exc).lower()

                if not any(token in message for token in self._RETRYABLE_SQLITE_ERRORS):
                    raise

                last_exc = exc
                LOGGER.error(
                    "Retryable SQLite error during %s (attempt %s/%s): %s",
                    op_name,
                    attempt,
                    max_attempts,
                    message or exc,
                )
                self._engine.dispose()

                if attempt == max_attempts:
                    break

                sleep_for = base_delay_seconds * (2 ** (attempt - 1))
                time.sleep(sleep_for)

        assert last_exc is not None
        LOGGER.error(
            "Exhausted retries for %s after %s attempts; re-raising.",
            op_name,
            max_attempts,
        )
        raise last_exc

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
                    "website": account.website,
                    "profile_image_url": account.profile_image_url,
                    "followers_count": account.followers_count,
                    "following_count": account.following_count,
                    "source_channel": account.source_channel,
                    "fetched_at": account.fetched_at,
                    "checked_at": account.checked_at,
                    "scrape_stats": account.scrape_stats,
                    "is_shadow": True,
                }
            )

        def _op(engine: Engine) -> int:
            with engine.begin() as conn:
                prepared_rows = [self._prepare_account_row(conn, row) for row in rows]
                if not prepared_rows:
                    return 0

                stmt = insert(self._account_table).values(prepared_rows)
                update_cols = {
                    col: func.coalesce(stmt.excluded[col], self._account_table.c[col])
                    for col in prepared_rows[0].keys()
                    if col != "account_id"
                }
                conn.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[self._account_table.c.account_id],
                        set_=update_cols,
                    )
                )
            return len(prepared_rows)

        return self._execute_with_retry("upsert_accounts", _op)

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
                self._account_table.c.website,
                self._account_table.c.profile_image_url,
                self._account_table.c.followers_count,
                self._account_table.c.following_count,
                self._account_table.c.scrape_stats,
            ).where(self._account_table.c.account_id == account_id)
            result = conn.execute(stmt).fetchone()
        if not result:
            return False
        location, website, avatar_url, followers_count, following_count, scrape_stats = result

        has_location = bool(location)
        has_website = bool(website)
        has_avatar = bool(avatar_url)
        has_counts = bool((followers_count or 0) > 0 and (following_count or 0) > 0)

        has_joined = False
        if scrape_stats:
            try:
                stats = scrape_stats if isinstance(scrape_stats, dict) else json.loads(scrape_stats)
                has_website = has_website or bool(stats.get("website"))
                has_joined = bool(stats.get("joined_date"))
            except (TypeError, json.JSONDecodeError):
                pass

        return has_location and (has_website or has_joined) and has_avatar and has_counts

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------
    def upsert_edges(self, edges: Sequence[ShadowEdge]) -> int:
        if not edges:
            return 0
        rows = []
        edge_keys = []  # Track keys for existence check
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
            edge_keys.append((edge.source_id, edge.target_id, edge.direction))

        # Check which edges already exist in the database
        # This allows us to accurately count new vs duplicate edges
        existing_count = 0
        with self._engine.connect() as conn:
            # Use tuple_ IN query for efficient batch check
            existing_result = conn.execute(
                select(func.count()).select_from(self._edge_table).where(
                    tuple_(
                        self._edge_table.c.source_id,
                        self._edge_table.c.target_id,
                        self._edge_table.c.direction,
                    ).in_(edge_keys)
                )
            )
            existing_count = existing_result.scalar() or 0

        new_count = len(rows) - existing_count

        def _op(engine: Engine) -> int:
            with engine.begin() as conn:
                stmt = insert(self._edge_table).values(rows)
                update_cols = {
                    col: stmt.excluded[col]
                    for col in rows[0].keys()
                    if col not in {"source_id", "target_id", "direction"}
                }
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
            return new_count  # Return actual new edges, not total attempted

        return self._execute_with_retry("upsert_edges", _op)

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

        def _op(engine: Engine) -> int:
            with engine.begin() as conn:
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

        return self._execute_with_retry("upsert_discoveries", _op)

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
    def get_recent_scrape_runs(self, days: int = 7) -> List[ScrapeRunMetrics]:
        """Get all scrape runs from the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of ScrapeRunMetrics ordered by run_at descending
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        with self._engine.begin() as conn:
            stmt = (
                select(self._metrics_table)
                .where(self._metrics_table.c.run_at >= cutoff)
                .order_by(self._metrics_table.c.run_at.desc())
            )
            result = conn.execute(stmt)
            metrics = []
            for row in result:
                metrics.append(ScrapeRunMetrics(
                    seed_account_id=row.seed_account_id,
                    seed_username=row.seed_username,
                    run_at=row.run_at,
                    duration_seconds=row.duration_seconds,
                    following_captured=row.following_captured,
                    followers_captured=row.followers_captured,
                    followers_you_follow_captured=row.followers_you_follow_captured,
                    following_claimed_total=row.following_claimed_total,
                    followers_claimed_total=row.followers_claimed_total,
                    followers_you_follow_claimed_total=row.followers_you_follow_claimed_total,
                    following_coverage=(
                        row.following_coverage / 10000.0
                        if row.following_coverage is not None
                        else None
                    ),
                    followers_coverage=(
                        row.followers_coverage / 10000.0
                        if row.followers_coverage is not None
                        else None
                    ),
                    followers_you_follow_coverage=(
                        row.followers_you_follow_coverage / 10000.0
                        if row.followers_you_follow_coverage is not None
                        else None
                    ),
                    accounts_upserted=row.accounts_upserted,
                    edges_upserted=row.edges_upserted,
                    discoveries_upserted=row.discoveries_upserted,
                    skipped=row.skipped,
                    skip_reason=row.skip_reason,
                    error_type=row.error_type,
                    error_details=row.error_details,
                ))
            return metrics

    def get_last_scrape_metrics(self, seed_account_id: str) -> Optional[ScrapeRunMetrics]:
        """Get the most recent scrape metrics for a seed account.

        Returns None if no scrape has been recorded for this seed.
        """
        with self._engine.begin() as conn:
            stmt = (
                select(self._metrics_table)
                .where(self._metrics_table.c.seed_account_id == seed_account_id)
                .where(self._metrics_table.c.skipped == False)
                .order_by(self._metrics_table.c.run_at.desc())
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            if not row:
                return None

            return ScrapeRunMetrics(
                seed_account_id=row.seed_account_id,
                seed_username=row.seed_username,
                run_at=row.run_at,
                duration_seconds=row.duration_seconds,
                following_captured=row.following_captured,
                followers_captured=row.followers_captured,
                followers_you_follow_captured=row.followers_you_follow_captured,
                following_claimed_total=row.following_claimed_total,
                followers_claimed_total=row.followers_claimed_total,
                followers_you_follow_claimed_total=row.followers_you_follow_claimed_total,
                following_coverage=(
                    row.following_coverage / 10000.0
                    if row.following_coverage is not None
                    else None
                ),
                followers_coverage=(
                    row.followers_coverage / 10000.0
                    if row.followers_coverage is not None
                    else None
                ),
                followers_you_follow_coverage=(
                    row.followers_you_follow_coverage / 10000.0
                    if row.followers_you_follow_coverage is not None
                    else None
                ),
                accounts_upserted=row.accounts_upserted,
                edges_upserted=row.edges_upserted,
                discoveries_upserted=row.discoveries_upserted,
                skipped=row.skipped,
                skip_reason=row.skip_reason,
                error_type=row.error_type,
                error_details=row.error_details,
            )

    def get_account_id_by_username(self, username: str) -> Optional[str]:
        """Find an account ID for a given username."""
        with self._engine.connect() as conn:
            stmt = select(self._account_table.c.account_id).where(
                func.lower(self._account_table.c.username) == username.lower()
            ).limit(1)
            result = conn.execute(stmt).fetchone()
            return result.account_id if result else None

    def get_following_usernames(self, username: str) -> List[str]:
        """Get the usernames of accounts followed by a given username from the cache."""
        account_id = self.get_account_id_by_username(username)
        if not account_id:
            return []

        with self._engine.connect() as conn:
            j = self._edge_table.join(
                self._account_table,
                self._edge_table.c.target_id == self._account_table.c.account_id
            )
            stmt = select(self._account_table.c.username).select_from(j).where(
                self._edge_table.c.source_id == account_id,
                self._edge_table.c.direction == 'outbound',
                self._account_table.c.username.isnot(None)
            )
            result = conn.execute(stmt)
            return [row.username for row in result]

    def get_shadow_account(self, account_id: str) -> Optional[ShadowAccount]:
        """Get a shadow account by account_id.

        Returns None if the account doesn't exist.
        """
        with self._engine.begin() as conn:
            stmt = (
                select(self._account_table)
                .where(self._account_table.c.account_id == account_id)
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            if not row:
                return None

            return ShadowAccount(
                account_id=row.account_id,
                username=row.username,
                display_name=row.display_name,
                bio=row.bio,
                location=row.location,
                website=row.website,
                profile_image_url=row.profile_image_url,
                followers_count=row.followers_count,
                following_count=row.following_count,
                source_channel=row.source_channel,
                fetched_at=row.fetched_at,
                checked_at=row.checked_at,
                scrape_stats=row.scrape_stats if isinstance(row.scrape_stats, dict) else (json.loads(row.scrape_stats) if row.scrape_stats else None),
            )

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
            "following_coverage": (
                round(metrics.following_coverage * 100, 2)  # Store as percentage (0-100)
                if metrics.following_coverage is not None
                else None
            ),
            "followers_coverage": (
                round(metrics.followers_coverage * 100, 2)  # Store as percentage (0-100)
                if metrics.followers_coverage is not None
                else None
            ),
            "followers_you_follow_coverage": (
                round(metrics.followers_you_follow_coverage * 100, 2)  # Store as percentage (0-100)
                if metrics.followers_you_follow_coverage is not None
                else None
            ),
            "accounts_upserted": metrics.accounts_upserted,
            "edges_upserted": metrics.edges_upserted,
            "discoveries_upserted": metrics.discoveries_upserted,
            "skipped": metrics.skipped,
            "skip_reason": metrics.skip_reason,
            "error_type": metrics.error_type,
            "error_details": metrics.error_details,
        }
        def _op(engine: Engine) -> int:
            with engine.begin() as conn:
                result = conn.execute(insert(self._metrics_table).values(row))
                return result.lastrowid

        return self._execute_with_retry("record_scrape_metrics", _op)

    # ------------------------------------------------------------------
    # Account maintenance helpers
    # ------------------------------------------------------------------

    def _prepare_account_row(self, conn, row: dict) -> dict:
        username = (row.get("username") or "").lower()
        account_id = row.get("account_id")

        if username and account_id and not account_id.startswith("shadow:"):
            self._merge_duplicate_accounts(conn, username, account_id, row)

        if username:
            archive_table = self._archive_account_table
            archive_row = conn.execute(
                select(
                    archive_table.c.account_id,
                    archive_table.c.num_followers,
                    archive_table.c.num_following,
                    archive_table.c.account_display_name,
                )
                .where(func.lower(archive_table.c.username) == username)
            ).fetchone()
            if archive_row:
                archive = archive_row._mapping
                canonical_id = archive["account_id"] or account_id
                if canonical_id:
                    row["account_id"] = canonical_id
                if archive["account_display_name"] and not row.get("display_name"):
                    row["display_name"] = archive["account_display_name"]
                row["followers_count"] = self._max_value(
                    row.get("followers_count"), archive["num_followers"]
                )
                row["following_count"] = self._max_value(
                    row.get("following_count"), archive["num_following"]
                )

        return row

    def _merge_duplicate_accounts(
        self,
        conn,
        username: str,
        canonical_id: str,
        row: dict,
    ) -> None:
        duplicates = conn.execute(
            select(
                self._account_table.c.account_id,
                self._account_table.c.display_name,
                self._account_table.c.bio,
                self._account_table.c.location,
                self._account_table.c.website,
                self._account_table.c.profile_image_url,
                self._account_table.c.followers_count,
                self._account_table.c.following_count,
            )
            .where(self._account_table.c.username == username)
            .where(self._account_table.c.account_id != canonical_id)
        ).fetchall()

        for dup_row in duplicates:
            dup = dup_row._mapping
            old_id = dup["account_id"]
            if old_id == canonical_id:
                continue

            for field in ("display_name", "bio", "location", "website", "profile_image_url"):
                if not row.get(field) and dup[field]:
                    row[field] = dup[field]

            row["followers_count"] = self._max_value(row.get("followers_count"), dup["followers_count"])
            row["following_count"] = self._max_value(row.get("following_count"), dup["following_count"])

            self._reassign_account_id(conn, old_id, canonical_id)

    def _reassign_account_id(self, conn, old_id: str, new_id: str) -> None:
        conn.execute(
            self._edge_table.update()
            .where(self._edge_table.c.source_id == old_id)
            .values(source_id=new_id)
        )
        conn.execute(
            self._edge_table.update()
            .where(self._edge_table.c.target_id == old_id)
            .values(target_id=new_id)
        )
        conn.execute(
            self._discovery_table.update()
            .where(self._discovery_table.c.shadow_account_id == old_id)
            .values(shadow_account_id=new_id)
        )
        conn.execute(
            self._account_table.delete().where(self._account_table.c.account_id == old_id)
        )

    @staticmethod
    def _max_value(current: Optional[int], baseline: Optional[int]) -> Optional[int]:
        if current is None and baseline is None:
            return None
        if current is None:
            return baseline
        if baseline is None:
            return current
        return max(current, baseline)

    @property
    def _archive_account_table(self) -> Table:
        if not hasattr(self, "_archive_table"):
            metadata = MetaData()
            self._archive_table = Table(
                "account",
                metadata,
                Column("account_id", String, primary_key=True),
                Column("username", String),
                Column("account_display_name", String),
                Column("num_followers", Integer),
                Column("num_following", Integer),
            )
        return self._archive_table

    def sync_archive_overlaps(self) -> int:
        def _op(engine: Engine) -> int:
            with engine.begin() as conn:
                archive_table = self._archive_account_table
                rows = conn.execute(
                    select(
                        self._account_table.c.username,
                        self._account_table.c.account_id,
                        archive_table.c.account_id.label("archive_id"),
                        archive_table.c.num_followers,
                        archive_table.c.num_following,
                        archive_table.c.account_display_name,
                    )
                    .select_from(
                        self._account_table.join(
                            archive_table,
                            func.lower(self._account_table.c.username)
                            == func.lower(archive_table.c.username),
                        )
                    )
                ).fetchall()

                updated = 0
                for record_row in rows:
                    record = record_row._mapping
                    canonical_id = record["archive_id"] or record["account_id"]
                    prepared = {
                        "account_id": canonical_id,
                        "username": record["username"],
                        "display_name": record["account_display_name"],
                        "bio": None,
                        "location": None,
                        "website": None,
                        "profile_image_url": None,
                        "followers_count": record["num_followers"],
                        "following_count": record["num_following"],
                        "source_channel": "archive_sync",
                        "fetched_at": datetime.utcnow(),
                        "checked_at": datetime.utcnow(),
                        "scrape_stats": None,
                        "is_shadow": True,
                    }

                    prepared = self._prepare_account_row(conn, prepared)

                    stmt = insert(self._account_table).values(prepared)
                    update_cols = {
                        col: func.coalesce(stmt.excluded[col], self._account_table.c[col])
                        for col in prepared.keys()
                        if col != "account_id"
                    }
                    conn.execute(
                        stmt.on_conflict_do_update(
                            index_elements=[self._account_table.c.account_id],
                            set_=update_cols,
                        )
                    )
                    updated += 1

                return updated

        return self._execute_with_retry("sync_archive_overlaps", _op)


def get_shadow_store(engine: Engine) -> ShadowStore:
    """Helper for one-line store construction."""

    return ShadowStore(engine)
