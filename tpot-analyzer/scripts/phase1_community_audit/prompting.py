"""Prompt rendering and response parsing for the Phase 1 audit."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def format_community_definitions(communities: Dict[str, Dict[str, Any]]) -> str:
    lines: List[str] = []
    for short_name in sorted(communities):
        community = communities[short_name]
        lines.append(
            f"- {community['short_name']}: {community['name']} — {community['description']}"
        )
    return "\n".join(lines)


def format_sample_posts(posts: Iterable[Dict[str, Any]]) -> str:
    rows = list(posts)
    if not rows:
        return "- No local sample posts available."
    lines = []
    for idx, post in enumerate(rows, start=1):
        text = str(post.get("text") or "").strip().replace("\n", " ")
        created_at = str(post.get("created_at") or "")
        source = str(post.get("source") or "")
        lines.append(f"{idx}. [{source}] {created_at} :: {text}")
    return "\n".join(lines)


def format_selected_hard_negatives(items: Iterable[Dict[str, Any]]) -> str:
    rows = list(items)
    if not rows:
        return "- None selected yet."
    lines = []
    for item in rows:
        lines.append(
            f"- @{item['username']} -> {item['target_community_short_name']} ({item['selection_reason']})"
        )
    return "\n".join(lines)


def render_template(template: str, mapping: Dict[str, str]) -> str:
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def strip_code_fences(text: str) -> str:
    content = text.strip()
    if not content.startswith("```"):
        return content
    first_newline = content.find("\n")
    if first_newline == -1:
        return content
    inner = content[first_newline + 1 :]
    if inner.endswith("```"):
        inner = inner[:-3]
    return inner.strip()


def parse_json_content(text: str) -> Any:
    return json.loads(strip_code_fences(text))


def normalize_membership_result(parsed: Dict[str, Any]) -> Dict[str, Any]:
    top_communities = parsed.get("top_communities") or []
    normalized_top = []
    for row in top_communities[:3]:
        if not isinstance(row, dict):
            continue
        normalized_top.append(
            {
                "community": str(row.get("community") or "").strip(),
                "score": float(row.get("score") or 0.0),
            }
        )
    return {
        "tpot_status": str(parsed.get("tpot_status") or "").strip().lower() or "uncertain",
        "top_communities": normalized_top,
        "bridge_account": bool(parsed.get("bridge_account", False)),
        "confidence": float(parsed.get("confidence") or 0.0),
        "rationale": str(parsed.get("rationale") or "").strip(),
        "evidence_signals": [str(v).strip() for v in (parsed.get("evidence_signals") or []) if str(v).strip()],
        "main_confusions": [str(v).strip() for v in (parsed.get("main_confusions") or []) if str(v).strip()],
        "why_not_in": str(parsed.get("why_not_in") or "").strip(),
    }


def normalize_hard_negative_result(parsed: Dict[str, Any]) -> Dict[str, Any]:
    candidates = []
    for row in parsed.get("hard_negative_candidates") or []:
        if not isinstance(row, dict):
            continue
        candidates.append(
            {
                "account": str(row.get("account") or "").strip(),
                "likely_confused_with": [
                    str(value).strip()
                    for value in (row.get("likely_confused_with") or [])
                    if str(value).strip()
                ],
                "why_hard_negative": str(row.get("why_hard_negative") or "").strip(),
                "risk_of_being_true_positive": str(row.get("risk_of_being_true_positive") or "").strip(),
            }
        )
    return {"hard_negative_candidates": candidates}
