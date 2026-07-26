from __future__ import annotations

import sys

import pytest

from scripts import build_tpot_spectral, calibrate_tpot_threshold


def test_tpot_builder_refuses_existing_flat_bundle(tmp_path, monkeypatch):
    (tmp_path / "graph_snapshot_tpot.spectral.npz").write_bytes(b"existing")
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_tpot_spectral", "--data-dir", str(tmp_path)],
    )

    with pytest.raises(FileExistsError, match="non-atomic overwrite"):
        build_tpot_spectral.main()


def test_tpot_builder_rejects_invalid_or_ambiguous_threshold_args(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_tpot_spectral", "--data-dir", str(tmp_path), "--tau", "nan"],
    )
    with pytest.raises(ValueError, match="finite and in"):
        build_tpot_spectral.main()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_tpot_spectral",
            "--data-dir",
            str(tmp_path),
            "--tau",
            "0.1",
            "--calibration-path",
            str(tmp_path / "calibration.json"),
        ],
    )
    with pytest.raises(ValueError, match="either --tau or --calibration-path"):
        build_tpot_spectral.main()


def test_calibrator_refuses_existing_output_generation(tmp_path, monkeypatch):
    (tmp_path / "tpot_calibration.json").write_text("{}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["calibrate_tpot_threshold", "--data-dir", str(tmp_path)],
    )

    with pytest.raises(FileExistsError, match="Refusing to replace"):
        calibrate_tpot_threshold.main()
