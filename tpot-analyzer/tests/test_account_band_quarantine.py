"""Behavioral boundaries for unbound legacy ``account_band`` rows."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from scripts._export_helpers._community_extractors import (
    extract_band_accounts,
)
from scripts.rank_frontier import load_band_data


def _write_band_table(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_band (
                account_id TEXT PRIMARY KEY,
                band TEXT NOT NULL
            );
            INSERT INTO account_band VALUES ('account-1', 'specialist');
            """
        )


def _write_valid_classic_artifact(npz_path) -> None:
    np.savez(
        npz_path,
        mode=np.array("classic"),
        memberships=np.array([[0.7, 0.2, 0.1]]),
        node_ids=np.array(["account-1"]),
        community_ids=np.array(["alpha", "beta"]),
        abstain_mask=np.array([False]),
        labeled_mask=np.array([False]),
    )


def test_band_export_rejects_unbound_table_with_valid_classic_artifact(
    tmp_path,
) -> None:
    """An unrelated classic NPZ must not legitimize stale SQLite rows."""
    db_path = tmp_path / "archive.db"
    npz_path = tmp_path / "community_propagation.npz"
    _write_band_table(db_path)
    _write_valid_classic_artifact(npz_path)

    with pytest.raises(RuntimeError, match="account_band.*quarantined"):
        extract_band_accounts(db_path=db_path, npz_path=npz_path)


def test_frontier_ranker_rejects_unbound_table_at_loader_boundary() -> None:
    """Direct callers must not bypass the ranker's CLI guard."""
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            "CREATE TABLE account_band "
            "(account_id TEXT PRIMARY KEY, band TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO account_band VALUES ('account-1', 'frontier')"
        )

        with pytest.raises(RuntimeError, match="account_band.*quarantined"):
            load_band_data(conn)
