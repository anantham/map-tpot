"""Immutable model predictions kept structurally separate from human gold."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.artifacts.digests import json_sha256

from .frame_validation import (
    require_sha256,
    require_text,
    require_utc_aware,
)
from .prediction_contract import (
    SCORE_SEMANTICS,
    assert_payload_hash,
    score_value,
)
from .global_roles import verify_global_role_registry
from .ontology_contract import verified_study_community_ids
from .schema import now_iso
from .study_access import assert_study_open
from .study_binding import (
    validate_persisted_study_row,
    validate_study_binding,
)

class CommunityGoldPredictionMixin:
    """Store content-addressed model outputs outside the judgment head."""

    def record_prediction(
        self,
        *,
        prediction_id: str,
        frame_id: str,
        account_id: str,
        community_id: str,
        model_run_id: str,
        score: Any,
        score_semantics: str,
        evidence_snapshot_id: str,
        evidence_snapshot_hash: str,
        context_hash: str,
        observed_at: str,
        calibration_record_hash: Optional[str] = None,
        predicted_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        prediction = require_text(prediction_id, field="prediction_id")
        model_run = require_text(model_run_id, field="model_run_id")
        semantics = require_text(
            score_semantics,
            field="score_semantics",
        )
        if semantics not in SCORE_SEMANTICS:
            raise ValueError(
                "score_semantics must be one of: "
                f"{', '.join(sorted(SCORE_SEMANTICS))}"
            )
        parsed_score = score_value(score, semantics=semantics)
        calibration_hash = (
            require_sha256(
                calibration_record_hash,
                field="calibration_record_hash",
            )
            if calibration_record_hash is not None
            else None
        )
        if semantics == "calibrated_probability" and calibration_hash is None:
            raise ValueError(
                "calibration_record_hash is required for "
                "calibrated_probability"
            )
        if semantics == "calibrated_probability":
            raise ValueError(
                "calibrated_probability is not available until a compatible "
                "calibration record registry is implemented"
            )
        if calibration_hash is not None:
            raise ValueError(
                "calibration_record_hash must be null for uncalibrated scores"
            )
        with self._open() as conn:
            binding = validate_study_binding(
                self,
                conn,
                frame_id=frame_id,
                account_id=account_id,
                community_id=community_id,
                evidence_snapshot_id=evidence_snapshot_id,
                evidence_snapshot_hash=evidence_snapshot_hash,
                context_hash=context_hash,
                observed_at=observed_at,
            )
            existing = conn.execute(
                """
                SELECT *
                FROM account_community_prediction
                WHERE prediction_id = ?
                """,
                (prediction,),
            ).fetchone()
            effective_predicted_at = (
                predicted_at
                if predicted_at is not None
                else (
                    str(existing["predicted_at"])
                    if existing is not None
                    else now_iso()
                )
            )
            predicted = require_utc_aware(
                effective_predicted_at,
                field="predicted_at",
            )
            payload = {
                "predictionId": prediction,
                "frameId": binding.frame_id,
                "accountId": binding.account_id,
                "communityId": binding.community_id,
                "modelRunId": model_run,
                "score": parsed_score,
                "scoreSemantics": semantics,
                "calibrationRecordHash": calibration_hash,
                "evidenceSnapshotId": binding.evidence_snapshot_id,
                "evidenceSnapshotHash": binding.evidence_snapshot_hash,
                "contextHash": binding.context_hash,
                "observedAt": binding.observed_at,
                "predictedAt": predicted,
            }
            payload_hash = json_sha256(payload)
            if existing is not None:
                stored_payload = assert_payload_hash(existing)
                if (
                    str(existing["payload_hash"]) != payload_hash
                    or stored_payload != payload
                ):
                    raise ValueError(
                        f"immutable prediction '{prediction}' already exists "
                        "with different content"
                    )
                return {
                    "created": False,
                    **payload,
                    "payloadHash": payload_hash,
                    "ontologyScope": dict(binding.scope),
                    "role": binding.role,
                }
            semantic_existing = conn.execute(
                """
                SELECT prediction_id
                FROM account_community_prediction
                WHERE frame_id = ? AND account_id = ?
                  AND community_id = ? AND model_run_id = ?
                """,
                (
                    binding.frame_id,
                    binding.account_id,
                    binding.community_id,
                    model_run,
                ),
            ).fetchone()
            if semantic_existing is not None:
                raise ValueError(
                    "prediction generation already has a different immutable "
                    "prediction_id for this frame/account/community/model run: "
                    f"{semantic_existing['prediction_id']}"
                )
            conn.execute("BEGIN IMMEDIATE")
            try:
                assert_study_open(
                    conn,
                    frame_id=binding.frame_id,
                    operation="prediction writes",
                )
                conn.execute(
                    """
                    INSERT INTO account_community_prediction
                    (prediction_id, frame_id, account_id, community_id,
                     model_run_id, score, score_semantics,
                     calibration_record_hash, evidence_snapshot_id,
                     evidence_snapshot_hash, context_hash, observed_at,
                     predicted_at, payload_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prediction,
                        binding.frame_id,
                        binding.account_id,
                        binding.community_id,
                        model_run,
                        parsed_score,
                        semantics,
                        calibration_hash,
                        binding.evidence_snapshot_id,
                        binding.evidence_snapshot_hash,
                        binding.context_hash,
                        binding.observed_at,
                        predicted,
                        payload_hash,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "created": True,
            **payload,
            "payloadHash": payload_hash,
            "ontologyScope": dict(binding.scope),
            "role": binding.role,
        }

    def list_predictions(
        self,
        *,
        frame_id: str,
        model_run_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        parsed_frame = require_text(frame_id, field="frame_id")
        parsed_model = (
            require_text(model_run_id, field="model_run_id")
            if model_run_id is not None
            else None
        )
        model_clause = "AND model_run_id = ?" if parsed_model else ""
        params = (
            (parsed_frame, parsed_model)
            if parsed_model is not None
            else (parsed_frame,)
        )
        with self._open() as conn:
            frame = self._load_study_frame_with_conn(conn, parsed_frame)
            verify_global_role_registry(conn, frame=frame)
            self._verify_role_projection(conn, frame)
            ontology_communities = verified_study_community_ids(
                conn,
                scope=frame["scope"],
            )
            rows = conn.execute(
                f"""
                SELECT *
                FROM account_community_prediction
                WHERE frame_id = ? {model_clause}
                ORDER BY predicted_at ASC, prediction_id ASC
                """,
                params,
            ).fetchall()
            output = []
            for row in rows:
                role = validate_persisted_study_row(
                    row,
                    frame=frame,
                    ontology_community_ids=ontology_communities,
                )
                payload = assert_payload_hash(row)
                output.append(
                    {
                        **payload,
                        "payloadHash": str(row["payload_hash"]),
                        "ontologyScope": dict(frame["scope"]),
                        "role": role,
                    }
                )
        return output
