"""Curator-private import of local Research Notes and proposal hints."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.data.research_notes_sections import source_sections_by_handle

logger = logging.getLogger(__name__)

research_notes_source_bp = Blueprint(
    "research_notes_source",
    __name__,
    url_prefix="/api/research-notes",
)

SOURCE_PATH_ENV = "RESEARCH_NOTES_SOURCE_PATH"
PROPOSALS_PATH_ENV = "RESEARCH_NOTES_PROPOSALS_PATH"
MAX_SOURCE_BYTES = 256 * 1024
MAX_PROPOSALS_BYTES = 1024 * 1024
_HANDLE = re.compile(r"^[a-z0-9_]{1,15}$")
_POLARITIES = {"in", "out", "review"}


class ResearchNotesSourceError(RuntimeError):
    """A private-file error safe to describe at the API boundary."""

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = status


class StaleResearchNotesProposals(ResearchNotesSourceError):
    """A safe proposal envelope bound to a different source receipt."""

    def __init__(self, *, bound_sha256: str, current_sha256: str) -> None:
        super().__init__(
            "Research Notes proposals do not match the configured source",
            status=409,
        )
        self.bound_sha256 = bound_sha256
        self.current_sha256 = current_sha256


def _read_limited_file(
    path: Path,
    *,
    label: str,
    limit: int,
) -> tuple[bytes, os.stat_result]:
    try:
        with path.open("rb") as source_file:
            file_stat = os.fstat(source_file.fileno())
            if file_stat.st_size > limit:
                raise ResearchNotesSourceError(
                    f"{label} exceeds the {limit}-byte limit",
                    status=413,
                )
            content = source_file.read(limit + 1)
    except ResearchNotesSourceError:
        raise
    except OSError as exc:
        raise ResearchNotesSourceError(
            f"{label} is unavailable",
            status=503,
        ) from exc

    if len(content) > limit:
        raise ResearchNotesSourceError(
            f"{label} exceeds the {limit}-byte limit",
            status=413,
        )
    return content, file_stat


def _decode_utf8(content: bytes, *, label: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchNotesSourceError(
            f"{label} must be UTF-8 text",
            status=422,
        ) from exc


def _source_payload(path: Path) -> tuple[dict[str, Any], str]:
    content, file_stat = _read_limited_file(
        path,
        label="Research Notes source",
        limit=MAX_SOURCE_BYTES,
    )
    text = _decode_utf8(content, label="Research Notes source")
    modified_at = datetime.fromtimestamp(
        file_stat.st_mtime,
        tz=timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    return {
        "name": path.name,
        "text": text,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "modifiedAt": modified_at,
    }, text


def _validate_suggestion(
    suggestion: Any,
    *,
    source_sections: tuple[str, ...],
) -> None:
    if not isinstance(suggestion, dict):
        raise ValueError("suggestion must be an object")
    for field in ("tag", "tagKind", "sourceQuote"):
        value = suggestion.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"suggestion {field} must be non-empty text")
    if not any(suggestion["sourceQuote"] in block for block in source_sections):
        raise ValueError("suggestion sourceQuote is not in the account source block")
    if suggestion.get("polarity") not in _POLARITIES:
        raise ValueError("suggestion polarity is invalid")
    if suggestion.get("proposalStatus") != "model-proposed":
        raise ValueError("suggestion is not marked model-proposed")
    if suggestion.get("goldStatus") != "not-gold":
        raise ValueError("suggestion is not marked non-gold")


def _load_suggestions(
    path: Path,
    *,
    source_sha256: str,
    source_text: str,
) -> dict[str, list[dict[str, Any]]]:
    content, _ = _read_limited_file(
        path,
        label="Research Notes proposals",
        limit=MAX_PROPOSALS_BYTES,
    )
    try:
        proposal = json.loads(_decode_utf8(
            content,
            label="Research Notes proposals",
        ))
        if not isinstance(proposal, dict) or proposal.get("schemaVersion") != 1:
            raise ValueError("unsupported proposal schema")
        if proposal.get("proposalStatus") != "model-proposed":
            raise ValueError("proposal set is not marked model-proposed")
        if proposal.get("goldStatus") != "not-gold":
            raise ValueError("proposal set is not marked non-gold")
        permissions = proposal.get("permissions")
        if permissions != {
            "mayTrain": False,
            "mayScore": False,
            "mayAutoWriteTags": False,
        }:
            raise ValueError("proposal permissions are not safely disabled")
        bound_sha256 = proposal.get("sourceSha256")
        if not isinstance(bound_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}",
            bound_sha256,
        ):
            raise ValueError("proposal sourceSha256 is invalid")
        if bound_sha256 != source_sha256:
            raise StaleResearchNotesProposals(
                bound_sha256=bound_sha256,
                current_sha256=source_sha256,
            )
        suggestions = proposal.get("suggestionsByHandle")
        if not isinstance(suggestions, dict):
            raise ValueError("suggestionsByHandle must be an object")
        source_sections = source_sections_by_handle(source_text)
        for handle, values in suggestions.items():
            if not isinstance(handle, str) or not _HANDLE.fullmatch(handle):
                raise ValueError("proposal handles must be normalized X handles")
            if not isinstance(values, list):
                raise ValueError("handle suggestions must be a list")
            handle_sections = source_sections.get(handle, ())
            if not handle_sections:
                raise ValueError("proposal handle has no account source block")
            for suggestion in values:
                _validate_suggestion(
                    suggestion,
                    source_sections=handle_sections,
                )
        return suggestions
    except ResearchNotesSourceError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ResearchNotesSourceError(
            "Research Notes proposals are invalid",
            status=422,
        ) from exc


def _proposal_payload(
    path: Path,
    *,
    source_sha256: str,
    source_text: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str] | None]:
    try:
        suggestions = _load_suggestions(
            path,
            source_sha256=source_sha256,
            source_text=source_text,
        )
        return suggestions, None
    except StaleResearchNotesProposals as exc:
        logger.warning("Research Notes proposals quarantined as stale: %s", exc)
        return {}, {
            "status": "stale",
            "boundSourceSha256": exc.bound_sha256,
            "currentSourceSha256": exc.current_sha256,
        }
    except ResearchNotesSourceError as exc:
        logger.warning("Research Notes proposals quarantined as invalid: %s", exc)
        return {}, {"status": "invalid"}


@research_notes_source_bp.get("/source")
@curator_only
def get_research_notes_source():
    """Return configured private notes and inert, source-bound suggestions."""

    configured_path = (os.getenv(SOURCE_PATH_ENV) or "").strip()
    if not configured_path:
        response = jsonify({
            "configured": False,
            "source": None,
            "suggestionsByHandle": {},
        })
        response.headers["Cache-Control"] = "private, no-store"
        return response

    try:
        source, source_text = _source_payload(Path(configured_path))
        proposals_path = (os.getenv(PROPOSALS_PATH_ENV) or "").strip()
        suggestions, proposal_metadata = (
            _proposal_payload(
                Path(proposals_path),
                source_sha256=source["sha256"],
                source_text=source_text,
            )
            if proposals_path
            else ({}, None)
        )
        payload = {
            "configured": True,
            "source": source,
            "suggestionsByHandle": suggestions,
        }
        if proposal_metadata is not None:
            payload["proposalMetadata"] = proposal_metadata
        response = jsonify(payload)
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except ResearchNotesSourceError as exc:
        logger.warning("Research Notes source import rejected: %s", exc)
        return error_response(str(exc), status=exc.status)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.exception("Unexpected Research Notes source import failure: %s", exc)
        return error_response("internal_error", status=500)
