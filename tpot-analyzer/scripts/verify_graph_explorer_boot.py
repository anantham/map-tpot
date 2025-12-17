"""Verify GraphExplorer prerequisites (seed settings + graph-data shape).

Human-friendly ✓/✗ output intended to be pasted into chat.

Checks:
  1) Backend reachable
  2) GET /api/seeds returns expected keys (GraphExplorer settings panel)
  3) GET /api/graph-data returns nodes/edges and reports counts/types
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def status_line(ok: bool, msg: str) -> str:
    return f"{'✓' if ok else '✗'} {msg}"


def _http_json(method: str, url: str, *, body: Any | None = None, timeout_s: float = 15.0):
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, method=method, data=data, headers=headers)
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else None
        return resp.status, payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify GraphExplorer boot dependencies.")
    parser.add_argument("--base-url", default="http://localhost:5001", help="Backend base URL.")
    parser.add_argument("--include-shadow", default="true", choices=["true", "false"], help="Pass include_shadow to /api/graph-data.")
    parser.add_argument("--mutual-only", default="false", choices=["true", "false"], help="Pass mutual_only to /api/graph-data.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    base = args.base_url.rstrip("/")

    lines: list[str] = []
    lines.append("TPOT GraphExplorer Boot Verification")
    lines.append(f"- base_url: {base}")
    lines.append("")

    # 1) Basic reachability
    try:
        status, payload = _http_json("GET", f"{base}/api/health")
        ok = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
        lines.append(status_line(ok, f"GET /api/health ok (status={status})"))
        if not ok:
            lines.append(f"  payload={payload}")
    except URLError as exc:
        lines.append(status_line(False, f"Backend unreachable ({exc})"))
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Start backend: `cd tpot-analyzer && ./scripts/start_dev.sh`")
        lines.append("- Or: `cd tpot-analyzer && source .venv/bin/activate && python3 -m scripts.start_api_server`")
        print("\n".join(lines))
        return 1

    # 2) Seed settings endpoint
    status, seeds_payload = _http_json("GET", f"{base}/api/seeds")
    ok_status = status == 200 and isinstance(seeds_payload, dict)
    lines.append(status_line(ok_status, f"GET /api/seeds returns JSON (status={status})"))
    required = {"active_list", "lists", "preset_names", "user_list_names", "settings"}
    ok_keys = ok_status and required.issubset(set(seeds_payload.keys()))
    lines.append(status_line(ok_keys, f"/api/seeds includes keys: {sorted(required)}"))
    if ok_status:
        lists = seeds_payload.get("lists") or {}
        lines.append(f"  lists: {len(lists)} (active={seeds_payload.get('active_list')})")

    # 3) Graph-data shape
    graph_url = f"{base}/api/graph-data?include_shadow={args.include_shadow}&mutual_only={args.mutual_only}&min_followers=0"
    status, graph_payload = _http_json("GET", graph_url, timeout_s=45.0)
    ok_graph = status == 200 and isinstance(graph_payload, dict)
    lines.append(status_line(ok_graph, f"GET /api/graph-data ok (status={status})"))
    if ok_graph:
        nodes = graph_payload.get("nodes") or []
        edges = graph_payload.get("edges") or []
        dn = graph_payload.get("directed_nodes")
        de = graph_payload.get("directed_edges")
        lines.append(f"  nodes: {len(nodes)} | edges: {len(edges)}")
        lines.append(f"  directed_nodes type: {type(dn).__name__} | directed_edges type: {type(de).__name__}")

    lines.append("")
    lines.append("Next steps:")
    lines.append("- Open GraphExplorer view; the control panel should load presets and render summary counts.")
    lines.append("- If GraphExplorer looks wrong, capture the request id from the Network tab and grep `logs/api.log`.")

    print("\n".join(lines))
    return 0 if ok_keys and ok_graph else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

