"""Validation tests comparing archive data to shadow scrape outputs."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

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


def _table_exists(name: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def _fetch_profile_overlap_rows() -> list[sqlite3.Row]:
    if not _table_exists("profile"):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.account_id,
            lower(s.username) AS username,
            s.display_name AS shadow_display_name,
            s.bio AS shadow_bio,
            s.website AS shadow_website,
            s.location AS shadow_location,
            s.profile_image_url AS shadow_avatar,
            p.bio AS archive_bio,
            p.website AS archive_website,
            p.location AS archive_location,
            p.avatar_media_url AS archive_avatar
        FROM shadow_account AS s
        INNER JOIN profile AS p ON lower(s.username) = lower(p.username)
        WHERE s.account_id IN (SELECT account_id FROM account)
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalize_url(value: Optional[str]) -> Optional[str]:
    text = _normalize_text(value)
    if not text:
        return None
    normalized = text.lower()
    for prefix in ("https://", "http://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.rstrip("/")
    return normalized

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


@pytest.mark.skipif(not DB_PATH.exists(), reason="data/cache.db not available")
def test_shadow_profile_fields_match_archive() -> None:
    if not _table_exists("profile"):
        pytest.skip(
            "Supabase profile table not cached locally; run fetcher to populate profile data"
        )

    rows = _fetch_profile_overlap_rows()
    if not rows:
        pytest.skip("No overlapping accounts with profile metadata available")

    def collect_mismatch(field_shadow: str, field_archive: str) -> list[str]:
        failures: list[str] = []
        for row in rows:
            s_val = _normalize_text(row[field_shadow])
            a_val = _normalize_text(row[field_archive])
            if s_val is None or a_val is None:
                continue
            if s_val != a_val:
                failures.append(
                    f"@{row['username']} {field_shadow}≠{field_archive}"
                    f" (shadow={row[field_shadow]!r}, archive={row[field_archive]!r})"
                )
        return failures

    text_failures = (
        collect_mismatch("shadow_bio", "archive_bio")
        + collect_mismatch("shadow_location", "archive_location")
    )
    assert not text_failures, "; ".join(text_failures)

    website_failures: list[str] = []
    for row in rows:
        s_url = _normalize_url(row["shadow_website"])
        a_url = _normalize_url(row["archive_website"])
        if s_url is None or a_url is None:
            continue
        if s_url != a_url:
            website_failures.append(
                f"@{row['username']} website mismatch (shadow={row['shadow_website']}, archive={row['archive_website']})"
            )
    assert not website_failures, "; ".join(website_failures)

    avatar_failures: list[str] = []
    for row in rows:
        shadow_avatar = _normalize_url(row["shadow_avatar"])
        archive_avatar = _normalize_url(row["archive_avatar"])
        if shadow_avatar is None or archive_avatar is None:
            continue
        if shadow_avatar != archive_avatar:
            avatar_failures.append(
                f"@{row['username']} avatar mismatch (shadow={row['shadow_avatar']}, archive={row['archive_avatar']})"
            )
    assert not avatar_failures, "; ".join(avatar_failures)
