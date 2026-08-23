"""Behavioral contract for the private Research Notes source endpoint."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.api.server import create_app

CURATOR_TOKEN = "research-notes-source-test-token"
SOURCE_LIMIT_BYTES = 256 * 1024
PROPOSALS_LIMIT_BYTES = 1024 * 1024


@pytest.fixture
def source_client(
    tmp_path: Path,
    temp_snapshot_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    monkeypatch.delenv("RESEARCH_NOTES_SOURCE_PATH", raising=False)
    monkeypatch.delenv("RESEARCH_NOTES_PROPOSALS_PATH", raising=False)

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = CURATOR_TOKEN
        yield client


@pytest.mark.integration
def test_source_requires_curator_auth(source_client) -> None:
    source_client.environ_base.pop("HTTP_X_TPOT_CURATOR_TOKEN")

    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 401
    assert "curator token" in response.get_json()["error"]


@pytest.mark.integration
def test_unconfigured_source_is_an_explicit_empty_state(source_client) -> None:
    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.get_json() == {
        "configured": False,
        "source": None,
        "suggestionsByHandle": {},
    }


@pytest.mark.integration
def test_source_returns_exact_private_bytes_as_text_and_receipt(
    source_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "messy takes.txt"
    source_bytes = "@Alice\r\nExact café notes.\r\n".encode("utf-8")
    source_path.write_bytes(source_bytes)
    modified_at = datetime(2026, 8, 2, 7, 30, tzinfo=timezone.utc)
    os.utime(source_path, (modified_at.timestamp(), modified_at.timestamp()))
    monkeypatch.setenv("RESEARCH_NOTES_SOURCE_PATH", str(source_path))

    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.get_json() == {
        "configured": True,
        "source": {
            "name": "messy takes.txt",
            "text": source_bytes.decode("utf-8"),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "bytes": len(source_bytes),
            "modifiedAt": "2026-08-02T07:30:00Z",
        },
        "suggestionsByHandle": {},
    }


@pytest.mark.integration
def test_bound_model_proposals_are_returned_without_becoming_tags(
    source_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "takes"
    source_path.write_text("@Alice\nDharma and meditation.\n", encoding="utf-8")
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    suggestions = {
        "alice": [
            {
                "tag": "dharma",
                "tagKind": "community_affiliation",
                "polarity": "in",
                "sourceQuote": "Dharma and meditation.",
                "proposalStatus": "model-proposed",
                "goldStatus": "not-gold",
            }
        ]
    }
    proposals_path = tmp_path / "proposals.json"
    proposals_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceSha256": source_sha,
                "proposalStatus": "model-proposed",
                "goldStatus": "not-gold",
                "permissions": {
                    "mayTrain": False,
                    "mayScore": False,
                    "mayAutoWriteTags": False,
                },
                "suggestionsByHandle": suggestions,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_NOTES_SOURCE_PATH", str(source_path))
    monkeypatch.setenv(
        "RESEARCH_NOTES_PROPOSALS_PATH",
        str(proposals_path),
    )

    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["suggestionsByHandle"] == suggestions
    assert "tags" not in payload
    assert "judgments" not in payload


@pytest.mark.integration
def test_source_rejects_oversize_private_file(
    source_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "too-large"
    source_path.write_bytes(b"x" * (SOURCE_LIMIT_BYTES + 1))
    monkeypatch.setenv("RESEARCH_NOTES_SOURCE_PATH", str(source_path))

    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 413
    assert "262144-byte limit" in response.get_json()["error"]
    assert str(source_path) not in response.get_json()["error"]


@pytest.mark.integration
def test_source_rejects_oversize_proposals_file(
    source_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "takes"
    source_path.write_text("@Alice\n", encoding="utf-8")
    proposals_path = tmp_path / "too-large-proposals"
    proposals_path.write_bytes(b"x" * (PROPOSALS_LIMIT_BYTES + 1))
    monkeypatch.setenv("RESEARCH_NOTES_SOURCE_PATH", str(source_path))
    monkeypatch.setenv(
        "RESEARCH_NOTES_PROPOSALS_PATH",
        str(proposals_path),
    )

    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 413
    assert "1048576-byte limit" in response.get_json()["error"]
    assert str(proposals_path) not in response.get_json()["error"]


@pytest.mark.integration
def test_proposals_must_match_the_exact_source_receipt(
    source_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "takes"
    source_path.write_text("@Alice\n", encoding="utf-8")
    proposals_path = tmp_path / "proposals.json"
    proposals_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceSha256": "0" * 64,
                "proposalStatus": "model-proposed",
                "goldStatus": "not-gold",
                "permissions": {
                    "mayTrain": False,
                    "mayScore": False,
                    "mayAutoWriteTags": False,
                },
                "suggestionsByHandle": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_NOTES_SOURCE_PATH", str(source_path))
    monkeypatch.setenv(
        "RESEARCH_NOTES_PROPOSALS_PATH",
        str(proposals_path),
    )

    response = source_client.get("/api/research-notes/source")

    assert response.status_code == 409
    assert response.get_json()["error"] == (
        "Research Notes proposals do not match the configured source"
    )
