"""Test intent: JSON-only cookies, bounded schema, exact0600 ownership,
atomic no-clobber creation and rejection of leaf/ancestor symlinks.
"""
import json
import os
import pickle
from pathlib import Path

import pytest

from src.shadow.cookie_store import load_cookies, save_cookies

COOKIE = [{"name": "auth_token", "value": "synthetic", "domain": ".twitter.com", "secure": True}]


def test_round_trip_uses_0600_even_with_permissive_umask(tmp_path):
    path = tmp_path / "secrets" / "cookies.json"
    original = os.umask(0)
    try:
        save_cookies(path, COOKIE)
    finally:
        os.umask(original)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == COOKIE
    assert load_cookies(path) == COOKIE


def test_no_overwrite_and_no_temporary_residue(tmp_path):
    path = tmp_path / "cookies.json"
    save_cookies(path, COOKIE)
    with pytest.raises(FileExistsError):
        save_cookies(path, [{"name": "auth_token", "value": "replacement"}])
    assert load_cookies(path) == COOKIE
    assert list(tmp_path.iterdir()) == [path]


def test_pickle_with_json_suffix_is_rejected(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_bytes(pickle.dumps(COOKIE))
    path.chmod(0o600)
    with pytest.raises(ValueError, match="JSON"):
        load_cookies(path)


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o400])
def test_insecure_permissions_are_rejected(tmp_path, mode):
    path = tmp_path / "cookies.json"
    save_cookies(path, COOKIE)
    path.chmod(mode)
    with pytest.raises(ValueError, match="0600"):
        load_cookies(path)


def test_leaf_and_parent_symlinks_are_rejected(tmp_path):
    target = tmp_path / "target.json"
    save_cookies(target, COOKIE)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(OSError):
        load_cookies(link)
    with pytest.raises(FileExistsError):
        save_cookies(link, COOKIE)
    directory = tmp_path / "linked-directory"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        save_cookies(directory / "other.json", COOKIE)
    assert not (tmp_path / "other.json").exists()


@pytest.mark.parametrize("cookies", [[], [{"name": "a", "value": "x", "domain": "attacker.test"}],
                                       [{"name": "a", "value": "x", "expiry": True}],
                                       [{"name": "a", "value": "x", "script": "hidden"}]])
def test_invalid_cookie_schema_never_writes(tmp_path, cookies):
    with pytest.raises(ValueError):
        save_cookies(tmp_path / "cookies.json", cookies)
    assert list(tmp_path.iterdir()) == []
