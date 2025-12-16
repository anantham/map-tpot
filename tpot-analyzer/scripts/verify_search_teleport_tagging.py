#!/usr/bin/env python3
"""
verify_search_teleport_tagging.py

Human-friendly verification for:
  - /api/clusters (baseline connectivity)
  - /api/accounts/search
  - /api/accounts/<id>/teleport_plan (focus_leaf planning)
  - /api/accounts/<id>/tags CRUD (IN / NOT IN)

Usage:
  cd tpot-analyzer
  python3 -m scripts.verify_search_teleport_tagging --base-url http://localhost:5001 --ego adityaarpitha
  python3 scripts/verify_search_teleport_tagging.py --ego adityaarpitha
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    duration_ms: Optional[int] = None


def _fmt_result(result: CheckResult) -> str:
    mark = "✓" if result.ok else "✗"
    dur = f" ({result.duration_ms}ms)" if result.duration_ms is not None else ""
    return f"{mark} {result.name}{dur} — {result.detail}"


def _request_json(
    *,
    url: str,
    method: str = "GET",
    body: Optional[dict] = None,
    timeout_s: float = 30.0,
) -> Tuple[int, Any, int]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            dur_ms = int((time.time() - start) * 1000)
            text = raw.decode("utf-8") if raw else ""
            payload = json.loads(text) if text else None
            return resp.status, payload, dur_ms
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        dur_ms = int((time.time() - start) * 1000)
        text = raw.decode("utf-8") if raw else ""
        try:
            payload = json.loads(text) if text else None
        except Exception:
            payload = {"raw": text}
        return exc.code, payload, dur_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5001", help="Flask API base URL")
    parser.add_argument("--ego", default="adityaarpitha", help="Ego scope for tags (any non-empty string)")
    parser.add_argument("--budget", type=int, default=25, help="Budget cap for cluster views")
    parser.add_argument("--visible", type=int, default=11, help="Starting visible (n) to test teleport planning")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    ego = (args.ego or "").strip()

    print("verify_search_teleport_tagging.py")
    print(f"API: {base_url}")
    print(f"ego: {ego or '(missing)'}")
    print("")

    results: list[CheckResult] = []

    # 1) /api/clusters reachable
    clusters_url = (
        f"{base_url}/api/clusters?"
        + urllib.parse.urlencode(
            {
                "n": "5",
                "budget": str(args.budget),
                "wl": "0.00",
                "expand_depth": "0.50",
                "reqId": f"verify-{_utc_now_compact()}",
            }
        )
    )
    status, payload, dur_ms = _request_json(url=clusters_url, timeout_s=60.0)
    if status != 200:
        results.append(
            CheckResult(
                name="GET /api/clusters",
                ok=False,
                duration_ms=dur_ms,
                detail=f"HTTP {status} payload={payload}",
            )
        )
        for r in results:
            print(_fmt_result(r))
        print("")
        print("Next steps:")
        print("- Start the API server: `cd tpot-analyzer; source .venv/bin/activate; python3 -m scripts.start_api_server`")
        print("- If port is busy: `lsof -nP -iTCP:5001 -sTCP:LISTEN` then `kill <pid>`")
        return 1

    clusters = payload.get("clusters") if isinstance(payload, dict) else None
    if not isinstance(clusters, list) or not clusters:
        results.append(
            CheckResult(
                name="GET /api/clusters",
                ok=False,
                duration_ms=dur_ms,
                detail=f"Missing/empty clusters in payload keys={list(payload.keys()) if isinstance(payload, dict) else type(payload)}",
            )
        )
        for r in results:
            print(_fmt_result(r))
        return 1

    results.append(
        CheckResult(
            name="GET /api/clusters",
            ok=True,
            duration_ms=dur_ms,
            detail=f"clusters={len(clusters)} budget_remaining={(payload.get('meta') or {}).get('budget_remaining')}",
        )
    )

    # 2) Pick a sample account_id from memberIds
    sample_account_id: Optional[str] = None
    sample_cluster_id: Optional[str] = None
    for c in clusters:
        member_ids = c.get("memberIds") if isinstance(c, dict) else None
        if isinstance(member_ids, list) and member_ids:
            sample_account_id = str(member_ids[0])
            sample_cluster_id = str(c.get("id"))
            break

    if not sample_account_id:
        results.append(
            CheckResult(
                name="Extract sample member account",
                ok=False,
                detail="No cluster returned memberIds; cannot proceed",
            )
        )
        for r in results:
            print(_fmt_result(r))
        return 1

    results.append(
        CheckResult(
            name="Extract sample member account",
            ok=True,
            detail=f"account_id={sample_account_id} from cluster_id={sample_cluster_id}",
        )
    )

    # 3) /api/accounts/<id>
    acct_url = f"{base_url}/api/accounts/{urllib.parse.quote(sample_account_id)}"
    status, acct_payload, dur_ms = _request_json(url=acct_url, timeout_s=20.0)
    if status != 200:
        results.append(
            CheckResult(
                name="GET /api/accounts/<id>",
                ok=False,
                duration_ms=dur_ms,
                detail=f"HTTP {status} payload={acct_payload}",
            )
        )
        for r in results:
            print(_fmt_result(r))
        return 1

    username = None
    if isinstance(acct_payload, dict):
        username = (acct_payload.get("username") or "").strip() or None

    results.append(
        CheckResult(
            name="GET /api/accounts/<id>",
            ok=True,
            duration_ms=dur_ms,
            detail=f"username={username or '(none)'}",
        )
    )

    # 4) /api/accounts/search
    q = (username or sample_account_id)[:32]
    search_url = f"{base_url}/api/accounts/search?{urllib.parse.urlencode({'q': q, 'limit': '10'})}"
    status, search_payload, dur_ms = _request_json(url=search_url, timeout_s=30.0)
    if status != 200 or not isinstance(search_payload, list):
        results.append(
            CheckResult(
                name="GET /api/accounts/search",
                ok=False,
                duration_ms=dur_ms,
                detail=f"HTTP {status} payload_type={type(search_payload)}",
            )
        )
        for r in results:
            print(_fmt_result(r))
        return 1

    hit_ids = {str(item.get("id")) for item in search_payload if isinstance(item, dict)}
    found = sample_account_id in hit_ids
    results.append(
        CheckResult(
            name="GET /api/accounts/search",
            ok=found,
            duration_ms=dur_ms,
            detail=f"q={q!r} results={len(search_payload)} contains_sample={found}",
        )
    )
    if not found:
        for r in results:
            print(_fmt_result(r))
        return 1

    # 5) /teleport_plan
    tp_url = f"{base_url}/api/accounts/{urllib.parse.quote(sample_account_id)}/teleport_plan?{urllib.parse.urlencode({'budget': str(args.budget), 'visible': str(args.visible)})}"
    status, tp_payload, dur_ms = _request_json(url=tp_url, timeout_s=30.0)
    ok_tp = (
        status == 200
        and isinstance(tp_payload, dict)
        and bool(tp_payload.get("leafClusterId"))
        and isinstance(tp_payload.get("targetVisible"), int)
    )
    results.append(
        CheckResult(
            name="GET /api/accounts/<id>/teleport_plan",
            ok=ok_tp,
            duration_ms=dur_ms,
            detail=f"leafClusterId={tp_payload.get('leafClusterId') if isinstance(tp_payload, dict) else None} targetVisible={tp_payload.get('targetVisible') if isinstance(tp_payload, dict) else None}",
        )
    )
    if not ok_tp:
        for r in results:
            print(_fmt_result(r))
        return 1

    # 6) Tags CRUD
    if not ego:
        results.append(
            CheckResult(
                name="Account tags CRUD",
                ok=False,
                detail="Skipped: ego is empty (pass --ego ...)",
            )
        )
        for r in results:
            print(_fmt_result(r))
        return 1

    tag_value = f"verify_{_utc_now_compact()}"
    tags_url = f"{base_url}/api/accounts/{urllib.parse.quote(sample_account_id)}/tags?{urllib.parse.urlencode({'ego': ego})}"
    status, up_payload, dur_ms = _request_json(url=tags_url, method="POST", body={"tag": tag_value, "polarity": "in"}, timeout_s=20.0)
    ok_up = status == 200 and isinstance(up_payload, dict) and up_payload.get("status") == "ok"
    results.append(
        CheckResult(
            name="POST /api/accounts/<id>/tags (IN)",
            ok=ok_up,
            duration_ms=dur_ms,
            detail=f"tag={tag_value}",
        )
    )
    if not ok_up:
        for r in results:
            print(_fmt_result(r))
        return 1

    status, list_payload, dur_ms = _request_json(url=tags_url, timeout_s=20.0)
    listed = []
    if isinstance(list_payload, dict):
        listed = list_payload.get("tags") or []
    ok_list = status == 200 and any(isinstance(t, dict) and t.get("tag") == tag_value and int(t.get("polarity")) == 1 for t in listed)
    results.append(
        CheckResult(
            name="GET /api/accounts/<id>/tags",
            ok=ok_list,
            duration_ms=dur_ms,
            detail=f"tag_present={ok_list} tags_count={len(listed)}",
        )
    )
    if not ok_list:
        for r in results:
            print(_fmt_result(r))
        return 1

    # 6b) Cluster tag summary (Phase 2): ensure member tag appears at the cluster level
    if sample_cluster_id:
        summary_url = (
            f"{base_url}/api/clusters/{urllib.parse.quote(sample_cluster_id)}/tag_summary?"
            + urllib.parse.urlencode(
                {
                    "ego": ego,
                    "n": "5",
                    "budget": str(args.budget),
                    "wl": "0.00",
                    "expand_depth": "0.50",
                }
            )
        )
        status, summary_payload, dur_ms = _request_json(url=summary_url, timeout_s=30.0)
        ok_summary = status == 200 and isinstance(summary_payload, dict) and isinstance(summary_payload.get("tagCounts"), list)
        matched = None
        if ok_summary:
            for row in summary_payload.get("tagCounts") or []:
                if isinstance(row, dict) and row.get("tag") == tag_value:
                    matched = row
                    break
        ok_contains = bool(matched) and int(matched.get("inCount") or 0) >= 1
        results.append(
            CheckResult(
                name="GET /api/clusters/<cluster_id>/tag_summary",
                ok=ok_summary and ok_contains,
                duration_ms=dur_ms,
                detail=f"cluster_id={sample_cluster_id} tag_present={bool(matched)} inCount={matched.get('inCount') if isinstance(matched, dict) else None}",
            )
        )
        if not (ok_summary and ok_contains):
            for r in results:
                print(_fmt_result(r))
            return 1

    status, up2_payload, dur_ms = _request_json(url=tags_url, method="POST", body={"tag": tag_value, "polarity": "not_in"}, timeout_s=20.0)
    ok_up2 = status == 200 and isinstance(up2_payload, dict) and up2_payload.get("status") == "ok"
    results.append(
        CheckResult(
            name="POST /api/accounts/<id>/tags (NOT IN)",
            ok=ok_up2,
            duration_ms=dur_ms,
            detail=f"tag={tag_value}",
        )
    )
    if not ok_up2:
        for r in results:
            print(_fmt_result(r))
        return 1

    status, list2_payload, dur_ms = _request_json(url=tags_url, timeout_s=20.0)
    listed2 = []
    if isinstance(list2_payload, dict):
        listed2 = list2_payload.get("tags") or []
    ok_list2 = status == 200 and any(isinstance(t, dict) and t.get("tag") == tag_value and int(t.get("polarity")) == -1 for t in listed2)
    results.append(
        CheckResult(
            name="GET /api/accounts/<id>/tags (polarity updated)",
            ok=ok_list2,
            duration_ms=dur_ms,
            detail=f"polarity_is_-1={ok_list2}",
        )
    )
    if not ok_list2:
        for r in results:
            print(_fmt_result(r))
        return 1

    distinct_url = f"{base_url}/api/tags?{urllib.parse.urlencode({'ego': ego})}"
    status, distinct_payload, dur_ms = _request_json(url=distinct_url, timeout_s=20.0)
    distinct = distinct_payload.get("tags") if isinstance(distinct_payload, dict) else None
    ok_distinct = status == 200 and isinstance(distinct, list)
    results.append(
        CheckResult(
            name="GET /api/tags",
            ok=ok_distinct,
            duration_ms=dur_ms,
            detail=f"distinct_tags={len(distinct) if isinstance(distinct, list) else None}",
        )
    )
    if not ok_distinct:
        for r in results:
            print(_fmt_result(r))
        return 1

    del_url = f"{base_url}/api/accounts/{urllib.parse.quote(sample_account_id)}/tags/{urllib.parse.quote(tag_value)}?{urllib.parse.urlencode({'ego': ego})}"
    status, del_payload, dur_ms = _request_json(url=del_url, method="DELETE", timeout_s=20.0)
    ok_del = status == 200 and isinstance(del_payload, dict) and del_payload.get("status") in ("deleted", "not_found")
    results.append(
        CheckResult(
            name="DELETE /api/accounts/<id>/tags/<tag>",
            ok=ok_del,
            duration_ms=dur_ms,
            detail=f"status={del_payload.get('status') if isinstance(del_payload, dict) else None}",
        )
    )
    if not ok_del:
        for r in results:
            print(_fmt_result(r))
        return 1

    status, list3_payload, dur_ms = _request_json(url=tags_url, timeout_s=20.0)
    listed3 = []
    if isinstance(list3_payload, dict):
        listed3 = list3_payload.get("tags") or []
    ok_removed = status == 200 and all(not (isinstance(t, dict) and t.get("tag") == tag_value) for t in listed3)
    results.append(
        CheckResult(
            name="GET /api/accounts/<id>/tags (removed)",
            ok=ok_removed,
            duration_ms=dur_ms,
            detail=f"still_present={not ok_removed} tags_count={len(listed3)}",
        )
    )

    for r in results:
        print(_fmt_result(r))

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    print("")
    print(f"Summary: {passed} passed, {failed} failed, {len(results)} total")
    print("Next steps:")
    print("- Frontend: open Graph Explorer and use “Teleport to @account…” to jump + tag.")
    print("- If teleport fails for a specific account, capture `focus_leaf` and budget/visible from the URL for debugging.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
