"""Resume helpers for shadow subset audit output files."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .normalize import normalize_username


@dataclass
class ResumeState:
    results: List[Dict[str, object]] = field(default_factory=list)
    completed_usernames: Set[str] = field(default_factory=set)
    total_remote_requests: int = 0
    previous_complete: bool = False
    previous_generated_at: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def _parse_int(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _derive_requests_from_results(results: List[Dict[str, object]]) -> int:
    total = 0
    for entry in results:
        for relation in ("followers", "followings"):
            relation_data = entry.get(relation)
            if not isinstance(relation_data, dict):
                continue
            remote_data = relation_data.get("remote")
            if not isinstance(remote_data, dict):
                continue
            request_count = _parse_int(remote_data.get("requests_made"))
            if isinstance(request_count, int) and request_count >= 0:
                total += request_count
    return total


def load_resume_state(*, output_path: Path, allowed_usernames: Set[str]) -> ResumeState:
    state = ResumeState()
    if not output_path.exists():
        state.notes.append(f"resume: output not found ({output_path}), starting fresh")
        return state

    try:
        payload = json.loads(output_path.read_text())
    except (OSError, ValueError) as exc:
        state.notes.append(f"resume: failed to parse output JSON ({exc}), starting fresh")
        return state

    if not isinstance(payload, dict):
        state.notes.append("resume: output JSON is not an object, starting fresh")
        return state

    state.previous_generated_at = payload.get("generated_at") if isinstance(payload.get("generated_at"), str) else None
    progress = payload.get("progress")
    if isinstance(progress, dict):
        state.previous_complete = bool(progress.get("is_complete"))

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        state.notes.append("resume: output has no results list, starting fresh")
        return state

    seen_usernames: Set[str] = set()
    filtered_results: List[Dict[str, object]] = []
    duplicate_count = 0
    ignored_count = 0
    invalid_count = 0

    for item in raw_results:
        if not isinstance(item, dict):
            invalid_count += 1
            continue
        username = normalize_username(item.get("username"))
        if not username:
            invalid_count += 1
            continue
        if username not in allowed_usernames:
            ignored_count += 1
            continue
        if username in seen_usernames:
            duplicate_count += 1
            continue
        seen_usernames.add(username)
        filtered_results.append(item)

    if invalid_count:
        state.notes.append(f"resume: ignored {invalid_count} invalid result rows")
    if ignored_count:
        state.notes.append(f"resume: ignored {ignored_count} rows outside current target set")
    if duplicate_count:
        state.notes.append(f"resume: ignored {duplicate_count} duplicate username rows")

    state.results = filtered_results
    state.completed_usernames = seen_usernames

    derived_requests = _derive_requests_from_results(filtered_results)
    report_total = _parse_int(payload.get("total_remote_requests"))
    if isinstance(report_total, int) and report_total > 0 and report_total < derived_requests:
        state.notes.append(
            f"resume: report total_remote_requests ({report_total}) < derived ({derived_requests}); using derived"
        )
    state.total_remote_requests = max(derived_requests, 0)
    return state
