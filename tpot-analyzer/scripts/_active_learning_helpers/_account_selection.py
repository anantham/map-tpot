"""Account selection from frontier_ranking + handle resolution + ego-proximity boost."""
from __future__ import annotations

import logging
import sqlite3

from scripts._active_learning_helpers.frontier_quarantine import (
    reject_unverified_frontier_ranking,
)
from scripts.fetch_tweets_for_account import is_stale

logger = logging.getLogger(__name__)


def _load_ego_hops(conn: sqlite3.Connection, ego_account_id: str) -> tuple[set, set]:
    """Load hop-1 and hop-2 account sets from ego's follow graph.

    Returns (hop1_ids, hop2_ids) where:
      hop1 = accounts ego follows directly
      hop2 = accounts ego's follows follow (excluding hop1)
    """
    hop1 = set(
        r[0] for r in conn.execute(
            "SELECT following_account_id FROM account_following WHERE account_id = ?",
            (ego_account_id,),
        ).fetchall()
    )
    if not hop1:
        return hop1, set()

    # Hop 2: friends-of-friends, batched to avoid huge IN clause
    hop2 = set()
    hop1_list = list(hop1)
    batch_size = 500
    for i in range(0, len(hop1_list), batch_size):
        batch = hop1_list[i:i + batch_size]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"SELECT DISTINCT following_account_id FROM account_following WHERE account_id IN ({placeholders})",
            batch,
        ).fetchall()
        hop2.update(r[0] for r in rows)
    hop2 -= hop1  # don't double-count hop1
    hop2.discard(ego_account_id)  # don't include self

    return hop1, hop2


def select_accounts(
    conn: sqlite3.Connection,
    top_n: int,
    round_num: int,
    ego_account_id: str | None = None,
) -> list[dict]:
    """Reject automatic selection from the quarantined frontier ranking."""
    reject_unverified_frontier_ranking("active-learning account selection")
    return _select_accounts_from_unverified_frontier(
        conn,
        top_n=top_n,
        round_num=round_num,
        ego_account_id=ego_account_id,
    )


def _select_accounts_from_unverified_frontier(
    conn: sqlite3.Connection,
    top_n: int,
    round_num: int,
    ego_account_id: str | None = None,
) -> list[dict]:
    """Select top accounts from frontier_ranking for enrichment.

    This private helper preserves the historical query for regression tests
    and a future versioned replacement. Production callers must use
    ``select_accounts()``, which currently fails closed.

    Excludes:
      - holdout accounts (in_holdout=1 OR in tpot_directory_holdout)
      - already enriched via the normal account fetch path
        (topic-seed search hits do NOT count as account enrichment)
      - accounts with no resolvable username (profiles OR resolved_accounts)

    If ego_account_id is provided, boosts accounts by proximity:
      - Hop 1 (ego follows them): 3x boost
      - Hop 2 (ego's follows follow them): 1.5x boost
      - Hop 3+: no boost

    Returns list of dicts sorted by priority DESC.
    """
    # Load more candidates than needed so proximity boost can re-rank
    fetch_limit = top_n * 5 if ego_account_id else top_n

    sql = """
        SELECT fr.account_id, fr.info_value, fr.top_community,
               COALESCE(p.username, ra.username) as username
        FROM frontier_ranking fr
        LEFT JOIN profiles p ON fr.account_id = p.account_id
        LEFT JOIN resolved_accounts ra ON fr.account_id = ra.account_id
        WHERE fr.in_holdout = 0
        AND COALESCE(p.username, ra.username) IS NOT NULL
        AND fr.account_id NOT IN (
            SELECT account_id FROM tpot_directory_holdout
            WHERE account_id IS NOT NULL
        )
        AND NOT EXISTS (
            SELECT 1
            FROM enriched_tweets et
            WHERE et.account_id = fr.account_id
            AND COALESCE(et.fetch_source, '') != 'topic_seed'
        )
        ORDER BY fr.info_value DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (fetch_limit,)).fetchall()

    accounts = [
        {
            "account_id": row[0],
            "info_value": row[1],
            "top_community": row[2],
            "username": row[3],
        }
        for row in rows
    ]

    # Apply ego proximity boost
    if ego_account_id and accounts:
        hop1, hop2 = _load_ego_hops(conn, ego_account_id)
        for acct in accounts:
            aid = acct["account_id"]
            if aid in hop1:
                acct["proximity"] = "hop1"
                acct["priority"] = acct["info_value"] * 3.0
            elif aid in hop2:
                acct["proximity"] = "hop2"
                acct["priority"] = acct["info_value"] * 1.5
            else:
                acct["proximity"] = "hop3+"
                acct["priority"] = acct["info_value"]
        accounts.sort(key=lambda a: a["priority"], reverse=True)
        logger.info(
            "Ego boost applied: %d hop1, %d hop2, %d hop3+",
            sum(1 for a in accounts if a["proximity"] == "hop1"),
            sum(1 for a in accounts if a["proximity"] == "hop2"),
            sum(1 for a in accounts if a["proximity"] == "hop3+"),
        )
    else:
        for acct in accounts:
            acct["proximity"] = "n/a"
            acct["priority"] = acct["info_value"]

    return accounts[:top_n]


def select_accounts_by_handle(
    conn: sqlite3.Connection, handles: list[str]
) -> list[dict]:
    """Select specific accounts by handle, bypassing frontier_ranking.

    Resolves handles to account_ids via profiles/resolved_accounts.
    Skips holdout accounts and already-enriched accounts.
    Does NOT require accounts to be in frontier_ranking.
    """
    holdout_ids = set(
        r[0] for r in conn.execute(
            "SELECT account_id FROM tpot_directory_holdout WHERE account_id IS NOT NULL"
        ).fetchall()
    )
    account_enriched_ids = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM enriched_tweets "
            "WHERE COALESCE(fetch_source, '') != 'topic_seed'"
        ).fetchall()
    )

    accounts = []
    seen_account_ids: set[str] = set()
    for raw_handle in handles:
        handle = raw_handle.strip().lstrip("@")
        if not handle:
            continue
        # Resolve handle → account_id
        row = conn.execute(
            "SELECT account_id, username FROM profiles WHERE LOWER(username) = LOWER(?)",
            (handle,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT account_id, username FROM resolved_accounts WHERE LOWER(username) = LOWER(?)",
                (handle,),
            ).fetchone()
        if not row:
            logger.warning("Could not resolve handle: @%s — skipping", handle)
            continue

        aid, username = row[0], row[1]
        if aid in seen_account_ids:
            logger.info(
                "@%s resolves to an already-selected account — skipping",
                handle,
            )
            continue
        seen_account_ids.add(aid)

        if aid in holdout_ids:
            logger.warning("@%s is a holdout account — skipping", handle)
            continue

        stale = is_stale(
            conn,
            aid,
            ignored_fetch_sources=("topic_seed",),
        )
        if aid in account_enriched_ids and not stale:
            logger.warning("@%s already enriched (fresh) — skipping", handle)
            continue
        if aid in account_enriched_ids and stale:
            logger.info("@%s enriched but stale (>%d days) — re-fetching", handle, 30)

        accounts.append({
            "account_id": aid,
            "info_value": 0.0,
            "top_community": "unknown",
            "username": username,
            "proximity": "manual",
            "priority": 999.0,  # manual picks always highest priority
        })

    return accounts
