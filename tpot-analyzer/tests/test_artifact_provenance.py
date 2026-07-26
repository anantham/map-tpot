from __future__ import annotations

import json

import numpy as np

from src.artifacts.digests import file_sha256, json_sha256
from src.artifacts.provenance import (
    CalibrationCompatibilityError,
    validate_artifact_provenance_identity,
)
from tests.artifact_provenance_fixtures import build_test_provenance


def test_builds_json_serializable_bound_provenance(tmp_path):
    provenance, propagation_path = build_test_provenance(tmp_path)

    assert provenance["schema_version"] == 1
    assert provenance["graph"]["node_count"] == 2
    assert provenance["graph"]["adjacency_construction"] == "directed_edge_rows"
    assert provenance["graph"]["source_files"]["nodes"]["file"] == "nodes"
    assert provenance["graph"]["source_files"]["nodes"]["sha256"] == file_sha256(
        tmp_path / "nodes"
    )
    assert provenance["graph"]["ordered_node_sha256"] == "n" * 64
    assert provenance["propagation"]["file_sha256"] == file_sha256(propagation_path)
    assert provenance["propagation"]["membership_shape"] == [2, 3]
    assert provenance["propagation"]["mode"] == "classic"
    assert provenance["propagation"]["mode_declared"] is False
    schema = provenance["propagation"]["community_schema"]
    assert schema["sha256"] == json_sha256(
        {
            "ids": ["c1", "c2"],
            "names": ["one", "two"],
            "colors": ["#111111", "#222222"],
        }
    )
    json.dumps(provenance)


def test_identity_ignores_candidate_diagnostics_but_not_scientific_fields(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    saved = json.loads(json.dumps(provenance))
    saved["propagation"]["candidate_evaluations"] = []

    validate_artifact_provenance_identity(saved, provenance)

    saved["propagation"]["score_semantics"] = "independent_lift"
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "score_semantics",
    ):
        validate_artifact_provenance_identity(saved, provenance)
