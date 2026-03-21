"""Verify account-community evaluator endpoints."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


def request_json(base_url: str, method: str, path: str, *, body: Optional[Dict[str, Any]] = None) -> HttpResult:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
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
    parser = argparse.ArgumentParser(description="Verify account-community evaluator endpoint")
    parser.add_argument("--base-url", default="http://localhost:5001", help="API base URL")
    parser.add_argument("--split", default="dev", help="Evaluation split (dev or test)")
    parser.add_argument("--reviewer", default="human", help="Reviewer namespace to evaluate")
    args = parser.parse_args()

    checks: list[str] = []
    failures = 0

    health = request_json(args.base_url, "GET", "/api/health")
    checks.append(status_line(health.ok, f"health endpoint reachable (status={health.status})"))
    if not health.ok:
        failures += 1

    metrics = request_json(args.base_url, "GET", "/api/community-gold/metrics")
    checks.append(status_line(metrics.ok, f"community-gold metrics reachable (status={metrics.status})"))
    if not metrics.ok:
        failures += 1

    evaluation = request_json(
        args.base_url,
        "POST",
        "/api/community-gold/evaluate",
        body={"split": args.split, "reviewer": args.reviewer},
    )
    checks.append(status_line(evaluation.ok, f"evaluation scoreboard reachable (status={evaluation.status})"))
    if not evaluation.ok:
        failures += 1

    summary = (evaluation.payload or {}).get("summary", {})
    scored_methods = sum(1 for row in summary.values() if row.get("scoredCommunities", 0) > 0)
    checks.append(status_line(scored_methods > 0, f"at least one method produced scored communities (count={scored_methods})"))
    if scored_methods == 0:
        failures += 1

    leakage = (metrics.payload or {}).get("leakageChecks", {})
    leakage_clean = leakage.get("duplicateActiveLabels") == 0 and leakage.get("accountsWithMultipleSplits") == 0
    checks.append(status_line(leakage_clean, f"leakage checks are clean ({leakage})"))
    if not leakage_clean:
        failures += 1

    print("Account-Community Evaluator Verification")
    print("=" * 39)
    for line in checks:
        print(line)

    print("\nMetrics")
    print(f"- reviewer: {args.reviewer}")
    print(f"- split: {args.split}")
    print(f"- total_active_labels: {(metrics.payload or {}).get('totalActiveLabels', 'n/a')}")
    print(f"- best_method_by_macro_auc_pr: {(evaluation.payload or {}).get('bestMethodByMacroAucPr', 'n/a')}")
    print(f"- method_summary: {summary}")

    print("\nNext steps")
    if failures:
        print("- Add more gold labels or fix missing graph artifacts if the scoreboard is unavailable.")
        print("- Re-run this verifier after the backend has enough labeled positives and negatives per community.")
        sys.exit(1)

    print("- The evaluator scoreboard is operational for the configured reviewer and split.")
    print("- Next: build the dedicated gold-label UI on top of /api/community-gold/labels and /evaluate.")


if __name__ == "__main__":
    main()
