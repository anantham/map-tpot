"""Verify MVP A golden curation loop (schema + routes + queue + eval)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

CHECK = "✓"
CROSS = "✗"


@dataclass
class HttpResult:
    ok: bool
    status: int
    payload: Dict[str, Any]
    error: Optional[str] = None


def status_line(ok: bool, message: str) -> str:
    return f"{CHECK if ok else CROSS} {message}"


def request_json(base_url: str, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None) -> HttpResult:
    query = ""
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        query = "?" + urlencode(filtered)
    url = f"{base_url.rstrip('/')}{path}{query}"

    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url=url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return HttpResult(ok=200 <= resp.status < 300, status=resp.status, payload=payload)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return HttpResult(ok=False, status=exc.code, payload=payload, error=str(exc))
    except URLError as exc:
        return HttpResult(ok=False, status=0, payload={}, error=str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify MVP A golden curation endpoints")
    parser.add_argument("--base-url", default="http://localhost:5001", help="API base URL")
    parser.add_argument("--axis", default="simulacrum")
    parser.add_argument("--reviewer", default=f"verify_{uuid4().hex[:8]}")
    parser.add_argument("--model-name", default="verify_model")
    parser.add_argument("--prompt-version", default="verify_v1")
    args = parser.parse_args()

    checks: list[str] = []
    failures = 0

    health = request_json(args.base_url, "GET", "/api/health")
    checks.append(status_line(health.ok, f"health endpoint reachable (status={health.status})"))
    if not health.ok:
        failures += 1

    candidates = request_json(
        args.base_url,
        "GET",
        "/api/golden/candidates",
        params={
            "axis": args.axis,
            "split": "train",
            "status": "unlabeled",
            "reviewer": args.reviewer,
            "limit": 10,
        },
    )
    checks.append(status_line(candidates.ok, f"golden candidates loaded (status={candidates.status})"))
    if not candidates.ok:
        failures += 1

    candidate_rows = candidates.payload.get("candidates", []) if isinstance(candidates.payload, dict) else []
    checks.append(status_line(bool(candidate_rows), f"at least one unlabeled train candidate available (count={len(candidate_rows)})"))
    if not candidate_rows:
        failures += 1

    tweet_id = candidate_rows[0].get("tweetId") if candidate_rows else None
    label_dist = {"l1": 0.7, "l2": 0.1, "l3": 0.2, "l4": 0.0}

    label_result = HttpResult(ok=False, status=0, payload={}, error="skipped")
    prediction_result = HttpResult(ok=False, status=0, payload={}, error="skipped")
    queue_result = HttpResult(ok=False, status=0, payload={}, error="skipped")
    eval_result = HttpResult(ok=False, status=0, payload={}, error="skipped")
    metrics_result = HttpResult(ok=False, status=0, payload={}, error="skipped")

    if tweet_id:
        label_result = request_json(
            args.base_url,
            "POST",
            "/api/golden/labels",
            body={
                "axis": args.axis,
                "tweet_id": tweet_id,
                "reviewer": args.reviewer,
                "distribution": label_dist,
                "note": "verify_mvp_a",
            },
        )
        checks.append(status_line(label_result.ok, f"label upsert accepted for tweet={tweet_id} (status={label_result.status})"))
        if not label_result.ok:
            failures += 1

        run_id = f"verify_run_{uuid4().hex[:8]}"
        prediction_result = request_json(
            args.base_url,
            "POST",
            "/api/golden/predictions/run",
            body={
                "axis": args.axis,
                "model_name": args.model_name,
                "prompt_version": args.prompt_version,
                "run_id": run_id,
                "reviewer": args.reviewer,
                "predictions": [{"tweet_id": tweet_id, "distribution": label_dist}],
            },
        )
        checks.append(status_line(prediction_result.ok, f"prediction ingest accepted (status={prediction_result.status})"))
        if not prediction_result.ok:
            failures += 1

        queue_result = request_json(
            args.base_url,
            "GET",
            "/api/golden/queue",
            params={"axis": args.axis, "status": "all", "split": "train", "limit": 25},
        )
        checks.append(status_line(queue_result.ok, f"queue endpoint reachable (status={queue_result.status})"))
        if not queue_result.ok:
            failures += 1

        eval_result = request_json(
            args.base_url,
            "POST",
            "/api/golden/eval/run",
            body={
                "axis": args.axis,
                "model_name": args.model_name,
                "prompt_version": args.prompt_version,
                "split": "train",
                "threshold": 0.18,
                "reviewer": args.reviewer,
                "run_id": f"verify_eval_{uuid4().hex[:8]}",
            },
        )
        checks.append(status_line(eval_result.ok, f"eval run completed (status={eval_result.status})"))
        if not eval_result.ok:
            failures += 1

        metrics_result = request_json(
            args.base_url,
            "GET",
            "/api/golden/metrics",
            params={"axis": args.axis, "reviewer": args.reviewer},
        )
        checks.append(status_line(metrics_result.ok, f"metrics endpoint reachable (status={metrics_result.status})"))
        if not metrics_result.ok:
            failures += 1

    print("MVP A Verification")
    print("=" * 18)
    for line in checks:
        print(line)

    print("\nMetrics")
    split_counts = candidates.payload.get("splitCounts", {}) if isinstance(candidates.payload, dict) else {}
    print(f"- axis: {args.axis}")
    print(f"- reviewer: {args.reviewer}")
    print(f"- candidates_returned: {len(candidate_rows)}")
    print(f"- split_counts: {split_counts}")
    if isinstance(prediction_result.payload, dict):
        print(f"- prediction_inserted: {prediction_result.payload.get('inserted', 'n/a')}")
        print(f"- queue_counts_after_prediction: {prediction_result.payload.get('queueCounts', {})}")
    if isinstance(eval_result.payload, dict):
        print(f"- eval_brier: {eval_result.payload.get('brierScore', 'n/a')}")
        print(f"- eval_sample_size: {eval_result.payload.get('sampleSize', 'n/a')}")
        print(f"- eval_passed: {eval_result.payload.get('passed', 'n/a')}")
    if isinstance(metrics_result.payload, dict):
        print(f"- labeled_count: {metrics_result.payload.get('labeledCount', 'n/a')}")
        print(f"- predicted_count: {metrics_result.payload.get('predictedCount', 'n/a')}")
        print(f"- queue_counts: {metrics_result.payload.get('queueCounts', {})}")

    print("\nNext steps")
    if failures:
        print("- Inspect response payloads for failed checks and fix route/store behavior.")
        print("- Re-run: python -m scripts.verify_mvp_a --base-url http://localhost:5001")
        sys.exit(1)

    print("- MVP A backend loop is operational for simulacrum axis.")
    print("- Next: connect dashboard UI to /api/golden/candidates, /labels, /queue, and /metrics.")


if __name__ == "__main__":
    main()
