"""Manifest and review-sheet IO for the Phase 1 audit."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from scripts.phase1_community_audit.config import BUCKET_ORDER, PHASE1_SLATE
    from scripts.phase1_community_audit.db import build_manifest_item, connect_db, load_community_lookup
except ImportError:  # pragma: no cover - direct script execution from scripts/
    from phase1_community_audit.config import BUCKET_ORDER, PHASE1_SLATE
    from phase1_community_audit.db import build_manifest_item, connect_db, load_community_lookup


REVIEW_FIELDNAMES = [
    "review_id",
    "bucket",
    "username",
    "display_name",
    "account_id",
    "target_community_short_name",
    "target_community_id",
    "suggested_contrasts",
    "expected_judgment",
    "grok_tpot_status",
    "grok_top_communities",
    "grok_confidence",
    "grok_bridge_account",
    "grok_rationale",
    "human_judgment",
    "human_confidence",
    "human_note",
]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_manifest(*, db_path: Path, post_limit: int = 3) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        communities = load_community_lookup(conn)
        items = [build_manifest_item(conn, communities, spec, post_limit=post_limit) for spec in PHASE1_SLATE]
    finally:
        conn.close()
    return sorted(items, key=lambda item: (BUCKET_ORDER.index(item["bucket"]), item["review_id"]))


def write_manifest(path: Path, manifest: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(list(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_bucket_counts(manifest: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    return dict(Counter(item["bucket"] for item in manifest))


def write_review_csv(path: Path, manifest: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    rows = []
    for item in manifest:
        rows.append(
            {
                "review_id": item["review_id"],
                "bucket": item["bucket"],
                "username": item["username"],
                "display_name": item["display_name"],
                "account_id": item["account_id"],
                "target_community_short_name": item["target_community_short_name"],
                "target_community_id": item["target_community_id"],
                "suggested_contrasts": "|".join(item.get("likely_confusions") or []),
                "expected_judgment": item["expected_judgment"],
                "grok_tpot_status": "",
                "grok_top_communities": "",
                "grok_confidence": "",
                "grok_bridge_account": "",
                "grok_rationale": "",
                "human_judgment": "",
                "human_confidence": "",
                "human_note": "",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def load_review_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def load_review_csv_with_fieldnames(path: Path) -> tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, [dict(row) for row in reader]


def merge_grok_results_into_review_csv(
    review_csv_path: Path,
    grok_results: Dict[str, Dict[str, Any]],
) -> None:
    fieldnames, rows = load_review_csv_with_fieldnames(review_csv_path)
    merged = []
    for row in rows:
        result = grok_results.get(row["review_id"])
        if result:
            row["grok_tpot_status"] = str(result.get("tpot_status") or "")
            row["grok_top_communities"] = "|".join(
                f"{item['community']}:{item['score']:.3f}"
                for item in result.get("top_communities") or []
                if item.get("community")
            )
            row["grok_confidence"] = f"{float(result.get('confidence') or 0.0):.3f}"
            row["grok_bridge_account"] = "1" if result.get("bridge_account") else "0"
            row["grok_rationale"] = str(result.get("rationale") or "")
        merged.append(row)
    merged_fieldnames = list(fieldnames)
    for name in REVIEW_FIELDNAMES:
        if name not in merged_fieldnames:
            merged_fieldnames.append(name)
    with review_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=merged_fieldnames)
        writer.writeheader()
        writer.writerows(merged)
