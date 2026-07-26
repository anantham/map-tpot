"""Build and validate machine-readable graph artifact provenance."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from src.artifacts.calibration_record import (
    CalibrationRecordError,
    validate_calibration_method_record,
)
from src.artifacts.digests import file_sha256, json_sha256
from src.artifacts.propagation_schema import propagation_score_semantics


class CalibrationCompatibilityError(ValueError):
    """Raised when calibration metadata contradicts the selected artifacts."""


IDENTITY_FIELDS = (
    "schema_version",
    "graph.node_count",
    "graph.adjacency_construction",
    "graph.source_files",
    "graph.ordered_node_sha256",
    "graph.structure_sha256",
    "graph.values_sha256",
    "propagation.file_sha256",
    "propagation.source_node_sha256",
    "propagation.membership_shape",
    "propagation.mode",
    "propagation.mode_declared",
    "propagation.score_semantics",
    "propagation.community_schema.sha256",
)


def build_artifact_provenance(
    binding,
    propagation,
    *,
    source_files: dict[str, object] | None = None,
) -> dict:
    """Return a JSON-serializable compatibility record."""
    memberships = propagation.arrays["memberships"]
    if binding.ordered_node_sha256 != propagation.graph_node_sha256:
        raise ValueError(
            "adjacency and propagation graph node digests disagree: "
            f"adjacency={binding.ordered_node_sha256}, "
            f"propagation={propagation.graph_node_sha256}"
        )
    if memberships.shape[0] != binding.node_count:
        raise ValueError(
            "aligned membership rows must match the bound graph: "
            f"memberships={memberships.shape}, graph_nodes={binding.node_count}"
        )

    community_schema = {
        "ids": [str(value) for value in propagation.arrays["community_ids"]],
        "names": [str(value) for value in propagation.arrays["community_names"]],
        "colors": [str(value) for value in propagation.arrays["community_colors"]],
    }
    community_schema["sha256"] = json_sha256(community_schema)
    mode, score_semantics, mode_declared = propagation_score_semantics(
        propagation.arrays
    )
    evaluations = [
        {
            "file": evaluation.path.name,
            "source_node_count": evaluation.source_node_count,
            "matched_node_count": evaluation.matched_node_count,
            "missing_node_count": evaluation.missing_node_count,
            "exact_order": bool(evaluation.exact_order),
            "reason": evaluation.reason,
        }
        for evaluation in propagation.evaluations
    ]
    source_file_records = {}
    for label, raw_path in sorted((source_files or {}).items()):
        path = Path(raw_path)
        source_file_records[str(label)] = {
            "file": path.name,
            "sha256": file_sha256(path),
        }
    return {
        "schema_version": 1,
        "graph": {
            "node_count": int(binding.node_count),
            "edge_row_count": int(binding.edge_row_count),
            "ignored_edge_count": int(binding.ignored_edge_count),
            "adjacency_nnz": int(binding.adjacency_nnz),
            "adjacency_construction": binding.construction_method,
            "source_files": source_file_records,
            "ordered_node_sha256": binding.ordered_node_sha256,
            "structure_sha256": binding.structure_sha256,
            "values_sha256": binding.values_sha256,
        },
        "propagation": {
            "file": propagation.path.name,
            "file_sha256": file_sha256(propagation.path),
            "source_node_count": int(propagation.source_node_count),
            "source_node_sha256": propagation.source_node_sha256,
            "exact_order": bool(propagation.exact_order),
            "membership_shape": [int(value) for value in memberships.shape],
            "mode": mode,
            "mode_declared": mode_declared,
            "score_semantics": score_semantics,
            "community_schema": community_schema,
            "candidate_evaluations": evaluations,
        },
    }


def _field(record: dict, dotted_path: str) -> Any:
    value: Any = record
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise CalibrationCompatibilityError(
                f"artifact provenance is missing {dotted_path}"
            )
        value = value[part]
    return value


def validate_artifact_provenance_identity(
    saved: dict,
    current: dict,
    *,
    label: str = "saved artifact",
) -> None:
    """Compare scientific identity fields while ignoring diagnostic context."""
    if not isinstance(saved, dict):
        raise CalibrationCompatibilityError(
            f"{label} provenance must be an object"
        )
    for field in IDENTITY_FIELDS:
        saved_value = _field(saved, field)
        current_value = _field(current, field)
        if saved_value != current_value:
            raise CalibrationCompatibilityError(
                f"{label} {field}={saved_value!r}, "
                f"but current artifacts have {current_value!r}"
            )


def validate_calibration_compatibility(calibration: dict, provenance: dict) -> str:
    """Validate calibration identity and return its binding status."""
    if not isinstance(calibration, dict):
        raise CalibrationCompatibilityError(
            f"calibration root must be an object; got {type(calibration).__name__}"
        )
    if calibration.get("calibrated") is not True:
        raise CalibrationCompatibilityError(
            "calibration must declare calibrated=true before it can supply "
            "the builder's default threshold; pass an explicit --tau to "
            "override intentionally"
        )
    tau = calibration.get("tau")
    if (
        isinstance(tau, bool)
        or not isinstance(tau, (int, float))
        or not math.isfinite(float(tau))
        or not 0.0 <= float(tau) <= 1.0
    ):
        raise CalibrationCompatibilityError(
            f"calibration tau must be finite and in [0, 1]; got {tau!r}"
        )
    current_nodes = _field(provenance, "graph.node_count")
    saved_nodes = calibration.get("n_nodes_total")
    if saved_nodes != current_nodes:
        raise CalibrationCompatibilityError(
            f"calibration n_nodes_total={saved_nodes!r}, "
            f"but current graph has {current_nodes}"
        )
    counts = {}
    for field in ("n_core", "n_halo", "n_total"):
        value = calibration.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CalibrationCompatibilityError(
                f"calibration is missing required count {field} "
                f"or it is not an integer: {value!r}"
            )
        if value < 0:
            raise CalibrationCompatibilityError(
                f"calibration {field} must be non-negative; got {value}"
            )
        counts[field] = value
    if counts["n_core"] + counts["n_halo"] != counts["n_total"]:
        raise CalibrationCompatibilityError(
            "calibration n_core + n_halo must equal n_total: "
            f"{counts['n_core']} + {counts['n_halo']} != {counts['n_total']}"
        )
    if counts["n_total"] > current_nodes:
        raise CalibrationCompatibilityError(
            f"calibration n_total={counts['n_total']} exceeds "
            f"graph nodes={current_nodes}"
        )

    saved = calibration.get("artifact_provenance")
    if saved is None:
        return "legacy-runtime-validation-required"
    if not isinstance(saved, dict):
        raise CalibrationCompatibilityError(
            "calibration artifact_provenance must be an object"
        )
    try:
        validate_calibration_method_record(calibration.get("calibration_method"))
    except CalibrationRecordError as exc:
        raise CalibrationCompatibilityError(str(exc)) from exc

    validate_artifact_provenance_identity(
        saved,
        provenance,
        label="calibration",
    )
    return "compatibility-record-bound"
