"""Verify the account-community gold review queue."""
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


def request_json(base_url: str, method: str, path: str) -> HttpResult:
    req = Request(
        url=f"{base_url.rstrip('/')}{path}",
        method=method.upper(),
        headers={"Accept": "application/json"},
    )
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
    parser = argparse.ArgumentParser(description="Verify account-community gold review queue")
    parser.add_argument("--base-url", default="http://localhost:5001", help="API base URL")
    parser.add_argument("--reviewer", default="human", help="Reviewer namespace")
    parser.add_argument("--limit", default=5, type=int, help="How many candidates to request")
    parser.add_argument("--community-id", default=None, help="Optional community to scope the queue")
    parser.add_argument("--split", default=None, help="Optional split filter: train, dev, or test")
    args = parser.parse_args()

    path = f"/api/community-gold/candidates?reviewer={args.reviewer}&limit={max(1, args.limit)}"
    if args.community_id:
        path += f"&communityId={args.community_id}"
    if args.split:
        path += f"&split={args.split}"

    checks: list[str] = []
    failures = 0

    health = request_json(args.base_url, "GET", "/api/health")
    checks.append(status_line(health.ok, f"health endpoint reachable (status={health.status})"))
    failures += 0 if health.ok else 1

    metrics = request_json(args.base_url, "GET", "/api/community-gold/metrics")
    checks.append(status_line(metrics.ok, f"community-gold metrics reachable (status={metrics.status})"))
    failures += 0 if metrics.ok else 1

    queue = request_json(args.base_url, "GET", path)
    checks.append(status_line(queue.ok, f"candidate queue reachable (status={queue.status})"))
    failures += 0 if queue.ok else 1

    candidates = (queue.payload or {}).get("candidates", [])
    checks.append(status_line(bool(candidates), f"candidate queue returned rows (count={len(candidates)})"))
    failures += 0 if candidates else 1

    required_keys = {"accountId", "communityId", "split", "selectionMode", "reason", "queueScore", "methodScores"}
    first = candidates[0] if candidates else {}
    shape_ok = required_keys.issubset(first.keys()) if first else False
    checks.append(status_line(shape_ok, f"candidate shape includes required keys ({sorted(required_keys)})"))
    failures += 0 if shape_ok else 1

    modes = sorted({row.get("selectionMode") for row in candidates if row.get("selectionMode")})
    checks.append(status_line(bool(modes), f"queue modes observed ({modes or ['none']})"))
    failures += 0 if modes else 1

    print("Account-Community Queue Verification")
    print("=" * 35)
    for line in checks:
        print(line)

    print("\nMetrics")
    print(f"- reviewer: {args.reviewer}")
    print(f"- requested_limit: {args.limit}")
    print(f"- community_id: {args.community_id or 'all'}")
    print(f"- total_active_labels: {(metrics.payload or {}).get('totalActiveLabels', 'n/a')}")
    print(f"- leakage_checks: {(metrics.payload or {}).get('leakageChecks', {})}")
    print(f"- observed_modes: {modes or ['none']}")

    print("\nSample candidates")
    for row in candidates[: min(3, len(candidates))]:
        print(
            f"- @{row.get('username') or row.get('accountId')} → {row.get('communityName') or row.get('communityId')} "
            f"[{row.get('selectionMode')}] score={row.get('queueScore'):.3f} reason={row.get('reason')}"
        )

    print("\nNext steps")
    if failures:
        print("- Seed more community memberships or fix backend reachability until the queue returns candidates.")
        print("- If warm mode never appears, add train positives and negatives for the target community and re-run.")
        sys.exit(1)

    if "warm" in modes:
        print("- Warm-mode queueing is active; disagreement/uncertainty scoring is available for review.")
    else:
        print("- Queue is operating in cold-start mode only; add train IN and OUT labels to unlock warm scoring.")
    print("- Next: review candidates from the Communities tab and compare queue usefulness against manual browsing.")


if __name__ == "__main__":
    main()
