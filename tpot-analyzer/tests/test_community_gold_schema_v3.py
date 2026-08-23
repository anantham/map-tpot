"""Behavioral migration and global-generation contracts for schema v3."""
from __future__ import annotations

from copy import deepcopy
import sqlite3

import pytest

from src.data.community_gold import CommunityGoldStore
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from tests.personal_ontology_fixtures import (
    frame_kwargs,
    registered_study_store,
    seed_legacy_gold_db,
)


pytestmark = pytest.mark.integration


def test_prior_v2_terminal_access_shape_upgrades_idempotently(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_community_gold_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO account_community_gold_schema_version
            VALUES (2, 'prior-v2');
            CREATE TABLE account_community_terminal_test_access (
                frame_id TEXT PRIMARY KEY,
                accessed_by TEXT NOT NULL,
                access_receipt_json TEXT NOT NULL,
                access_receipt_hash TEXT NOT NULL,
                accessed_at TEXT NOT NULL
            );
            """
        )
        conn.commit()

    CommunityGoldStore(db_path)
    CommunityGoldStore(db_path)

    with sqlite3.connect(db_path) as conn:
        version = conn.execute(
            "SELECT MAX(version) FROM account_community_gold_schema_version"
        ).fetchone()[0]
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(account_community_terminal_test_access)"
            )
        }
    assert version == 3
    assert {
        "role_registry_id",
        "release_manifest_json",
        "release_manifest_hash",
        "access_envelope_hash",
        "released_label_head_count",
    } <= columns


def test_nonempty_pre_v3_terminal_access_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_community_gold_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO account_community_gold_schema_version
            VALUES (2, 'prior-v2');
            CREATE TABLE account_community_terminal_test_access (
                frame_id TEXT PRIMARY KEY,
                accessed_by TEXT NOT NULL,
                access_receipt_json TEXT NOT NULL,
                access_receipt_hash TEXT NOT NULL,
                accessed_at TEXT NOT NULL
            );
            INSERT INTO account_community_terminal_test_access
            VALUES ('old-frame', 'actor', '{}', 'not-verifiable', 'old');
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="release coverage is unverifiable"):
        CommunityGoldStore(db_path)

    with sqlite3.connect(db_path) as conn:
        versions = [
            row[0]
            for row in conn.execute(
                """
                SELECT version
                FROM account_community_gold_schema_version
                ORDER BY version
                """
            )
        ]
        access_count = conn.execute(
            "SELECT COUNT(*) FROM account_community_terminal_test_access"
        ).fetchone()[0]
    assert versions == [2]
    assert access_count == 1


def test_malformed_existing_scientific_table_fails_before_version_write(
    tmp_path,
) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE personal_ontology_version (x TEXT)")
        conn.commit()

    with pytest.raises(RuntimeError, match="incompatible.*missing"):
        CommunityGoldStore(db_path)

    with sqlite3.connect(db_path) as conn:
        version_table = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table'
              AND name = 'account_community_gold_schema_version'
            """
        ).fetchone()
    assert version_table is None


def test_reinitialization_replaces_stale_canonical_trigger(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    )
    judgment = store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=account["accountId"],
        community_id="comm-a",
        reviewer="human",
        judgment="in",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            DROP TRIGGER prevent_scoped_gold_update;
            CREATE TRIGGER prevent_scoped_gold_update
            AFTER INSERT ON account_community_gold_label_set
            BEGIN
                SELECT 1;
            END;
            """
        )
        conn.commit()

    CommunityGoldStore(db_path)

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                """
                UPDATE account_community_gold_label_set
                SET judgment = 'out'
                WHERE id = ?
                """,
                (judgment["labelSetId"],),
            )


def test_new_registry_id_cannot_reassign_existing_global_accounts(
    tmp_path,
) -> None:
    store, original = registered_study_store(
        tmp_path / "archive_tweets.db"
    )
    changed_kwargs = deepcopy(frame_kwargs())
    changed_kwargs["frame_id"] = "synthetic-frame-new-registry"
    changed_kwargs["role_registry_id"] = "attacker-selected-registry"
    changed_kwargs["seed"] = "attacker-selected-seed"
    changed = freeze_evaluation_frame(**changed_kwargs)
    changed_roles = {
        row["accountId"]: row["assignedRole"]
        for row in changed["roleAssignments"]
    }
    original_roles = {
        row["accountId"]: row["assignedRole"]
        for row in original["roleAssignments"]
    }
    assert changed_roles != original_roles

    with pytest.raises(ValueError, match="global account roles"):
        store.freeze_study(changed)


def test_text_primary_keys_are_explicitly_not_null(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)
    CommunityGoldStore(db_path)
    targets = {
        "account_community_role_registry": "role_registry_id",
        "account_community_evaluation_frame": "frame_id",
        "account_community_terminal_test_access": "frame_id",
        "account_community_prediction": "prediction_id",
    }
    with sqlite3.connect(db_path) as conn:
        observed = {}
        for table, column in targets.items():
            info = {
                str(row[1]): row
                for row in conn.execute(f"PRAGMA table_info({table})")
            }
            observed[(table, column)] = int(info[column][3])
    assert observed == {
        (table, column): 1
        for table, column in targets.items()
    }
