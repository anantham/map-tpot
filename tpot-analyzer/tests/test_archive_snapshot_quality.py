from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pyarrow.parquet as pq

from src.archive.snapshot_manifest import inspect_enriched_tweets_parquet


TWITTER_EPOCH_MS = 1_288_834_974_657


def _snowflake(value: datetime) -> str:
    milliseconds = int(value.timestamp() * 1000)
    return str((milliseconds - TWITTER_EPOCH_MS) << 22)


def _source_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S+00")


def test_inspection_surfaces_snowflake_timestamp_anomalies(tmp_path):
    exact = datetime(2020, 1, 1, tzinfo=timezone.utc)
    plus_one = datetime(2021, 1, 1, tzinfo=timezone.utc)
    plus_two = datetime(2022, 1, 1, tzinfo=timezone.utc)
    corrupted = datetime(2023, 1, 1, tzinfo=timezone.utc)
    path = tmp_path / "enriched_tweets.parquet"
    table = pa.table(
        {
            "tweet_id": [
                _snowflake(exact),
                _snowflake(plus_one),
                _snowflake(plus_two),
                _snowflake(corrupted),
            ],
            "account_id": ["1", "2", "3", "4"],
            "username": ["one", "two", "three", "four"],
            "created_at": [
                _source_time(exact),
                _source_time(plus_one + timedelta(seconds=1)),
                _source_time(plus_two + timedelta(seconds=2)),
                "2000-01-01 00:00:00+00",
            ],
            "full_text": ["a", "b", "c", "d"],
            "archive_upload_id": [1, 1, 1, 1],
        }
    )
    pq.write_table(table, path)

    result = inspect_enriched_tweets_parquet(path)

    assert result["snowflake_eligible_rows"] == 4
    assert result["created_at_snowflake_exact_rows"] == 1
    assert result["created_at_snowflake_within_one_second_rows"] == 2
    assert result["created_at_snowflake_mismatch_gt_one_second_rows"] == 2
    assert result["created_at_pre_twitter_rows"] == 1
    assert result["snowflake_created_at_min"] == "2020-01-01T00:00:00+00:00"
    assert result["snowflake_created_at_max"] == "2023-01-01T00:00:00+00:00"
    assert len(result["created_at_anomaly_samples"]) == 2
