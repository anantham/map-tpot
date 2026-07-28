"""Synthetic, network-free fixture for the Slice 1 verifier."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.communities.store import init_db, upsert_community
from src.data.community_gold import CommunityGoldStore
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame


def seed_database(db_path: Path) -> None:
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
        upsert_community(conn, "verify-a", "Verifier Group A")
        upsert_community(conn, "verify-b", "Verifier Group B")
        conn.commit()


def frozen_frame() -> dict[str, Any]:
    u0 = [f"verify-{index:02d}" for index in range(12)]
    u_eval = u0[2:]
    rich = u_eval[:4]
    catalog = {
        "model_development": {
            "readPurposes": ["training", "selection"],
            "requiresRich": False,
        },
        "policy_development": {
            "readPurposes": ["selection"],
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
    return freeze_evaluation_frame(
        frame_id="slice1-verifier-frame",
        scope={
            "userId": "verifier-user",
            "ontologyId": "verifier-ontology",
            "ontologyVersion": 1,
            "taskId": "affiliation",
        },
        u0_account_ids=u0,
        fixed_training_ids=[u0[0]],
        fixed_challenge_ids=[u0[1]],
        rich_account_ids=rich,
        strata_by_account={
            account_id: ("rich" if account_id in rich else "sparse")
            for account_id in u_eval
        },
        role_catalog=catalog,
        quotas_by_stratum={
            "rich": {
                "model_development": 1,
                "policy_development": 1,
                "terminal_test": 1,
                "frame_only": 1,
            },
            "sparse": {
                "model_development": 3,
                "policy_development": 0,
                "terminal_test": 1,
                "frame_only": 2,
            },
        },
        terminal_test_roles=["terminal_test"],
        role_registry_id="slice1-verifier-registry",
        seed="slice1-verifier-seed",
        evidence_snapshot_id="slice1-verifier-snapshot",
        evidence_snapshot_hash="a" * 64,
        graph_manifest_hash="b" * 64,
        identity_resolution_digest="c" * 64,
        evidence_cutoff="2026-07-26T00:00:00+00:00",
        candidate_rules={"source": "synthetic"},
        ood_rules={"statistic": "synthetic", "threshold": 1.0},
    )


def terminal_receipt() -> dict[str, Any]:
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


def record_judgment(
    store: CommunityGoldStore,
    frame: dict[str, Any],
    *,
    account_id: str,
    judgment: str,
    context_digit: str,
    community_id: str = "verify-a",
) -> dict[str, Any]:
    return store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id=community_id,
        reviewer="verifier-human",
        judgment=judgment,
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash=context_digit * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
