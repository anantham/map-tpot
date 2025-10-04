from __future__ import annotations

from src.graph.seeds import extract_usernames_from_html, load_seed_candidates


def test_extract_usernames_from_html():
    html = "<a>@UserA</a> text @userb and @user_a"
    usernames = extract_usernames_from_html(html)
    assert usernames == ["usera", "user_a", "userb"]


def test_load_seed_candidates(tmp_path):
    seeds = load_seed_candidates(additional=["extraUser"])
    assert "extrauser" in seeds
