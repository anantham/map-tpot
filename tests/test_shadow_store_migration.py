"""Tests that legacy social graph data migrates cleanly into the shadow store."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Tuple

import pytest
import sqlite3
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer

ROOT = Path(__file__).resolve().parents[1] / "tpot-analyzer"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.shadow_store import ShadowAccount, ShadowEdge, get_shadow_store


LEGACY_DB = Path(
    "/Users/aditya/Library/CloudStorage/OneDrive-IndianInstituteofScience/"
    "Documents/Ongoing/Project 2 - tpot/data/social_graph.db"
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


def _canonical_account_id(user: dict) -> str:
    """Get canonical account ID (username if available, otherwise user_id)."""
    return user.get("username") or user["user_id"]


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
def test_shadow_store_accepts_legacy_accounts_and_edges() -> None:
    legacy_users, legacy_edges = _load_legacy_sample()

    # Build mapping from user_id to canonical account_id
    id_mapping = {user["user_id"]: _canonical_account_id(user) for user in legacy_users}

    # Calculate expected unique accounts (after deduplication by username)
    unique_account_ids = set(id_mapping.values())
    expected_account_count = len(unique_account_ids)

    with TemporaryDirectory() as tmp_dir:
        engine = create_engine(f"sqlite:///{tmp_dir}/shadow.db", future=True)
        _create_archive_table(engine)  # Create archive table before initializing store
        store = get_shadow_store(engine)

        timestamp = datetime.utcnow()
        accounts = [
            ShadowAccount(
                account_id=_canonical_account_id(user),  # Use canonical ID
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

        # Note: returned count is new inserts, not total (may be less due to deduplication)
        inserted_accounts = store.upsert_accounts(accounts)

        fetched_accounts = store.fetch_accounts()
        assert len(fetched_accounts) == expected_account_count  # Expect deduplicated count
        sample_account = fetched_accounts[0]
        assert sample_account["is_shadow"] is True
        assert sample_account["source_channel"] == "legacy_migration"

        edges = [
            ShadowEdge(
                source_id=id_mapping.get(edge["source_user_id"], edge["source_user_id"]),  # Map to canonical ID
                target_id=id_mapping.get(edge["target_user_id"], edge["target_user_id"]),  # Map to canonical ID
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
        # Note: may insert fewer edges if source/target IDs reference non-existent accounts

        fetched_edges = store.fetch_edges()
        assert len(fetched_edges) > 0  # At least some edges should be inserted
        assert all(edge["metadata"]["legacy"] for edge in fetched_edges)


@pytest.mark.skipif(not LEGACY_DB.exists(), reason="Legacy social graph database unavailable")
def test_shadow_store_upsert_is_idempotent() -> None:
    legacy_users, legacy_edges = _load_legacy_sample(limit=5)

    # Build mapping from user_id to canonical account_id
    id_mapping = {user["user_id"]: _canonical_account_id(user) for user in legacy_users}

    # Calculate expected unique accounts/edges (after deduplication)
    unique_account_ids = set(id_mapping.values())
    expected_account_count = len(unique_account_ids)

    with TemporaryDirectory() as tmp_dir:
        engine = create_engine(f"sqlite:///{tmp_dir}/shadow.db", future=True)
        _create_archive_table(engine)  # Create archive table before initializing store
        store = get_shadow_store(engine)
        timestamp = datetime.utcnow()

        account_records = [
            ShadowAccount(
                account_id=_canonical_account_id(user),  # Use canonical ID
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
                source_id=id_mapping.get(edge["source_user_id"], edge["source_user_id"]),  # Map to canonical ID
                target_id=id_mapping.get(edge["target_user_id"], edge["target_user_id"]),  # Map to canonical ID
                direction=edge.get("edge_type", "follows"),
                source_channel=edge.get("discovery_method", "legacy"),
                fetched_at=timestamp,
            )
            for edge in legacy_edges
        ]

        # First upsert
        store.upsert_accounts(account_records)
        store.upsert_edges(edge_records)
        accounts_after_first = store.fetch_accounts()
        edges_after_first = store.fetch_edges()

        # Second upsert (should be idempotent)
        store.upsert_accounts(account_records)
        store.upsert_edges(edge_records)
        accounts_after_second = store.fetch_accounts()
        edges_after_second = store.fetch_edges()

        # Idempotency check: second upsert should not change counts
        assert len(accounts_after_first) == expected_account_count
        assert len(accounts_after_second) == expected_account_count
        assert len(edges_after_first) == len(edges_after_second)
