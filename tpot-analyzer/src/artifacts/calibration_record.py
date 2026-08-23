"""Build and validate reproducible TPOT calibration method records."""
from __future__ import annotations

import math
import re
from pathlib import Path

from src.artifacts.digests import file_sha256


class CalibrationRecordError(ValueError):
    """Raised when calibration method provenance is missing or invalid."""


METHOD_NAME = "recall_compactness_harmonic_utility"
METHOD_OBJECTIVE = (
    "harmonic_mean(holdout_positive_recall,"
    "one_minus_selected_graph_fraction)"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_CODE_ROLES = {
    "relevance_scorer",
    "threshold_selector",
    "calibrator",
}


def validate_calibration_method_record(record) -> None:
    """Reject missing or ambiguous calibration methodology provenance."""
    if not isinstance(record, dict):
        raise CalibrationRecordError("calibration_method must be an object")
    if record.get("name") != METHOD_NAME:
        raise CalibrationRecordError(
            f"calibration_method name must be {METHOD_NAME!r}; "
            f"got {record.get('name')!r}"
        )
    if record.get("objective") != METHOD_OBJECTIVE:
        raise CalibrationRecordError(
            f"calibration_method objective must be {METHOD_OBJECTIVE!r}; "
            f"got {record.get('objective')!r}"
        )

    recall_floor = record.get("recall_floor")
    tau_min = record.get("tau_min")
    tau_max = record.get("tau_max")
    numeric_values = {
        "recall_floor": recall_floor,
        "tau_min": tau_min,
        "tau_max": tau_max,
        "holdout_fraction": record.get("holdout_fraction"),
    }
    for field, value in numeric_values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise CalibrationRecordError(
                f"calibration_method {field} must be finite; got {value!r}"
            )
    if not 0.0 <= float(recall_floor) <= 1.0:
        raise CalibrationRecordError(
            f"calibration_method recall_floor must be in [0, 1]; got {recall_floor!r}"
        )
    if not 0.0 <= float(tau_min) <= float(tau_max) <= 1.0:
        raise CalibrationRecordError(
            "calibration_method tau bounds must satisfy "
            f"0 <= tau_min <= tau_max <= 1; got {tau_min!r}, {tau_max!r}"
        )
    fraction = float(record["holdout_fraction"])
    if not 0.0 < fraction < 1.0:
        raise CalibrationRecordError(
            "calibration_method holdout_fraction must be in (0, 1); "
            f"got {fraction!r}"
        )

    for field in ("tau_steps", "holdout_seed", "n_holdout", "n_train"):
        value = record.get(field)
        minimum = 0 if field == "holdout_seed" else 1
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
        ):
            raise CalibrationRecordError(
                f"calibration_method {field} must be an integer >= {minimum}; "
                f"got {value!r}"
            )
    holdout_file = record.get("holdout_file")
    if not isinstance(holdout_file, str) or not holdout_file.strip():
        raise CalibrationRecordError(
            "calibration_method holdout_file must be a non-empty string"
        )
    holdout_hash = record.get("holdout_file_sha256")
    if not isinstance(holdout_hash, str) or not _SHA256_PATTERN.fullmatch(
        holdout_hash
    ):
        raise CalibrationRecordError(
            "calibration_method holdout_file_sha256 must be 64 lowercase hex "
            f"characters; got {holdout_hash!r}"
        )
    code_files = record.get("code_files")
    if not isinstance(code_files, dict) or not code_files:
        raise CalibrationRecordError(
            "calibration_method code_files must be a non-empty object"
        )
    missing_roles = sorted(_REQUIRED_CODE_ROLES - set(code_files))
    if missing_roles:
        raise CalibrationRecordError(
            "calibration_method code_files is missing required roles: "
            f"{missing_roles}"
        )
    for label, code_record in code_files.items():
        if not isinstance(code_record, dict):
            raise CalibrationRecordError(
                f"calibration_method code_files.{label} must be an object"
            )
        filename = code_record.get("file")
        digest = code_record.get("sha256")
        if not isinstance(filename, str) or not filename.strip():
            raise CalibrationRecordError(
                f"calibration_method code_files.{label}.file is invalid"
            )
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise CalibrationRecordError(
                f"calibration_method code_files.{label}.sha256 is invalid"
            )


def validate_calibration_code_files(record, current_files) -> None:
    """Verify saved method hashes for code that a consumer executes again."""
    validate_calibration_method_record(record)
    for label, raw_path in current_files.items():
        path = Path(raw_path)
        saved = record["code_files"].get(label)
        if saved is None:
            raise CalibrationRecordError(
                f"calibration_method code_files is missing {label}"
            )
        observed_hash = file_sha256(path)
        if saved["sha256"] != observed_hash:
            raise CalibrationRecordError(
                f"calibration_method code_files.{label}.sha256="
                f"{saved['sha256']!r}, but current {path} is {observed_hash!r}"
            )


def build_calibration_method_record(
    *,
    recall_floor,
    tau_min,
    tau_max,
    tau_steps,
    holdout,
    holdout_path,
    code_files,
):
    """Build the exact method and input record saved with calibration."""
    holdout_path = Path(holdout_path)
    code_records = {
        str(label): {
            "file": str(Path(path).name),
            "sha256": file_sha256(Path(path)),
        }
        for label, path in sorted(code_files.items())
    }
    record = {
        "name": METHOD_NAME,
        "objective": METHOD_OBJECTIVE,
        "recall_floor": float(recall_floor),
        "tau_min": float(tau_min),
        "tau_max": float(tau_max),
        "tau_steps": int(tau_steps),
        "holdout_file": holdout_path.name,
        "holdout_file_sha256": file_sha256(holdout_path),
        "holdout_fraction": float(holdout["holdout_fraction"]),
        "holdout_seed": int(holdout["holdout_seed"]),
        "n_holdout": int(holdout["n_holdout"]),
        "n_train": int(holdout["n_train"]),
        "code_files": code_records,
    }
    validate_calibration_method_record(record)
    return record
