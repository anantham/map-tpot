from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from src.api.server import create_app
from src.data.account_tags import AccountTagStore


CURATOR_TOKEN = "frontier-test-token"


def _seed_archive(path: Path, *, include_claims: bool = True) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_following (
                account_id TEXT NOT NULL,
                following_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            """
        )
        if include_claims:
            conn.execute(
                "CREATE TABLE user_profile_cache ("
                "account_id TEXT PRIMARY KEY, username TEXT, following INTEGER)"
            )
        conn.executemany(
            "INSERT INTO account_following VALUES (?, ?)",
            [
                ("p1", "niche"),
                ("p1", "shared"),
                ("p1", "p2"),
                ("p1", "n1"),
                ("p1", "p1"),  # dirty self-edge must not inflate diagnostics
                ("p2", "broad-only"),
                ("p2", "shared"),
                ("p2", "p1"),
                ("n1", "shared"),
                ("n1", "negative-only"),
                ("other", "intruder"),
            ],
        )
        conn.executemany(
            "INSERT INTO profiles VALUES (?, ?)",
            [
                ("niche", "NichePerson"),
                ("broad-only", "BroadPerson"),
                ("shared", "SharedPerson"),
                ("intruder", "WrongTarget"),
            ],
        )
        if include_claims:
            conn.executemany(
                "INSERT INTO user_profile_cache VALUES (?, ?, ?)",
                [
                    ("p1", "PositiveOne", 10),
                    ("p2", "PositiveTwo", 100),
                    ("n1", "NegativeOne", 4),
                ],
            )
        conn.commit()


def _seed_tags(snapshot_dir: Path) -> None:
    store = AccountTagStore(snapshot_dir / "account_tags.db")
    store.upsert_tag(ego="aditya", account_id="p1", tag="Dharma", polarity=1)
    store.upsert_tag(ego="aditya", account_id="p2", tag="dharma", polarity=1)
    store.upsert_tag(ego="aditya", account_id="n1", tag="DHARMA", polarity=-1)
    # These rows prove target lookup is exact rather than the legacy all-tag sum.
    store.upsert_tag(ego="aditya", account_id="p1", tag="Other", polarity=-1)
    store.upsert_tag(ego="aditya", account_id="other", tag="Other", polarity=1)
    store.upsert_tag(ego="someone-else", account_id="other", tag="Dharma", polarity=1)


@pytest.fixture
def frontier_client(tmp_path: Path, temp_snapshot_dir: Path, monkeypatch):
    archive_path = tmp_path / "archive with spaces.db"
    _seed_archive(archive_path)
    _seed_tags(temp_snapshot_dir)
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(archive_path))
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = CURATOR_TOKEN
        yield client


@pytest.mark.integration
def test_frontier_is_exact_tag_selective_contrast_with_observable_diagnostics(
    frontier_client,
) -> None:
    response = frontier_client.get(
        "/api/research-notes/frontier?ego=aditya&tag=dHaRmA&limit=3"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["target"] == {
        "ego": "aditya",
        "tag": "dHaRmA",
        "tagKey": "dharma",
    }
    assert payload["status"] == "provisional"
    assert payload["reason"] == "uncalibrated_observed_follow_contrast"
    assert payload["semantics"]["method"] == "source_selectivity_contrast_v1"
    assert payload["semantics"]["calibrated"] is False

    assert payload["anchors"]["positive"]["count"] == 2
    assert payload["anchors"]["negative"]["count"] == 1
    positive_coverage = payload["anchors"]["positive"]["coverage"]
    assert positive_coverage["anchorsWithObservedFollowing"] == 2
    assert positive_coverage["observedUniqueFollowingEdges"] == 7
    assert positive_coverage["claimedCountsAvailable"] == 2
    assert math.isclose(
        positive_coverage["observedToEffectiveDegreeRatio"],
        7 / 110,
    )

    candidates = payload["candidates"]
    assert [row["accountId"] for row in candidates] == [
        "niche",
        "broad-only",
        "shared",
    ]
    niche, broad, shared = candidates
    assert niche["username"] == "NichePerson"
    assert math.isclose(niche["positiveScore"], 0.1)
    assert niche["negativeScore"] == 0
    assert math.isclose(niche["contrast"], 0.1)
    assert niche["positiveRawSupport"] == 1
    assert niche["negativeRawSupport"] == 0
    assert broad["username"] == "BroadPerson"
    assert math.isclose(broad["contrast"], 0.01)
    assert shared["positiveRawSupport"] == 2
    assert shared["negativeRawSupport"] == 1
    assert math.isclose(shared["positiveScore"], 0.11)
    assert math.isclose(shared["negativeScore"], 0.25)
    assert math.isclose(shared["contrast"], -0.14)
    assert "intruder" not in {row["accountId"] for row in candidates}
    assert "negative-only" not in {row["accountId"] for row in candidates}

    diagnostics = payload["diagnostics"]
    assert diagnostics["candidateCount"] == 3
    assert diagnostics["returnedCount"] == 3
    assert diagnostics["observedAnchorReachability"] == {
        "eligiblePositiveAnchors": 2,
        "positiveAnchorsReachedByPositive": 2,
        "observedFraction": 1.0,
    }
    assert diagnostics["observedPositivePairLinks"] == {
        "possibleDirectedEdges": 2,
        "observedDirectedEdges": 2,
        "observedFraction": 1.0,
    }
    assert diagnostics["observedBoundaryCrossing"] == {
        "eligibleNegativeAnchors": 1,
        "negativeAnchorsReachedByPositive": 1,
        "observedFraction": 1.0,
    }
    assert "no held-out recovery" in diagnostics["semantics"]["generalization"]


@pytest.mark.integration
def test_frontier_requires_curator_and_valid_target(frontier_client) -> None:
    frontier_client.environ_base.pop("HTTP_X_TPOT_CURATOR_TOKEN")
    assert frontier_client.get(
        "/api/research-notes/frontier?ego=aditya&tag=Dharma"
    ).status_code == 401
    frontier_client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = CURATOR_TOKEN
    response = frontier_client.get("/api/research-notes/frontier?ego=aditya")
    assert response.status_code == 400
    assert "tag" in response.get_json()["error"]


@pytest.mark.integration
@pytest.mark.parametrize("bad_polarity", [2, "oops"])
def test_frontier_fails_closed_on_corrupt_stored_polarity(
    frontier_client,
    temp_snapshot_dir: Path,
    bad_polarity: object,
) -> None:
    with sqlite3.connect(temp_snapshot_dir / "account_tags.db") as conn:
        conn.execute(
            "UPDATE account_tags SET polarity = ? "
            "WHERE ego = 'aditya' AND account_id = 'p1' AND tag_key = 'dharma'",
            (bad_polarity,),
        )
        conn.commit()

    response = frontier_client.get(
        "/api/research-notes/frontier?ego=aditya&tag=Dharma"
    )
    assert response.status_code == 500
    assert "unavailable" in response.get_json()["error"]


@pytest.mark.integration
def test_frontier_fails_closed_when_tag_store_is_missing(
    tmp_path: Path,
    temp_snapshot_dir: Path,
    monkeypatch,
) -> None:
    archive_path = tmp_path / "archive.db"
    _seed_archive(archive_path)
    assert not (temp_snapshot_dir / "account_tags.db").exists()
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(archive_path))
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    client = create_app({"TESTING": True}).test_client()

    response = client.get(
        "/api/research-notes/frontier?ego=aditya&tag=Dharma",
        headers={"X-TPOT-Curator-Token": CURATOR_TOKEN},
    )
    assert response.status_code == 500
    assert "unavailable" in response.get_json()["error"]


@pytest.mark.integration
def test_frontier_returns_honest_insufficient_states_and_optional_claims(
    tmp_path: Path,
    temp_snapshot_dir: Path,
    monkeypatch,
) -> None:
    archive_path = tmp_path / "no-claims.db"
    _seed_archive(archive_path, include_claims=False)
    store = AccountTagStore(temp_snapshot_dir / "account_tags.db")
    store.upsert_tag(ego="aditya", account_id="p1", tag="Dharma", polarity=1)
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(archive_path))
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    app = create_app({"TESTING": True})
    client = app.test_client()
    headers = {"X-TPOT-Curator-Token": CURATOR_TOKEN}

    response = client.get(
        "/api/research-notes/frontier?ego=aditya&tag=Dharma", headers=headers
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "insufficient"
    assert payload["reason"] == "single_positive_anchor_only"
    assert payload["candidates"]
    coverage = payload["anchors"]["positive"]["coverage"]
    assert coverage["claimedCountsAvailable"] == 0
    assert coverage["claimedCountsMissing"] == 1
    assert coverage["selectivityFallbackSources"] == 1
    assert coverage["observedToEffectiveDegreeRatio"] is None
    assert "may be overstated" in payload["semantics"]["denominatorFallback"]

    empty = client.get(
        "/api/research-notes/frontier?ego=aditya&tag=Unknown", headers=headers
    ).get_json()
    assert empty["status"] == "insufficient"
    assert empty["reason"] == "no_positive_anchors"
    assert empty["candidates"] == []
