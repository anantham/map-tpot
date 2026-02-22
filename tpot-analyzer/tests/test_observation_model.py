from __future__ import annotations

import numpy as np
import pandas as pd

from src.graph.observation_model import (
    ObservationWeightingConfig,
    build_binary_adjacency_from_edges,
    build_ipw_adjacency_from_edges,
    compute_observation_completeness,
    summarize_completeness,
)


def test_observation_weighting_config_from_settings_defaults_and_clamps() -> None:
    cfg = ObservationWeightingConfig.from_settings({"obs_weighting": "ipw", "obs_p_min": 0.0, "obs_completeness_floor": 1.0})
    assert cfg.mode == "ipw"
    assert cfg.p_min == 1e-4
    assert cfg.completeness_floor == 0.5


def test_compute_observation_completeness_uses_expected_following() -> None:
    node_ids = np.array(["a", "b", "c"], dtype=object)
    edges = pd.DataFrame(
        {
            "source": ["a", "a", "b"],
            "target": ["b", "c", "a"],
            "mutual": [False, False, False],
        }
    )
    expected_following = {"a": 4, "b": 1, "c": 10}

    completeness = compute_observation_completeness(
        edges,
        node_ids,
        expected_following,
        completeness_floor=0.05,
    )

    # a: observed 2 / expected 4
    assert np.isclose(completeness[0], 0.5)
    # b: observed 1 / expected 1
    assert np.isclose(completeness[1], 1.0)
    # c: observed 0 / expected 10 -> clipped to floor
    assert np.isclose(completeness[2], 0.05)

    summary = summarize_completeness(completeness)
    assert summary["min"] == 0.05
    assert summary["max"] == 1.0


def test_build_binary_adjacency_adds_reverse_for_mutual_edges() -> None:
    node_ids = np.array(["a", "b", "c"], dtype=object)
    edges = pd.DataFrame(
        {
            "source": ["a", "b"],
            "target": ["b", "c"],
            "mutual": [True, False],
        }
    )

    adjacency = build_binary_adjacency_from_edges(edges, node_ids)

    # a->b and reverse b->a from mutual, plus b->c
    assert adjacency.count_nonzero() == 3
    assert adjacency[0, 1] == 1
    assert adjacency[1, 0] == 1
    assert adjacency[1, 2] == 1


def test_build_ipw_adjacency_weights_low_completeness_pairs_higher() -> None:
    node_ids = np.array(["a", "b", "c"], dtype=object)
    edges = pd.DataFrame(
        {
            "source": ["a", "c"],
            "target": ["b", "b"],
            "mutual": [False, False],
        }
    )
    completeness = np.array([0.5, 1.0, 0.2], dtype=np.float64)

    adjacency, stats = build_ipw_adjacency_from_edges(
        edges,
        node_ids,
        completeness,
        p_min=0.01,
    )

    # c->b should get larger weight than a->b because c has lower completeness.
    w_ab = float(adjacency[0, 1])
    w_cb = float(adjacency[2, 1])
    assert w_cb > w_ab

    assert stats["mode"] == "ipw"
    assert stats["observed_edges"] == 2
    assert stats["weighted_edges"] == 2
    assert stats["mean_weight"] > 1.0
