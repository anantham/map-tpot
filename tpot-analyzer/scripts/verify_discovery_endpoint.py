"""Human-friendly verification for /api/subgraph/discover behavior."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def _status_line(ok: bool, message: str) -> str:
    return f"{'✓' if ok else '✗'} {message}"


def _http_json(
    method: str,
    url: str,
    *,
    body: Any | None = None,
    timeout_s: float = 30.0,
):
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, method=method, data=data, headers=headers)
    with urlopen(req, timeout=timeout_s) as response:
        raw = response.read()
        payload = json.loads(raw.decode("utf-8")) if raw else None
        return response.status, payload


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify discovery endpoint behavior.")
    parser.add_argument("--base-url", default="http://localhost:5001", help="Backend base URL.")
    parser.add_argument("--timeout-s", type=float, default=30.0, help="HTTP timeout per request.")
    return parser.parse_args(argv)


def _build_payload(seed: str, *, debug: bool = True) -> dict[str, Any]:
    return {
        "seeds": [seed],
        "weights": {
            "neighbor_overlap": 0.4,
            "pagerank": 0.3,
            "community": 0.2,
            "path_distance": 0.1,
        },
        "filters": {
            "max_distance": 3,
            "min_overlap": 0,
            "min_followers": 0,
            "max_followers": 1_000_000,
            "include_shadow": True,
        },
        "limit": 10,
        "offset": 0,
        "debug": debug,
    }


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    base = args.base_url.rstrip("/")
    lines: list[str] = []
    checks_ok = True

    lines.append("TPOT Discovery Endpoint Verification")
    lines.append(f"- base_url: {base}")
    lines.append("")

    # 1) Reachability
    try:
        health_status, health_payload = _http_json("GET", f"{base}/api/health", timeout_s=args.timeout_s)
    except URLError as exc:
        lines.append(_status_line(False, f"Backend unreachable ({exc})"))
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Start backend: `cd tpot-analyzer && .venv/bin/python -m scripts.start_api_server`")
        print("\n".join(lines))
        return 1

    ok = health_status == 200 and isinstance(health_payload, dict) and health_payload.get("status") == "ok"
    checks_ok &= ok
    lines.append(_status_line(ok, f"GET /api/health is healthy (status={health_status})"))

    # 2) Pick a seed from graph-data for stable smoke checks.
    graph_status, graph_payload = _http_json(
        "GET",
        f"{base}/api/graph-data?include_shadow=true&mutual_only=false&min_followers=0",
        timeout_s=max(args.timeout_s, 45.0),
    )
    graph_ok = graph_status == 200 and isinstance(graph_payload, dict) and isinstance(graph_payload.get("nodes"), list)
    checks_ok &= graph_ok
    lines.append(_status_line(graph_ok, f"GET /api/graph-data returns nodes (status={graph_status})"))

    if not graph_ok or not graph_payload["nodes"]:
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Ensure snapshot/cache DB has graph data.")
        print("\n".join(lines))
        return 1

    sample_node = graph_payload["nodes"][0]
    sample_id = str(sample_node.get("id", ""))
    sample_username = str(sample_node.get("username") or sample_id)
    lines.append(f"  sample_seed_id={sample_id} sample_seed_username={sample_username}")

    # 3) Username-seed request.
    username_payload = _build_payload(sample_username, debug=True)
    username_status, username_data = _http_json(
        "POST",
        f"{base}/api/subgraph/discover",
        body=username_payload,
        timeout_s=max(args.timeout_s, 45.0),
    )
    username_ok = (
        username_status == 200
        and isinstance(username_data, dict)
        and "error" not in username_data
        and isinstance(username_data.get("recommendations"), list)
        and isinstance(username_data.get("meta"), dict)
    )
    checks_ok &= username_ok
    lines.append(_status_line(username_ok, f"POST /api/subgraph/discover username-seed succeeds (status={username_status})"))
    if username_ok:
        lines.append(
            f"  recommendations={username_data['meta'].get('recommendation_count')} "
            f"candidates={username_data['meta'].get('total_candidates')} "
            f"compute_ms={username_data['meta'].get('computation_time_ms')}"
        )

    # 4) Account-id request.
    account_payload = _build_payload(sample_id, debug=False)
    account_status, account_data = _http_json(
        "POST",
        f"{base}/api/subgraph/discover",
        body=account_payload,
        timeout_s=max(args.timeout_s, 45.0),
    )
    account_ok = (
        account_status == 200
        and isinstance(account_data, dict)
        and "error" not in account_data
        and account_data.get("meta", {}).get("seed_count", 0) >= 1
    )
    checks_ok &= account_ok
    lines.append(_status_line(account_ok, f"POST /api/subgraph/discover account-id seed succeeds (status={account_status})"))

    # 5) Unknown-handle behavior.
    unknown_seed = "__definitely_unknown_seed__"
    unknown_status, unknown_data = _http_json(
        "POST",
        f"{base}/api/subgraph/discover",
        body=_build_payload(unknown_seed, debug=True),
    )
    unknown_ok = (
        unknown_status == 200
        and isinstance(unknown_data, dict)
        and unknown_data.get("error", {}).get("code") == "NO_VALID_SEEDS"
        and unknown_seed in (unknown_data.get("error", {}).get("unknown_handles") or [])
    )
    checks_ok &= unknown_ok
    lines.append(_status_line(unknown_ok, "Unknown-only seeds return NO_VALID_SEEDS with unknown_handles"))

    mixed_payload = _build_payload(sample_username, debug=False)
    mixed_payload["seeds"] = [sample_username, unknown_seed]
    mixed_status, mixed_data = _http_json(
        "POST",
        f"{base}/api/subgraph/discover",
        body=mixed_payload,
    )
    mixed_ok = (
        mixed_status == 200
        and isinstance(mixed_data, dict)
        and "error" not in mixed_data
        and any(unknown_seed in warning for warning in (mixed_data.get("warnings") or []))
    )
    checks_ok &= mixed_ok
    lines.append(_status_line(mixed_ok, "Mixed known+unknown seeds return warnings without failing"))

    # 6) Non-object JSON body should be a shape validation error.
    invalid_status, invalid_payload = _http_json(
        "POST",
        f"{base}/api/subgraph/discover",
        body=["not", "an", "object"],
    )
    invalid_ok = (
        invalid_status == 400
        and isinstance(invalid_payload, dict)
        and invalid_payload.get("error", {}).get("message") == "Request body must be a JSON object"
    )
    checks_ok &= invalid_ok
    lines.append(_status_line(invalid_ok, "Non-object JSON body returns structured 400"))

    lines.append("")
    lines.append("Next steps:")
    lines.append("- If any check failed, inspect logs/api.log and reproduce with scripts/verify_discovery_endpoint.py --base-url ...")
    lines.append("- If all checks pass, run targeted tests: `.venv/bin/python -m pytest tests/test_discovery_endpoint_matrix.py -q`")
    print("\n".join(lines))
    return 0 if checks_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
