"""Validation tests comparing archive data to shadow scrape outputs."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.data.shadow_store import get_shadow_store


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "cache.db"


def _fetch_overlap_rows() -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.account_id,
            s.username AS shadow_username,
            s.display_name AS shadow_display_name,
            s.followers_count AS shadow_followers,
            s.following_count AS shadow_following,
            a.username AS archive_username,
            a.account_display_name AS archive_display_name,
            a.num_followers AS archive_followers,
            a.num_following AS archive_following
        FROM shadow_account AS s
        INNER JOIN account AS a ON s.account_id = a.account_id
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def _sync_overlaps() -> None:
    engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
    store = get_shadow_store(engine)
    store.sync_archive_overlaps()


@pytest.mark.skipif(not DB_PATH.exists(), reason="data/cache.db not available")
def test_shadow_usernames_align_with_archive() -> None:
    _sync_overlaps()
    overlap_rows = _fetch_overlap_rows()
    assert overlap_rows, "Expected at least one overlapping archive/shadow account"

    mismatches = [
        (row["account_id"], row["shadow_username"], row["archive_username"])
        for row in overlap_rows
        if (row["shadow_username"] or "").lower() != (row["archive_username"] or "").lower()
    ]

    assert not mismatches, (
        "Shadow usernames diverge from archive for account_ids: "
        + ", ".join(f"{aid} (shadow={su}, archive={au})" for aid, su, au in mismatches)
    )

    display_mismatches = [
        (row["account_id"], row["shadow_display_name"], row["archive_display_name"])
        for row in overlap_rows
        if row["shadow_display_name"]
        and row["archive_display_name"]
        and row["shadow_display_name"].strip() != row["archive_display_name"].strip()
    ]

    assert not display_mismatches, (
        "Display names diverge from archive for account_ids: "
        + ", ".join(
            f"{aid} (shadow={sd}, archive={ad})" for aid, sd, ad in display_mismatches
        )
    )


@pytest.mark.skipif(not DB_PATH.exists(), reason="data/cache.db not available")
def test_shadow_follow_counts_within_archive_tolerance() -> None:
    _sync_overlaps()
    overlap_rows = _fetch_overlap_rows()
    assert overlap_rows, "Expected at least one overlapping archive/shadow account"

    tolerance_pct = 0.05  # 5%
    tolerance_abs = 200

    follower_rows = [
        row
        for row in overlap_rows
        if row["shadow_followers"] is not None and row["archive_followers"] is not None
    ]
    following_rows = [
        row
        for row in overlap_rows
        if row["shadow_following"] is not None and row["archive_following"] is not None
    ]

    # If Selenium hasn’t captured counts yet, skip with a friendly message.
    if not follower_rows and not following_rows:
        pytest.skip("No overlapping accounts with both archive and shadow counts populated")

    def _collect_failures(rows: list[sqlite3.Row], attr_shadow: str, attr_archive: str) -> list[str]:
        failures: list[str] = []
        for row in rows:
            shadow_val = row[attr_shadow]
            archive_val = row[attr_archive]
            diff = abs(shadow_val - archive_val)
            if diff <= tolerance_abs:
                continue
            pct = diff / max(archive_val, 1)
            if pct <= tolerance_pct:
                continue
            failures.append(
                f"@{row['shadow_username']} {attr_shadow}->{shadow_val} vs {attr_archive}->{archive_val} (Δ={diff}, {pct:.1%})"
            )
        return failures

    follower_failures = _collect_failures(
        follower_rows, "shadow_followers", "archive_followers"
    )
    following_failures = _collect_failures(
        following_rows, "shadow_following", "archive_following"
    )

    errors = follower_failures + following_failures
    assert not errors, "; ".join(errors)
