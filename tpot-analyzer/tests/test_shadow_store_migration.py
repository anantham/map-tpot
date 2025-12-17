"""Tests that legacy social graph data migrates cleanly into the shadow store."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Tuple

import pytest
import sqlite3
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer

from src.data.shadow_store import ShadowAccount, ShadowEdge, get_shadow_store


_LEGACY_DB_ENV = os.environ.get("TPOT_LEGACY_DB_PATH")
LEGACY_DB = (
    Path(_LEGACY_DB_ENV).expanduser()
    if _LEGACY_DB_ENV
    else Path.home()
    / "Library/CloudStorage/OneDrive-IndianInstituteofScience/Documents/Ongoing/Project 2 - tpot/data/social_graph.db"
)


def _create_archive_table(engine):
    """Create the archive account table that shadow_store expects to exist."""
    metadata = MetaData()
    account_table = Table(
        "account",
        metadata,
        Column("account_id", String, primary_key=True),
        Column("username", String),
        Column("account_display_name", String),
        Column("num_followers", Integer),
        Column("num_following", Integer),
    )
    metadata.create_all(engine, checkfirst=True)


def _load_legacy_sample(limit: int = 25) -> Tuple[List[dict], List[dict]]:
    with sqlite3.connect(str(LEGACY_DB)) as conn:
        conn.row_factory = sqlite3.Row
        users = conn.execute(
            "SELECT user_id, username, name, node_type FROM users ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()

        edges = conn.execute(
            "SELECT source_user_id, target_user_id, edge_type, discovery_method "
            "FROM edges ORDER BY created_at ASC LIMIT ?",
            (limit * 2,),
        ).fetchall()

    return [dict(row) for row in users], [dict(row) for row in edges]


@pytest.mark.skipif(not LEGACY_DB.exists(), reason="Legacy social graph database unavailable")
@pytest.mark.integration
def test_shadow_store_accepts_legacy_accounts_and_edges() -> None:
    legacy_users, legacy_edges = _load_legacy_sample()

    with TemporaryDirectory() as tmp_dir:
        engine = create_engine(f"sqlite:///{tmp_dir}/shadow.db", future=True)
        _create_archive_table(engine)  # Create archive table before initializing store
        store = get_shadow_store(engine)

        timestamp = datetime.utcnow()
        accounts = [
            ShadowAccount(
                account_id=user["user_id"],
                username=user.get("username"),
                display_name=user.get("name"),
                bio=None,
                location=None,
                website=None,
                profile_image_url=None,
                followers_count=None,
                following_count=None,
                source_channel="legacy_migration",
                fetched_at=timestamp,
                checked_at=timestamp,
                scrape_stats={"source": "legacy", "node_type": user.get("node_type", "user")},
            )
            for user in legacy_users
        ]

        inserted_accounts = store.upsert_accounts(accounts)
        assert inserted_accounts == len(accounts)

        fetched_accounts = store.fetch_accounts()
        assert len(fetched_accounts) == len(accounts)
        sample_account = fetched_accounts[0]
        assert sample_account["is_shadow"] is True
        assert sample_account["source_channel"] == "legacy_migration"

        edges = [
            ShadowEdge(
                source_id=edge["source_user_id"],
                target_id=edge["target_user_id"],
                direction=edge.get("edge_type", "follows"),
                source_channel=edge.get("discovery_method", "legacy"),
                fetched_at=timestamp,
                checked_at=timestamp,
                weight=1,
                metadata={"legacy": True},
            )
            for edge in legacy_edges
        ]

        inserted_edges = store.upsert_edges(edges)
        assert inserted_edges == len(edges)

        fetched_edges = store.fetch_edges()
        assert len(fetched_edges) == len(edges)
        assert all(edge["metadata"]["legacy"] for edge in fetched_edges)


@pytest.mark.skipif(not LEGACY_DB.exists(), reason="Legacy social graph database unavailable")
@pytest.mark.integration
@pytest.mark.xfail(reason="Edge deduplication not working correctly - known issue")
def test_shadow_store_upsert_is_idempotent() -> None:
    legacy_users, legacy_edges = _load_legacy_sample(limit=5)
    with TemporaryDirectory() as tmp_dir:
        engine = create_engine(f"sqlite:///{tmp_dir}/shadow.db", future=True)
        _create_archive_table(engine)  # Create archive table before initializing store
        store = get_shadow_store(engine)
        timestamp = datetime.utcnow()

        account_records = [
            ShadowAccount(
                account_id=user["user_id"],
                username=user.get("username"),
                display_name=user.get("name"),
                bio=None,
                location=None,
                website=None,
                profile_image_url=None,
                followers_count=None,
                following_count=None,
                source_channel="legacy_migration",
                fetched_at=timestamp,
                checked_at=timestamp,
            )
            for user in legacy_users
        ]

        edge_records = [
            ShadowEdge(
                source_id=edge["source_user_id"],
                target_id=edge["target_user_id"],
                direction=edge.get("edge_type", "follows"),
                source_channel=edge.get("discovery_method", "legacy"),
                fetched_at=timestamp,
            )
            for edge in legacy_edges
        ]

        store.upsert_accounts(account_records)
        store.upsert_edges(edge_records)
        store.upsert_accounts(account_records)
        store.upsert_edges(edge_records)

        assert len(store.fetch_accounts()) == len(account_records)
        assert len(store.fetch_edges()) == len(edge_records)
