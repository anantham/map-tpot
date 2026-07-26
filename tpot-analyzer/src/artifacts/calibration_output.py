"""No-clobber persistence for calibration outputs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import numpy as np

from src.artifacts.calibration_record import validate_calibration_method_record
from src.graph.tpot_relevance import build_core_halo_mask


def save_calibration_outputs(
    output_dir,
    relevance,
    adjacency,
    *,
    tau,
    artifact_provenance,
    calibration_method,
    results=None,
):
    """Persist relevance and calibration without replacing existing outputs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    relevance = np.asarray(relevance)
    if relevance.ndim != 1:
        raise ValueError(
            f"relevance must be one-dimensional; got shape={relevance.shape}"
        )
    if adjacency.shape != (len(relevance), len(relevance)):
        raise ValueError(
            "adjacency shape must match relevance: "
            f"adjacency={adjacency.shape}, relevance={len(relevance)}"
        )
    validate_calibration_method_record(calibration_method)

    relevance_path = output_dir / "tpot_relevance_scores.npy"
    calibration_path = output_dir / "tpot_calibration.json"
    lock_path = output_dir / ".tpot_calibration.write.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Calibration writer already active: {lock_path}"
        ) from exc
    os.close(lock_fd)

    relevance_temp = output_dir / f".relevance.{uuid4().hex}.tmp"
    calibration_temp = output_dir / f".calibration.{uuid4().hex}.tmp"
    try:
        existing = [
            path
            for path in (relevance_path, calibration_path)
            if path.exists()
        ]
        if existing:
            raise FileExistsError(
                "Refusing to replace existing calibration outputs; choose a "
                f"new --output-dir. Existing={existing}"
            )

        mask = build_core_halo_mask(relevance, adjacency, tau)
        n_core = int((relevance >= tau).sum())
        record = {
            "tau": float(tau),
            "calibrated": True,
            "n_nodes_total": int(len(relevance)),
            "n_core": n_core,
            "n_halo": int(mask.sum() - n_core),
            "n_total": int(mask.sum()),
            "artifact_provenance": artifact_provenance,
            "calibration_method": calibration_method,
        }
        if results:
            record["sweep"] = results

        with relevance_temp.open("wb") as handle:
            np.save(handle, relevance.astype(np.float32))
        calibration_temp.write_text(json.dumps(record, indent=2))
        os.replace(relevance_temp, relevance_path)
        os.replace(calibration_temp, calibration_path)
        return record
    finally:
        relevance_temp.unlink(missing_ok=True)
        calibration_temp.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
