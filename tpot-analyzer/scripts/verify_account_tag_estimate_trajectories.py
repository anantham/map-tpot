#!/usr/bin/env python3
"""Dry-run the estimate-trajectory migration without writing the source DB."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.account_tag_estimates import AccountTagEstimateStore
from scripts.account_tag_estimate_behavior_checks import behavior_checks


PRESERVED_TABLES = (
    "account_tags",
    "account_tag_events",
    "tag_meta_notes",
)
ESTIMATE_TABLE = "account_tag_estimate_events"
ESTIMATE_INDEX = "idx_account_tag_estimates_subject"


@dataclass(frozen=True)
class TableReceipt:
    rows: int
    sha256: str


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def table_receipt(conn: sqlite3.Connection, table: str) -> TableReceipt:
    columns = [
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]
    if not columns:
        return TableReceipt(rows=-1, sha256="missing")
    rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
    payload = json.dumps(
        {"columns": columns, "rows": rows},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return TableReceipt(rows=len(rows), sha256=hashlib.sha256(payload).hexdigest())


def receipts(conn: sqlite3.Connection) -> dict[str, TableReceipt]:
    return {table: table_receipt(conn, table) for table in PRESERVED_TABLES}


def copy_database(source: Path, destination: Path) -> None:
    with readonly_connection(source) as source_conn:
        with sqlite3.connect(destination) as destination_conn:
            source_conn.backup(destination_conn)


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def sample_subject(conn: sqlite3.Connection) -> tuple[str, str, str]:
    row = conn.execute(
        """
        SELECT ego, account_id, tag_display
        FROM account_tags
        ORDER BY rowid
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return "verification-curator", "verification-account", "verification-tag"
    return str(row[0]), str(row[1]), str(row[2])


def verify_copy(
    source: Path, *, expect_activated: bool = False
) -> tuple[list[Check], dict[str, object]]:
    source_hash_before = file_sha256(source)
    with tempfile.TemporaryDirectory(prefix="tpot-estimate-migration-") as temp_dir:
        copy_path = Path(temp_dir) / "account_tags-copy.db"
        copy_database(source, copy_path)

        with sqlite3.connect(copy_path) as conn:
            names_before = table_names(conn)
            source_activated = ESTIMATE_TABLE in names_before
            before = receipts(conn)
            ego, account_id, tag = sample_subject(conn)

        store = AccountTagEstimateStore(copy_path)
        current_before, history_before = store.get_estimates(
            ego=ego, account_id=account_id, tag=tag
        )

        with sqlite3.connect(copy_path) as conn:
            names_after_migration = table_names(conn)
            indexes_after_migration = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            after_migration = receipts(conn)
            new_rows_before_sample = int(
                conn.execute(
                    f'SELECT COUNT(*) FROM "{ESTIMATE_TABLE}"'
                ).fetchone()[0]
            )
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])

        sample = store.append_estimate(
            ego=ego,
            account_id=account_id,
            tag=tag,
            point_estimate=0.5,
            plausible_low=0.25,
            plausible_high=0.75,
            review_session_id="dry-run-review-session",
            source="verification_script",
        )
        current_after, history_after = store.get_estimates(
            ego=ego, account_id=account_id, tag=tag
        )

        with sqlite3.connect(copy_path) as conn:
            after_sample = receipts(conn)
            new_rows_after_sample = int(
                conn.execute(
                    f'SELECT COUNT(*) FROM "{ESTIMATE_TABLE}"'
                ).fetchone()[0]
            )

    source_hash_after = file_sha256(source)
    preserved = all(
        before[table] == after_migration[table] == after_sample[table]
        for table in PRESERVED_TABLES
    )
    newly_added = names_after_migration - names_before
    expected_new_tables = set() if expect_activated else {ESTIMATE_TABLE}
    checks = [
        Check(
            "Source opened read-only",
            source_hash_before == source_hash_after,
            f"sha256={source_hash_after}",
        ),
        Check(
            "Preserved row receipts",
            preserved,
            "; ".join(
                f"{table}={before[table].rows}:{before[table].sha256[:12]}"
                for table in PRESERVED_TABLES
            ),
        ),
        Check(
            "Additive schema only",
            source_activated == expect_activated
            and newly_added == expected_new_tables,
            (
                f"source_activated={source_activated} "
                f"new_tables={sorted(newly_added)}"
            ),
        ),
        Check(
            "Legacy estimates remain unknown",
            current_before is None
            and history_before == []
            and new_rows_before_sample == 0,
            f"preexisting_estimate_rows={new_rows_before_sample}",
        ),
        Check(
            "Estimate lookup index exists",
            ESTIMATE_INDEX in indexes_after_migration,
            ESTIMATE_INDEX,
        ),
        Check(
            "Trajectory round trip",
            current_after == sample
            and len(history_after) == 1
            and new_rows_after_sample == 1,
            (
                f"event_id={sample.event_id} point={sample.point_estimate:.2f} "
                f"range=[{sample.plausible_low:.2f},{sample.plausible_high:.2f}]"
            ),
        ),
        Check("Copied database integrity", integrity == "ok", integrity),
    ]
    metrics = {
        "source": str(source),
        "sourceSha256": source_hash_before,
        "sourceActivated": source_activated,
        "preservedRows": {
            table: before[table].rows for table in PRESERVED_TABLES
        },
        "newEstimateRowsBeforeSample": new_rows_before_sample,
        "newEstimateRowsAfterSample": new_rows_after_sample,
        "sampleSubject": {"ego": ego, "accountId": account_id, "tag": tag},
        "sourceWrites": 0,
    }
    return checks, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-db",
        required=True,
        type=Path,
        help="existing account_tags.db to read and copy; the source is never opened writable",
    )
    parser.add_argument(
        "--expect-activated",
        action="store_true",
        help="require the source to already contain the empty estimate table",
    )
    args = parser.parse_args()
    source = args.source_db.expanduser().resolve()
    if not source.is_file():
        parser.error(f"--source-db does not exist: {source}")

    print("Account Tag Estimate Trajectory Migration Verification")
    print("=" * 55)
    checks, metrics = verify_copy(
        source, expect_activated=args.expect_activated
    )
    checks.extend(behavior_checks())
    for check in checks:
        print(f"{'✓' if check.passed else '✗'} {check.name}: {check.detail}")
    failures = [check for check in checks if not check.passed]
    print("-" * 55)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    print(
        f"Checks: {len(checks)} | Passed: {len(checks) - len(failures)} | "
        f"Failed: {len(failures)}"
    )
    if failures:
        print("Next: decline live migration and inspect the failed receipt.")
        return 1
    if args.expect_activated:
        print(
            "Next: activation is verified; keep legacy estimates unknown until "
            "the curator explicitly records one. This run made zero source writes."
        )
    else:
        print(
            "Next: inspect these receipts and explicitly approve or decline the "
            "live additive migration. This run made zero source writes."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
