#!/usr/bin/env python3
"""Prepare and optionally run the Phase 1 community-correctness audit."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

try:
    from scripts.phase1_community_audit.config import (
        DEFAULT_DB_PATH,
        DEFAULT_HARD_NEGATIVE_PATH,
        DEFAULT_HARD_NEGATIVE_PROMPT_PATH,
        DEFAULT_MANIFEST_PATH,
        DEFAULT_MEMBERSHIP_PROMPT_PATH,
        DEFAULT_MODEL,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_RESULTS_JSONL_PATH,
        DEFAULT_REVIEW_CSV_PATH,
        PROJECT_ROOT,
    )
    from scripts.phase1_community_audit.db import connect_db, load_community_lookup
    from scripts.phase1_community_audit.io import (
        build_manifest,
        load_manifest,
        merge_grok_results_into_review_csv,
        write_manifest,
        write_review_csv,
    )
    from scripts.phase1_community_audit.prompting import (
        format_community_definitions,
        format_sample_posts,
        format_selected_hard_negatives,
        load_template,
        normalize_hard_negative_result,
        normalize_membership_result,
        parse_json_content,
        render_template,
    )
except ImportError:  # pragma: no cover - direct script execution from scripts/
    from phase1_community_audit.config import (
        DEFAULT_DB_PATH,
        DEFAULT_HARD_NEGATIVE_PATH,
        DEFAULT_HARD_NEGATIVE_PROMPT_PATH,
        DEFAULT_MANIFEST_PATH,
        DEFAULT_MEMBERSHIP_PROMPT_PATH,
        DEFAULT_MODEL,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_RESULTS_JSONL_PATH,
        DEFAULT_REVIEW_CSV_PATH,
        PROJECT_ROOT,
    )
    from phase1_community_audit.db import connect_db, load_community_lookup
    from phase1_community_audit.io import (
        build_manifest,
        load_manifest,
        merge_grok_results_into_review_csv,
        write_manifest,
        write_review_csv,
    )
    from phase1_community_audit.prompting import (
        format_community_definitions,
        format_sample_posts,
        format_selected_hard_negatives,
        load_template,
        normalize_hard_negative_result,
        normalize_membership_result,
        parse_json_content,
        render_template,
    )


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or run the Phase 1 Grok membership audit")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to archive_tweets.db")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH, help="Audit manifest JSON path")
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV_PATH, help="Review-sheet CSV path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Audit output directory")
    parser.add_argument("--results-jsonl", type=Path, default=DEFAULT_RESULTS_JSONL_PATH, help="Membership results JSONL path")
    parser.add_argument("--hard-negative-output", type=Path, default=DEFAULT_HARD_NEGATIVE_PATH, help="Hard-negative suggestion output path")
    parser.add_argument("--mode", choices=("membership", "hard-negatives"), default="membership", help="Audit mode")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model id")
    parser.add_argument("--api-key", default="", help="Override OPENROUTER_API_KEY")
    parser.add_argument("--bucket", default="", help="Optional bucket filter")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit after filtering")
    parser.add_argument("--prepare-only", action="store_true", help="Only write manifest + review sheet")
    parser.add_argument("--dry-run", action="store_true", help="Render prompts without calling OpenRouter")
    parser.add_argument("--post-limit", type=int, default=3, help="Local sample posts per account in manifest")
    parser.add_argument("--temperature", type=float, default=0.1, help="OpenRouter temperature")
    parser.add_argument("--max-tokens", type=int, default=900, help="OpenRouter max_tokens")
    return parser.parse_args()


def prepare_artifacts(args: argparse.Namespace) -> List[Dict[str, Any]]:
    manifest = build_manifest(db_path=args.db_path, post_limit=args.post_limit)
    write_manifest(args.manifest_path, manifest)
    write_review_csv(args.review_csv, manifest)
    return manifest


def resolve_api_key(cli_value: str) -> str:
    if cli_value:
        return cli_value
    return os.getenv("OPENROUTER_API_KEY", "")


def call_openrouter(*, api_key: str, model: str, prompt: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


def load_or_prepare_manifest(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.prepare_only or not args.manifest_path.exists():
        return prepare_artifacts(args)
    return load_manifest(args.manifest_path)


def filter_manifest(manifest: List[Dict[str, Any]], *, bucket: str, limit: int) -> List[Dict[str, Any]]:
    rows = manifest
    if bucket:
        rows = [item for item in rows if item["bucket"] == bucket]
    if limit > 0:
        rows = rows[:limit]
    return rows


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_membership_error_result(
    item: Dict[str, Any],
    *,
    model: str,
    error_type: str,
    error_message: str,
    raw_content: str = "",
) -> Dict[str, Any]:
    return {
        "review_id": item["review_id"],
        "username": item["username"],
        "target_community_short_name": item["target_community_short_name"],
        "model": model,
        "usage": {},
        "raw_content": raw_content,
        "tpot_status": "error",
        "top_communities": [],
        "bridge_account": False,
        "confidence": 0.0,
        "rationale": "",
        "evidence_signals": [],
        "main_confusions": [],
        "why_not_in": "",
        "error_type": error_type,
        "error_message": error_message,
    }


def run_membership_mode(args: argparse.Namespace, manifest: List[Dict[str, Any]]) -> int:
    prompt_template = load_template(DEFAULT_MEMBERSHIP_PROMPT_PATH)
    conn = connect_db(args.db_path)
    try:
        communities = load_community_lookup(conn)
    finally:
        conn.close()
    community_definitions = format_community_definitions(communities)
    selected = filter_manifest(manifest, bucket=args.bucket, limit=args.limit)
    if not selected:
        print("No manifest rows matched the requested filters.")
        return 2

    results = []
    for item in selected:
        prompt = render_template(
            prompt_template,
            {
                "community_definitions": community_definitions,
                "account_handle": f"@{item['username']}",
                "bio": item["bio"] or "(no bio available)",
                "sample_posts": format_sample_posts(item.get("sample_posts") or []),
            },
        )
        if args.dry_run:
            results.append({"review_id": item["review_id"], "prompt_preview": prompt[:1200]})
            continue
        api_key = resolve_api_key(args.api_key)
        if not api_key:
            print("Missing OPENROUTER_API_KEY. Re-run with --dry-run or provide --api-key.")
            return 2
        content = ""
        try:
            raw = call_openrouter(
                api_key=api_key,
                model=args.model,
                prompt=prompt,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = normalize_membership_result(parse_json_content(content))
            results.append(
                {
                    "review_id": item["review_id"],
                    "username": item["username"],
                    "target_community_short_name": item["target_community_short_name"],
                    "model": args.model,
                    "usage": raw.get("usage") or {},
                    "raw_content": content,
                    **parsed,
                }
            )
        except Exception as exc:
            logger.error(
                "Membership audit failed for @%s (%s): %s",
                item["username"],
                item["review_id"],
                exc,
                exc_info=True,
            )
            results.append(
                build_membership_error_result(
                    item,
                    model=args.model,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    raw_content=content,
                )
            )

    write_jsonl(args.results_jsonl, results)
    if not args.dry_run:
        indexed = {row["review_id"]: row for row in results}
        merge_grok_results_into_review_csv(args.review_csv, indexed)
    print(f"Wrote {len(results)} membership audit rows to {args.results_jsonl}")
    return 0


def run_hard_negative_mode(args: argparse.Namespace, manifest: List[Dict[str, Any]]) -> int:
    prompt_template = load_template(DEFAULT_HARD_NEGATIVE_PROMPT_PATH)
    conn = connect_db(args.db_path)
    try:
        communities = load_community_lookup(conn)
    finally:
        conn.close()
    current_hard_negs = [item for item in manifest if item["bucket"] == "hard_negative"]
    prompt = render_template(
        prompt_template,
        {
            "community_definitions": format_community_definitions(communities),
            "selected_hard_negatives": format_selected_hard_negatives(current_hard_negs),
        },
    )
    if args.dry_run:
        args.hard_negative_output.parent.mkdir(parents=True, exist_ok=True)
        args.hard_negative_output.write_text(prompt, encoding="utf-8")
        print(f"Wrote hard-negative prompt preview to {args.hard_negative_output}")
        return 0

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("Missing OPENROUTER_API_KEY. Re-run with --dry-run or provide --api-key.")
        return 2
    content = ""
    try:
        raw = call_openrouter(
            api_key=api_key,
            model=args.model,
            prompt=prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        normalized = normalize_hard_negative_result(parse_json_content(content))
        payload = {"model": args.model, "usage": raw.get("usage") or {}, **normalized, "raw_content": content}
    except Exception as exc:
        logger.error("Hard-negative audit failed: %s", exc, exc_info=True)
        payload = {
            "model": args.model,
            "usage": {},
            "hard_negative_candidates": [],
            "raw_content": content,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    args.hard_negative_output.parent.mkdir(parents=True, exist_ok=True)
    args.hard_negative_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote hard-negative suggestions to {args.hard_negative_output}")
    return 0


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    manifest = load_or_prepare_manifest(args)
    print(f"Manifest ready: {args.manifest_path} ({len(manifest)} review items)")
    print(f"Review sheet ready: {args.review_csv}")
    if args.prepare_only:
        return 0
    if args.mode == "membership":
        return run_membership_mode(args, manifest)
    return run_hard_negative_mode(args, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
