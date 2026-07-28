"""Synthetic inputs shared by personal-ontology integrity tests."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sqlite3
from typing import Any, Dict

from src.communities.store import init_db, upsert_community
from src.data.community_gold import CommunityGoldStore
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from src.data.community_gold.schema import SCHEMA


def role_inputs() -> Dict[str, Any]:
    u0 = [f"acct-{index:02d}" for index in range(20)]
    u_eval = u0[2:]
    rich = u_eval[:9]
    strata = {
        account_id: ("rich" if account_id in rich else "sparse")
        for account_id in u_eval
    }
    catalog = {
        "model_development": {
            "readPurposes": ["training", "selection"],
            "requiresRich": False,
        },
        "policy_development": {
            "readPurposes": ["selection"],
            "requiresRich": True,
        },
        "policy_evaluation": {
            "readPurposes": [],
            "requiresRich": True,
        },
        "terminal_test": {
            "readPurposes": ["terminal_evaluation"],
            "requiresRich": False,
        },
        "frame_only": {
            "readPurposes": [],
            "requiresRich": False,
        },
    }
    quotas = {
        "rich": {
            "model_development": 2,
            "policy_development": 2,
            "policy_evaluation": 2,
            "terminal_test": 1,
            "frame_only": 2,
        },
        "sparse": {
            "model_development": 4,
            "policy_development": 0,
            "policy_evaluation": 0,
            "terminal_test": 2,
            "frame_only": 3,
        },
    }
    return {
        "u0": u0,
        "u_eval": u_eval,
        "rich": rich,
        "strata": strata,
        "catalog": catalog,
        "quotas": quotas,
    }


def allocation_kwargs() -> Dict[str, Any]:
    fixture = role_inputs()
    return {
        "account_ids": fixture["u_eval"],
        "strata_by_account": fixture["strata"],
        "rich_account_ids": fixture["rich"],
        "role_catalog": deepcopy(fixture["catalog"]),
        "quotas_by_stratum": deepcopy(fixture["quotas"]),
        "terminal_test_roles": ["terminal_test"],
        "seed": "slice-1-synthetic-seed",
        "role_registry_id": "synthetic-role-registry-v1",
    }


def frame_kwargs() -> Dict[str, Any]:
    fixture = role_inputs()
    return {
        "frame_id": "synthetic-frame-v1",
        "scope": {
            "userId": "user-aditya",
            "ontologyId": "personal-subcultures",
            "ontologyVersion": 1,
            "taskId": "affiliation",
        },
        "u0_account_ids": fixture["u0"],
        "fixed_training_ids": [fixture["u0"][0]],
        "fixed_challenge_ids": [fixture["u0"][1]],
        "rich_account_ids": fixture["rich"],
        "strata_by_account": fixture["strata"],
        "role_catalog": deepcopy(fixture["catalog"]),
        "quotas_by_stratum": deepcopy(fixture["quotas"]),
        "terminal_test_roles": ["terminal_test"],
        "role_registry_id": "synthetic-role-registry-v1",
        "seed": "slice-1-synthetic-seed",
        "evidence_snapshot_id": "snapshot-synthetic-v1",
        "evidence_snapshot_hash": "a" * 64,
        "graph_manifest_hash": "b" * 64,
        "identity_resolution_digest": "c" * 64,
        "evidence_cutoff": "2026-07-26T00:00:00+00:00",
        "candidate_rules": {"source": "synthetic", "deduplicate": True},
        "ood_rules": {"statistic": "distance", "threshold": 0.8},
    }


def terminal_access_receipt() -> Dict[str, Any]:
    return {
        "modelsFinal": True,
        "policyFinal": True,
        "stoppingFinal": True,
        "continuationFinal": True,
        "modelArtifactHashes": ["1" * 64],
        "policyArtifactHash": "2" * 64,
        "stoppingRuleHash": "3" * 64,
        "continuationRuleHash": "4" * 64,
        "runManifestHash": "5" * 64,
    }


def seed_community_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT,
                display_name TEXT
            )
            """
        )
        upsert_community(conn, "comm-a", "Community A", color="#111111")
        upsert_community(conn, "comm-b", "Community B", color="#222222")
        conn.commit()


def seed_legacy_gold_db(db_path: Path) -> None:
    seed_community_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO account_community_gold_split
            (account_id, split, assigned_by, assigned_at)
            VALUES ('legacy-account', 'train', 'legacy-import', '2026-03-21T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO account_community_gold_label_set
            (account_id, community_id, reviewer, judgment, confidence, note,
             evidence_json, is_active, created_at, supersedes_label_set_id)
            VALUES (
                'legacy-account', 'comm-a', 'curator:adityaarpitha', 'in',
                0.9, 'imported positive', '{"handle":"legacy","source":"import"}',
                1, '2026-03-21T00:01:00+00:00', NULL
            )
            """
        )
        conn.commit()


def registered_study_store(db_path: Path) -> tuple[CommunityGoldStore, Dict[str, Any]]:
    seed_community_db(db_path)
    store = CommunityGoldStore(db_path)
    store.register_ontology_version(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        definition={
            "name": "Personal subcultures",
            "groups": [
                {"communityId": "comm-a", "definition": "Group A boundary"},
                {"communityId": "comm-b", "definition": "Group B boundary"},
            ],
        },
    )
    store.register_ontology_task(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        task_id="affiliation",
        target_type="affiliation",
        definition={"question": "Does this account participate in this group?"},
    )
    frame = freeze_evaluation_frame(**frame_kwargs())
    store.freeze_study(frame)
    return store, frame


def record_complete_terminal_judgments(
    store: CommunityGoldStore,
    frame: Dict[str, Any],
    *,
    reviewer: str = "human",
) -> list[Dict[str, Any]]:
    """Label every terminal account/group pair for a complete release."""

    terminal = [
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    ]
    communities = ("comm-a", "comm-b")
    judgments = ("in", "out", "abstain")
    output = []
    for account_index, assignment in enumerate(terminal):
        for community_index, community_id in enumerate(communities):
            judgment = judgments[
                (account_index * len(communities) + community_index)
                % len(judgments)
            ]
            output.append(
                store.record_study_judgment(
                    frame_id=frame["frameId"],
                    account_id=assignment["accountId"],
                    community_id=community_id,
                    reviewer=reviewer,
                    judgment=judgment,
                    evidence_snapshot_id=frame["evidence"]["snapshotId"],
                    evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
                    context_hash=(
                        "d" if community_id == "comm-a" else "e"
                    ) * 64,
                    observed_at="2026-07-25T00:00:00+00:00",
                )
            )
    return output
