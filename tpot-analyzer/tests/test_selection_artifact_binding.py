from __future__ import annotations

import numpy as np
import pytest

from src.artifacts.selection_binding import (
    SelectionBindingError,
    validate_selection_mapping,
)


def _mapping():
    return {
        "tau": 0.05,
        "n_total_graph": 3,
        "n_tpot_subgraph": 2,
        "n_core": 1,
        "n_halo": 1,
        "tpot_node_ids": ["a", "c"],
    }


def test_validates_exact_ordered_selection_mapping():
    digest = validate_selection_mapping(
        _mapping(),
        np.array(["a", "b", "c"]),
        np.array(["a", "c"]),
        0.05,
        {"n_core": 1, "n_halo": 1, "n_total": 2},
    )

    assert len(digest) == 64


def test_rejects_reordered_selection_or_count_mismatch():
    with pytest.raises(SelectionBindingError, match="ordered node IDs"):
        validate_selection_mapping(
            _mapping(),
            np.array(["a", "b", "c"]),
            np.array(["c", "a"]),
            0.05,
            {"n_core": 1, "n_halo": 1, "n_total": 2},
        )

    stale = _mapping()
    stale["n_halo"] = 2
    with pytest.raises(SelectionBindingError, match="n_halo"):
        validate_selection_mapping(
            stale,
            np.array(["a", "b", "c"]),
            np.array(["a", "c"]),
            0.05,
            {"n_core": 1, "n_halo": 1, "n_total": 2},
        )


def test_rejects_missing_or_invalid_mapping_fields():
    missing = _mapping()
    del missing["tpot_node_ids"]
    with pytest.raises(SelectionBindingError, match="missing.*tpot_node_ids"):
        validate_selection_mapping(
            missing,
            np.array(["a", "b", "c"]),
            np.array(["a", "c"]),
            0.05,
            {"n_core": 1, "n_halo": 1, "n_total": 2},
        )

    stale_tau = _mapping()
    stale_tau["tau"] = 0.1
    with pytest.raises(SelectionBindingError, match="tau"):
        validate_selection_mapping(
            stale_tau,
            np.array(["a", "b", "c"]),
            np.array(["a", "c"]),
            0.05,
            {"n_core": 1, "n_halo": 1, "n_total": 2},
        )
