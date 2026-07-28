"""Declarative SQLite table constraints for Community Gold schema v3."""
from __future__ import annotations

from typing import Mapping

_NOT_NULL_COLUMNS: Mapping[str, frozenset[str]] = {
    "account_community_gold_schema_version": frozenset({"applied_at"}),
    "personal_ontology_version": frozenset(
        {
            "user_id", "ontology_id", "ontology_version", "definition_json",
            "definition_hash", "created_at",
        }
    ),
    "personal_ontology_group": frozenset(
        {
            "user_id", "ontology_id", "ontology_version", "community_id",
            "boundary_definition",
        }
    ),
    "personal_ontology_task": frozenset(
        {
            "user_id", "ontology_id", "ontology_version", "task_id",
            "target_type", "definition_json", "definition_hash", "created_at",
        }
    ),
    "account_community_role_registry": frozenset(
        {
            "role_registry_id", "registry_json", "registry_digest",
            "created_at",
        }
    ),
    "account_community_global_role": frozenset(
        {
            "role_registry_id", "account_id", "assigned_role", "role_json",
            "role_hash",
        }
    ),
    "account_community_evaluation_frame": frozenset(
        {
            "frame_id", "user_id", "ontology_id", "ontology_version", "task_id",
            "manifest_json", "manifest_digest", "evidence_snapshot_id",
            "evidence_snapshot_hash", "graph_manifest_hash",
            "evidence_cutoff", "role_registry_id", "created_at",
        }
    ),
    "account_community_evaluation_role": frozenset(
        {
            "frame_id", "account_id", "stratum", "assigned_role",
            "assigned_probability", "terminal_test_probability",
            "role_probabilities_json",
        }
    ),
    "account_community_gold_head": frozenset(
        {
            "frame_id", "account_id", "community_id", "reviewer",
            "label_set_id", "updated_at",
        }
    ),
    "account_community_terminal_test_access": frozenset(
        {
            "frame_id", "role_registry_id", "accessed_by",
            "access_receipt_json",
            "access_receipt_hash", "release_manifest_json",
            "release_manifest_hash", "access_envelope_hash",
            "released_label_head_count",
            "accessed_at",
        }
    ),
    "account_community_prediction": frozenset(
        {
            "prediction_id", "frame_id", "account_id", "community_id",
            "model_run_id",
            "score", "score_semantics", "evidence_snapshot_id",
            "evidence_snapshot_hash", "context_hash", "observed_at",
            "predicted_at", "payload_hash",
        }
    ),
}

_CHECK_FRAGMENTS: Mapping[str, tuple[str, ...]] = {
    "personal_ontology_version": ("check (ontology_version > 0)",),
    "personal_ontology_task": (
        "check (target_type in "
        "('affiliation','competence','participation_interest'))",
    ),
    "account_community_evaluation_role": (
        "check (assigned_probability > 0.0 "
        "and assigned_probability <= 1.0)",
        "check (terminal_test_probability > 0.0 "
        "and terminal_test_probability <= 1.0)",
    ),
    "account_community_terminal_test_access": (
        "check (typeof(released_label_head_count) = 'integer' "
        "and released_label_head_count > 0)",
    ),
    "account_community_prediction": (
        "check (score_semantics in "
        "('simplex','lift','affinity','calibrated_probability'))",
    ),
}

_FOREIGN_KEYS: Mapping[
    str,
    frozenset[tuple[tuple[str, ...], str, tuple[str, ...], str]],
] = {
    "personal_ontology_group": frozenset(
        {
            (
                ("user_id", "ontology_id", "ontology_version"),
                "personal_ontology_version",
                ("user_id", "ontology_id", "ontology_version"),
                "RESTRICT",
            ),
            (("community_id",), "community", ("id",), "RESTRICT"),
        }
    ),
    "personal_ontology_task": frozenset(
        {
            (
                ("user_id", "ontology_id", "ontology_version"),
                "personal_ontology_version",
                ("user_id", "ontology_id", "ontology_version"),
                "RESTRICT",
            )
        }
    ),
    "account_community_global_role": frozenset(
        {
            (
                ("role_registry_id",),
                "account_community_role_registry",
                ("role_registry_id",),
                "RESTRICT",
            )
        }
    ),
    "account_community_evaluation_frame": frozenset(
        {
            (
                ("user_id", "ontology_id", "ontology_version", "task_id"),
                "personal_ontology_task",
                ("user_id", "ontology_id", "ontology_version", "task_id"),
                "RESTRICT",
            ),
            (
                ("role_registry_id",),
                "account_community_role_registry",
                ("role_registry_id",),
                "RESTRICT",
            ),
        }
    ),
    "account_community_evaluation_role": frozenset(
        {
            (
                ("frame_id",),
                "account_community_evaluation_frame",
                ("frame_id",),
                "RESTRICT",
            )
        }
    ),
    "account_community_gold_head": frozenset(
        {
            (
                ("frame_id",),
                "account_community_evaluation_frame",
                ("frame_id",),
                "RESTRICT",
            ),
            (("community_id",), "community", ("id",), "RESTRICT"),
            (
                ("label_set_id",),
                "account_community_gold_label_set",
                ("id",),
                "RESTRICT",
            ),
        }
    ),
    "account_community_terminal_test_access": frozenset(
        {
            (
                ("frame_id",),
                "account_community_evaluation_frame",
                ("frame_id",),
                "RESTRICT",
            ),
            (
                ("role_registry_id",),
                "account_community_role_registry",
                ("role_registry_id",),
                "RESTRICT",
            ),
        }
    ),
    "account_community_prediction": frozenset(
        {
            (
                ("frame_id",),
                "account_community_evaluation_frame",
                ("frame_id",),
                "RESTRICT",
            ),
            (("community_id",), "community", ("id",), "RESTRICT"),
        }
    ),
}

_UNIQUE_COLUMNS: Mapping[str, frozenset[tuple[str, ...]]] = {
    "account_community_role_registry": frozenset({("registry_digest",)}),
    "account_community_evaluation_frame": frozenset({("manifest_digest",)}),
    "account_community_gold_head": frozenset({("label_set_id",)}),
    "account_community_terminal_test_access": frozenset(
        {("role_registry_id",)}
    ),
}
