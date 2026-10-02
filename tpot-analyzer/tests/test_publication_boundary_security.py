"""Test intent: explicit recursive allowlist prevents incidental dossier fields;
exact byte digests change with content/policy, candidates are unapproved and local.
"""
import json

import pytest

from scripts._export_helpers._publication import candidate_digest, write_public_candidate


def candidate():
    return ({"communities": [], "accounts": [{"id": "1", "tier": "classified", "memberships": [
        {"community_id": "a", "weight": 0.5, "private_hypothesis": "sensitive"}],
        "dossier": {"private_note": "secret"}}], "meta": {"site_name": "Example", "private_key": "hidden"},
        "private_audit": []}, {"synthetic": {"tier": "classified", "memberships": [], "private_notes": "hidden"}})


def test_allowlist_strips_unapproved_fields_recursively(tmp_path):
    manifest = write_public_candidate(tmp_path, *candidate())
    data = json.loads((tmp_path / "data.json").read_bytes())
    search = json.loads((tmp_path / "search.json").read_bytes())
    assert set(data) == {"communities", "accounts", "meta"}
    assert set(data["accounts"][0]) == {"id", "tier", "memberships"}
    assert set(data["accounts"][0]["memberships"][0]) == {"community_id", "weight"}
    assert search == {"synthetic": {"tier": "classified", "memberships": []}}
    assert manifest["status"] == "unapproved"
    assert manifest["export_digest"] == candidate_digest((tmp_path / "data.json").read_bytes(), (tmp_path / "search.json").read_bytes())


def test_digest_binds_exact_bytes():
    assert candidate_digest(b"{}", b"{}") != candidate_digest(b"{}\n", b"{}")


def test_invalid_leaf_is_rejected_before_files_are_written(tmp_path):
    data, search = candidate()
    data["accounts"][0]["memberships"][0]["weight"] = float("nan")
    with pytest.raises(ValueError, match="number"):
        write_public_candidate(tmp_path, data, search)
    assert list(tmp_path.iterdir()) == []
