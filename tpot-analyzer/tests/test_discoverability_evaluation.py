"""Behavioral tests for the frozen discoverability evaluation contract."""
from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from scripts import verify_network_discoverability as verifier
from src.evaluation.discoverability import (
    FalsifierThresholds,
    load_fixed_seed_handles,
    measure_frozen_discoverability,
    resolve_seed_indices,
    write_json_no_clobber,
)


def _fixture():
    ids = ["seed", "mutual", "near_a", "near_b", "other_center"] + [
        f"leaf_{i}" for i in range(10)
    ]
    nodes = pd.DataFrame(
        {
            "node_id": ids,
            "username": ids,
            "shadow": [True] * len(ids),
        }
    )
    rows = [
        ("seed", "mutual", "outbound"),
        ("mutual", "seed", "inbound"),
        ("seed", "near_a", "outbound"),
        ("near_b", "seed", "inbound"),
    ]
    rows.extend(("other_center", f"leaf_{i}", "outbound") for i in range(10))
    edges = pd.DataFrame(
        {
            "source": [row[0] for row in rows],
            "target": [row[1] for row in rows],
            "direction_label": [row[2] for row in rows],
            "shadow": [True] * len(rows),
        }
    )
    relevance = np.zeros(len(ids), dtype=np.float32)
    relevance[0] = 1.0
    thresholds = FalsifierThresholds(
        center_node_max_pct=20.0,
        high_degree_min=3,
    )
    report = measure_frozen_discoverability(
        nodes,
        edges,
        ["seed", "mutual", "near_a", "near_b"],
        relevance,
        0.5,
        ["seed"],
        thresholds=thresholds,
    )
    return nodes, report


def test_measures_capture_components_reachability_and_core_halo():
    _, report = _fixture()

    assert report["measurement_complete"] is True
    assert report["strict_pass"] is True
    assert (
        report["hypotheses"]["H-D1"]["measurements"]["degree_one_node_pct"]
        > 50
    )
    h2 = report["hypotheses"]["H-D2"]["measurements"]
    assert (
        h2["components"]["weak"]["giant_pct"]
        > h2["components"]["mutual"]["giant_pct"]
    )
    assert (
        h2["seed_reachability"]["undirected"]["pct"]
        > h2["seed_reachability"]["mutual"]["pct"]
    )
    assert report["hypotheses"]["H-D5"]["measurements"]["exact_core_halo_match"]


def test_rejects_missing_fixed_seed():
    nodes, _ = _fixture()

    with pytest.raises(ValueError, match="did not resolve uniquely"):
        resolve_seed_indices(nodes, ["absent"])


def test_rejects_selected_ids_outside_graph():
    nodes, _ = _fixture()
    edges = pd.DataFrame(
        {
            "source": ["seed"],
            "target": ["mutual"],
            "direction_label": ["outbound"],
            "shadow": [True],
        }
    )

    with pytest.raises(ValueError, match="absent from graph"):
        measure_frozen_discoverability(
            nodes,
            edges,
            ["seed", "not-a-node"],
            np.r_[1.0, np.zeros(len(nodes) - 1)],
            0.5,
            ["seed"],
        )


def test_seed_file_requires_exact_fixed_panel(tmp_path):
    path = tmp_path / "seeds.json"
    path.write_text(json.dumps({"adi_tpot": ["only_one"]}))

    with pytest.raises(ValueError, match="exactly 18"):
        load_fixed_seed_handles(path)


def test_json_result_is_no_clobber(tmp_path):
    path = tmp_path / "result.json"
    write_json_no_clobber(path, {"measurement_complete": True})

    with pytest.raises(FileExistsError):
        write_json_no_clobber(path, {"measurement_complete": False})


def test_json_serialization_failure_does_not_reserve_output(tmp_path):
    path = tmp_path / "invalid.json"

    with pytest.raises(TypeError):
        write_json_no_clobber(path, {"not_json": object()})

    assert not path.exists()


def test_verifier_checks_manifest_before_measurement(monkeypatch, tmp_path):
    _, report = _fixture()
    events = []
    monkeypatch.setattr(
        verifier,
        "verify_frozen_manifest",
        lambda _: events.append("manifest") or {"bundle_id": "test"},
    )
    monkeypatch.setattr(
        verifier,
        "load_and_measure_frozen",
        lambda *_: events.append("measure") or report,
    )
    monkeypatch.setattr(verifier, "file_sha256", lambda _: "a" * 64)

    assert verifier.verify(tmp_path) == 0
    assert events == ["manifest", "measure"]


def test_verifier_input_failure_exits_one(monkeypatch, tmp_path):
    def reject_manifest(_):
        raise ValueError("identity mismatch")

    monkeypatch.setattr(verifier, "verify_frozen_manifest", reject_manifest)

    assert verifier.verify(tmp_path) == 1


def test_verifier_renders_missing_degree_stratum(monkeypatch, tmp_path, capsys):
    _, base = _fixture()
    report = copy.deepcopy(base)
    selection = report["hypotheses"]["H-D5"]["measurements"]
    selection["high_minus_degree_one_selection_pp"] = None
    report["hypotheses"]["H-D5"]["falsified"] = True
    report["strict_pass"] = False
    monkeypatch.setattr(
        verifier,
        "verify_frozen_manifest",
        lambda _: {"bundle_id": "test"},
    )
    monkeypatch.setattr(verifier, "load_and_measure_frozen", lambda *_: report)
    monkeypatch.setattr(verifier, "file_sha256", lambda _: "a" * 64)

    assert verifier.verify(tmp_path, strict=False) == 0
    assert "degree gap=unavailable" in capsys.readouterr().out
    assert verifier.verify(tmp_path, strict=True) == 2


def test_strict_mode_enforces_falsifiers_but_default_completes(
    monkeypatch, tmp_path
):
    _, base = _fixture()
    report = copy.deepcopy(base)
    report["hypotheses"]["H-D1"]["falsified"] = True
    report["strict_pass"] = False
    monkeypatch.setattr(
        verifier, "verify_frozen_manifest", lambda _: {"bundle_id": "test"}
    )
    monkeypatch.setattr(verifier, "load_and_measure_frozen", lambda *_: report)
    monkeypatch.setattr(verifier, "file_sha256", lambda _: "a" * 64)

    assert verifier.verify(tmp_path, strict=False) == 0
    assert verifier.verify(tmp_path, strict=True) == 2
