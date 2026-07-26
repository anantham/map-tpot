"""Load and bind a TPOT threshold to graph/propagation compatibility."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.artifacts.calibration_record import validate_calibration_code_files
from src.artifacts.digests import file_sha256
from src.artifacts.provenance import validate_calibration_compatibility


@dataclass(frozen=True)
class BoundThreshold:
    tau: float
    calibration: dict | None
    record: dict


def load_bound_threshold(
    data_dir,
    *,
    explicit_tau,
    calibration_path,
    provenance,
    relevance_scorer_path,
) -> BoundThreshold:
    """Return an explicit or provenance-bound threshold record."""
    data_dir = Path(data_dir)
    if explicit_tau is not None:
        return BoundThreshold(
            tau=float(explicit_tau),
            calibration=None,
            record={
                "source": "cli",
                "status": "explicit-override",
                "tau": float(explicit_tau),
            },
        )

    path = Path(calibration_path) if calibration_path else (
        data_dir / "tpot_calibration.json"
    )
    if not path.exists():
        raise FileNotFoundError(
            f"No calibration found at {path}. Run calibrated holdout "
            "evaluation first or pass --tau explicitly."
        )
    calibration = json.loads(path.read_text())
    status = validate_calibration_compatibility(calibration, provenance)
    record = {
        "source": path.name,
        "file_sha256": file_sha256(path),
        "status": status,
        "tau": float(calibration["tau"]),
    }
    if status == "compatibility-record-bound":
        validate_calibration_code_files(
            calibration["calibration_method"],
            {"relevance_scorer": Path(relevance_scorer_path)},
        )
        record["method_code_status"] = (
            "current-relevance-scorer-sha256-verified"
        )
    return BoundThreshold(
        tau=float(calibration["tau"]),
        calibration=calibration,
        record=record,
    )
