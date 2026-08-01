"""Verify the bounded dossier executor-to-snapshot chain without spending."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.dossier_acquisition_executor import (
    execute_dossier_acquisition_plan,
)
from src.evaluation.dossier_acquisition_plan import build_dossier_acquisition_plan
from src.evaluation.dossier_evidence_artifact import (
    build_dossier_evidence_artifact,
    verify_dossier_evidence_artifact,
)
from src.evaluation.dossier_executor_types import TransportResponse
from src.evaluation.dossier_snapshot_transform import (
    build_research_notes_snapshot_from_evidence,
)


PRICE_CARD = ROOT / "data/manifests/twitterapiio_price_card_20260730.json"


class _ReplayTransport:
    def __init__(self, responses: list[TransportResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.records: list[dict[str, Any]] = []

    def request(
        self, endpoint: str, params: dict[str, str]
    ) -> TransportResponse:
        response = self._responses.pop(0)
        self.calls.append((endpoint, deepcopy(params)))
        self.records.append({
            "endpoint": endpoint,
            "params": deepcopy(params),
            "status_code": response.status_code,
            "requested_at": response.requested_at,
            "received_at": response.received_at,
            "body": deepcopy(response.body),
        })
        return response


def _response(body: dict[str, Any], second: int) -> TransportResponse:
    return TransportResponse(
        status_code=200,
        body=body,
        requested_at=f"2026-07-31T13:00:{second:02d}Z",
        received_at=f"2026-07-31T13:00:{second + 1:02d}Z",
    )


def _plan() -> dict[str, Any]:
    price_card = json.loads(PRICE_CARD.read_text(encoding="utf-8"))
    return build_dossier_acquisition_plan(
        targets=[{
            "handle": "PilotAcct",
            "fetch_profile": True,
            "recent_tweets_limit": 20,
        }],
        price_card=price_card,
        selection_manifest_sha256="a" * 64,
        planned_at="2026-07-31T12:20:24Z",
        hard_cap_usd="0.05",
        max_price_age_days=7,
    )


def _transport() -> _ReplayTransport:
    return _ReplayTransport([
        _response({"recharge_credits": 10_000}, 0),
        _response({
            "status": "success",
            "data": {
                "id": "42",
                "userName": "PilotAcct",
                "name": "Pilot",
                "description": "verification only",
                "location": None,
            },
        }, 2),
        _response({
            "status": "success",
            "data": {"tweets": [
                {
                    "id": "101",
                    "text": "first private evidence text",
                    "createdAt": "Wed Jul 30 10:00:00 +0000 2026",
                    "likeCount": 3,
                    "retweetCount": 1,
                    "author": {"id": "42", "userName": "PilotAcct"},
                },
                {
                    "id": "102",
                    "text": "second private evidence text",
                    "createdAt": "2026-07-29T10:00:00Z",
                    "likeCount": 1,
                    "retweetCount": 0,
                    "author": {"id": "42", "userName": "pilotacct"},
                },
            ]},
        }, 4),
        _response({"recharge_credits": 9_952}, 6),
    ])


def _check(label: str, passed: bool, detail: str) -> bool:
    print(f"{'✓' if passed else '✗'} {label}: {detail}")
    return passed


def main() -> int:
    checks: list[bool] = []
    try:
        plan = _plan()
        transport = _transport()
        receipt = execute_dossier_acquisition_plan(
            plan=plan,
            expected_plan_sha256=plan["plan_sha256"],
            accepted_max_credits=plan["reservation"]["total_credits"],
            accepted_max_usd=plan["reservation"]["total_usd"],
            executed_at="2026-07-31T13:00:00Z",
            frozen_holdout_account_ids=frozenset({"999"}),
            transport=transport,
        )
        evidence = build_dossier_evidence_artifact(
            plan=plan,
            receipt=receipt,
            records=transport.records,
        )
        verified = verify_dossier_evidence_artifact(
            evidence,
            plan=plan,
            receipt=receipt,
        )
        snapshot = build_research_notes_snapshot_from_evidence(
            snapshot_id="verification-only",
            evidence_artifact=evidence,
            plan=plan,
            receipt=receipt,
        )
        checks.append(_check(
            "Non-authorizing quote",
            plan["authorizes_execution"] is False,
            f"reserve={plan['reservation']['total_credits']} credits",
        ))
        checks.append(_check(
            "Frozen call order",
            [call[0] for call in transport.calls] == [
                "/oapi/my/info",
                "/twitter/user/info",
                "/twitter/user/last_tweets",
                "/oapi/my/info",
            ],
            "balance → profile → tweets → balance; no retry",
        ))
        checks.append(_check(
            "Receipt reconciliation",
            receipt["status"] == "completed"
            and receipt["balance"]["debited_credits"] == 48,
            f"observed_debit={receipt['balance']['debited_credits']} credits",
        ))
        checks.append(_check(
            "Raw evidence binding",
            verified == evidence and len(evidence["records"]) == 4,
            f"artifact_sha256={evidence['artifact_sha256']}",
        ))
        checks.append(_check(
            "Blind snapshot",
            len(snapshot["dossiers"]) == 1
            and len(snapshot["dossiers"][0]["tweets"]) == 2,
            f"snapshot_sha256={snapshot['snapshotHash']}",
        ))
        serialized_receipt = json.dumps(receipt)
        checks.append(_check(
            "Sanitized receipt",
            "private evidence text" not in serialized_receipt,
            "tweet bodies remain only in the private evidence artifact",
        ))
    except Exception as error:
        _check("Execution chain", False, str(error))
        print("Next: repair the first failing contract; do not call the provider.")
        return 1
    print(f"\nchecks_passed={sum(checks)}/{len(checks)}")
    if not all(checks):
        print("Next: repair failed checks; do not call the provider.")
        return 1
    print(
        "Next: verify any private live bundle separately; a new paid attempt "
        "requires fresh explicit authorization."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
