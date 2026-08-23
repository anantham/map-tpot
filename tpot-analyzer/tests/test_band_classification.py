"""Behavioral regressions for display-band safety and artifact contracts."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from scripts.analyze_frontier_confidence import (
    load_propagation as load_frontier_analysis_propagation,
)
from scripts.classify_bands import classify_bands
from scripts._export_helpers._community_extractors import (
    _load_npz_memberships,
    extract_band_accounts,
)
from scripts.rank_frontier import load_propagation as load_frontier_propagation


def _write_minimal_band_db(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_band (
                account_id TEXT PRIMARY KEY,
                band TEXT NOT NULL,
                top_weight REAL,
                entropy REAL,
                none_weight REAL
            );
            INSERT INTO account_band
            VALUES ('account-1', 'unknown', 2.0, -3.0, 0.1);

            CREATE TABLE profiles (account_id TEXT, username TEXT);
            INSERT INTO profiles VALUES ('account-1', 'example');

            CREATE TABLE community_account (
                account_id TEXT,
                community_id TEXT,
                weight REAL
            );
            """
        )


def test_independent_band_classification_fails_closed() -> None:
    """Unvalidated Lift thresholds must not create authoritative band rows."""
    propagation = {
        "memberships": np.array([[6.0, 3.0, 0.2]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_names": np.array(["Alpha", "Beta"]),
        "seed_neighbor_counts": np.array([[1, 1]]),
        "independent_mode": True,
    }

    with pytest.raises(RuntimeError, match="independent.*band"):
        classify_bands(propagation)


def test_classic_band_classification_preserves_legacy_partial_entropy() -> None:
    """The safety slice must not silently retune historical classic bands."""
    community_weights = np.array([0.3] + [0.4 / 15] * 15)
    propagation = {
        "mode": "classic",
        "memberships": np.array([[*community_weights, 0.3]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_names": np.array([f"community-{i}" for i in range(16)]),
    }

    result = classify_bands(propagation)

    assert result["band"].tolist() == ["specialist"]
    assert result["entropy"][0] == pytest.approx(0.653, abs=0.001)


def test_lift_rows_cannot_masquerade_as_classic() -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array([[2.0, 1.0, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_names": np.array(["Alpha", "Beta"]),
    }

    with pytest.raises(RuntimeError, match="classic.*simplex"):
        classify_bands(propagation)


def test_band_artifact_requires_an_explicit_mode() -> None:
    propagation = {
        "memberships": np.array([[0.6, 0.3, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_names": np.array(["Alpha", "Beta"]),
    }

    with pytest.raises(RuntimeError, match="mode.*undeclared"):
        classify_bands(propagation)


def test_band_artifact_rejects_membership_node_mismatch() -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array([[0.6, 0.3, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1", "account-2"]),
        "community_names": np.array(["Alpha", "Beta"]),
    }

    with pytest.raises(RuntimeError, match="rows must match node_ids"):
        classify_bands(propagation)


def test_band_artifact_rejects_community_dimension_mismatch() -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array([[0.6, 0.3, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_ids": np.array(["alpha"]),
        "community_names": np.array(["Alpha", "Beta"]),
    }

    with pytest.raises(RuntimeError, match="identity lengths disagree"):
        classify_bands(propagation)


def test_band_artifact_requires_community_identity() -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array([[0.6, 0.3, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
    }

    with pytest.raises(RuntimeError, match="community_ids/community_names"):
        classify_bands(propagation)


def test_band_classification_accepts_community_ids_as_identity() -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array([[0.6, 0.3, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_ids": np.array(["alpha", "beta"]),
    }

    result = classify_bands(propagation)

    assert result["top_community_idx"].tolist() == [0]


@pytest.mark.parametrize("mask_key", ["abstain_mask", "labeled_mask"])
def test_band_artifact_rejects_broadcastable_mask_length(mask_key) -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array(
            [[0.6, 0.3, 0.1], [0.2, 0.7, 0.1]]
        ),
        "abstain_mask": np.array([False, False]),
        "labeled_mask": np.array([False, False]),
        "node_ids": np.array(["account-1", "account-2"]),
        "community_names": np.array(["Alpha", "Beta"]),
    }
    propagation[mask_key] = np.array([False])

    with pytest.raises(RuntimeError, match=rf"{mask_key}.*shape"):
        classify_bands(propagation)


@pytest.mark.parametrize("mask_key", ["abstain_mask", "labeled_mask"])
def test_band_artifact_rejects_non_boolean_mask(mask_key) -> None:
    propagation = {
        "mode": "classic",
        "memberships": np.array([[0.6, 0.3, 0.1]]),
        "abstain_mask": np.array([False]),
        "labeled_mask": np.array([False]),
        "node_ids": np.array(["account-1"]),
        "community_names": np.array(["Alpha", "Beta"]),
    }
    propagation[mask_key] = np.array([0], dtype=np.int64)

    with pytest.raises(RuntimeError, match=rf"{mask_key}.*boolean"):
        classify_bands(propagation)


def test_npz_membership_mode_comes_from_explicit_mode_not_snc(tmp_path) -> None:
    npz_path = tmp_path / "classic-with-snc.npz"
    np.savez(
        npz_path,
        mode=np.array("classic"),
        memberships=np.array([[0.6, 0.3, 0.1]]),
        node_ids=np.array(["account-1"]),
        community_ids=np.array(["alpha", "beta"]),
        seed_neighbor_counts=np.array([[0, 0]]),
    )

    memberships = _load_npz_memberships(npz_path)

    assert [row["community_id"] for row in memberships["account-1"]] == [
        "alpha",
        "beta",
    ]
    assert all(
        "seed_neighbors" not in row for row in memberships["account-1"]
    )


def test_export_rejects_unbound_table_before_independent_artifact(tmp_path) -> None:
    """Artifact mode cannot legitimize a table without an exact receipt."""
    db_path = tmp_path / "archive.db"
    _write_minimal_band_db(db_path)

    npz_path = tmp_path / "community_propagation.npz"
    np.savez(
        npz_path,
        mode=np.array("independent"),
        memberships=np.array([[2.0, 0.1]]),
        node_ids=np.array(["account-1"]),
        community_ids=np.array(["community-1"]),
        seed_neighbor_counts=np.array([[0]]),
    )

    with pytest.raises(RuntimeError, match="account_band.*quarantined"):
        extract_band_accounts(db_path=db_path, npz_path=npz_path)


def test_export_rejects_unbound_table_before_missing_artifact(tmp_path) -> None:
    db_path = tmp_path / "archive.db"
    _write_minimal_band_db(db_path)

    with pytest.raises(RuntimeError, match="account_band.*quarantined"):
        extract_band_accounts(
            db_path=db_path,
            npz_path=tmp_path / "missing.npz",
        )


def test_frontier_ranker_rejects_independent_band_artifact(tmp_path) -> None:
    """Invalid bands and synthetic none-Lift must not steer acquisition."""
    npz_path = tmp_path / "community_propagation.npz"
    np.savez(
        npz_path,
        mode=np.array("independent"),
        memberships=np.array([[2.0, 0.1]]),
        uncertainty=np.array([0.0]),
        node_ids=np.array(["account-1"]),
        community_names=np.array(["community-1"]),
        seed_neighbor_counts=np.array([[0]]),
    )

    with pytest.raises(RuntimeError, match="independent.*band"):
        load_frontier_propagation(npz_path)


def test_frontier_confidence_analysis_rejects_independent_bands(
    tmp_path,
) -> None:
    """Compositional Lift spread must not be relabeled as confidence."""
    npz_path = tmp_path / "community_propagation.npz"
    np.savez(
        npz_path,
        mode=np.array("independent"),
        memberships=np.array([[2.0, 0.1]]),
        seed_neighbor_counts=np.array([[0]]),
    )

    with pytest.raises(RuntimeError, match="independent.*band"):
        load_frontier_analysis_propagation(npz_path)
