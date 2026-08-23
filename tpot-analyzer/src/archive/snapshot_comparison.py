"""Evidence-preserving comparison of two Community Archive snapshots."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.archive.snapshot_contract import MANIFEST_FILENAME
from src.archive.snapshot_manifest import verify_local_snapshot


COUNT_FIELDS = (
    "row_count",
    "account_count",
    "archive_upload_linked_rows",
    "archive_upload_id_missing_rows",
)


def _timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string; got {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone: {value!r}")
    return parsed


def _nonnegative_integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer; got {value!r}")
    return value


def _object(manifest: dict[str, Any], field: str) -> dict[str, Any]:
    value = manifest.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"manifest.{field} must be an object; got {value!r}")
    return value


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Extract comparison-safe provenance and corpus metrics from a manifest."""
    dataset = _object(manifest, "dataset")
    source = _object(manifest, "source")
    local = _object(manifest, "local")
    snapshot_id = manifest.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("manifest.snapshot_id must be a non-empty string")

    counts = {
        field: _nonnegative_integer(dataset.get(field), field=f"dataset.{field}")
        for field in COUNT_FIELDS
    }
    latest = dataset.get("created_at_max")
    _timestamp(latest, field="dataset.created_at_max")
    size_bytes = _nonnegative_integer(
        local.get("size_bytes"),
        field="local.size_bytes",
    )
    sample_rows = dataset.get("sample_rows", [])
    if not isinstance(sample_rows, list):
        raise ValueError("dataset.sample_rows must be an array")

    return {
        "snapshot_id": snapshot_id,
        "sha256": local.get("sha256"),
        "size_bytes": size_bytes,
        "etag": source.get("etag"),
        "last_modified": source.get("last_modified"),
        "observed_at": source.get("observed_at"),
        "created_at_max": latest,
        **counts,
        "archive_linked_fraction": (
            counts["archive_upload_linked_rows"] / counts["row_count"]
            if counts["row_count"]
            else 0.0
        ),
        "sample_rows": sample_rows[:2],
    }


def load_verified_manifest(snapshot_dir: Path, *, deep: bool = True) -> dict[str, Any]:
    """Verify a snapshot identity before returning its manifest."""
    snapshot_dir = Path(snapshot_dir)
    checks, _ = verify_local_snapshot(snapshot_dir, deep=deep)
    failures = [f"{check.name}: {check.detail}" for check in checks if not check.passed]
    if failures:
        raise ValueError(
            f"snapshot verification failed for {snapshot_dir}: " + "; ".join(failures)
        )
    manifest_path = snapshot_dir / MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"verified manifest became unreadable at {manifest_path}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest must be an object: {manifest_path}")
    return manifest


def compare_snapshot_manifests(
    baseline_manifest: dict[str, Any],
    candidate_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Compare two verified manifests using predeclared freshness hypotheses."""
    baseline = summarize_manifest(baseline_manifest)
    candidate = summarize_manifest(candidate_manifest)
    deltas = {
        field: candidate[field] - baseline[field]
        for field in (*COUNT_FIELDS, "size_bytes")
    }
    latest_delta = (
        _timestamp(candidate["created_at_max"], field="candidate.created_at_max")
        - _timestamp(baseline["created_at_max"], field="baseline.created_at_max")
    ).total_seconds()
    linked_fraction_delta = (
        candidate["archive_linked_fraction"] - baseline["archive_linked_fraction"]
    )
    deltas["created_at_max_seconds"] = latest_delta
    deltas["archive_linked_fraction"] = linked_fraction_delta

    source_changed = any(
        candidate[field] != baseline[field]
        for field in ("snapshot_id", "sha256", "etag", "last_modified")
    )
    corpus_advanced = deltas["row_count"] > 0 and latest_delta > 0
    non_regressive = (
        deltas["row_count"] >= 0
        and deltas["account_count"] >= 0
        and deltas["archive_upload_linked_rows"] >= 0
        and latest_delta >= 0
    )
    linkage_kept_pace = (
        deltas["row_count"] > 0
        and deltas["archive_upload_linked_rows"] >= deltas["row_count"]
        and deltas["archive_upload_id_missing_rows"] <= 0
    )

    return {
        "method": {
            "counts_are_manifest_metrics": True,
            "unknown_rows_are_not_inferred_as_archive_linked": True,
        },
        "baseline": baseline,
        "candidate": candidate,
        "deltas": deltas,
        "hypotheses": {
            "source_identity_changed": {
                "passed": source_changed,
                "falsifier": "snapshot ID, SHA-256, ETag, and Last-Modified all unchanged",
            },
            "corpus_advanced": {
                "passed": corpus_advanced,
                "falsifier": "row delta <= 0 or newest-tweet timestamp did not advance",
            },
            "non_regressive_counts": {
                "passed": non_regressive,
                "falsifier": "rows, accounts, linked rows, or newest timestamp regressed",
            },
            "archive_linkage_kept_pace": {
                "passed": linkage_kept_pace,
                "falsifier": (
                    "new linked-row count trails new row count, or missing-ID rows grew"
                ),
            },
        },
    }


def compare_snapshot_directories(
    baseline_dir: Path,
    candidate_dir: Path,
    *,
    deep: bool = True,
) -> dict[str, Any]:
    baseline = load_verified_manifest(baseline_dir, deep=deep)
    candidate = load_verified_manifest(candidate_dir, deep=deep)
    return compare_snapshot_manifests(baseline, candidate)


def write_json_no_clobber(path: Path, payload: dict[str, Any]) -> None:
    """Serialize fully, then create a result without replacing prior evidence."""
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
