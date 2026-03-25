"""Routes for account-community gold labels and held-out split diagnostics."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request

from src.api.responses import error_response

from src.data.community_gold import CommunityGoldStore, EVALUATION_METHODS, SPLIT_NAMES

logger = logging.getLogger(__name__)

community_gold_bp = Blueprint("community_gold", __name__, url_prefix="/api/community-gold")

from src.config import DEFAULT_ARCHIVE_DB

_DEFAULT_DB = DEFAULT_ARCHIVE_DB
_community_gold_store: Optional[CommunityGoldStore] = None
_community_gold_store_path: Optional[Path] = None


def _get_db_path() -> Path:
    return Path(os.getenv("ARCHIVE_DB_PATH", str(_DEFAULT_DB)))


def _get_store() -> CommunityGoldStore:
    global _community_gold_store, _community_gold_store_path
    db_path = _get_db_path()
    if _community_gold_store is None or _community_gold_store_path != db_path:
        _community_gold_store = CommunityGoldStore(db_path)
        _community_gold_store_path = db_path
    return _community_gold_store


def _parse_limit(raw: Optional[str], *, default: int = 100, maximum: int = 1000) -> int:
    parsed = int(raw or default)
    return max(1, min(maximum, parsed))


def _parse_split(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip().lower()
    if not value or value == "all":
        return None
    if value not in SPLIT_NAMES:
        raise ValueError("split must be one of: train, dev, test, all")
    return value


def _parse_bool(raw: Optional[str]) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


@community_gold_bp.route("/communities", methods=["GET"])
def list_communities():
    try:
        return jsonify({"communities": _get_store().list_communities()})
    except RuntimeError as exc:
        logger.error("Community gold communities failed: %s", exc)
        return error_response("Failed to list communities", status=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold communities failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@community_gold_bp.route("/labels", methods=["GET"])
def get_labels():
    try:
        labels = _get_store().list_labels(
            community_id=(request.args.get("communityId") or request.args.get("community_id") or "").strip() or None,
            account_id=(request.args.get("accountId") or request.args.get("account_id") or "").strip() or None,
            split=_parse_split(request.args.get("split")),
            reviewer=(request.args.get("reviewer") or "").strip() or None,
            judgment=(request.args.get("judgment") or "").strip() or None,
            include_inactive=_parse_bool(request.args.get("includeInactive") or request.args.get("include_inactive")),
            limit=_parse_limit(request.args.get("limit")),
        )
        return jsonify({"labels": labels, "count": len(labels)})
    except ValueError as exc:
        return error_response(str(exc))
    except RuntimeError as exc:
        logger.error("Community gold labels query failed: %s", exc)
        return error_response("Failed to query labels", status=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold labels query failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@community_gold_bp.route("/labels", methods=["POST"])
def upsert_label():
    data = request.get_json(silent=True) or {}
    try:
        account_id = str(data.get("accountId") or data.get("account_id") or "").strip()
        community_id = str(data.get("communityId") or data.get("community_id") or "").strip()
        reviewer = str(data.get("reviewer") or "human").strip() or "human"
        if not account_id:
            raise ValueError("accountId is required")
        if not community_id:
            raise ValueError("communityId is required")
        result = _get_store().upsert_label(
            account_id=account_id,
            community_id=community_id,
            reviewer=reviewer,
            judgment=data.get("judgment"),
            confidence=data.get("confidence"),
            note=data.get("note"),
            evidence=data.get("evidence"),
        )
        return jsonify({"status": "ok", **result})
    except ValueError as exc:
        return error_response(str(exc))
    except RuntimeError as exc:
        logger.error("Community gold label upsert failed: %s", exc)
        return error_response("Failed to save label", status=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold label upsert failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@community_gold_bp.route("/labels", methods=["DELETE"])
def clear_label():
    data = request.get_json(silent=True) or {}
    try:
        account_id = str(
            data.get("accountId")
            or data.get("account_id")
            or request.args.get("accountId")
            or request.args.get("account_id")
            or ""
        ).strip()
        community_id = str(
            data.get("communityId")
            or data.get("community_id")
            or request.args.get("communityId")
            or request.args.get("community_id")
            or ""
        ).strip()
        reviewer = str(data.get("reviewer") or request.args.get("reviewer") or "human").strip() or "human"
        if not account_id or not community_id:
            raise ValueError("accountId and communityId are required")
        cleared = _get_store().clear_label(
            account_id=account_id,
            community_id=community_id,
            reviewer=reviewer,
        )
        return jsonify({"status": "deleted" if cleared else "not_found"})
    except ValueError as exc:
        return error_response(str(exc))
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold label delete failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@community_gold_bp.route("/metrics", methods=["GET"])
def get_metrics():
    try:
        return jsonify(_get_store().metrics())
    except RuntimeError as exc:
        logger.error("Community gold metrics failed: %s", exc)
        return error_response("Failed to compute metrics", status=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold metrics failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@community_gold_bp.route("/candidates", methods=["GET"])
def get_candidates():
    try:
        candidates = _get_store().list_review_candidates(
            reviewer=(request.args.get("reviewer") or "human").strip() or "human",
            limit=_parse_limit(request.args.get("limit"), default=20, maximum=200),
            split=_parse_split(request.args.get("split")),
            community_id=(request.args.get("communityId") or request.args.get("community_id") or "").strip() or None,
        )
        return jsonify({"candidates": candidates, "count": len(candidates)})
    except ValueError as exc:
        return error_response(str(exc))
    except RuntimeError as exc:
        logger.error("Community gold candidate queue failed: %s", exc)
        return error_response("Failed to list candidates", status=500)
    except FileNotFoundError as exc:
        logger.error("Community gold candidate artifact missing: %s", exc)
        return error_response("Required data artifact not found", status=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold candidate queue failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@community_gold_bp.route("/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json(silent=True) or {}
    try:
        split = _parse_split(str(data.get("split") or "dev")) or "dev"
        train_split = _parse_split(str(data.get("trainSplit") or data.get("train_split") or "train")) or "train"
        reviewer = str(data.get("reviewer") or "human").strip() or "human"
        methods = data.get("methods") or list(EVALUATION_METHODS)
        if not isinstance(methods, list):
            raise ValueError("methods must be a list")
        communities = data.get("communityIds") or data.get("community_ids")
        if communities is not None and not isinstance(communities, list):
            raise ValueError("communityIds must be a list")
        result = _get_store().evaluate_scoreboard(
            split=split,
            reviewer=reviewer,
            train_split=train_split,
            methods=methods,
            community_ids=communities,
        )
        return jsonify(result)
    except ValueError as exc:
        return error_response(str(exc))
    except RuntimeError as exc:
        logger.error("Community gold evaluation failed: %s", exc)
        return error_response("Evaluation failed", status=500)
    except FileNotFoundError as exc:
        logger.error("Community gold evaluation artifact missing: %s", exc)
        return error_response("Required data artifact not found", status=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Community gold evaluation failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500
