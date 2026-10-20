"""Receipt validation shared by curator-owned mutation routes."""
from __future__ import annotations

from flask import Request


CURATION_SOURCE_HEADER = "X-TPOT-Curation-Source"
ALLOWED_CURATION_SOURCES = frozenset({
    "agent_assisted_curator",
    "human_curator_api",
    "verification_script",
})


def require_curation_source(req: Request) -> str:
    source = (req.headers.get(CURATION_SOURCE_HEADER) or "").strip()
    if not source:
        raise ValueError(
            f"{CURATION_SOURCE_HEADER} is required for curator mutations"
        )
    if source not in ALLOWED_CURATION_SOURCES:
        raise ValueError(
            f"{CURATION_SOURCE_HEADER} must be one of "
            f"{sorted(ALLOWED_CURATION_SOURCES)}"
        )
    return source
