from __future__ import annotations

import sqlite3

import pytest

from src.data.community_gold import CommunityGoldStore
from tests.personal_ontology_fixtures import seed_legacy_gold_db


@pytest.mark.integration
def test_migration_refuses_a_future_schema_version(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE account_community_gold_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO account_community_gold_schema_version
            (version, applied_at)
            VALUES (999, 'future')
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="newer than this code"):
        CommunityGoldStore(db_path)


@pytest.mark.integration
def test_future_schema_refusal_performs_no_mutation(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE account_community_gold_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO account_community_gold_schema_version
            (version, applied_at)
            VALUES (999, 'future')
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="newer than this code"):
        CommunityGoldStore(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == {"account_community_gold_schema_version"}
