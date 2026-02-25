"""Unit tests for list-mode vs username-mode dispatch in enrich_shadow_graph."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import scripts.enrich_shadow_graph as enrich_script


def _build_args(tmp_path, *, center):
    return SimpleNamespace(
        cookies=tmp_path / "cookies.pkl",
        seeds=[],
        bearer_token=None,
        pause=0.0,
        include_followers=True,
        include_following=True,
        include_followers_you_follow=True,
        output=tmp_path / "summary.json",
        refresh_snapshot=False,
        headless=True,
        chrome_binary=None,
        max_scrolls=1,
        delay_min=0.0,
        delay_max=0.0,
        retry_attempts=1,
        auto_continue=True,
        auto_confirm_first=True,
        profile_only=False,
        profile_only_all=False,
        preview_count=1,
        require_confirmation=False,
        skip_if_ever_scraped=True,
        center=center,
        force_refresh_list=False,
        log_level="INFO",
        quiet=True,
        enable_api_fallback=False,
    )


class _FakeFetcher:
    def __init__(self, accounts_df):
        self._accounts_df = accounts_df
        self.engine = object()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def fetch_accounts(self):
        return self._accounts_df


class _FakeStore:
    def __init__(self, following_usernames):
        self.following_usernames = following_usernames
        self.following_calls = []

    def get_following_usernames(self, username):
        self.following_calls.append(username)
        return self.following_usernames


class _FakeEnricher:
    def __init__(self, list_entries):
        self.list_entries = list_entries
        self.list_calls = []
        self.enrich_calls = []

    def fetch_list_members_with_cache(self, list_id, force_refresh=False):
        self.list_calls.append((list_id, force_refresh))
        return SimpleNamespace(entries=self.list_entries)

    def enrich(self, seeds):
        self.enrich_calls.append(list(seeds))
        return {"status": "ok"}

    def quit(self):
        return None


def _install_common_fakes(monkeypatch, tmp_path, *, args, accounts_df, preset_seeds, store):
    monkeypatch.setattr(enrich_script, "parse_args", lambda: args)
    monkeypatch.setattr(enrich_script, "_resolve_cookie_path", lambda _: args.cookies)
    monkeypatch.setattr(enrich_script, "setup_enrichment_logging", lambda **_: None)
    monkeypatch.setattr(
        enrich_script,
        "get_cache_settings",
        lambda: SimpleNamespace(path=tmp_path / "cache.db"),
    )

    def fake_load_seed_candidates(additional=None):
        base = list(preset_seeds)
        if additional:
            return base + list(additional)
        return base

    monkeypatch.setattr(enrich_script, "load_seed_candidates", fake_load_seed_candidates)
    monkeypatch.setattr(
        enrich_script,
        "CachedDataFetcher",
        lambda cache_db=None: _FakeFetcher(accounts_df),
    )
    monkeypatch.setattr(enrich_script, "get_shadow_store", lambda engine: store)


def test_center_numeric_triggers_list_mode(monkeypatch, tmp_path):
    accounts_df = pd.DataFrame(
        [
            {"account_id": "1", "username": "preset"},
            {"account_id": "2", "username": "archive_user"},
        ]
    )
    args = _build_args(tmp_path, center="1234567890")
    store = _FakeStore(following_usernames=[])
    _install_common_fakes(
        monkeypatch,
        tmp_path,
        args=args,
        accounts_df=accounts_df,
        preset_seeds=["preset"],
        store=store,
    )

    list_entries = [SimpleNamespace(username="list_user")]
    holder = {}

    def fake_enricher_factory(store, config, policy):
        enricher = _FakeEnricher(list_entries=list_entries)
        holder["instance"] = enricher
        return enricher

    monkeypatch.setattr(enrich_script, "HybridShadowEnricher", fake_enricher_factory)

    enrich_script.main()

    enricher = holder["instance"]
    assert enricher.list_calls == [("1234567890", False)]
    assert len(enricher.enrich_calls) == 1
    usernames = [seed.username for seed in enricher.enrich_calls[0]]
    assert usernames == ["preset", "list_user", "archive_user"]


def test_center_username_triggers_enrich_first(monkeypatch, tmp_path):
    accounts_df = pd.DataFrame(
        [
            {"account_id": "1", "username": "center_user"},
            {"account_id": "2", "username": "preset"},
            {"account_id": "3", "username": "archive_user"},
        ]
    )
    args = _build_args(tmp_path, center="center_user")
    store = _FakeStore(following_usernames={"followed_user"})
    _install_common_fakes(
        monkeypatch,
        tmp_path,
        args=args,
        accounts_df=accounts_df,
        preset_seeds=["preset"],
        store=store,
    )

    holder = {}

    def fake_enricher_factory(store, config, policy):
        enricher = _FakeEnricher(list_entries=[])
        holder["instance"] = enricher
        return enricher

    monkeypatch.setattr(enrich_script, "HybridShadowEnricher", fake_enricher_factory)

    enrich_script.main()

    enricher = holder["instance"]
    assert enricher.list_calls == []
    assert len(enricher.enrich_calls) == 2
    first_call = [seed.username for seed in enricher.enrich_calls[0]]
    second_call = [seed.username for seed in enricher.enrich_calls[1]]
    assert first_call == ["center_user"]
    assert second_call == ["center_user", "preset", "followed_user", "archive_user"]
    assert store.following_calls == ["center_user"]
