"""Dataset-specific checks for enriched-tweet snapshot manifests."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.archive.snapshot_contract import REQUIRED_COLUMNS, SnapshotCheck


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_dataset(
    dataset: dict[str, Any],
) -> tuple[list[SnapshotCheck], dict[str, object]]:
    row_count = dataset.get("row_count")
    account_count = dataset.get("account_count")
    linked = dataset.get("archive_upload_linked_rows")
    missing_upload = dataset.get("archive_upload_id_missing_rows")
    columns = dataset.get("columns")
    sample_rows = dataset.get("sample_rows")
    cutoff_min = _timestamp(dataset.get("created_at_min"))
    cutoff_max = _timestamp(dataset.get("created_at_max"))

    columns_valid = isinstance(columns, list) and REQUIRED_COLUMNS.issubset(columns)
    samples_valid = (
        isinstance(sample_rows, list)
        and len(sample_rows) <= 5
        and (_integer(row_count) and (row_count == 0 or bool(sample_rows)))
        and all(
            isinstance(sample, dict)
            and isinstance(sample.get("tweet_id"), str)
            and isinstance(sample.get("account_id"), str)
            and _timestamp(sample.get("created_at")) is not None
            for sample in sample_rows
        )
    )
    checks = [
        SnapshotCheck(
            "dataset account count",
            _integer(row_count)
            and _integer(account_count)
            and account_count <= row_count,
            f"rows={row_count}, accounts={account_count}",
        ),
        SnapshotCheck(
            "dataset row partition",
            _integer(row_count)
            and _integer(linked)
            and _integer(missing_upload)
            and linked + missing_upload == row_count,
            f"rows={row_count}, linked={linked}, missing_upload_id={missing_upload}",
        ),
        SnapshotCheck(
            "dataset columns",
            columns_valid,
            f"missing={sorted(REQUIRED_COLUMNS - set(columns or []))}"
            if isinstance(columns, list)
            else type(columns).__name__,
        ),
        SnapshotCheck(
            "dataset samples",
            samples_valid,
            f"count={len(sample_rows) if isinstance(sample_rows, list) else 'invalid'}",
        ),
        SnapshotCheck(
            "dataset time range",
            cutoff_min is not None
            and cutoff_max is not None
            and cutoff_min <= cutoff_max,
            f"min={dataset.get('created_at_min')}, max={dataset.get('created_at_max')}",
        ),
    ]
    metrics = {
        "row_count": row_count,
        "account_count": account_count,
        "created_at_min": dataset.get("created_at_min"),
        "created_at_max": dataset.get("created_at_max"),
        "archive_upload_id_missing_rows": missing_upload,
        "archive_upload_linked_rows": linked,
        "sample_rows": sample_rows,
    }
    return checks, metrics
