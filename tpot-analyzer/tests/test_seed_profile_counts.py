"""Tests seed profile record behavior when header totals are missing."""
from __future__ import annotations

import logging

import pytest

from src.shadow.enricher import HybridShadowEnricher, ProfileOverview, SeedAccount, ShadowAccount


class _StubStore:  # minimal stub; _make_seed_account_record no longer queries store
    pass


class _StubSelenium:  # stub for selenium to handle _save_page_snapshot calls
    def _save_page_snapshot(self, username: str, context: str) -> None:
        pass  # no-op for testing


def _build_enricher() -> HybridShadowEnricher:
    enricher = object.__new__(HybridShadowEnricher)
    enricher._store = _StubStore()  # type: ignore[attr-defined]
    enricher._config = None  # type: ignore[attr-defined]
    enricher._selenium = _StubSelenium()  # type: ignore[attr-defined]
    return enricher


def _make_overview(*, followers: int | None, following: int | None) -> ProfileOverview:
    return ProfileOverview(
        username="example",
        display_name="Example",
        bio="bio",
        location="Somewhere",
        website="https://example.com",
        followers_total=followers,
        following_total=following,
        joined_date="Joined 2020",
        profile_image_url="https://example.com/avatar.png",
    )


def test_seed_profile_counts_preserved_when_header_available() -> None:
    enricher = _build_enricher()
    seed = SeedAccount(account_id="seed:123", username="example")
    overview = _make_overview(followers=42, following=99)

    record = enricher._make_seed_account_record(seed, overview)

    assert isinstance(record, ShadowAccount)
    assert record.followers_count == 42
    assert record.following_count == 99


def test_seed_profile_counts_remain_null_when_header_missing(caplog: pytest.LogCaptureFixture) -> None:
    enricher = _build_enricher()
    seed = SeedAccount(account_id="seed:456", username="missing")
    overview = _make_overview(followers=None, following=None)

    with caplog.at_level(logging.WARNING):
        record = enricher._make_seed_account_record(seed, overview)

    assert record.followers_count is None
    assert record.following_count is None
    messages = "".join(event.message for event in caplog.records)
    assert "storing NULL" in messages
