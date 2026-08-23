"""Parquet inspection for Community Archive enriched-tweet snapshots."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.archive.snapshot import utc_iso
from src.archive.snapshot_contract import REQUIRED_COLUMNS
from src.archive.snapshot_quality import TimestampQualityAccumulator


UTC_STRING_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2} "
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?\+00$"
)


def _created_at_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _created_at_seconds(
    values: pa.Array,
    *,
    string_values: bool,
) -> pa.Array:
    if string_values:
        return pc.binary_join_element_wise(
            pc.utf8_slice_codeunits(values, 0, 19),
            pa.scalar("+00"),
            pa.scalar(""),
        )
    return pc.strftime(
        pc.cast(values, pa.timestamp("s", tz="UTC"), safe=False),
        format="%Y-%m-%d %H:%M:%S+00",
    )


def _validate_schema(parquet: pq.ParquetFile) -> tuple[list[str], bool]:
    schema = parquet.schema_arrow
    columns = schema.names
    missing = sorted(REQUIRED_COLUMNS - set(columns))
    if missing:
        raise ValueError(
            "Community Archive Parquet is missing required columns: "
            + ", ".join(missing)
        )
    invalid_id_types = [
        f"{name}={schema.field(name).type}"
        for name in ("tweet_id", "account_id")
        if not (
            pa.types.is_string(schema.field(name).type)
            or pa.types.is_large_string(schema.field(name).type)
        )
    ]
    if invalid_id_types:
        raise ValueError(
            "Community Archive Parquet must preserve snowflake values as string IDs; "
            + ", ".join(invalid_id_types)
        )
    created_type = schema.field("created_at").type
    timestamp_created_at = (
        pa.types.is_timestamp(created_type) and created_type.tz is not None
    )
    string_created_at = pa.types.is_string(created_type) or pa.types.is_large_string(
        created_type
    )
    if not timestamp_created_at and not string_created_at:
        raise ValueError(
            "Community Archive created_at must be a timezone-aware timestamp "
            f"or canonical UTC string; got {created_type}"
        )
    return columns, string_created_at


def _validate_batch(batch: pa.RecordBatch, *, string_created_at: bool) -> pa.Array:
    valid_tweet_ids = pc.fill_null(
        pc.match_substring_regex(batch.column("tweet_id"), pattern=r"^[0-9]+$"),
        False,
    )
    invalid_tweet_ids = pc.sum(pc.invert(valid_tweet_ids)).as_py()
    if invalid_tweet_ids:
        raise ValueError(
            "Community Archive tweet_id contains "
            f"{invalid_tweet_ids} nonnumeric string(s) in a batch"
        )
    created_column = batch.column("created_at")
    if string_created_at:
        valid_created = pc.fill_null(
            pc.match_substring_regex(
                created_column,
                pattern=UTC_STRING_PATTERN,
            ),
            False,
        )
        invalid_count = pc.sum(pc.invert(valid_created)).as_py()
        if invalid_count:
            raise ValueError(
                "Community Archive created_at contains "
                f"{invalid_count} noncanonical UTC string(s) in a batch"
            )
    return created_column


def inspect_enriched_tweets_parquet(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    columns, string_created_at = _validate_schema(parquet)
    account_ids: set[str] = set()
    created_min: datetime | None = None
    created_max: datetime | None = None
    linked_rows = 0
    missing_upload_id_rows = 0
    scanned_rows = 0
    sample_rows: list[dict[str, Any]] = []
    timestamp_quality = TimestampQualityAccumulator()

    for batch in parquet.iter_batches(
        batch_size=262_144,
        columns=[
            "tweet_id",
            "account_id",
            "username",
            "created_at",
            "archive_upload_id",
        ],
    ):
        scanned_rows += batch.num_rows
        created_column = _validate_batch(
            batch,
            string_created_at=string_created_at,
        )
        account_ids.update(
            str(value)
            for value in batch.column("account_id").to_pylist()
            if value is not None
        )
        timestamp_quality.update(
            batch,
            _created_at_seconds(
                created_column,
                string_values=string_created_at,
            ),
        )
        created = pc.min_max(created_column).as_py()
        batch_min = created.get("min")
        batch_max = created.get("max")
        if batch_min is not None:
            batch_min = _created_at_datetime(batch_min)
            created_min = batch_min if created_min is None else min(created_min, batch_min)
        if batch_max is not None:
            batch_max = _created_at_datetime(batch_max)
            created_max = batch_max if created_max is None else max(created_max, batch_max)
        upload_ids = batch.column("archive_upload_id")
        missing_upload_id_rows += upload_ids.null_count
        linked_rows += batch.num_rows - upload_ids.null_count
        _add_samples(sample_rows, batch, upload_ids)

    row_count = parquet.metadata.num_rows
    if scanned_rows != row_count:
        raise ValueError(
            f"Parquet row scan mismatch: metadata={row_count}, scanned={scanned_rows}"
        )
    return {
        "row_count": row_count,
        "account_count": len(account_ids),
        "columns": columns,
        "created_at_min": utc_iso(created_min) if created_min else None,
        "created_at_max": utc_iso(created_max) if created_max else None,
        "archive_upload_linked_rows": linked_rows,
        "archive_upload_id_missing_rows": missing_upload_id_rows,
        "sample_rows": sample_rows,
        **timestamp_quality.metrics(),
    }


def _add_samples(
    samples: list[dict[str, Any]],
    batch: pa.RecordBatch,
    upload_ids: pa.Array,
) -> None:
    remaining = 5 - len(samples)
    if remaining <= 0:
        return
    for tweet_id, account_id, created_at, upload_id in zip(
        batch.column("tweet_id").slice(0, remaining).to_pylist(),
        batch.column("account_id").slice(0, remaining).to_pylist(),
        batch.column("created_at").slice(0, remaining).to_pylist(),
        upload_ids.slice(0, remaining).to_pylist(),
    ):
        samples.append(
            {
                "tweet_id": tweet_id,
                "account_id": account_id,
                "created_at": utc_iso(_created_at_datetime(created_at)),
                "archive_upload_id": upload_id,
            }
        )
