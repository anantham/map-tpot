"""Behavioral regressions for schema-v3 migration shape validation."""
from __future__ import annotations

import sqlite3

import pytest

from src.data.community_gold import CommunityGoldStore
from tests.personal_ontology_fixtures import seed_legacy_gold_db


pytestmark = pytest.mark.integration


def _assert_schema_v3_absent(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        table = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table'
              AND name = 'account_community_gold_schema_version'
            """
        ).fetchone()
        if table is None:
            return
        versions = {
            int(row[0])
            for row in conn.execute(
                "SELECT version FROM account_community_gold_schema_version"
            )
        }
    assert 3 not in versions


def test_exact_column_shape_without_constraints_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE personal_ontology_version (
                user_id TEXT,
                ontology_id TEXT,
                ontology_version INTEGER,
                definition_json TEXT,
                definition_hash TEXT,
                supersedes_version INTEGER,
                created_at TEXT,
                PRIMARY KEY (user_id, ontology_id, ontology_version)
            )
            """
        )
        conn.commit()

    with pytest.raises(
        RuntimeError,
        match="incompatible|constraint|NOT NULL|schema",
    ):
        CommunityGoldStore(db_path)

    _assert_schema_v3_absent(db_path)


def test_stale_wrong_named_index_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_community_role_registry (
                role_registry_id TEXT PRIMARY KEY,
                registry_json TEXT NOT NULL,
                registry_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE account_community_global_role (
                role_registry_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                assigned_role TEXT NOT NULL,
                role_json TEXT NOT NULL,
                role_hash TEXT NOT NULL,
                PRIMARY KEY (role_registry_id, account_id),
                FOREIGN KEY (role_registry_id)
                    REFERENCES account_community_role_registry(
                        role_registry_id
                    ) ON DELETE RESTRICT
            );

            CREATE INDEX idx_global_role_one_registry_per_account
            ON account_community_global_role(role_registry_id);
            """
        )
        conn.commit()

    with pytest.raises(
        RuntimeError,
        match="index|incompatible|unique|account_id",
    ):
        CommunityGoldStore(db_path)

    _assert_schema_v3_absent(db_path)


def test_owned_index_rejects_weakened_partial_predicate(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    CommunityGoldStore(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            DROP INDEX idx_account_community_gold_active_legacy;
            CREATE UNIQUE INDEX idx_account_community_gold_active_legacy
            ON account_community_gold_label_set(
                account_id, community_id, reviewer
            )
            WHERE is_active = 1
              AND identity_status = 'legacy_unbound'
              AND 0 = 1;
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="index|predicate|incompatible"):
        CommunityGoldStore(db_path)


def test_partial_unique_cannot_impersonate_required_unique(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_community_role_registry (
                role_registry_id TEXT NOT NULL PRIMARY KEY,
                registry_json TEXT NOT NULL,
                registry_digest TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX attacker_partial_digest
            ON account_community_role_registry(registry_digest)
            WHERE 0;
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="UNIQUE|unique|constraint"):
        CommunityGoldStore(db_path)
    _assert_schema_v3_absent(db_path)


def test_check_constraint_rejects_weakened_expression(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE personal_ontology_task (
                user_id TEXT NOT NULL,
                ontology_id TEXT NOT NULL,
                ontology_version INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                target_type TEXT NOT NULL CHECK (
                    target_type IN ('affiliation','competence','participation_interest')
                    OR 1 = 1
                ),
                definition_json TEXT NOT NULL,
                definition_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (
                    user_id, ontology_id, ontology_version, task_id
                ),
                FOREIGN KEY (user_id, ontology_id, ontology_version)
                    REFERENCES personal_ontology_version(
                        user_id, ontology_id, ontology_version
                    ) ON DELETE RESTRICT
            )
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="CHECK|check|constraint"):
        CommunityGoldStore(db_path)
    _assert_schema_v3_absent(db_path)


def test_check_constraint_cannot_be_impersonated_by_comment(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE personal_ontology_version (
                user_id TEXT NOT NULL,
                ontology_id TEXT NOT NULL,
                ontology_version INTEGER NOT NULL CHECK (1),
                definition_json TEXT NOT NULL,
                definition_hash TEXT NOT NULL,
                supersedes_version INTEGER,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, ontology_id, ontology_version)
                /* check (ontology_version > 0) */
            )
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="CHECK|check|constraint"):
        CommunityGoldStore(db_path)
    _assert_schema_v3_absent(db_path)


def test_check_constraint_cannot_be_impersonated_by_string(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE personal_ontology_version (
                user_id TEXT NOT NULL,
                ontology_id TEXT NOT NULL,
                ontology_version INTEGER NOT NULL CHECK (1),
                definition_json TEXT NOT NULL
                    DEFAULT 'check (ontology_version > 0)',
                definition_hash TEXT NOT NULL,
                supersedes_version INTEGER,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, ontology_id, ontology_version)
            )
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="CHECK|check|constraint"):
        CommunityGoldStore(db_path)
    _assert_schema_v3_absent(db_path)


def test_version_marker_cannot_be_silently_ignored(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_community_gold_schema_version (
                version INTEGER PRIMARY KEY CHECK (version < 3),
                applied_at TEXT NOT NULL
            );
            INSERT INTO account_community_gold_schema_version
            VALUES (2, 'prior-v2');
            """
        )
        conn.commit()

    with pytest.raises(
        (RuntimeError, sqlite3.IntegrityError),
        match="version|constraint|CHECK",
    ):
        CommunityGoldStore(db_path)
    _assert_schema_v3_absent(db_path)
