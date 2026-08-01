"""Behavioral tests for transforming bound raw evidence into blind dossiers."""
from __future__ import annotations

from copy import deepcopy

import pytest

from src.data.research_notes_snapshot import verify_research_notes_snapshot
from src.evaluation.dossier_evidence_artifact import (
    build_dossier_evidence_artifact,
)
from src.evaluation.dossier_executor_types import TransportResponse
from src.evaluation.dossier_response_contract import response_receipt
from src.evaluation.dossier_snapshot_transform import (
    DossierSnapshotTransformError,
    build_research_notes_snapshot_from_evidence,
)
from tests.test_dossier_evidence_artifact import execution_fixture


def _refresh_action_fingerprint(
    receipt: dict,
    records: list[dict],
    action_index: int,
) -> None:
    record = records[action_index + 1]
    fingerprint = response_receipt(TransportResponse(
        status_code=record["status_code"],
        body=record["body"],
        requested_at=record["requested_at"],
        received_at=record["received_at"],
    ))
    receipt["actions"][action_index].update(fingerprint)


def _transform(
    plan: dict,
    receipt: dict,
    records: list[dict],
) -> dict:
    artifact = build_dossier_evidence_artifact(
        plan=plan,
        receipt=receipt,
        records=records,
    )
    return build_research_notes_snapshot_from_evidence(
        snapshot_id="dharma-boundary-pretrial-v1",
        evidence_artifact=artifact,
        plan=plan,
        receipt=receipt,
    )


def test_maps_verified_raw_responses_without_changing_api_tweet_order() -> None:
    plan, receipt, records = execution_fixture()
    snapshot = _transform(plan, receipt, records)
    dossier = snapshot["dossiers"][0]

    assert verify_research_notes_snapshot(snapshot) == snapshot
    assert snapshot["createdAt"] == "2026-07-31T13:00:07Z"
    assert snapshot["provenance"] == {
        "source": "bounded_private_acquisition",
        "acquisitionPlanSha256": plan["plan_sha256"],
        "acquisitionReceiptSha256": (
            build_dossier_evidence_artifact(
                plan=plan, receipt=receipt, records=records
            )["execution_receipt_sha256"]
        ),
    }
    assert dossier["account"] == {
        "accountId": "42",
        "username": "PilotAcct",
        "displayName": "Pilot Name",
        "bio": "bio",
        "location": "Earth",
        "website": "https://canonical.example",
        "fetchedAt": "2026-07-31T13:00:03Z",
    }
    assert dossier["tweets"] == [
        {
            "tweetId": "101",
            "text": "first",
            "createdAt": "2026-07-30T10:00:00Z",
            "favoriteCount": 3,
            "retweetCount": 1,
            "fetchedAt": "2026-07-31T13:00:05Z",
        },
        {
            "tweetId": "102",
            "text": "second",
            "createdAt": "2026-07-29T10:00:00Z",
            "favoriteCount": 1,
            "retweetCount": 0,
            "fetchedAt": "2026-07-31T13:00:05Z",
        },
    ]


def test_never_falls_back_to_profile_top_level_url() -> None:
    plan, receipt, records = execution_fixture()
    records[1]["body"]["data"].pop("profile_bio")
    _refresh_action_fingerprint(receipt, records, 0)

    snapshot = _transform(plan, receipt, records)
    assert snapshot["dossiers"][0]["account"]["website"] is None


def test_transform_rechecks_tweet_identity_with_executor_parser() -> None:
    plan, receipt, records = execution_fixture()
    records[2]["body"]["tweets"][0]["author"]["id"] = "999"
    _refresh_action_fingerprint(receipt, records, 1)

    with pytest.raises(DossierSnapshotTransformError, match="identity binding"):
        _transform(plan, receipt, records)


@pytest.mark.parametrize(
    ("record_index", "mutate", "action_index", "message"),
    [
        (1, lambda body: body["data"].update(name=7), 0, "display name"),
        (
            2,
            lambda body: body["tweets"][0].update(createdAt="not-a-time"),
            1,
            "createdAt",
        ),
        (2, lambda body: body["tweets"][0].update(likeCount=True), 1, "likeCount"),
        (
            1,
            lambda body: body["data"]["profile_bio"]["entities"]["url"].update(
                urls={"expanded_url": "wrong shape"}
            ),
            0,
            "profile website",
        ),
    ],
)
def test_selected_display_fields_fail_closed_on_malformed_types(
    record_index: int,
    mutate,
    action_index: int,
    message: str,
) -> None:
    plan, receipt, records = execution_fixture()
    mutate(records[record_index]["body"])
    _refresh_action_fingerprint(receipt, records, action_index)

    with pytest.raises(DossierSnapshotTransformError, match=message):
        _transform(plan, receipt, records)


def test_transform_reverifies_artifact_before_reading_raw_body() -> None:
    plan, receipt, records = execution_fixture()
    artifact = build_dossier_evidence_artifact(
        plan=plan, receipt=receipt, records=records
    )
    tampered = deepcopy(artifact)
    tampered["records"][1]["body"]["data"]["description"] = "forged"

    with pytest.raises(DossierSnapshotTransformError, match="artifact_sha256"):
        build_research_notes_snapshot_from_evidence(
            snapshot_id="dharma-boundary-pretrial-v1",
            evidence_artifact=tampered,
            plan=plan,
            receipt=receipt,
        )
