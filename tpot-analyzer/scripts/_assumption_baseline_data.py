"""Read-only data checks for the assumption baseline verifier."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts._assumption_baseline_checks import Report, format_bytes, sha256


EXPECTED_DATA = (
    "archive_tweets.db",
    "cache.db",
    "graph_snapshot.nodes.parquet",
    "graph_snapshot.edges.parquet",
    "graph_snapshot.meta.json",
    "graph_snapshot.spectral.npz",
    "graph_snapshot.spectral_meta.json",
    "community_propagation.npz",
)


def _snowflake_datetime(tweet_id: str | None) -> datetime | None:
    """Decode a Twitter Snowflake ID without trusting mixed date strings."""
    if not tweet_id:
        return None
    try:
        timestamp_ms = (int(tweet_id) >> 22) + 1_288_834_974_657
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _connection(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def inspect_archive(path: Path, report: Report, deep: bool) -> None:
    try:
        with _connection(path) as connection:
            tables = _table_names(connection)
            required = {"tweets", "likes", "fetch_log"}
            report.check(
                "archive schema",
                required <= tables,
                f"{len(tables)} tables; required={sorted(required)}",
            )
            if not required <= tables:
                return
            tweet_count = connection.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
            newest_row = connection.execute(
                """
                SELECT tweet_id, created_at
                FROM tweets
                WHERE length(tweet_id) = 19
                ORDER BY tweet_id DESC
                LIMIT 1
                """
            ).fetchone()
            newest_tweet_id, newest_tweet_text = (
                newest_row if newest_row is not None else (None, None)
            )
            report.check(
                "archive has a valid newest tweet",
                newest_tweet_id is not None,
                str(newest_tweet_id or "no 19-digit Twitter Snowflake ID found"),
            )
            like_count = connection.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
            fetch_rows, distinct_account_ids, latest_fetch = connection.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT account_id), MAX(fetched_at)
                FROM fetch_log
                """
            ).fetchone()
            report.metrics.extend(
                (
                    f"archive_tweets: {tweet_count:,}",
                    f"archive_likes: {like_count:,}",
                    f"archive_fetch_log_usernames: {fetch_rows:,}",
                    f"archive_fetch_log_account_ids: {distinct_account_ids:,}",
                    f"newest_tweet_id: {newest_tweet_id or 'unknown'}",
                    f"newest_tweet_source_date: {newest_tweet_text or 'unknown'}",
                    f"latest_archive_fetch: {latest_fetch or 'unknown'}",
                )
            )
            newest = _snowflake_datetime(newest_tweet_id)
            if newest:
                age_days = (datetime.now(timezone.utc) - newest).days
                report.metrics.append(f"newest_tweet_utc: {newest.isoformat()}")
                if age_days > 30:
                    report.warn(
                        "archive freshness",
                        f"newest tweet is {age_days} days old ({newest.isoformat()})",
                    )
            if deep:
                outcome = connection.execute("PRAGMA quick_check").fetchone()[0]
                report.check("archive quick_check", outcome == "ok", str(outcome))
    except sqlite3.Error as exc:
        report.check("archive readable", False, f"{type(exc).__name__}: {exc}")


def _inspect_cache(path: Path, report: Report, deep: bool) -> None:
    try:
        with _connection(path) as connection:
            tables = _table_names(connection)
            required = {"profile", "following", "followers", "cache_metadata"}
            report.check(
                "cache schema",
                required <= tables,
                f"{len(tables)} tables; required={sorted(required)}",
            )
            if not required <= tables:
                return
            for table in ("profile", "following", "followers"):
                count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                report.metrics.append(f"cache_{table}: {count:,}")
            latest_cache = connection.execute(
                "SELECT MAX(fetched_at) FROM cache_metadata"
            ).fetchone()[0]
            report.metrics.append(f"latest_cache_fetch: {latest_cache or 'unknown'}")
            if deep:
                outcome = connection.execute("PRAGMA quick_check").fetchone()[0]
                report.check("cache quick_check", outcome == "ok", str(outcome))
    except sqlite3.Error as exc:
        report.check("cache readable", False, f"{type(exc).__name__}: {exc}")


def inspect_data(
    data_dir: Path,
    source_dir: Path | None,
    report: Report,
    require_data: bool,
    hash_data: bool,
    deep: bool,
) -> None:
    present = 0
    for name in EXPECTED_DATA:
        destination = data_dir / name
        exists = destination.is_file() and not destination.is_symlink()
        if exists:
            present += 1
        if require_data:
            report.check("working data file", exists, str(destination))
        elif exists:
            report.check("optional data file", True, str(destination))

        if not exists:
            continue
        stat = destination.stat()
        report.metrics.append(
            f"{name}: {format_bytes(stat.st_size)}, "
            f"mtime={datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()}"
        )
        if destination.suffix == ".db":
            working_wal = destination.with_name(f"{destination.name}-wal")
            wal_size = working_wal.stat().st_size if working_wal.exists() else 0
            report.check(
                "working SQLite WAL quiescent",
                wal_size == 0,
                f"{working_wal}: {wal_size} bytes",
            )
        if name in {"graph_snapshot.spectral.npz", "community_propagation.npz"}:
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            age_days = (datetime.now(timezone.utc) - modified).days
            if age_days > 30:
                report.warn(
                    f"{name} freshness",
                    f"artifact is {age_days} days old ({modified.isoformat()})",
                )
        if source_dir is None:
            continue
        source = source_dir / name
        source_exists = source.is_file() and not source.is_symlink()
        report.check("source data file", source_exists, str(source))
        if not source_exists:
            continue
        source_stat = source.stat()
        if source.suffix == ".db":
            source_wal = source.with_name(f"{source.name}-wal")
            wal_size = source_wal.stat().st_size if source_wal.exists() else 0
            report.check(
                "source SQLite WAL quiescent",
                wal_size == 0,
                f"{source_wal}: {wal_size} bytes",
            )
        independent = (stat.st_dev, stat.st_ino) != (
            source_stat.st_dev,
            source_stat.st_ino,
        )
        report.check("independent data copy", independent, name)
        report.check(
            "data size parity",
            stat.st_size == source_stat.st_size,
            f"{name}: source={source_stat.st_size}, working={stat.st_size}",
        )
        if hash_data:
            source_hash = sha256(source)
            destination_hash = sha256(destination)
            report.check(
                "data hash parity",
                source_hash == destination_hash,
                f"{name}: sha256={destination_hash}",
            )

    if not require_data and present == 0:
        report.warn(
            "working data",
            "no production artifacts attached; fixture-only checks remain available",
        )
    archive_path = data_dir / "archive_tweets.db"
    if archive_path.is_file():
        inspect_archive(archive_path, report, deep)
    cache_path = data_dir / "cache.db"
    if cache_path.is_file():
        _inspect_cache(cache_path, report, deep)

    metadata_path = data_dir / "graph_snapshot.spectral_meta.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            report.metrics.append(
                "spectral_metadata: "
                + ", ".join(
                    f"{key}={metadata[key]}"
                    for key in ("n_nodes", "n_components", "created_at", "generated_at")
                    if key in metadata
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            report.warn("spectral metadata", f"could not parse: {exc}")
