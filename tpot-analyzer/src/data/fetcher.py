"""Cached data access layer for the Community Archive Supabase REST API."""
from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import httpx
import pandas as pd
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.config import CacheSettings, SupabaseConfig, get_cache_settings, get_supabase_config

logger = logging.getLogger(__name__)


class CachedDataFetcher(AbstractContextManager["CachedDataFetcher"]):
    """Fetch Community Archive data using Supabase REST endpoints with local caching."""

    _METADATA_TABLE_NAME = "cache_metadata"
    _DEFAULT_PARAMS = {"select": "*"}

    def __init__(
        self,
        cache_db: Optional[Path | str] = None,
        *,
        max_age_days: Optional[int] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._cache_settings: CacheSettings = get_cache_settings()
        cache_path = Path(cache_db or self._cache_settings.path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path = cache_path
        self.max_age_days = max_age_days if max_age_days is not None else self._cache_settings.max_age_days

        self._supabase: Optional[SupabaseConfig] = None
        self._owns_client = http_client is None
        self._http_client: Optional[httpx.Client] = http_client

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
    # Context manager / lifecycle
    # ------------------------------------------------------------------
    def __enter__(self) -> "CachedDataFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None
        # Always dispose SQLAlchemy engine/pool so SQLite file descriptors are released.
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_profiles(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return a dataframe of account profiles."""

        return self._fetch_dataset(
            table_name="profile",
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_accounts(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return account-level metadata (followers, tweets, etc.)."""

        return self._fetch_dataset(
            table_name="account",
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_followers(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return follower edges (follower -> account)."""

        return self._fetch_dataset(
            table_name="followers",
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_following(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return following edges (account -> following_account)."""

        return self._fetch_dataset(
            table_name="following",
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_archive_following(self) -> pd.DataFrame:
        """Return archive following edges from local staging table.

        Note: This reads from archive_following table which is populated
        from blob storage imports, not from Supabase REST API.
        """
        try:
            df = pd.read_sql_table("archive_following", self.engine)
        except ValueError:
            # Table doesn't exist or is empty
            return pd.DataFrame(columns=["account_id", "following_account_id", "uploaded_at", "imported_at"])
        return df

    def fetch_archive_followers(self) -> pd.DataFrame:
        """Return archive follower edges from local staging table.

        Note: This reads from archive_followers table which is populated
        from blob storage imports, not from Supabase REST API.
        """
        try:
            df = pd.read_sql_table("archive_followers", self.engine)
        except ValueError:
            # Table doesn't exist or is empty
            return pd.DataFrame(columns=["account_id", "follower_account_id", "uploaded_at", "imported_at"])
        return df

    def fetch_tweets(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return a dataframe of tweets."""

        return self._fetch_dataset(
            table_name="tweets",
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_likes(self, *, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
        """Return a dataframe of like interactions."""

        return self._fetch_dataset(
            table_name="likes",
            use_cache=use_cache,
            force_refresh=force_refresh,
        )

    def fetch_table(
        self,
        table_name: str,
        *,
        use_cache: bool = True,
        force_refresh: bool = False,
        params: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """Generic entrypoint for fetching any REST table."""

        return self._fetch_dataset(
            table_name=table_name,
            use_cache=use_cache,
            force_refresh=force_refresh,
            params=params,
        )

    def cache_status(self) -> Dict[str, Dict[str, object]]:
        """Return metadata about cached tables for reporting."""

        with self.engine.connect() as conn:
            rows = conn.execute(select(self._meta_table)).fetchall()
        status: Dict[str, Dict[str, object]] = {}
        now = datetime.now(timezone.utc)
        for row in rows:
            fetched_at = row.fetched_at
            if isinstance(fetched_at, str):
                fetched_at = datetime.fromisoformat(fetched_at)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            status[row.table_name] = {
                "fetched_at": fetched_at,
                "age_days": (now - fetched_at).total_seconds() / 86400,
                "row_count": row.row_count,
            }
        return status

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _fetch_dataset(
        self,
        *,
        table_name: str,
        use_cache: bool,
        force_refresh: bool,
        params: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        logger.debug(
            "Fetching dataset '%s' (use_cache=%s, force_refresh=%s)",
            table_name,
            use_cache,
            force_refresh,
        )

        cached: Optional[pd.DataFrame] = None
        cache_age_days: Optional[float] = None
        cache_expired = False

        if use_cache and not force_refresh:
            cached = self._read_cache(table_name)
            if cached is not None:
                cache_expired = self._is_cache_expired(table_name)
                cache_age_days = self._get_cache_age_days(table_name)
                if cache_expired:
                    logger.warning(
                        "Cache for %s is stale (age=%.2f days, max_age_days=%d); attempting Supabase refresh.",
                        table_name,
                        cache_age_days if cache_age_days is not None else -1.0,
                        self.max_age_days,
                    )
                else:
                    logger.info("Using cached data for %s (rows=%d)", table_name, len(cached))
                    return cached

        try:
            fresh = self._fetch_from_supabase(table_name=table_name, params=params)
        except Exception as exc:
            if cached is not None and use_cache and not force_refresh:
                logger.error(
                    "Supabase refresh failed for %s; returning STALE cache instead (rows=%d, age_days=%.2f, max_age_days=%d). Error: %s",
                    table_name,
                    len(cached),
                    cache_age_days if cache_age_days is not None else -1.0,
                    self.max_age_days,
                    exc,
                )
                return cached
            raise

        self._write_cache(table_name, fresh)
        return fresh

    def _fetch_from_supabase(
        self,
        *,
        table_name: str,
        params: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        logger.info("Querying Supabase REST endpoint for table %s", table_name)
        client = self._ensure_http_client()

        try:
            response = client.get(
                f"/rest/v1/{table_name}",
                params=params or self._DEFAULT_PARAMS,
                headers={"Range": "0-999999"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Supabase REST query for %s failed: %s", table_name, exc)
            raise RuntimeError(f"Supabase REST query for '{table_name}' failed: {exc}") from exc

        data = response.json()
        if not isinstance(data, list):
            logger.error("Supabase returned unexpected payload for table %s", table_name)
            raise RuntimeError(f"Supabase returned unexpected payload for '{table_name}'")

        df = pd.DataFrame(data)
        logger.info("Fetched %d rows from Supabase table %s", len(df), table_name)
        return df

    def _ensure_http_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client

        self._supabase = get_supabase_config()
        self._http_client = httpx.Client(
            base_url=self._supabase.url,
            headers=self._supabase.rest_headers,
            timeout=30.0,
        )
        return self._http_client

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

    def _get_cache_age_days(self, table_name: str) -> Optional[float]:
        with self.engine.connect() as conn:
            result = conn.execute(
                select(self._meta_table.c.fetched_at).where(self._meta_table.c.table_name == table_name)
            ).fetchone()
        if result is None:
            return None
        fetched_at = result[0]
        if isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - fetched_at
        return age.total_seconds() / 86400
