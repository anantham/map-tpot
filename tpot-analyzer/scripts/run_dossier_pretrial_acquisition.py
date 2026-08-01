"""Preflight or execute one exact private formative-dossier acquisition plan."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import httpx
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.dossier_acquisition_executor import (
    execute_dossier_acquisition_plan,
)
from src.evaluation.dossier_execution_bundle import (
    DossierExecutionBundle,
    DossierExecutionBundleError,
)
from src.evaluation.dossier_evidence_artifact import (
    build_dossier_evidence_artifact,
)
from src.evaluation.dossier_execution_preflight import (
    DossierPreflightError,
    preflight_dossier_execution,
)
from src.evaluation.dossier_executor_types import AcquisitionExecutionError
from src.evaluation.dossier_http_transport import TwitterApiIoHttpTransport
from src.evaluation.dossier_private_diagnostics import (
    record_post_network_failure,
)
from src.evaluation.dossier_snapshot_transform import (
    build_research_notes_snapshot_from_evidence,
)


PRIVATE_ROOT = ROOT / "data" / "private"


class _PrivateRunError(ValueError):
    """Public-safe failure whose detailed context is inside the private bundle."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_key(path: Path) -> str:
    try:
        value = dotenv_values(path).get("TWITTERAPI_IO_API_KEY")
    except OSError as error:
        raise ValueError(f"cannot read the explicitly supplied env file: {error}") from error
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "env file lacks a nonempty TWITTERAPI_IO_API_KEY; no request was made"
        )
    return value.strip()


def _load_plan_quote(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load accepted plan quote: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("reservation"), dict):
        raise ValueError("accepted plan quote lacks a reservation object")
    return value


class _ProgressTransport:
    def __init__(self, transport: TwitterApiIoHttpTransport, total: int):
        self.transport = transport
        self.total = total
        self.count = 0

    def request(self, endpoint: str, params: dict[str, str]):
        self.count += 1
        kind = endpoint.rsplit("/", 1)[-1]
        print(f"→ request {self.count}/{self.total}: {kind}", flush=True)
        try:
            response = self.transport.request(endpoint, params)
        except AcquisitionExecutionError:
            print(f"✗ request {self.count}/{self.total}: stopped", flush=True)
            raise
        print(
            f"✓ response {self.count}/{self.total}: HTTP {response.status_code}",
            flush=True,
        )
        return response


def _print_preflight(result: dict[str, Any]) -> None:
    print(f"✓ exact plan: {result['plan_sha256']}")
    print(
        "✓ frozen panel: "
        f"{result['panel_account_count']} accounts; "
        f"strata={result['strata_counts']}"
    )
    print(
        "✓ evidence bound: "
        f"{result['profile_request_count']} profiles; "
        f"{result['maximum_tweet_count']} tweets maximum"
    )
    print("✓ holdout exclusion: overlap=0")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--price-card", type=Path, required=True)
    parser.add_argument("--archive-db", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--accepted-max-credits", type=int)
    parser.add_argument("--accepted-max-usd")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        checked_at = _now()
        checked = preflight_dossier_execution(
            plan_path=args.plan,
            panel_path=args.panel,
            price_card_path=args.price_card,
            archive_db_path=args.archive_db,
            expected_plan_sha256=args.expected_plan_sha256,
            checked_at=checked_at,
        )
        _print_preflight(checked)
        if not args.execute:
            print("✓ dry preflight only: no credential read, network call, or spend")
            print("Next: rerun with explicit execution caps and a new private output directory.")
            return 0
        if any(value is None for value in (
            args.accepted_max_credits,
            args.accepted_max_usd,
            args.env_file,
            args.output_dir,
        )):
            raise ValueError(
                "--execute requires accepted caps, --env-file, and --output-dir"
            )
        plan_quote = _load_plan_quote(args.plan)
        quoted_reservation = plan_quote["reservation"]
        if (
            args.accepted_max_credits != quoted_reservation.get("total_credits")
            or args.accepted_max_usd != quoted_reservation.get("total_usd")
        ):
            raise ValueError(
                "live CLI accepts only the plan's exact total reserve, not a wider cap"
            )
        bundle = DossierExecutionBundle.initialize(
            output_dir=args.output_dir,
            private_root=PRIVATE_ROOT,
            source_paths={
                "plan": args.plan,
                "panel": args.panel,
                "price_card": args.price_card,
            },
            preflight=checked,
            accepted_cap={
                "credits": args.accepted_max_credits,
                "usd": args.accepted_max_usd,
            },
        )
        plan = bundle.source_object("plan")
        reservation = plan["reservation"]
        api_key = _load_key(args.env_file)
        executed_at = _now()
        phase = "client_open"
        try:
            with httpx.Client(follow_redirects=False) as client:
                phase = "transport_setup"
                raw_transport = TwitterApiIoHttpTransport(
                    api_key,
                    client=client,
                    journal=bundle,
                )
                transport = _ProgressTransport(
                    raw_transport,
                    total=reservation["request_count"],
                )
                phase = "acquisition"
                try:
                    receipt = execute_dossier_acquisition_plan(
                        plan=plan,
                        expected_plan_sha256=args.expected_plan_sha256,
                        accepted_max_credits=args.accepted_max_credits,
                        accepted_max_usd=args.accepted_max_usd,
                        executed_at=executed_at,
                        transport=transport,
                        frozen_holdout_account_ids=checked[
                            "_frozen_holdout_account_ids"
                        ],
                    )
                except AcquisitionExecutionError as error:
                    phase = "persist_aborted_execution"
                    if error.receipt is not None:
                        bundle.write_execution_receipt(error.receipt)
                    else:
                        bundle.write_json("execution-error.json", {
                            "schema_version": 1,
                            "kind": "twitterapiio-dossier-private-error",
                            "message": str(error),
                        })
                    records = raw_transport.response_records()
                    bundle.write_response_records(
                        filename="partial-response-records.json",
                        plan_sha256=args.expected_plan_sha256,
                        records=records,
                        status="aborted",
                    )
                    raise _PrivateRunError(
                        "acquisition stopped fail-closed; details are in the private "
                        "bundle; no retry is allowed"
                    ) from None
                records = raw_transport.response_records()
                phase = "persist_completed_execution"
                bundle.write_execution_receipt(receipt)
                bundle.write_response_records(
                    filename="raw-response-records.json",
                    plan_sha256=args.expected_plan_sha256,
                    records=records,
                    status="completed",
                )
                phase = "build_evidence"
                evidence = build_dossier_evidence_artifact(
                    plan=plan,
                    receipt=receipt,
                    records=records,
                )
                phase = "persist_evidence"
                bundle.write_json("response-evidence.json", evidence)
                phase = "build_snapshot"
                snapshot = build_research_notes_snapshot_from_evidence(
                    snapshot_id=checked["panel_run_id"],
                    evidence_artifact=evidence,
                    plan=plan,
                    receipt=receipt,
                )
                phase = "persist_snapshot"
                bundle.write_json("dossier-snapshot.json", snapshot)
                phase = "client_close"
        except _PrivateRunError:
            raise
        except Exception as error:
            recorded = record_post_network_failure(bundle, phase, error)
            detail = (
                "private diagnostics are in the bundle"
                if recorded
                else "private diagnostics could not be persisted; the bundle may be incomplete"
            )
            raise _PrivateRunError(
                f"live processing stopped fail-closed; {detail}; "
                "no retry is allowed"
            ) from None
        print(
            "✓ completed: "
            f"debit={receipt['balance']['debited_credits']} credits; "
            f"snapshot_sha256={snapshot['snapshotHash']}"
        )
        print(f"✓ private artifacts: {bundle.path} (directory 0700; files 0600)")
        return 0
    except (
        DossierExecutionBundleError,
        DossierPreflightError,
        ValueError,
        KeyError,
    ) as error:
        print(f"✗ stopped: {error}")
        print("Next: inspect the recorded mismatch; do not retry or widen the plan.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
