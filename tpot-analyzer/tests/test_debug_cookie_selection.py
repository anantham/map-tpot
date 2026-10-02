"""Test intent: debug tooling rejects retired credentials before any activity;
JSON selection uses synthetic, owner-only validated files without browser calls.
"""
import sys
import pytest

from scripts import debug_single_account
from scripts._debug_cookie_selection import select_cookie_path
from src.shadow.cookie_store import save_cookies


def test_debug_legacy_cookie_rejected_before_logging_or_database(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["debug", "synthetic", "--cookies", "secrets/synthetic.pkl"])
    def forbidden_activity():
        raise AssertionError("Invalid credentials must fail before logging, database or Selenium activity")
    monkeypatch.setattr(debug_single_account, "setup_debug_logging", forbidden_activity)
    assert debug_single_account.main() == 1
    assert "JSON" in capsys.readouterr().err


def synthetic_cookie(path):
    save_cookies(path, [{"name": "auth_token", "value": "synthetic", "domain": ".x.com", "path": "/"}])
    return path


def test_selects_validated_json_and_never_opens_legacy(tmp_path):
    legacy = tmp_path / "legacy.pkl"
    legacy.write_bytes(b"synthetic legacy marker")
    expected = synthetic_cookie(tmp_path / "current.json")
    assert select_cookie_path(secrets_dir=tmp_path) == expected
    assert legacy.read_bytes() == b"synthetic legacy marker"


def test_multiple_validated_json_choices_are_deterministic(tmp_path, capsys):
    synthetic_cookie(tmp_path / "a.json")
    expected = synthetic_cookie(tmp_path / "b.json")
    assert select_cookie_path(secrets_dir=tmp_path, prompt=lambda _: "2") == expected
    assert "synthetic" not in capsys.readouterr().out


@pytest.mark.parametrize("choice", ["0", "3", "bogus", ""])
def test_invalid_choice_rejected(tmp_path, choice):
    synthetic_cookie(tmp_path / "a.json")
    synthetic_cookie(tmp_path / "b.json")
    with pytest.raises(ValueError, match="selection"):
        select_cookie_path(secrets_dir=tmp_path, prompt=lambda _: choice)


def test_legacy_only_requires_recapture_without_migration(tmp_path):
    (tmp_path / "legacy.pkl").write_bytes(b"synthetic non-executable legacy")
    with pytest.raises(ValueError, match="recapture"):
        select_cookie_path(secrets_dir=tmp_path)


def test_explicit_json_validates_permissions_schema_and_symlinks(tmp_path):
    valid = synthetic_cookie(tmp_path / "valid.json")
    assert select_cookie_path(valid) == valid
    valid.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        select_cookie_path(valid)
    valid.chmod(0o600)
    alias = tmp_path / "alias.json"
    alias.symlink_to(valid)
    with pytest.raises((ValueError, OSError)):
        select_cookie_path(alias)
    bad = tmp_path / "bad.json"
    bad.write_text('{"not":"cookies"}')
    bad.chmod(0o600)
    with pytest.raises(ValueError):
        select_cookie_path(bad)


def test_invalid_candidate_cannot_silently_select_another_identity(tmp_path):
    synthetic_cookie(tmp_path / "valid.json")
    (tmp_path / "invalid.json").write_text("invalid synthetic JSON")
    (tmp_path / "invalid.json").chmod(0o600)
    with pytest.raises(ValueError):
        select_cookie_path(secrets_dir=tmp_path)
