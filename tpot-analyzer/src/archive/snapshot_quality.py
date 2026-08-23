"""Quality metrics comparing source timestamps with tweet Snowflake time."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from src.archive.snapshot import utc_iso


TWITTER_EPOCH_MS = 1_288_834_974_657
# Legacy sequential tweet IDs are many orders of magnitude smaller. This
# conservative boundary excludes only the first hours after the Snowflake epoch.
MIN_SNOWFLAKE_ID = 100_000_000_000_000
PRE_TWITTER_BOUNDARY = "2006-03-21 00:00:00+00"


@dataclass
class TimestampQualityAccumulator:
    eligible_rows: int = 0
    exact_rows: int = 0
    within_one_second_rows: int = 0
    mismatch_gt_one_second_rows: int = 0
    pre_twitter_rows: int = 0
    snowflake_min: datetime | None = None
    snowflake_max: datetime | None = None
    anomaly_samples: list[dict[str, Any]] = field(default_factory=list)

    def update(self, batch: pa.RecordBatch, source_seconds: pa.Array) -> None:
        tweet_ids = pc.cast(batch.column("tweet_id"), pa.uint64(), safe=True)
        eligible = pc.greater_equal(
            tweet_ids,
            pa.scalar(MIN_SNOWFLAKE_ID, type=pa.uint64()),
        )
        milliseconds = pc.add(
            pc.shift_right(tweet_ids, 22),
            pa.scalar(TWITTER_EPOCH_MS, type=pa.uint64()),
        )
        snowflake_times = pc.cast(
            milliseconds,
            pa.timestamp("ms", tz="UTC"),
        )
        snowflake_seconds = pc.cast(
            snowflake_times,
            pa.timestamp("s", tz="UTC"),
            safe=False,
        )
        derived_strings = pc.strftime(
            snowflake_seconds,
            format="%Y-%m-%d %H:%M:%S+00",
        )
        exact = pc.equal(derived_strings, source_seconds)
        plus_one = pc.equal(
            pc.strftime(
                pc.add(
                    snowflake_seconds,
                    pa.scalar(1, type=pa.duration("s")),
                ),
                format="%Y-%m-%d %H:%M:%S+00",
            ),
            source_seconds,
        )
        minus_one = pc.equal(
            pc.strftime(
                pc.subtract(
                    snowflake_seconds,
                    pa.scalar(1, type=pa.duration("s")),
                ),
                format="%Y-%m-%d %H:%M:%S+00",
            ),
            source_seconds,
        )
        within_one = pc.or_(pc.or_(exact, plus_one), minus_one)
        severe = pc.and_(eligible, pc.invert(within_one))

        self.eligible_rows += _true_count(eligible)
        self.exact_rows += _true_count(pc.and_(eligible, exact))
        self.within_one_second_rows += _true_count(pc.and_(eligible, within_one))
        self.mismatch_gt_one_second_rows += _true_count(severe)
        self.pre_twitter_rows += _true_count(
            pc.less(source_seconds, pa.scalar(PRE_TWITTER_BOUNDARY))
        )

        eligible_times = pc.filter(snowflake_times, eligible)
        if len(eligible_times):
            bounds = pc.min_max(eligible_times).as_py()
            self.snowflake_min = _earlier(self.snowflake_min, bounds["min"])
            self.snowflake_max = _later(self.snowflake_max, bounds["max"])
        self._capture_samples(batch, derived_strings, severe)

    def _capture_samples(
        self,
        batch: pa.RecordBatch,
        derived_strings: pa.Array,
        severe: pa.Array,
    ) -> None:
        remaining = 5 - len(self.anomaly_samples)
        if remaining <= 0 or not pc.any(severe).as_py():
            return
        for index in pc.indices_nonzero(severe).to_pylist()[:remaining]:
            source_value = batch.column("created_at")[index].as_py()
            if isinstance(source_value, datetime):
                source_value = utc_iso(source_value)
            self.anomaly_samples.append(
                {
                    "tweet_id": batch.column("tweet_id")[index].as_py(),
                    "account_id": batch.column("account_id")[index].as_py(),
                    "username": batch.column("username")[index].as_py(),
                    "source_created_at": source_value,
                    "snowflake_created_at": derived_strings[index].as_py(),
                }
            )

    def metrics(self) -> dict[str, Any]:
        return {
            "snowflake_eligible_rows": self.eligible_rows,
            "created_at_snowflake_exact_rows": self.exact_rows,
            "created_at_snowflake_within_one_second_rows": (
                self.within_one_second_rows
            ),
            "created_at_snowflake_mismatch_gt_one_second_rows": (
                self.mismatch_gt_one_second_rows
            ),
            "created_at_pre_twitter_rows": self.pre_twitter_rows,
            "snowflake_created_at_min": (
                utc_iso(self.snowflake_min) if self.snowflake_min else None
            ),
            "snowflake_created_at_max": (
                utc_iso(self.snowflake_max) if self.snowflake_max else None
            ),
            "created_at_anomaly_samples": self.anomaly_samples,
        }


def _true_count(values: pa.Array) -> int:
    return int(pc.sum(values).as_py() or 0)


def _earlier(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None else min(current, candidate)


def _later(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None else max(current, candidate)
