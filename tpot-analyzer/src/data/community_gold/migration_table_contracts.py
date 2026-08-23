"""Runtime validation for canonical Community Gold table constraints."""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import Any

from .migration_table_specs import (
    _CHECK_FRAGMENTS,
    _FOREIGN_KEYS,
    _NOT_NULL_COLUMNS,
    _UNIQUE_COLUMNS,
)


def _normalized_sql(value: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(value).strip().lower())
    normalized = re.sub(r"\bcheck\s*\(", "check (", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    return re.sub(r"\s+\)", ")", normalized)


def _without_comments(value: Any) -> str:
    sql = str(value)
    output: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(sql):
        character = sql[index]
        if quote is not None:
            output.append(character)
            if character == quote:
                if (
                    quote in {"'", '"'}
                    and index + 1 < len(sql)
                    and sql[index + 1] == quote
                ):
                    output.append(sql[index + 1])
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            output.append(character)
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = len(sql) if newline < 0 else newline
            output.append(" ")
            continue
        if sql.startswith("/*", index):
            closing = sql.find("*/", index + 2)
            index = len(sql) if closing < 0 else closing + 2
            output.append(" ")
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _next_check(sql: str, start: int) -> tuple[int, int] | None:
    quote: str | None = None
    index = start
    while index < len(sql):
        character = sql[index]
        if quote is not None:
            if character == quote:
                if (
                    quote in {"'", '"'}
                    and index + 1 < len(sql)
                    and sql[index + 1] == quote
                ):
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            index += 1
            continue
        if sql.startswith("check", index):
            before = sql[index - 1] if index else " "
            after = sql[index + 5] if index + 5 < len(sql) else " "
            opening = index + 5
            while opening < len(sql) and sql[opening].isspace():
                opening += 1
            if (
                not (before.isalnum() or before == "_")
                and not (after.isalnum() or after == "_")
                and opening < len(sql)
                and sql[opening] == "("
            ):
                return index, opening
        index += 1
    return None


def _check_clauses(value: Any) -> set[str]:
    """Extract balanced CHECK clauses while ignoring comments and strings."""

    sql = _normalized_sql(_without_comments(value))
    output: set[str] = set()
    cursor = 0
    while True:
        match = _next_check(sql, cursor)
        if match is None:
            return output
        start, opening = match
        depth = 0
        quoted = False
        index = opening
        while index < len(sql):
            character = sql[index]
            if character == "'":
                if quoted and index + 1 < len(sql) and sql[index + 1] == "'":
                    index += 2
                    continue
                quoted = not quoted
            elif not quoted and character == "(":
                depth += 1
            elif not quoted and character == ")":
                depth -= 1
                if depth == 0:
                    output.add(sql[start : index + 1])
                    cursor = index + 1
                    break
            index += 1
        else:
            return output


def _unique_column_sets(
    conn: sqlite3.Connection,
    table: str,
) -> set[tuple[str, ...]]:
    output = set()
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if (
            int(row[2]) != 1
            or str(row[3]).lower() != "u"
            or int(row[4]) != 0
        ):
            continue
        output.add(
            tuple(
                str(item[2])
                for item in conn.execute(
                    f"PRAGMA index_info({row[1]})"
                ).fetchall()
            )
        )
    return output


def _foreign_key_set(
    conn: sqlite3.Connection,
    table: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...], str]]:
    grouped: dict[int, list[Any]] = defaultdict(list)
    for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall():
        grouped[int(row[0])].append(row)
    return {
        (
            tuple(str(row[3]) for row in sorted(rows, key=lambda row: row[1])),
            str(rows[0][2]),
            tuple(str(row[4]) for row in sorted(rows, key=lambda row: row[1])),
            str(rows[0][6]).upper(),
        )
        for rows in grouped.values()
    }


def validate_table_constraints(
    conn: sqlite3.Connection,
    *,
    table: str,
) -> None:
    """Reject lookalike tables missing canonical scientific constraints."""

    info = {
        str(row[1]): row
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    missing_not_null = sorted(
        column
        for column in _NOT_NULL_COLUMNS.get(table, frozenset())
        if column not in info or int(info[column][3]) != 1
    )
    if missing_not_null:
        raise RuntimeError(
            f"Community Gold table '{table}' has incompatible NOT NULL "
            f"constraints: missing={missing_not_null}"
        )

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    checks = _check_clauses(row[0] if row is not None else "")
    missing_checks = [
        fragment
        for fragment in _CHECK_FRAGMENTS.get(table, ())
        if fragment not in checks
    ]
    if missing_checks:
        raise RuntimeError(
            f"Community Gold table '{table}' has incompatible CHECK "
            f"constraints: missing={missing_checks}"
        )

    expected_fks = _FOREIGN_KEYS.get(table, frozenset())
    observed_fks = _foreign_key_set(conn, table)
    if observed_fks != set(expected_fks):
        raise RuntimeError(
            f"Community Gold table '{table}' has incompatible foreign keys: "
            f"expected={sorted(expected_fks)}, observed={sorted(observed_fks)}"
        )

    unique_sets = _unique_column_sets(conn, table)
    missing_unique = sorted(
        set(_UNIQUE_COLUMNS.get(table, frozenset())) - unique_sets
    )
    if missing_unique:
        raise RuntimeError(
            f"Community Gold table '{table}' has incompatible UNIQUE "
            f"constraints: missing={missing_unique}"
        )
