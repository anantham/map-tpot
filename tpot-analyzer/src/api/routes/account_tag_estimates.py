"""Curator-private routes for subjective account-tag estimate trajectories."""
from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request

from src.api.curation_source import require_curation_source
from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.config import get_snapshot_dir
from src.data.account_tag_estimates import AccountTagEstimateStore
from src.data.tag_meta_notes import normalize_ego, normalize_tag


logger = logging.getLogger(__name__)
account_tag_estimates_bp = Blueprint(
    "account_tag_estimates", __name__, url_prefix="/api"
)
_estimate_store: Optional[AccountTagEstimateStore] = None


def _get_estimate_store() -> AccountTagEstimateStore:
    global _estimate_store
    if _estimate_store is None:
        _estimate_store = AccountTagEstimateStore(
            Path(get_snapshot_dir()) / "account_tags.db"
        )
    return _estimate_store


def _require_subject(account_id: str) -> tuple[str, str, str]:
    raw_ego = request.args.get("ego")
    raw_tag = request.args.get("tag")
    if raw_ego is None:
        raise ValueError("ego query param is required")
    if raw_tag is None:
        raise ValueError("tag query param is required")
    ego = normalize_ego(raw_ego)
    _, tag_display = normalize_tag(raw_tag)
    normalized_account = str(account_id).strip()
    if not normalized_account:
        raise ValueError("account_id cannot be empty")
    return ego, normalized_account, tag_display


@account_tag_estimates_bp.route(
    "/accounts/<account_id>/tag-estimates", methods=["GET"]
)
@curator_only
def get_account_tag_estimates(account_id: str):
    try:
        ego, normalized_account, tag = _require_subject(account_id)
        current, history = _get_estimate_store().get_estimates(
            ego=ego,
            account_id=normalized_account,
            tag=tag,
        )
    except ValueError as exc:
        return error_response(str(exc))
    except Exception:
        logger.exception(
            "Estimate trajectory read failed account=%s", account_id
        )
        return error_response(
            "estimate trajectory read failed; inspect the API log", status=500
        )
    response = jsonify({
        "ego": ego,
        "accountId": normalized_account,
        "tag": tag,
        "current": asdict(current) if current is not None else None,
        "history": [asdict(row) for row in history],
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response


@account_tag_estimates_bp.route(
    "/accounts/<account_id>/tag-estimates", methods=["POST"]
)
@curator_only
def append_account_tag_estimate(account_id: str):
    try:
        ego, normalized_account, tag = _require_subject(account_id)
        source = require_curation_source(request)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        saved = _get_estimate_store().append_estimate(
            ego=ego,
            account_id=normalized_account,
            tag=tag,
            point_estimate=data.get("pointEstimate"),
            plausible_low=data.get("plausibleLow"),
            plausible_high=data.get("plausibleHigh"),
            review_session_id=data.get("reviewSessionId"),
            source=source,
        )
        _, history = _get_estimate_store().get_estimates(
            ego=ego,
            account_id=normalized_account,
            tag=tag,
        )
    except ValueError as exc:
        logger.info(
            "Rejected estimate input ego=%r account=%s tag=%r: %s",
            request.args.get("ego"),
            account_id,
            request.args.get("tag"),
            exc,
        )
        return error_response(str(exc))
    except Exception:
        logger.exception(
            "Estimate trajectory append failed account=%s", account_id
        )
        return error_response(
            "estimate trajectory append failed; inspect the API log", status=500
        )
    return jsonify({
        "status": "appended",
        "current": asdict(saved),
        "history": [asdict(row) for row in history],
    })
