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
    snowflake_eligible = dataset.get("snowflake_eligible_rows")
    snowflake_exact = dataset.get("created_at_snowflake_exact_rows")
    snowflake_within = dataset.get(
        "created_at_snowflake_within_one_second_rows"
    )
    snowflake_mismatch = dataset.get(
        "created_at_snowflake_mismatch_gt_one_second_rows"
    )
    pre_twitter = dataset.get("created_at_pre_twitter_rows")
    snowflake_min = _timestamp(dataset.get("snowflake_created_at_min"))
    snowflake_max = _timestamp(dataset.get("snowflake_created_at_max"))
    anomaly_samples = dataset.get("created_at_anomaly_samples")

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
    timestamp_quality_valid = (
        _integer(row_count)
        and all(
            _integer(value)
            for value in (
                snowflake_eligible,
                snowflake_exact,
                snowflake_within,
                snowflake_mismatch,
                pre_twitter,
            )
        )
        and snowflake_exact <= snowflake_within <= snowflake_eligible
        and snowflake_within + snowflake_mismatch == snowflake_eligible
        and pre_twitter <= row_count
        and (
            (snowflake_eligible == 0 and snowflake_min is None and snowflake_max is None)
            or (
                snowflake_eligible > 0
                and snowflake_min is not None
                and snowflake_max is not None
                and snowflake_min <= snowflake_max
            )
        )
        and isinstance(anomaly_samples, list)
        and len(anomaly_samples) <= 5
        and len(anomaly_samples) <= snowflake_mismatch
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
        SnapshotCheck(
            "dataset timestamp quality",
            timestamp_quality_valid,
            "eligible="
            f"{snowflake_eligible}, within_1s={snowflake_within}, "
            f"mismatch_gt_1s={snowflake_mismatch}, pre_twitter={pre_twitter}",
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
        "snowflake_eligible_rows": snowflake_eligible,
        "created_at_snowflake_exact_rows": snowflake_exact,
        "created_at_snowflake_within_one_second_rows": snowflake_within,
        "created_at_snowflake_mismatch_gt_one_second_rows": snowflake_mismatch,
        "created_at_pre_twitter_rows": pre_twitter,
        "snowflake_created_at_min": dataset.get("snowflake_created_at_min"),
        "snowflake_created_at_max": dataset.get("snowflake_created_at_max"),
        "created_at_anomaly_samples": anomaly_samples,
    }
    return checks, metrics
