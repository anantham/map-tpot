"""Score semantics and content-address checks for model predictions."""
from __future__ import annotations

import math
from typing import Any, Dict

from src.artifacts.digests import json_sha256

from .frame_validation import (
    require_sha256,
    require_text,
    require_utc_aware,
)

SCORE_SEMANTICS = frozenset(
    {"simplex", "lift", "affinity", "calibrated_probability"}
)


def score_value(value: Any, *, semantics: str) -> float:
    if semantics not in SCORE_SEMANTICS:
        raise ValueError(
            "score_semantics must be one of: "
            f"{', '.join(sorted(SCORE_SEMANTICS))}"
        )
    if isinstance(value, bool):
        raise ValueError("score must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("score must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ValueError("score must be a finite number")
    if semantics in {"simplex", "calibrated_probability"}:
        if not 0.0 <= parsed <= 1.0:
            raise ValueError(f"{semantics} score must be in [0, 1]")
    elif semantics == "lift" and parsed < 0.0:
        raise ValueError("lift score must be non-negative")
    return parsed


def payload_from_row(row: Any) -> Dict[str, Any]:
    semantics = require_text(
        row["score_semantics"],
        field="stored score_semantics",
    )
    score = score_value(row["score"], semantics=semantics)
    calibration_hash = row["calibration_record_hash"]
    if calibration_hash is not None:
        calibration_hash = require_sha256(
            calibration_hash,
            field="stored calibration_record_hash",
        )
    if semantics != "calibrated_probability" and calibration_hash is not None:
        raise ValueError(
            "calibration_record_hash must be null for uncalibrated scores"
        )
    return {
        "predictionId": require_text(
            row["prediction_id"], field="stored prediction_id"
        ),
        "frameId": require_text(
            row["frame_id"], field="stored frame_id"
        ),
        "accountId": require_text(
            row["account_id"], field="stored account_id"
        ),
        "communityId": require_text(
            row["community_id"], field="stored community_id"
        ),
        "modelRunId": require_text(
            row["model_run_id"], field="stored model_run_id"
        ),
        "score": score,
        "scoreSemantics": semantics,
        "calibrationRecordHash": calibration_hash,
        "evidenceSnapshotId": require_text(
            row["evidence_snapshot_id"],
            field="stored evidence_snapshot_id",
        ),
        "evidenceSnapshotHash": require_sha256(
            row["evidence_snapshot_hash"],
            field="stored evidence_snapshot_hash",
        ),
        "contextHash": require_sha256(
            row["context_hash"], field="stored context_hash"
        ),
        "observedAt": require_utc_aware(
            row["observed_at"], field="stored observed_at"
        ),
        "predictedAt": require_utc_aware(
            row["predicted_at"], field="stored predicted_at"
        ),
    }


def assert_payload_hash(row: Any) -> Dict[str, Any]:
    payload = payload_from_row(row)
    observed = json_sha256(payload)
    expected = str(row["payload_hash"])
    if observed != expected:
        raise ValueError(
            "prediction payload hash mismatch: "
            f"prediction_id={row['prediction_id']}, "
            f"expected={expected}, observed={observed}"
        )
    if payload["scoreSemantics"] == "calibrated_probability":
        raise ValueError(
            "stored calibrated_probability is invalid because no compatible "
            "calibration record registry exists"
        )
    return payload
