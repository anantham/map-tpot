"""Fail-closed lineage checks for study-scoped judgment heads."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Mapping, Sequence

JudgmentKey = tuple[str, str, str]


def assert_complete_linear_histories(
    conn: sqlite3.Connection,
    *,
    frame_id: str,
    reviewer: str,
    expected_keys: set[JudgmentKey],
    current_rows: Sequence[Mapping[str, object]],
) -> None:
    """Require every released head to terminate one complete linear history."""

    current_by_key = {
        (
            str(row["accountId"]),
            str(row["communityId"]),
            str(row["reviewer"]),
        ): int(row["labelSetId"])
        for row in current_rows
    }
    if set(current_by_key) != expected_keys:
        raise ValueError(
            "terminal judgment heads do not match expected lineage keys"
        )

    stored = conn.execute(
        """
        SELECT id, account_id, community_id, reviewer,
               supersedes_label_set_id
        FROM account_community_gold_label_set
        WHERE identity_status = 'scoped'
          AND study_frame_id = ? AND reviewer = ?
        ORDER BY id
        """,
        (frame_id, reviewer),
    ).fetchall()
    histories: dict[JudgmentKey, list[sqlite3.Row]] = defaultdict(list)
    for row in stored:
        key = (
            str(row["account_id"]),
            str(row["community_id"]),
            str(row["reviewer"]),
        )
        if key in expected_keys:
            histories[key].append(row)

    for key in sorted(expected_keys):
        rows = histories.get(key, [])
        by_id = {int(row["id"]): row for row in rows}
        roots = [
            int(row["id"])
            for row in rows
            if row["supersedes_label_set_id"] is None
        ]
        children: dict[int, list[int]] = defaultdict(list)
        for row in rows:
            parent = row["supersedes_label_set_id"]
            if parent is None:
                continue
            parent_id = int(parent)
            if parent_id not in by_id:
                raise ValueError(
                    "scoped judgment history crosses identity or frame: "
                    f"key={key}, label_set_id={row['id']}, parent={parent_id}"
                )
            children[parent_id].append(int(row["id"]))
        branches = {
            parent: child_ids
            for parent, child_ids in children.items()
            if len(child_ids) != 1
        }
        if len(roots) != 1 or branches:
            raise ValueError(
                "scoped judgment history is not one linear chain: "
                f"key={key}, roots={roots}, branches={branches}"
            )

        visited: list[int] = []
        cursor = roots[0]
        while True:
            if cursor in visited:
                raise ValueError(
                    f"scoped judgment history contains a cycle: key={key}"
                )
            visited.append(cursor)
            next_ids = children.get(cursor, [])
            if not next_ids:
                break
            cursor = next_ids[0]
        if len(visited) != len(rows) or cursor != current_by_key[key]:
            raise ValueError(
                "scoped judgment head is stale or history is disconnected: "
                f"key={key}, head={current_by_key[key]}, leaf={cursor}, "
                f"visited={len(visited)}, stored={len(rows)}"
            )
