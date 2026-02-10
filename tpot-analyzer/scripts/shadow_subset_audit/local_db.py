"""Local sqlite query helpers for shadow subset audit."""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .normalize import normalize_username


def load_targets(
    conn: sqlite3.Connection,
    usernames: Sequence[str],
    sample_size: int,
) -> List[Tuple[str, Optional[str], List[str]]]:
    if usernames:
        target_names = sorted(
            {normalize_username(item) for item in usernames if normalize_username(item)}
        )
    else:
        rows = conn.execute(
            """
            SELECT username
            FROM shadow_account
            WHERE username IS NOT NULL
            ORDER BY COALESCE(followers_count, 0) DESC, COALESCE(following_count, 0) DESC
            LIMIT ?
            """,
            (max(1, sample_size),),
        ).fetchall()
        target_names = [normalize_username(row[0]) for row in rows if normalize_username(row[0])]

    if not target_names:
        return []

    out: List[Tuple[str, Optional[str], List[str]]] = []
    for username in target_names:
        candidate_ids: Set[str] = set()
        for row in conn.execute(
            "SELECT account_id FROM shadow_account WHERE lower(username) = ?",
            (username,),
        ):
            candidate_ids.add(str(row[0]))
        for row in conn.execute(
            "SELECT account_id FROM account WHERE lower(username) = ?",
            (username,),
        ):
            candidate_ids.add(str(row[0]))
        if not candidate_ids:
            candidate_ids.add(f"shadow:{username}")

        numeric_id = next((cid for cid in candidate_ids if cid.isdigit()), None)
        out.append((username, numeric_id, sorted(candidate_ids)))
    return out


def load_id_to_username(conn: sqlite3.Connection) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for table in ("shadow_account", "account"):
        for row in conn.execute(f"SELECT account_id, username FROM {table} WHERE username IS NOT NULL"):
            account_id = str(row[0])
            username = normalize_username(str(row[1]))
            if username:
                mapping[account_id] = username
    return mapping


def local_relation_usernames(
    conn: sqlite3.Connection,
    account_ids: Sequence[str],
    relation: str,
    id_to_username: Dict[str, str],
) -> Set[str]:
    if not account_ids:
        return set()

    placeholders = ",".join("?" for _ in account_ids)
    if relation == "followers":
        sql = (
            f"SELECT DISTINCT source_id AS rel_id FROM shadow_edge WHERE target_id IN ({placeholders}) AND direction='inbound' "
            f"UNION SELECT DISTINCT target_id AS rel_id FROM shadow_edge WHERE source_id IN ({placeholders}) AND direction='inbound'"
        )
    else:
        sql = (
            f"SELECT DISTINCT target_id AS rel_id FROM shadow_edge WHERE source_id IN ({placeholders}) AND direction='outbound' "
            f"UNION SELECT DISTINCT source_id AS rel_id FROM shadow_edge WHERE target_id IN ({placeholders}) AND direction='outbound'"
        )

    rows = conn.execute(sql, tuple(account_ids) + tuple(account_ids)).fetchall()
    usernames: Set[str] = set()
    for row in rows:
        rel_id = str(row[0])
        username = id_to_username.get(rel_id)
        if not username and rel_id.startswith("shadow:"):
            username = normalize_username(rel_id.split("shadow:", 1)[1])
        if username:
            usernames.add(username)
    return usernames
