"""Verify account-community gold label storage and split isolation."""
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
    parser = argparse.ArgumentParser(description="Verify account-community holdout endpoints")
    parser.add_argument("--base-url", default="http://localhost:5001", help="API base URL")
    parser.add_argument("--account-id", required=True, help="Account id to label during verification")
    parser.add_argument("--community-id", required=True, help="Primary community id to label during verification")
    parser.add_argument(
        "--secondary-community-id",
        required=True,
        help="Second community id to confirm the split is account-scoped",
    )
    parser.add_argument("--reviewer", default="verify_holdout")
    args = parser.parse_args()

    checks: list[str] = []
    failures = 0

    health = request_json(args.base_url, "GET", "/api/health")
    checks.append(status_line(health.ok, f"health endpoint reachable (status={health.status})"))
    if not health.ok:
        failures += 1

    communities = request_json(args.base_url, "GET", "/api/community-gold/communities")
    checks.append(status_line(communities.ok, f"community-gold communities endpoint reachable (status={communities.status})"))
    if not communities.ok:
        failures += 1

    first = request_json(
        args.base_url,
        "POST",
        "/api/community-gold/labels",
        body={
            "accountId": args.account_id,
            "communityId": args.community_id,
            "reviewer": args.reviewer,
            "judgment": "in",
            "confidence": 0.9,
            "note": "verification positive",
        },
    )
    checks.append(status_line(first.ok, f"primary label accepted (status={first.status})"))
    if not first.ok:
        failures += 1

    second = request_json(
        args.base_url,
        "POST",
        "/api/community-gold/labels",
        body={
            "accountId": args.account_id,
            "communityId": args.secondary_community_id,
            "reviewer": args.reviewer,
            "judgment": "out",
            "note": "verification explicit negative",
        },
    )
    checks.append(status_line(second.ok, f"secondary label accepted (status={second.status})"))
    if not second.ok:
        failures += 1

    same_split = bool(first.payload.get("split")) and first.payload.get("split") == second.payload.get("split")
    checks.append(status_line(same_split, f"same account receives one split across communities ({first.payload.get('split')} vs {second.payload.get('split')})"))
    if not same_split:
        failures += 1

    labels = request_json(
        args.base_url,
        "GET",
        f"/api/community-gold/labels?accountId={args.account_id}&reviewer={args.reviewer}&limit=10",
    )
    checks.append(status_line(labels.ok, f"labels endpoint reachable (status={labels.status})"))
    if not labels.ok:
        failures += 1

    metrics = request_json(args.base_url, "GET", "/api/community-gold/metrics")
    checks.append(status_line(metrics.ok, f"metrics endpoint reachable (status={metrics.status})"))
    if not metrics.ok:
        failures += 1

    leakage = (metrics.payload or {}).get("leakageChecks", {})
    leakage_clean = leakage.get("duplicateActiveLabels") == 0 and leakage.get("accountsWithMultipleSplits") == 0
    checks.append(status_line(leakage_clean, f"leakage checks are clean ({leakage})"))
    if not leakage_clean:
        failures += 1

    print("Account-Community Holdout Verification")
    print("=" * 37)
    for line in checks:
        print(line)

    print("\nMetrics")
    print(f"- account_id: {args.account_id}")
    print(f"- reviewer: {args.reviewer}")
    print(f"- primary_split: {first.payload.get('split')}")
    print(f"- labels_returned: {len((labels.payload or {}).get('labels', []))}")
    print(f"- total_active_labels: {(metrics.payload or {}).get('totalActiveLabels', 'n/a')}")
    print(f"- split_counts: {(metrics.payload or {}).get('splitCounts', {})}")
    print(f"- judgment_counts: {(metrics.payload or {}).get('judgmentCounts', {})}")
    print(f"- leakage_checks: {leakage}")

    print("\nNext steps")
    if failures:
        print("- Fix the failing contract or route/store behavior before adding evaluator logic.")
        print("- Re-run this verifier against the local backend once the errors are addressed.")
        sys.exit(1)

    print("- The held-out label substrate is operational and split isolation is enforced per account.")
    print("- Next: add evaluator endpoints that score baselines and graph methods on dev/test labels.")


if __name__ == "__main__":
    main()
