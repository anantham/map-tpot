#!/usr/bin/env python3
"""Human-friendly verification for extension feed ingestion endpoints."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status(ok: bool, message: str) -> str:
    return f"{'✓' if ok else '✗'} {message}"


def _http_json(url: str, *, method: str = "GET", body: Optional[dict] = None, timeout_s: float = 30.0) -> Tuple[int, Any]:
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    req = Request(url, method=method, headers=headers, data=payload)
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify extension feed ingestion APIs.")
    parser.add_argument("--base-url", default="http://localhost:5001", help="Backend base URL")
    parser.add_argument("--ego", default="adityaarpitha", help="Ego scope for feed data")
    parser.add_argument("--workspace-id", default="default", help="Workspace scope")
    parser.add_argument("--timeout-s", type=float, default=30.0, help="HTTP timeout in seconds")
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    scope_qs = urlencode({"ego": args.ego, "workspace_id": args.workspace_id})
    run_id = int(time.time())
    account_id = f"verify_ext_account_{run_id}"
    tag_name = f"verify_ext_tag_{run_id}"
    now = _utc_iso()

    lines: list[str] = []
    checks_ok = True

    lines.append("TPOT Extension Feed Verification")
    lines.append(f"- base_url: {base}")
    lines.append(f"- ego: {args.ego}")
    lines.append(f"- workspace_id: {args.workspace_id}")
    lines.append("")

    try:
        status, payload = _http_json(f"{base}/api/health", timeout_s=args.timeout_s)
    except URLError as exc:
        lines.append(_status(False, f"Backend unreachable ({exc})"))
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Start backend: `cd tpot-analyzer && .venv/bin/python -m scripts.start_api_server`")
        print("\n".join(lines))
        return 1

    health_ok = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
    checks_ok &= health_ok
    lines.append(_status(health_ok, f"GET /api/health (status={status})"))

    settings_get_status, settings_get_payload = _http_json(
        f"{base}/api/extension/settings?{scope_qs}",
        timeout_s=args.timeout_s,
    )
    settings_get_ok = (
        settings_get_status == 200
        and isinstance(settings_get_payload, dict)
        and settings_get_payload.get("ingestionMode") in {"open", "guarded"}
    )
    checks_ok &= settings_get_ok
    lines.append(
        _status(
            settings_get_ok,
            f"GET /api/extension/settings mode={settings_get_payload.get('ingestionMode') if isinstance(settings_get_payload, dict) else None} status={settings_get_status}",
        )
    )

    settings_put_status, settings_put_payload = _http_json(
        f"{base}/api/extension/settings?{scope_qs}",
        method="PUT",
        body={
            "ingestionMode": "open",
            "retentionMode": "infinite",
            "processingMode": "continuous",
            "allowlistEnabled": False,
            "firehoseEnabled": True,
        },
        timeout_s=args.timeout_s,
    )
    settings_put_ok = (
        settings_put_status == 200
        and isinstance(settings_put_payload, dict)
        and (settings_put_payload.get("settings") or {}).get("retentionMode") == "infinite"
    )
    checks_ok &= settings_put_ok
    lines.append(
        _status(
            settings_put_ok,
            f"PUT /api/extension/settings status={settings_put_status}",
        )
    )

    ingest_url = f"{base}/api/extension/feed_events?{scope_qs}"
    ingest_body = {
        "events": [
            {
                "accountId": account_id,
                "username": "verify_account",
                "tweetId": f"tweet_{int(time.time())}",
                "tweetText": "Testing extension ingestion for TPOT feed semantics",
                "surface": "home",
                "position": 1,
                "seenAt": now,
            },
            {
                "accountId": account_id,
                "username": "verify_account",
                "tweetId": f"tweet_{int(time.time())}_2",
                "tweetText": "Second exposure sample for keyword extraction checks",
                "surface": "following",
                "position": 2,
                "seenAt": now,
            },
        ]
    }
    ingest_status, ingest_payload = _http_json(
        ingest_url,
        method="POST",
        body=ingest_body,
        timeout_s=args.timeout_s,
    )
    ingest_ok = (
        ingest_status == 200
        and isinstance(ingest_payload, dict)
        and ingest_payload.get("status") == "ok"
        and int((ingest_payload.get("ingest") or {}).get("inserted") or 0) >= 1
    )
    checks_ok &= ingest_ok
    lines.append(
        _status(
            ingest_ok,
            f"POST /api/extension/feed_events inserted={((ingest_payload or {}).get('ingest') or {}).get('inserted')} "
            f"duplicates={((ingest_payload or {}).get('ingest') or {}).get('duplicates')} "
            f"firehose_written={((ingest_payload or {}).get('firehose') or {}).get('written')} status={ingest_status}",
        )
    )

    raw_status, raw_payload = _http_json(
        f"{base}/api/extension/feed_events/raw?{scope_qs}&limit=20",
        timeout_s=args.timeout_s,
    )
    raw_events = raw_payload.get("events") if isinstance(raw_payload, dict) else None
    raw_ok = (
        raw_status == 200
        and isinstance(raw_events, list)
        and any((row or {}).get("accountId") == account_id for row in raw_events)
    )
    checks_ok &= raw_ok
    lines.append(
        _status(
            raw_ok,
            f"GET /api/extension/feed_events/raw events={len(raw_events) if isinstance(raw_events, list) else 0} status={raw_status}",
        )
    )

    summary_url = f"{base}/api/extension/accounts/{account_id}/summary?{scope_qs}&days=365"
    summary_status, summary_payload = _http_json(summary_url, timeout_s=args.timeout_s)
    summary_ok = (
        summary_status == 200
        and isinstance(summary_payload, dict)
        and int(summary_payload.get("impressions") or 0) >= 1
    )
    checks_ok &= summary_ok
    lines.append(
        _status(
            summary_ok,
            f"GET /api/extension/accounts/<id>/summary impressions={summary_payload.get('impressions') if isinstance(summary_payload, dict) else None} "
            f"uniqueTweetsSeen={summary_payload.get('uniqueTweetsSeen') if isinstance(summary_payload, dict) else None} status={summary_status}",
        )
    )

    top_url = f"{base}/api/extension/exposure/top?{scope_qs}&days=365&limit=10"
    top_status, top_payload = _http_json(top_url, timeout_s=args.timeout_s)
    top_accounts = top_payload.get("accounts") if isinstance(top_payload, dict) else None
    top_ok = top_status == 200 and isinstance(top_accounts, list) and len(top_accounts) >= 1
    checks_ok &= top_ok
    lines.append(
        _status(
            top_ok,
            f"GET /api/extension/exposure/top accounts={len(top_accounts) if isinstance(top_accounts, list) else 0} status={top_status}",
        )
    )

    tag_status, tag_payload = _http_json(
        f"{base}/api/accounts/{account_id}/tags?ego={args.ego}",
        method="POST",
        body={"tag": tag_name, "polarity": "in"},
        timeout_s=args.timeout_s,
    )
    tag_ok = tag_status == 200 and isinstance(tag_payload, dict) and tag_payload.get("status") == "ok"
    checks_ok &= tag_ok
    lines.append(_status(tag_ok, f"POST /api/accounts/<id>/tags status={tag_status}"))

    purge_status, purge_payload = _http_json(
        f"{base}/api/extension/feed_events/purge_by_tag?{scope_qs}",
        method="POST",
        body={"tag": tag_name},
        timeout_s=args.timeout_s,
    )
    purge_ok = (
        purge_status == 200
        and isinstance(purge_payload, dict)
        and int(purge_payload.get("accountCount") or 0) >= 1
    )
    checks_ok &= purge_ok
    lines.append(
        _status(
            purge_ok,
            f"POST /api/extension/feed_events/purge_by_tag accountCount={purge_payload.get('accountCount') if isinstance(purge_payload, dict) else None} status={purge_status}",
        )
    )

    lines.append("")
    lines.append("Next steps:")
    lines.append("- If checks fail, inspect logs/api.log for '/api/extension/*' and '/api/accounts/*' traces.")
    lines.append("- Run focused tests: `.venv/bin/python -m pytest tests/test_extension_routes.py tests/test_feed_signals_store.py tests/test_feed_signals_admin_store.py tests/test_feed_scope_policy_store.py -q`")
    print("\n".join(lines))
    return 0 if checks_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
