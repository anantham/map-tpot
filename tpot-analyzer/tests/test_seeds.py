from __future__ import annotations

import pytest

from src.graph.seeds import extract_usernames_from_html, load_seed_candidates


@pytest.mark.unit
def test_extract_usernames_from_html():
    html = "<a>@UserA</a> text @userb and @user_a"
    usernames = extract_usernames_from_html(html)
    assert usernames == ["usera", "user_a", "userb"]


@pytest.mark.unit
def test_load_seed_candidates(tmp_path):
    seeds = load_seed_candidates(additional=["extraUser"])
    assert "extrauser" in seeds
