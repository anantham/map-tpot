"""Durable private run bundle for bounded dossier execution."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re
from typing import Any

from .acquisition_manifest import canonical_json_hash
from .dossier_bundle_io import (
    DossierExecutionBundleError,
    atomic_exclusive_write,
    create_bundle_directory,
    json_bytes,
    load_sources,
    resolved_output,
)


_SOURCE_NAMES = {
    "plan": "source-plan.json",
    "panel": "source-panel.json",
    "price_card": "source-price-card.json",
}
_PREFLIGHT_FIELDS = {
    "plan_sha256", "selection_manifest_sha256", "price_card_sha256",
    "panel_run_id", "checked_at",
    "panel_account_count", "strata_counts", "plan_target_count",
    "profile_request_count", "recent_tweets_request_count",
    "maximum_tweet_count", "holdout_table_present", "holdout_overlap_count",
    "holdout_handle_count", "holdout_account_id_count", "holdout_snapshot_sha256",
    "_frozen_holdout_account_ids", "_frozen_holdout_handles",
}
_OBSERVATION_FIELDS = {
    "outcome", "status_code", "received_at", "raw_body_sha256",
    "raw_body_bytes", "response_sha256", "failure_code",
}
_FAILURE_CODES = {
    None, "http_request_failed", "invalid_status", "invalid_json",
    "non_object_json", "invalid_json_value", "credential_echo",
    "timestamp_failed", "timestamp_regression",
}
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _holdout_source(preflight: dict[str, Any]) -> dict[str, Any]:
    account_ids = preflight.get("_frozen_holdout_account_ids")
    handles = preflight.get("_frozen_holdout_handles")
    if not isinstance(account_ids, frozenset) or not isinstance(handles, frozenset):
        raise DossierExecutionBundleError(
            "preflight must provide frozen holdout exclusion sets"
        )
    if (
        len(account_ids) != preflight.get("holdout_account_id_count")
        or len(handles) != preflight.get("holdout_handle_count")
        or any(not isinstance(value, str) or not value for value in account_ids | handles)
    ):
        raise DossierExecutionBundleError("frozen holdout exclusion sets are invalid")
    logical = {
        "schema_version": 1,
        "normalized_handles": sorted(handles),
        "account_ids": sorted(account_ids),
    }
    digest = canonical_json_hash(logical)
    if digest != preflight.get("holdout_snapshot_sha256"):
        raise DossierExecutionBundleError("frozen holdout logical hash mismatch")
    return {
        "kind": "dossier-holdout-exclusion-snapshot",
        "logical_sha256": digest,
        **logical,
    }


class DossierExecutionBundle:
    """Append-only private artifacts and per-call journal events."""

    def __init__(self, path: Path, source_objects: dict[str, dict[str, Any]]):
        self.path = path
        self._source_objects = deepcopy(source_objects)
        self._next_call = 0
        self._open_calls: set[int] = set()
        self._response_calls: set[int] = set()
        self._finished_calls: set[int] = set()

    @classmethod
    def initialize(
        cls,
        *,
        output_dir: Path,
        private_root: Path,
        source_paths: dict[str, Path],
        preflight: dict[str, Any],
        accepted_cap: dict[str, Any],
    ) -> DossierExecutionBundle:
        path = resolved_output(output_dir, private_root)
        if not isinstance(preflight, dict) or set(preflight) != _PREFLIGHT_FIELDS:
            raise DossierExecutionBundleError(
                "preflight receipt fields are not exact and sanitized"
            )
        if (
            not isinstance(accepted_cap, dict)
            or set(accepted_cap) != {"credits", "usd"}
            or type(accepted_cap["credits"]) is not int
            or not isinstance(accepted_cap["usd"], str)
        ):
            raise DossierExecutionBundleError("accepted cap is invalid")
        payloads, objects = load_sources(source_paths, set(_SOURCE_NAMES), preflight)
        holdout_source = _holdout_source(preflight)
        create_bundle_directory(path)
        bundle = cls(path, objects)
        for label, filename in _SOURCE_NAMES.items():
            atomic_exclusive_write(path / filename, payloads[label])
        bundle.write_json("source-holdout-snapshot.json", holdout_source)
        source_receipts = {
            _SOURCE_NAMES[label]: {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for label, payload in payloads.items()
        }
        public_checks = {
            key: deepcopy(value)
            for key, value in preflight.items()
            if not key.startswith("_")
        }
        receipt = {
            "schema_version": 1,
            "kind": "twitterapiio-dossier-preflight-receipt",
            "plan_sha256": preflight["plan_sha256"],
            "accepted_cap": deepcopy(accepted_cap),
            "source_files": source_receipts,
            "checks": public_checks,
        }
        bundle.write_json("preflight-receipt.json", receipt)
        return bundle

    def source_object(self, label: str) -> dict[str, Any]:
        if label not in self._source_objects:
            raise DossierExecutionBundleError("unknown preserved source")
        return deepcopy(self._source_objects[label])

    def write_json(self, filename: str, value: Any) -> None:
        if Path(filename).name != filename or filename.startswith("."):
            raise DossierExecutionBundleError("artifact filename must be a plain name")
        atomic_exclusive_write(self.path / filename, json_bytes(value))

    def write_execution_receipt(
        self, receipt: dict[str, Any], filename: str = "execution-receipt.json"
    ) -> None:
        self.write_json(filename, {
            "schema_version": 1,
            "kind": "twitterapiio-dossier-receipt-envelope",
            "receipt_sha256": canonical_json_hash(receipt),
            "receipt": deepcopy(receipt),
        })

    def write_response_records(
        self,
        *,
        filename: str,
        plan_sha256: str,
        records: list[dict[str, Any]],
        status: str,
    ) -> None:
        manifest = {
            "schema_version": 1,
            "kind": "twitterapiio-response-records",
            "visibility": "private",
            "status": status,
            "plan_sha256": plan_sha256,
            "records": deepcopy(records),
        }
        self.write_json(filename, {
            **manifest,
            "artifact_sha256": canonical_json_hash(manifest),
        })

    def begin_call(
        self, endpoint: str, params: dict[str, str], requested_at: str
    ) -> int:
        call_id = self._next_call
        event = {
            "schema_version": 1,
            "kind": "twitterapiio-call-journal-event",
            "event": "attempt",
            "call_id": call_id,
            "endpoint": endpoint,
            "params": deepcopy(params),
            "requested_at": requested_at,
        }
        atomic_exclusive_write(
            self.path / "events" / f"{call_id:04d}-attempt.json",
            json_bytes(event),
        )
        self._next_call += 1
        self._open_calls.add(call_id)
        return call_id

    def finish_call(self, call_id: int, observation: dict[str, Any]) -> None:
        if call_id in self._finished_calls:
            raise DossierExecutionBundleError("call was already observed")
        if call_id not in self._open_calls:
            raise DossierExecutionBundleError("call has no durable attempt event")
        if not isinstance(observation, dict) or set(observation) != _OBSERVATION_FIELDS:
            raise DossierExecutionBundleError("call observation fields are not sanitized")
        if observation["outcome"] not in {"safe_response", "rejected_response", "request_failed"}:
            raise DossierExecutionBundleError("call observation outcome is invalid")
        if (
            observation["outcome"] == "safe_response"
            and call_id not in self._response_calls
        ):
            raise DossierExecutionBundleError(
                "safe response observation requires durable full response"
            )
        if observation["failure_code"] not in _FAILURE_CODES:
            raise DossierExecutionBundleError("call observation failure code is unsafe")
        for field in ("raw_body_sha256", "response_sha256"):
            value = observation[field]
            if value is not None and (not isinstance(value, str) or _SHA256.fullmatch(value) is None):
                raise DossierExecutionBundleError(f"call observation {field} is invalid")
        event = {
            "schema_version": 1,
            "kind": "twitterapiio-call-journal-event",
            "event": "observation",
            "call_id": call_id,
            **deepcopy(observation),
        }
        atomic_exclusive_write(
            self.path / "events" / f"{call_id:04d}-observation.json",
            json_bytes(event),
        )
        self._open_calls.remove(call_id)
        self._finished_calls.add(call_id)

    def record_response(self, call_id: int, record: dict[str, Any]) -> None:
        if call_id not in self._open_calls:
            raise DossierExecutionBundleError("response has no durable attempt event")
        if call_id in self._response_calls:
            raise DossierExecutionBundleError("full response was already recorded")
        expected = {
            "endpoint", "params", "status_code", "requested_at", "received_at", "body"
        }
        if not isinstance(record, dict) or set(record) != expected:
            raise DossierExecutionBundleError("full response record fields are not exact")
        atomic_exclusive_write(
            self.path / "events" / f"{call_id:04d}-response.json",
            json_bytes(record),
        )
        self._response_calls.add(call_id)
