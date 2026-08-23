"""Focused read queries over the mutable account-tag projection."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetTagAnchors:
    positive: tuple[str, ...]
    negative: tuple[str, ...]


class AccountTagStoreError(RuntimeError):
    """Base for unavailable or invalid working-tag state."""


class AccountTagStoreUnavailableError(AccountTagStoreError):
    """Raised when the configured working-tag projection is absent."""


class AccountTagIntegrityError(AccountTagStoreError):
    """Raised when persisted working-tag state violates its contract."""


def load_target_tag_anchors(
    db_path: Path,
    *,
    ego: str,
    tag: str,
) -> TargetTagAnchors:
    """Return current anchors for exactly one ego/tag pair.

    This intentionally does not use ``list_anchor_polarities``: that legacy
    query combines unrelated tags and cannot define an overlapping target.
    A missing store means there are no judgments yet; a malformed store still
    fails loudly through SQLite.
    """
    tag_key = str(tag or "").strip().casefold()
    normalized_ego = str(ego or "").strip()
    if not normalized_ego:
        raise ValueError("ego is required")
    if not tag_key:
        raise ValueError("tag is required")
    resolved = Path(db_path).expanduser().resolve()
    if not resolved.is_file():
        raise AccountTagStoreUnavailableError(
            f"account tag database not found: {resolved}"
        )

    with closing(
        sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    ) as conn:
        conn.execute("PRAGMA query_only=ON")
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(account_tags)")
        }
        required = {"ego", "account_id", "tag_key", "polarity"}
        if not required <= columns:
            raise AccountTagStoreUnavailableError(
                "account tag database lacks an initialized account_tags schema"
            )
        rows = conn.execute(
            """
            SELECT account_id, polarity
            FROM account_tags
            WHERE ego = ? AND tag_key = ?
            ORDER BY account_id
            """,
            (normalized_ego, tag_key),
        ).fetchall()
    polarities: list[tuple[str, int]] = []
    for account_id, polarity in rows:
        if type(polarity) is not int or polarity not in (-1, 1):
            raise AccountTagIntegrityError(
                "account_tags contains a polarity outside the {-1, 1} contract"
            )
        polarities.append((str(account_id), polarity))
    return TargetTagAnchors(
        positive=tuple(account_id for account_id, value in polarities if value == 1),
        negative=tuple(account_id for account_id, value in polarities if value == -1),
    )
