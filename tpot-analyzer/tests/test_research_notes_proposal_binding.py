"""Account-section provenance contract for Research Notes suggestions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.api.server import create_app


TOKEN = "proposal-binding-test-token"


@pytest.mark.integration
def test_quote_from_another_account_section_is_quarantined(
    tmp_path: Path,
    temp_snapshot_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "takes"
    source_path.write_text(
        "@Alice\nAlice builds tools.\n\n@Bob\nBob practices dharma.\n",
        encoding="utf-8",
    )
    proposals_path = tmp_path / "proposals.json"
    proposals_path.write_text(
        json.dumps({
            "schemaVersion": 1,
            "sourceSha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "proposalStatus": "model-proposed",
            "goldStatus": "not-gold",
            "permissions": {
                "mayTrain": False,
                "mayScore": False,
                "mayAutoWriteTags": False,
            },
            "suggestionsByHandle": {
                "alice": [{
                    "tag": "Dharma",
                    "tagKind": "community_affiliation",
                    "polarity": "in",
                    "sourceQuote": "Bob practices dharma.",
                    "proposalStatus": "model-proposed",
                    "goldStatus": "not-gold",
                }],
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", TOKEN)
    monkeypatch.setenv("RESEARCH_NOTES_SOURCE_PATH", str(source_path))
    monkeypatch.setenv("RESEARCH_NOTES_PROPOSALS_PATH", str(proposals_path))
    client = create_app({"TESTING": True}).test_client()

    response = client.get(
        "/api/research-notes/source",
        headers={"X-TPOT-Curator-Token": TOKEN},
    )

    assert response.status_code == 200
    assert response.get_json()["source"]["text"].startswith("@Alice")
    assert response.get_json()["suggestionsByHandle"] == {}
    assert response.get_json()["proposalMetadata"] == {"status": "invalid"}
