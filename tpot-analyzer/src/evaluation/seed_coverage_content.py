"""Immutable Community Archive content adapter for seed coverage."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.archive.snapshot_manifest import verify_local_snapshot


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def snapshot_content(
    snapshot_dir: Path,
    seeds: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    return _snapshot_content_cached(
        str(Path(snapshot_dir).expanduser().resolve()),
        tuple(seed["account_id"] for seed in seeds),
    )


@lru_cache(maxsize=4)
def _snapshot_content_cached(
    snapshot_dir: str,
    ids: tuple[str, ...],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    resolved_snapshot = Path(snapshot_dir)
    checks, metrics = verify_local_snapshot(resolved_snapshot, deep=True)
    failed = [check.name for check in checks if not check.passed]
    if failed:
        raise ValueError(f"archive snapshot failed verification: {failed}")
    data_path = resolved_snapshot / "enriched_tweets.parquet"
    schema = set(pq.ParquetFile(data_path).schema_arrow.names)
    required = {"account_id", "created_at", "reply_to_user_id"}
    if not required <= schema:
        raise ValueError(
            f"archive snapshot missing columns: {sorted(required - schema)}"
        )
    columns = ["account_id", "created_at", "reply_to_user_id"]
    authored = pq.read_table(
        data_path,
        columns=columns,
        filters=[("account_id", "in", ids)],
    )
    incoming = pq.read_table(
        data_path,
        columns=columns,
        filters=[("reply_to_user_id", "in", ids)],
    )
    output: dict[str, dict[str, Any]] = {}
    for account_id in ids:
        own = authored.filter(pc.equal(authored["account_id"], account_id))
        received = incoming.filter(pc.equal(incoming["reply_to_user_id"], account_id))
        nonself = received.filter(pc.not_equal(received["account_id"], account_id))
        times = [_iso(value) for value in own["created_at"].to_pylist()]
        valid_times = sorted(value for value in times if value is not None)
        reply_targets = own["reply_to_user_id"].to_pylist()
        output[account_id] = {
            "status": "observed",
            "authored_rows": len(own),
            "authored_reply_rows": sum(value is not None for value in reply_targets),
            "incoming_nonself_reply_rows": len(nonself),
            "incoming_nonself_reply_accounts": len(
                {str(value) for value in nonself["account_id"].to_pylist()}
            ),
            "created_at_min": valid_times[0] if valid_times else None,
            "created_at_max": valid_times[-1] if valid_times else None,
        }
    return output, {
        "path": str(resolved_snapshot),
        "snapshot_id": metrics["snapshot_id"],
        "sha256": metrics["sha256"],
        "row_count": metrics["row_count"],
        "account_count": metrics["account_count"],
        "created_at_max": metrics["created_at_max"],
        "verification": "deep sha256 and manifest checks passed",
    }
