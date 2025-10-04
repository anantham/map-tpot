"""Cached data access layer for the Community Archive Supabase API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.config import CacheSettings, get_cache_settings, get_supabase_client

logger = logging.getLogger(__name__)


SupabaseQuery = Callable[[object], object]


class CachedDataFetcher:
    """Fetch Community Archive data with a cache-aware Supabase adapter.

    Parameters
    ----------
    cache_db : str | Path, optional
        Location of the SQLite cache. Defaults to the value derived from
        :func:`src.config.get_cache_settings`.
    max_age_days : int, optional
        Number of days before cached data is considered stale. Defaults to the
        configured cache setting.
    client : supabase.Client, optional
        Injected Supabase client, primarily for testing.
    """

    _METADATA_TABLE_NAME = "cache_metadata"

    def __init__(
        self,
        cache_db: Optional[Path | str] = None,
        *,
        max_age_days: Optional[int] = None,
        client: Optional[object] = None,
    ) -> None:
        self._cache_settings: CacheSettings = get_cache_settings()
        cache_path = Path(cache_db or self._cache_settings.path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path = cache_path
        self.max_age_days = max_age_days if max_age_days is not None else self._cache_settings.max_age_days
        self.client = client or get_supabase_client()
        self.engine: Engine = create_engine(f"sqlite:///{self.cache_path}", future=True)
        self._metadata = MetaData()
        self._meta_table = Table(
            self._METADATA_TABLE_NAME,
            self._metadata,
            Column("table_name", String, primary_key=True),
            Column("fetched_at", DateTime(timezone=False), nullable=False),
            Column("row_count", Integer, nullable=False),
        )
        self._metadata.create_all(self.engine)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_profiles(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return profiles dataframe.

        Columns (subject to upstream schema) include: account_id, username,
        account_display_name, followers_count, friends_count, created_at, etc.
        """

        return self._fetch_dataset(
            table_name="profiles",
            query=lambda c: c.table("profiles").select("*").execute(),
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_tweets(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return tweets dataframe with raw tweet metadata."""

        return self._fetch_dataset(
            table_name="tweets",
            query=lambda c: c.table("tweets").select("*").execute(),
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_likes(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return likes dataframe capturing user ↔ tweet interactions."""

        return self._fetch_dataset(
            table_name="likes",
            query=lambda c: c.table("likes").select("*").execute(),
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _fetch_dataset(
        self,
        *,
        table_name: str,
        query: SupabaseQuery,
        use_cache: bool,
        force_refresh: bool,
    ) -> pd.DataFrame:
        logger.debug("Fetching dataset '%s' (use_cache=%s, force_refresh=%s)", table_name, use_cache, force_refresh)

        if use_cache and not force_refresh:
            cached = self._read_cache(table_name)
            if cached is not None:
                if self._is_cache_expired(table_name):
                    logger.warning(
                        "Cache for %s is older than %d day(s); refreshing from Supabase.",
                        table_name,
                        self.max_age_days,
                    )
                else:
                    logger.info("Using cached data for %s (rows=%d)", table_name, len(cached))
                    return cached

        fresh = self._fetch_from_supabase(table_name=table_name, query=query)
        self._write_cache(table_name, fresh)
        return fresh

    def _fetch_from_supabase(self, *, table_name: str, query: SupabaseQuery) -> pd.DataFrame:
        logger.info("Querying Supabase for table %s", table_name)
        try:
            response = query(self.client)
        except Exception as exc:  # pragma: no cover - transports may raise various errors
            logger.error("Supabase query for %s failed: %s", table_name, exc)
            raise RuntimeError(f"Supabase query for '{table_name}' failed: {exc}") from exc

        # Supabase-py responses expose .error and .data; fall back to dict assumptions.
        error = getattr(response, "error", None)
        if error:
            logger.error("Supabase returned error for %s: %s", table_name, error)
            raise RuntimeError(f"Supabase returned an error for '{table_name}': {error}")

        data = getattr(response, "data", response)
        if data is None:
            logger.error("Supabase returned no data for table %s", table_name)
            raise RuntimeError(f"Supabase returned no data for '{table_name}'")

        df = pd.DataFrame(data)
        logger.info("Fetched %d rows from Supabase table %s", len(df), table_name)
        return df

    def _read_cache(self, table_name: str) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_sql_table(table_name, self.engine)
        except ValueError:
            return None
        except SQLAlchemyError as exc:  # pragma: no cover - environment-specific errors
            logger.error("Failed reading cache table %s: %s", table_name, exc)
            raise RuntimeError(f"Failed reading cache table '{table_name}': {exc}") from exc
        return df

    def _write_cache(self, table_name: str, df: pd.DataFrame) -> None:
        logger.info("Writing %d rows to cache table %s", len(df), table_name)
        try:
            df.to_sql(table_name, self.engine, if_exists="replace", index=False)
        except SQLAlchemyError as exc:
            logger.error("Failed writing cache table %s: %s", table_name, exc)
            raise RuntimeError(f"Failed writing cache table '{table_name}': {exc}") from exc

        fetched_at = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                self._meta_table.delete().where(self._meta_table.c.table_name == table_name)
            )
            conn.execute(
                self._meta_table.insert().values(
                    table_name=table_name,
                    fetched_at=fetched_at,
                    row_count=len(df),
                )
            )

    def _is_cache_expired(self, table_name: str) -> bool:
        with self.engine.connect() as conn:
            result = conn.execute(
                select(self._meta_table.c.fetched_at).where(self._meta_table.c.table_name == table_name)
            ).fetchone()
        if result is None:
            return True
        fetched_at = result[0]
        if isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - fetched_at
        return age > timedelta(days=self.max_age_days)

    # Exposed for verification tooling
    def cache_status(self) -> Dict[str, Dict[str, object]]:
        """Return metadata about cached tables for reporting."""

        with self.engine.connect() as conn:
            rows = conn.execute(select(self._meta_table)).fetchall()
        status: Dict[str, Dict[str, object]] = {}
        for row in rows:
            fetched_at = row.fetched_at
            if isinstance(fetched_at, str):
                fetched_at = datetime.fromisoformat(fetched_at)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            status[row.table_name] = {
                "fetched_at": fetched_at,
                "age_days": (datetime.now(timezone.utc) - fetched_at).total_seconds() / 86400,
                "row_count": row.row_count,
            }
        return status
