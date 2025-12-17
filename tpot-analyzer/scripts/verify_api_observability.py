"""Verify API observability (request IDs + log files).

This script is designed for humans to run and paste output into chat.

It checks:
  1) Backend is reachable
  2) X-Request-ID correlation works (client -> server -> api.log)
  3) Frontend log ingestion writes to logs/frontend.log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.error import URLError
from urllib.request import Request, urlopen


def status_line(ok: bool, msg: str) -> str:
    return f"{'✓' if ok else '✗'} {msg}"


def _default_log_dir() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    return Path(os.getenv("TPOT_LOG_DIR") or (project_root / "logs"))


def _http_json(method: str, url: str, *, headers: dict[str, str] | None = None, body: Any | None = None, timeout_s: float = 5.0):
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = Request(url, method=method, data=data, headers=req_headers)
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else None
        return resp.status, dict(resp.headers), payload


def _wait_for_log_match(path: Path, needle: str, *, timeout_s: float = 2.0) -> tuple[bool, list[str]]:
    deadline = time.time() + timeout_s
    last_lines: list[str] = []
    while time.time() < deadline:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []
        last_lines = [line.rstrip("\n") for line in lines[-200:]]
        if any(needle in line for line in last_lines):
            return True, last_lines
        time.sleep(0.1)
    return False, last_lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify TPOT API observability (logs + request IDs).")
    parser.add_argument("--base-url", default="http://localhost:5001", help="Backend base URL (default: http://localhost:5001).")
    parser.add_argument("--log-dir", type=Path, default=_default_log_dir(), help="Directory containing log files.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    base_url = args.base_url.rstrip("/")
    log_dir: Path = args.log_dir
    api_log = log_dir / "api.log"
    frontend_log = log_dir / "frontend.log"

    lines: list[str] = []
    lines.append("TPOT Observability Verification")
    lines.append(f"- base_url: {base_url}")
    lines.append(f"- log_dir:  {log_dir}")
    lines.append("")

    # 1) Health + X-Request-ID propagation
    client_req_id = f"verify-{uuid4().hex[:8]}"
    try:
        status, headers, payload = _http_json("GET", f"{base_url}/api/health", headers={"X-Request-ID": client_req_id})
        ok_health = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
        header_req_id = headers.get("X-Request-ID")
        ok_header = header_req_id == client_req_id
        lines.append(status_line(ok_health, f"GET /api/health returns ok (status={status})"))
        lines.append(status_line(ok_header, f"X-Request-ID echoes client id ({header_req_id})"))
    except URLError as exc:
        lines.append(status_line(False, f"Backend unreachable at {base_url} ({exc})"))
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Start backend: `cd tpot-analyzer && ./scripts/start_dev.sh`")
        lines.append("- Or: `cd tpot-analyzer && source .venv/bin/activate && API_LOG_LEVEL=DEBUG python3 -m scripts.start_api_server`")
        print("\n".join(lines))
        return 1

    # 2) api.log contains the request id (correlation)
    ok_api_log_exists = api_log.exists()
    lines.append(status_line(ok_api_log_exists, f"api.log exists ({api_log})"))
    if ok_api_log_exists:
        ok_match, tail = _wait_for_log_match(api_log, f"req={client_req_id}", timeout_s=2.0)
        lines.append(status_line(ok_match, "api.log contains request id from health check"))
        if not ok_match:
            lines.append("  Sample (last ~20 lines):")
            for line in tail[-20:]:
                lines.append(f"  {line}")
    else:
        lines.append("  Note: api.log is created when the API logger writes its first line.")

    # 3) Frontend log ingestion writes to disk
    marker = f"verify_frontend_log:{uuid4().hex[:8]}"
    try:
        status, headers, payload = _http_json(
            "POST",
            f"{base_url}/api/log",
            headers={"X-Request-ID": f"verifylog-{uuid4().hex[:8]}"},
            body={"level": "INFO", "message": marker, "payload": {"source": "verify_api_observability.py"}},
        )
        ok_post = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
        lines.append(status_line(ok_post, f"POST /api/log accepted (status={status})"))
    except URLError as exc:
        lines.append(status_line(False, f"POST /api/log failed ({exc})"))
        ok_post = False

    ok_frontend_log_exists = frontend_log.exists()
    lines.append(status_line(ok_frontend_log_exists, f"frontend.log exists ({frontend_log})"))
    if ok_post and ok_frontend_log_exists:
        ok_match, tail = _wait_for_log_match(frontend_log, marker, timeout_s=2.0)
        lines.append(status_line(ok_match, "frontend.log contains the posted marker"))
        if not ok_match:
            lines.append("  Sample (last ~10 lines):")
            for line in tail[-10:]:
                lines.append(f"  {line}")

    lines.append("")
    lines.append("Next steps:")
    lines.append(f"- Tail cluster logs: `python3 -m scripts.tail_cluster_logs --clusters`")
    lines.append(f"- Tail by request id: `python3 -m scripts.tail_cluster_logs --req {client_req_id}`")
    lines.append(f"- Cluster API logs live in: `{api_log}`")
    lines.append(f"- Frontend POST /api/log lands in: `{frontend_log}`")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

