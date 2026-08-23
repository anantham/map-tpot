"""Versioned ontology, study, judgment, and prediction HTTP contracts."""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.data.community_gold.terminal_delivery import (
    TerminalReleaseConflict,
)

from . import community_gold as legacy_routes

logger = logging.getLogger(__name__)

community_gold_integrity_bp = Blueprint(
    "community_gold_integrity",
    __name__,
    url_prefix="/api/community-gold",
)


def _endpoint(handler: Callable[..., Any]) -> Callable[..., Any]:
    """Return consistent, descriptive validation and internal errors."""

    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any):
        try:
            return handler(*args, **kwargs)
        except TerminalReleaseConflict as exc:
            return error_response(str(exc), status=409)
        except ValueError as exc:
            return error_response(str(exc))
        except RuntimeError as exc:
            logger.error(
                "Community Gold integrity operation failed in %s: %s",
                handler.__name__,
                exc,
            )
            return error_response(
                "Community Gold integrity operation failed",
                status=500,
            )
        except Exception as exc:  # pragma: no cover - defensive API boundary
            logger.exception(
                "Unexpected Community Gold integrity failure in %s: %s",
                handler.__name__,
                exc,
            )
            return error_response("internal_error", status=500)

    return wrapped


def _body() -> Dict[str, Any]:
    value = request.get_json(silent=True)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    return value


def _status_for(result: Dict[str, Any]) -> int:
    return 201 if result.get("created") is True else 200


_PRIVATE_STUDY_FIELDS = frozenset(
    {
        "u0AccountIds",
        "fixedTrainingIds",
        "fixedChallengeIds",
        "uEvalAccountIds",
        "uRichAccountIds",
        "strataByAccount",
        "roleAssignments",
        "roleAssignmentsDigest",
    }
)


def _study_for_http(study: Dict[str, Any]) -> Dict[str, Any]:
    """Return study metadata without account-level role disclosure."""

    result = {
        key: value
        for key, value in study.items()
        if key not in _PRIVATE_STUDY_FIELDS
    }
    registry = result.get("roleRegistry")
    if isinstance(registry, dict):
        result["roleRegistry"] = {
            key: value
            for key, value in registry.items()
            if key != "seed"
        }
    result["roleIdentitiesWithheld"] = True
    return result


def _without_role(record: Dict[str, Any]) -> Dict[str, Any]:
    """Keep internal allocation roles out of curator-facing payloads."""

    return {
        key: value
        for key, value in record.items()
        if key != "role"
    }


@community_gold_integrity_bp.post("/ontologies")
@curator_only
@_endpoint
def register_ontology():
    data = _body()
    result = legacy_routes._get_store().register_ontology_version(
        user_id=data.get("userId"),
        ontology_id=data.get("ontologyId"),
        ontology_version=data.get("ontologyVersion"),
        definition=data.get("definition"),
        supersedes_version=data.get("supersedesVersion"),
    )
    return jsonify({"status": "ok", **result}), _status_for(result)


@community_gold_integrity_bp.post("/tasks")
@curator_only
@_endpoint
def register_task():
    data = _body()
    result = legacy_routes._get_store().register_ontology_task(
        user_id=data.get("userId"),
        ontology_id=data.get("ontologyId"),
        ontology_version=data.get("ontologyVersion"),
        task_id=data.get("taskId"),
        target_type=data.get("targetType"),
        definition=data.get("definition"),
    )
    return jsonify({"status": "ok", **result}), _status_for(result)


@community_gold_integrity_bp.post("/studies")
@curator_only
@_endpoint
def freeze_study():
    data = _body()
    frame = data.get("frame")
    if not isinstance(frame, dict):
        raise ValueError("frame must be a JSON object")
    result = legacy_routes._get_store().freeze_study(frame)
    return jsonify({"status": "ok", **result}), _status_for(result)


@community_gold_integrity_bp.get("/studies/<frame_id>")
@curator_only
@_endpoint
def get_study(frame_id: str):
    study = legacy_routes._get_store().get_study(frame_id)
    return jsonify(_study_for_http(study))


@community_gold_integrity_bp.post("/studies/<frame_id>/judgments")
@curator_only
@_endpoint
def record_judgment(frame_id: str):
    data = _body()
    result = legacy_routes._get_store().record_study_judgment(
        frame_id=frame_id,
        account_id=data.get("accountId"),
        community_id=data.get("communityId"),
        reviewer=data.get("reviewer"),
        judgment=data.get("judgment"),
        confidence=data.get("confidence"),
        note=data.get("note"),
        evidence=data.get("evidence"),
        evidence_snapshot_id=data.get("evidenceSnapshotId"),
        evidence_snapshot_hash=data.get("evidenceSnapshotHash"),
        context_hash=data.get("contextHash"),
        observed_at=data.get("observedAt"),
    )
    return jsonify({"status": "ok", **_without_role(result)}), 201


@community_gold_integrity_bp.get("/studies/<frame_id>/judgments")
@curator_only
@_endpoint
def list_judgments(frame_id: str):
    purpose = str(request.args.get("purpose") or "").strip()
    if purpose == "terminal_evaluation":
        raise ValueError(
            "terminal_evaluation requires the one-use terminal-test endpoint"
        )
    rows = legacy_routes._get_store().list_study_judgments(
        frame_id=frame_id,
        purpose=purpose,
        reviewer=(request.args.get("reviewer") or "").strip() or None,
    )
    public_rows = [_without_role(row) for row in rows]
    return jsonify({"judgments": public_rows, "count": len(public_rows)})


@community_gold_integrity_bp.post(
    "/studies/<frame_id>/terminal-test"
)
@curator_only
@_endpoint
def release_terminal_test(frame_id: str):
    data = _body()
    store = legacy_routes._get_store()
    release = store.release_terminal_test(
        frame_id=frame_id,
        reviewer=str(data.get("reviewer") or "").strip() or None,
        accessed_by=data.get("accessedBy"),
        access_receipt=data.get("accessReceipt"),
    )
    public_rows = [
        _without_role(row)
        for row in release["judgments"]
    ]
    return jsonify(
        {
            "judgments": public_rows,
            "count": len(public_rows),
            "terminalAccess": release["terminalAccess"],
            "replayed": release["replayed"],
        }
    )


@community_gold_integrity_bp.post("/predictions")
@curator_only
@_endpoint
def record_prediction():
    data = _body()
    result = legacy_routes._get_store().record_prediction(
        prediction_id=data.get("predictionId"),
        frame_id=data.get("frameId"),
        account_id=data.get("accountId"),
        community_id=data.get("communityId"),
        model_run_id=data.get("modelRunId"),
        score=data.get("score"),
        score_semantics=data.get("scoreSemantics"),
        calibration_record_hash=data.get("calibrationRecordHash"),
        evidence_snapshot_id=data.get("evidenceSnapshotId"),
        evidence_snapshot_hash=data.get("evidenceSnapshotHash"),
        context_hash=data.get("contextHash"),
        observed_at=data.get("observedAt"),
        predicted_at=data.get("predictedAt"),
    )
    public_result = _without_role(result)
    return jsonify({"status": "ok", **public_result}), _status_for(result)


@community_gold_integrity_bp.get("/predictions")
@curator_only
@_endpoint
def list_predictions():
    frame_id = str(request.args.get("frameId") or "").strip()
    rows = legacy_routes._get_store().list_predictions(
        frame_id=frame_id,
        model_run_id=(
            str(request.args.get("modelRunId") or "").strip() or None
        ),
    )
    public_rows = [_without_role(row) for row in rows]
    return jsonify({"predictions": public_rows, "count": len(public_rows)})
