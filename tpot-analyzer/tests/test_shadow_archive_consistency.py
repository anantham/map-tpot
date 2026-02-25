"""Validation tests comparing archive data to shadow scrape outputs."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pytest


@pytest.fixture
def shadow_archive_db(tmp_path) -> Path:
    db_path = tmp_path / "shadow_archive.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE account (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            account_display_name TEXT,
            num_followers INTEGER,
            num_following INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE shadow_account (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            followers_count INTEGER,
            following_count INTEGER,
            bio TEXT,
            website TEXT,
            location TEXT,
            profile_image_url TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE profile (
            account_id TEXT PRIMARY KEY,
            bio TEXT,
            website TEXT,
            location TEXT,
            avatar_media_url TEXT
        )
    """)

    cur.execute(
        "INSERT INTO account VALUES (?, ?, ?, ?, ?)",
        ("a1", "user_a", "User A", 100, 50),
    )
    cur.execute(
        "INSERT INTO shadow_account VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "a1",
            "user_a",
            "User A",
            100,
            50,
            "Bio A",
            "https://example.com",
            "Test City",
            "https://example.com/avatar.png",
        ),
    )
    cur.execute(
        "INSERT INTO profile VALUES (?, ?, ?, ?, ?)",
        ("a1", "Bio A", "example.com", "Test City", "https://example.com/avatar.png"),
    )

    conn.commit()
    conn.close()
    return db_path


def _fetch_overlap_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
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


def _table_exists(db_path: Path, name: str) -> bool:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def _fetch_profile_overlap_rows(db_path: Path) -> list[sqlite3.Row]:
    if not _table_exists(db_path, "profile"):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.account_id,
            lower(a.username) AS username,
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
        INNER JOIN account AS a ON s.account_id = a.account_id
        INNER JOIN profile AS p ON p.account_id = a.account_id
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


def test_shadow_usernames_align_with_archive(shadow_archive_db) -> None:
    overlap_rows = _fetch_overlap_rows(shadow_archive_db)
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


def test_shadow_follow_counts_within_archive_tolerance(shadow_archive_db) -> None:
    overlap_rows = _fetch_overlap_rows(shadow_archive_db)
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

    assert follower_rows or following_rows, (
        "Expected overlapping accounts with follower/following counts populated"
    )

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


def test_shadow_profile_fields_match_archive(shadow_archive_db) -> None:
    assert _table_exists(shadow_archive_db, "profile"), (
        "Expected profile table in test database fixture"
    )

    rows = _fetch_profile_overlap_rows(shadow_archive_db)
    assert rows, "Expected overlapping accounts with profile metadata available"

    def collect_missing(field_shadow: str, field_archive: str) -> list[str]:
        failures: list[str] = []
        for row in rows:
            s_val = _normalize_text(row[field_shadow])
            a_val = _normalize_text(row[field_archive])
            if a_val is None:
                continue
            if s_val is None:
                failures.append(
                    f"@{row['username']} missing {field_shadow} while archive has {field_archive}"
                )
        return failures

    text_failures = (
        collect_missing("shadow_bio", "archive_bio")
        + collect_missing("shadow_location", "archive_location")
    )
    assert not text_failures, "; ".join(text_failures)

    website_failures: list[str] = []
    for row in rows:
        a_url = _normalize_url(row["archive_website"])
        if a_url is None:
            continue
        s_url = _normalize_url(row["shadow_website"])
        if s_url is None:
            website_failures.append(
                f"@{row['username']} missing website despite archive value {row['archive_website']!r}"
            )
    assert not website_failures, "; ".join(website_failures)

    avatar_failures: list[str] = []
    for row in rows:
        a_avatar = _normalize_url(row["archive_avatar"])
        if a_avatar is None:
            continue
        s_avatar = _normalize_url(row["shadow_avatar"])
        if s_avatar is None:
            avatar_failures.append(
                f"@{row['username']} missing avatar despite archive value {row['archive_avatar']!r}"
            )
    assert not avatar_failures, "; ".join(avatar_failures)
