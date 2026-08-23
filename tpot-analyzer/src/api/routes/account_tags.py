"""Curator-private routes for mutable, ego-scoped account tags."""
from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.config import get_snapshot_dir
from src.data.account_tags import AccountTagStore
from src.data.tag_meta_notes import (
    TagMetaNoteStore,
    normalize_ego,
    normalize_tag,
)

logger = logging.getLogger(__name__)

account_tags_bp = Blueprint("account_tags", __name__, url_prefix="/api")
_tag_store: Optional[AccountTagStore] = None
_meta_note_store: Optional[TagMetaNoteStore] = None
_SOURCE_HEADER = "X-TPOT-Curation-Source"
_ALLOWED_SOURCES = {
    "agent_assisted_curator",
    "human_curator_api",
    "verification_script",
}


def _require_ego() -> str:
    ego = (request.args.get("ego") or "").strip()
    if not ego:
        raise ValueError("ego query param is required")
    return ego


def _get_tag_store() -> AccountTagStore:
    global _tag_store
    if _tag_store is None:
        _tag_store = AccountTagStore(Path(get_snapshot_dir()) / "account_tags.db")
    return _tag_store


def _get_meta_note_store() -> TagMetaNoteStore:
    global _meta_note_store
    if _meta_note_store is None:
        _meta_note_store = TagMetaNoteStore(
            Path(get_snapshot_dir()) / "account_tags.db"
        )
    return _meta_note_store


def _require_meta_note_subject() -> tuple[str, str, str]:
    raw_ego = request.args.get("ego")
    raw_tag = request.args.get("tag")
    if raw_ego is None or not raw_ego.strip():
        raise ValueError("ego query param is required")
    if raw_tag is None or not raw_tag.strip():
        raise ValueError("tag query param is required")
    ego = normalize_ego(raw_ego)
    tag_key, tag_display = normalize_tag(raw_tag)
    return ego, tag_key, tag_display


def _parse_polarity(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value in (1, -1):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in ("in", "pos", "positive", "yes", "true"):
        return 1
    if normalized in ("not_in", "not-in", "neg", "negative", "no", "false"):
        return -1
    return None


def _event_source() -> str:
    source = (request.headers.get(_SOURCE_HEADER) or "").strip()
    if not source:
        raise ValueError(f"{_SOURCE_HEADER} is required for tag mutations")
    if source not in _ALLOWED_SOURCES:
        raise ValueError(
            f"{_SOURCE_HEADER} must be one of {sorted(_ALLOWED_SOURCES)}"
        )
    return source


@account_tags_bp.route("/accounts/<account_id>/tags", methods=["GET"])
@curator_only
def get_account_tags(account_id: str):
    """Return current tags and recent append-only working-tag events."""
    try:
        ego = _require_ego()
    except ValueError as exc:
        return error_response(str(exc))
    store = _get_tag_store()
    tags = store.list_tags(ego=ego, account_id=str(account_id))
    events = store.list_events(ego=ego, account_id=str(account_id))
    return jsonify(
        {
            "ego": ego,
            "accountId": str(account_id),
            "tags": [asdict(tag) for tag in tags],
            "events": [asdict(event) for event in events],
        }
    )


@account_tags_bp.route("/accounts/<account_id>/tags", methods=["POST"])
@curator_only
def upsert_account_tag(account_id: str):
    """Set one working tag while retaining the change as an event."""
    try:
        ego = _require_ego()
        source = _event_source()
    except ValueError as exc:
        return error_response(str(exc))
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object")
    raw_tag = data.get("tag")
    if not isinstance(raw_tag, str):
        return error_response("tag must be a string")
    tag = raw_tag.strip()
    polarity = _parse_polarity(data.get("polarity"))
    confidence = data.get("confidence")
    if polarity is None:
        return error_response("polarity must be 'in' or 'not_in'")

    try:
        saved = _get_tag_store().upsert_tag(
            ego=ego,
            account_id=str(account_id),
            tag=tag,
            polarity=polarity,
            confidence=float(confidence) if confidence is not None else None,
            source=source,
        )
    except (TypeError, ValueError) as exc:
        logger.info(
            "Rejected tag input ego=%s account=%s tag=%r: %s",
            ego,
            account_id,
            tag,
            exc,
        )
        return error_response(str(exc))
    except Exception:
        logger.exception("Tag write failed ego=%s account=%s tag=%r", ego, account_id, tag)
        return error_response("tag write failed; inspect the API log", status=500)
    return jsonify({"status": "ok", "tag": asdict(saved)})


@account_tags_bp.route("/accounts/<account_id>/tags", methods=["DELETE"])
@curator_only
def delete_account_tag(account_id: str):
    """Remove one current tag while retaining a removal event."""
    try:
        ego = _require_ego()
        source = _event_source()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        raw_tag = data.get("tag")
        if not isinstance(raw_tag, str):
            raise ValueError("tag must be a string")
        deleted = _get_tag_store().delete_tag(
            ego=ego,
            account_id=str(account_id),
            tag=raw_tag,
            source=source,
        )
    except ValueError as exc:
        return error_response(str(exc))
    return jsonify({"status": "deleted" if deleted else "not_found"})


@account_tags_bp.route("/tags", methods=["GET"])
@curator_only
def list_tags():
    """Return this curator's current vocabulary for tag suggestions."""
    try:
        ego = _require_ego()
    except ValueError as exc:
        return error_response(str(exc))
    return jsonify({"ego": ego, "tags": _get_tag_store().list_distinct_tags(ego=ego)})


@account_tags_bp.route("/tag-meta-notes", methods=["GET"])
@curator_only
def get_tag_meta_notes():
    """Return the latest note and append-only history for one curator/tag."""
    try:
        ego, tag_key, tag_display = _require_meta_note_subject()
        current, history = _get_meta_note_store().get_notes(
            ego=ego,
            tag=tag_key,
        )
    except ValueError as exc:
        return error_response(str(exc))
    except Exception:
        logger.exception("Tag meta-note read failed")
        return error_response(
            "tag meta-note read failed; inspect the API log",
            status=500,
        )
    response = jsonify({
        "ego": ego,
        "tag": tag_display,
        "tagKey": tag_key,
        "current": asdict(current) if current is not None else None,
        "history": [asdict(row) for row in history],
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response


@account_tags_bp.route("/tag-meta-notes", methods=["POST"])
@curator_only
def append_tag_meta_note():
    """Append a new working intension without rewriting prior notes."""
    try:
        ego, _, tag_display = _require_meta_note_subject()
        source = _event_source()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        raw_note = data.get("note")
        if not isinstance(raw_note, str):
            raise ValueError("note must be a string")
        saved = _get_meta_note_store().append_note(
            ego=ego,
            tag=tag_display,
            note=raw_note,
            source=source,
        )
    except ValueError as exc:
        return error_response(str(exc))
    except Exception:
        logger.exception("Tag meta-note append failed")
        return error_response(
            "tag meta-note append failed; inspect the API log",
            status=500,
        )
    return jsonify({"status": "appended", "current": asdict(saved)})
