"""Behavioral contract for private raw dossier evidence artifacts."""
from __future__ import annotations

from copy import deepcopy

import pytest

from src.evaluation.dossier_acquisition_executor import (
    execute_dossier_acquisition_plan,
)
from src.evaluation.dossier_acquisition_plan import build_dossier_acquisition_plan
from src.evaluation.dossier_evidence_artifact import (
    DossierEvidenceArtifactError,
    build_dossier_evidence_artifact,
    canonical_evidence_bytes,
    verify_dossier_evidence_artifact,
)
from src.evaluation.dossier_executor_types import TransportResponse
from src.evaluation.dossier_response_contract import response_receipt


def _price_card() -> dict:
    return {
        "schema_version": 1,
        "provider": "twitterapi.io",
        "currency": "USD",
        "card_id": "test-card",
        "verified_at": "2026-07-30T12:00:00Z",
        "credits_per_usd": 100_000,
        "user_info": {
            "endpoint": "/twitter/user/info",
            "credits_per_profile": 18,
            "minimum_call_credits": 18,
        },
        "user_last_tweets": {
            "endpoint": "/twitter/user/last_tweets",
            "maximum_page_size": 20,
            "credits_per_tweet": 15,
            "minimum_call_credits": 15,
        },
    }


def _plan() -> dict:
    return build_dossier_acquisition_plan(
        targets=[{
            "handle": "PilotAcct",
            "fetch_profile": True,
            "recent_tweets_limit": 20,
        }],
        price_card=_price_card(),
        selection_manifest_sha256="a" * 64,
        planned_at="2026-07-31T12:00:00Z",
        hard_cap_usd="0.05",
    )


class _CapturingTransport:
    def __init__(self, responses: list[TransportResponse]):
        self.responses = list(responses)
        self.records: list[dict] = []

    def request(self, endpoint: str, params: dict[str, str]) -> TransportResponse:
        response = self.responses.pop(0)
        self.records.append({
            "endpoint": endpoint,
            "params": deepcopy(params),
            "status_code": response.status_code,
            "requested_at": response.requested_at,
            "received_at": response.received_at,
            "body": deepcopy(response.body),
        })
        return response


def _response(index: int, body: dict) -> TransportResponse:
    return TransportResponse(
        status_code=200,
        body=body,
        requested_at=f"2026-07-31T13:00:{index * 2:02d}Z",
        received_at=f"2026-07-31T13:00:{index * 2 + 1:02d}Z",
    )


def execution_fixture() -> tuple[dict, dict, list[dict]]:
    plan = _plan()
    transport = _CapturingTransport([
        _response(0, {"recharge_credits": 10_000}),
        _response(1, {
            "status": "success",
            "data": {
                "id": "42",
                "userName": "PilotAcct",
                "name": "Pilot Name",
                "description": "bio",
                "location": "Earth",
                "url": "https://ignored.example",
                "profile_bio": {
                    "entities": {
                        "url": {
                            "urls": [{
                                "expanded_url": "https://canonical.example"
                            }]
                        }
                    }
                },
            }
        }),
        _response(2, {
            "status": "success",
            "tweets": [
                {
                    "id": "101",
                    "text": "first",
                    "createdAt": "Wed Jul 30 10:00:00 +0000 2026",
                    "likeCount": 3,
                    "retweetCount": 1,
                    "author": {"id": "42", "userName": "pilotacct"},
                },
                {
                    "id": 102,
                    "text": "second",
                    "createdAt": "2026-07-29T15:30:00+05:30",
                    "likeCount": 1,
                    "retweetCount": 0,
                    "author": {"id": 42, "userName": "PilotAcct"},
                },
            ]
        }),
        _response(3, {"recharge_credits": 9_950}),
    ])
    receipt = execute_dossier_acquisition_plan(
        plan=plan,
        expected_plan_sha256=plan["plan_sha256"],
        accepted_max_credits=plan["reservation"]["total_credits"],
        accepted_max_usd=plan["reservation"]["total_usd"],
        executed_at="2026-07-31T13:00:00Z",
        frozen_holdout_account_ids=frozenset({"999"}),
        transport=transport,
    )
    return plan, receipt, transport.records


def test_build_is_canonical_private_deep_copied_and_verifiable() -> None:
    plan, receipt, records = execution_fixture()
    artifact = build_dossier_evidence_artifact(
        plan=plan, receipt=receipt, records=records
    )
    rebuilt = build_dossier_evidence_artifact(
        plan=deepcopy(plan), receipt=deepcopy(receipt), records=deepcopy(records)
    )

    assert artifact == rebuilt
    assert artifact["visibility"] == "private"
    assert artifact["plan_sha256"] == plan["plan_sha256"]
    assert artifact["selection_manifest_sha256"] == "a" * 64
    assert len(artifact["execution_receipt_sha256"]) == 64
    assert len(artifact["artifact_sha256"]) == 64
    assert verify_dossier_evidence_artifact(
        artifact, plan=plan, receipt=receipt
    ) == artifact
    assert canonical_evidence_bytes(
        artifact, plan=plan, receipt=receipt
    ) == canonical_evidence_bytes(rebuilt, plan=plan, receipt=receipt)

    records[2]["body"]["tweets"][0]["text"] = "mutated input"
    assert artifact["records"][2]["body"]["tweets"][0]["text"] == "first"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows: rows[1]["params"].update(userName="other"), "params"),
        (lambda rows: rows[1].update(status_code=201), "status"),
        (
            lambda rows: rows[1].update(requested_at="2026-07-31T13:00:00Z"),
            "requested_at",
        ),
        (lambda rows: rows[1]["body"]["data"].update(name="forged"), "hash"),
        (lambda rows: rows.reverse(), "mismatch"),
    ],
)
def test_records_must_reconcile_call_for_call(mutation, message: str) -> None:
    plan, receipt, records = execution_fixture()
    mutation(records)
    with pytest.raises(DossierEvidenceArtifactError, match=message):
        build_dossier_evidence_artifact(plan=plan, receipt=receipt, records=records)


def test_only_completed_receipts_with_validated_actions_are_accepted() -> None:
    plan, receipt, records = execution_fixture()
    receipt["actions"][0]["status"] = "response_received"
    with pytest.raises(DossierEvidenceArtifactError, match="validated"):
        build_dossier_evidence_artifact(plan=plan, receipt=receipt, records=records)

    _, receipt, records = execution_fixture()
    receipt["selection_manifest_sha256"] = "b" * 64
    with pytest.raises(DossierEvidenceArtifactError, match="selection"):
        build_dossier_evidence_artifact(plan=plan, receipt=receipt, records=records)


def test_forged_completed_receipt_cannot_hide_an_over_cap_debit() -> None:
    plan, receipt, records = execution_fixture()
    final = records[-1]
    final["body"]["recharge_credits"] = 9_000
    fingerprint = response_receipt(TransportResponse(
        status_code=final["status_code"],
        body=final["body"],
        requested_at=final["requested_at"],
        received_at=final["received_at"],
    ))
    receipt["telemetry"][1].update(fingerprint)
    receipt["balance"].update(after_credits=9_000, debited_credits=1_000)

    with pytest.raises(DossierEvidenceArtifactError, match="accepted cap"):
        build_dossier_evidence_artifact(plan=plan, receipt=receipt, records=records)


def test_tampered_artifact_or_external_receipt_is_rejected() -> None:
    plan, receipt, records = execution_fixture()
    artifact = build_dossier_evidence_artifact(
        plan=plan, receipt=receipt, records=records
    )
    artifact["records"][2]["body"]["tweets"][0]["text"] = "forged"
    with pytest.raises(DossierEvidenceArtifactError, match="artifact_sha256"):
        verify_dossier_evidence_artifact(artifact, plan=plan, receipt=receipt)

    artifact = build_dossier_evidence_artifact(
        plan=plan, receipt=receipt, records=records
    )
    receipt["balance"]["after_credits"] -= 1
    with pytest.raises(DossierEvidenceArtifactError, match="receipt"):
        verify_dossier_evidence_artifact(artifact, plan=plan, receipt=receipt)


def test_artifact_and_record_fields_use_strict_allowlists() -> None:
    plan, receipt, records = execution_fixture()
    records[0]["secret"] = "leak"
    with pytest.raises(DossierEvidenceArtifactError, match="unexpected field"):
        build_dossier_evidence_artifact(plan=plan, receipt=receipt, records=records)

    _, receipt, records = execution_fixture()
    artifact = build_dossier_evidence_artifact(
        plan=plan, receipt=receipt, records=records
    )
    artifact["sourceNotes"] = "analyst prior"
    with pytest.raises(DossierEvidenceArtifactError, match="unexpected field"):
        verify_dossier_evidence_artifact(artifact, plan=plan, receipt=receipt)
