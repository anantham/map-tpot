from __future__ import annotations

import json

import pytest

from scripts import compare_community_archive_snapshots as verifier
from src.archive.snapshot_comparison import (
    compare_snapshot_manifests,
    load_verified_manifest,
    summarize_manifest,
    write_json_no_clobber,
)


def _manifest(
    *,
    snapshot_id: str,
    rows: int,
    accounts: int,
    linked: int,
    missing: int,
    latest: str,
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "source": {
            "etag": f'"{snapshot_id}"',
            "last_modified": latest,
            "observed_at": latest,
        },
        "local": {
            "sha256": snapshot_id.ljust(64, "0"),
            "size_bytes": rows * 10,
        },
        "dataset": {
            "row_count": rows,
            "account_count": accounts,
            "archive_upload_linked_rows": linked,
            "archive_upload_id_missing_rows": missing,
            "created_at_max": latest,
            "sample_rows": [{"tweet_id": "1", "account_id": "a"}],
        },
    }


def test_comparison_reports_advance_and_linkage_falsification():
    baseline = _manifest(
        snapshot_id="old",
        rows=100,
        accounts=10,
        linked=80,
        missing=20,
        latest="2026-07-25T04:00:00+00:00",
    )
    candidate = _manifest(
        snapshot_id="new",
        rows=110,
        accounts=11,
        linked=80,
        missing=30,
        latest="2026-07-26T04:00:00+00:00",
    )

    result = compare_snapshot_manifests(baseline, candidate)

    assert result["deltas"]["row_count"] == 10
    assert result["deltas"]["account_count"] == 1
    assert result["deltas"]["created_at_max_seconds"] == 86400
    assert result["hypotheses"]["corpus_advanced"]["passed"] is True
    assert result["hypotheses"]["non_regressive_counts"]["passed"] is True
    assert result["hypotheses"]["archive_linkage_kept_pace"]["passed"] is False


def test_same_snapshot_does_not_count_as_an_advance():
    manifest = _manifest(
        snapshot_id="same",
        rows=100,
        accounts=10,
        linked=80,
        missing=20,
        latest="2026-07-25T04:00:00+00:00",
    )

    result = compare_snapshot_manifests(manifest, manifest)

    assert result["hypotheses"]["source_identity_changed"]["passed"] is False
    assert result["hypotheses"]["corpus_advanced"]["passed"] is False


def test_summary_rejects_ambiguous_numeric_metrics():
    manifest = _manifest(
        snapshot_id="bad",
        rows=100,
        accounts=10,
        linked=80,
        missing=20,
        latest="2026-07-25T04:00:00+00:00",
    )
    manifest["dataset"]["row_count"] = "100"

    with pytest.raises(ValueError, match="dataset.row_count"):
        summarize_manifest(manifest)


def test_verified_loader_rejects_missing_snapshot(tmp_path):
    with pytest.raises(ValueError, match="snapshot verification failed"):
        load_verified_manifest(tmp_path / "missing", deep=False)


def test_json_output_is_no_clobber(tmp_path):
    path = tmp_path / "comparison.json"
    write_json_no_clobber(path, {"measurement_complete": True})

    assert json.loads(path.read_text(encoding="utf-8"))["measurement_complete"] is True
    with pytest.raises(FileExistsError):
        write_json_no_clobber(path, {"measurement_complete": False})


def _comparison_report() -> dict:
    baseline = _manifest(
        snapshot_id="old",
        rows=100,
        accounts=10,
        linked=80,
        missing=20,
        latest="2026-07-25T04:00:00+00:00",
    )
    candidate = _manifest(
        snapshot_id="new",
        rows=110,
        accounts=11,
        linked=80,
        missing=30,
        latest="2026-07-26T04:00:00+00:00",
    )
    return compare_snapshot_manifests(baseline, candidate)


def test_verifier_exit_contract_distinguishes_falsification(
    monkeypatch,
    tmp_path,
):
    report = _comparison_report()
    monkeypatch.setattr(
        verifier,
        "compare_snapshot_directories",
        lambda *_args, **_kwargs: report,
    )

    assert verifier.compare(tmp_path / "old", tmp_path / "new") == 0
    assert (
        verifier.compare(
            tmp_path / "old",
            tmp_path / "new",
            strict=True,
        )
        == 2
    )


def test_verifier_input_failure_exits_one(monkeypatch, tmp_path):
    def fail(*_args, **_kwargs):
        raise ValueError("identity mismatch")

    monkeypatch.setattr(verifier, "compare_snapshot_directories", fail)

    assert verifier.compare(tmp_path / "old", tmp_path / "new") == 1
