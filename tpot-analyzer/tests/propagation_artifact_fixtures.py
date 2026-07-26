from __future__ import annotations

import numpy as np


def write_propagation(
    path,
    node_ids,
    *,
    offset=0,
    include_optional=False,
    extra_arrays=None,
):
    node_ids = np.asarray(node_ids)
    rows = np.arange(len(node_ids), dtype=np.float32) + offset
    arrays = {
        "node_ids": node_ids,
        "memberships": np.tile(
            np.array([[0.6, 0.3, 0.1]], dtype=np.float32),
            (len(node_ids), 1),
        ),
        "uncertainty": (
            np.arange(1, len(node_ids) + 1, dtype=np.float32)
            / (len(node_ids) + 1)
        ),
        "abstain_mask": rows.astype(int) % 2 == 0,
        "labeled_mask": rows.astype(int) % 2 == 1,
        "community_ids": np.array(["c1", "c2"]),
        "community_names": np.array(["one", "two"]),
        "community_colors": np.array(["#111111", "#222222"]),
        "converged": np.array([True, True, True]),
        "cg_iterations": np.array([1, 2, 3]),
        "mode": np.array("independent"),
    }
    if include_optional:
        arrays["seed_neighbor_counts"] = np.column_stack((rows, rows + 10))
        arrays["stability"] = np.column_stack((rows + 20, rows + 30))
        arrays["confidence_intervals"] = np.stack(
            (
                np.column_stack((rows + 40, rows + 50)),
                np.column_stack((rows + 60, rows + 70)),
            ),
            axis=2,
        )
    arrays.update(extra_arrays or {})
    np.savez(path, **arrays)
