"""Verify public-site blob-backed data delivery.

Checks local export artifacts and the deployed Blob-backed API endpoints, then
prints human-friendly ✓/✗ lines with concrete counts and next steps.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _ok(label: str, detail: str) -> None:
    print(f"✓ {label}: {detail}")


def _fail(label: str, detail: str) -> None:
    print(f"✗ {label}: {detail}")


def _fetch_json(url: str, timeout_s: float) -> tuple[int, Any, int]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = response.read()
        return response.status, json.loads(body.decode("utf-8")), len(body)


def _load_local_json(path: Path) -> tuple[Any, int]:
    body = path.read_bytes()
    return json.loads(body.decode("utf-8")), len(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Blob-backed public-site data delivery")
    parser.add_argument("--base-url", default="https://amiingroup.vercel.app")
    parser.add_argument(
        "--public-dir",
        type=Path,
        default=Path("tpot-analyzer/public-site/public"),
    )
    parser.add_argument("--timeout-s", type=float, default=20.0)
    args = parser.parse_args()

    public_dir = args.public_dir
    data_path = public_dir / "data.json"
    search_path = public_dir / "search.json"

    print("VERIFY PUBLIC SITE BLOB DATA")
    print(f"Base URL: {args.base_url}")
    print(f"Public dir: {public_dir}")
    print("")

    failures = 0

    if not data_path.exists():
        failures += 1
        _fail("Local data.json", f"missing at {data_path}")
        local_data = None
        local_data_bytes = 0
    else:
        local_data, local_data_bytes = _load_local_json(data_path)
        counts = local_data.get("meta", {}).get("counts", {})
        _ok(
            "Local data.json",
            f"{local_data_bytes:,} bytes | "
            f"communities={counts.get('communities')} | "
            f"accounts={counts.get('total_accounts')} | "
            f"searchable={counts.get('total_searchable')}",
        )

    if not search_path.exists():
        failures += 1
        _fail("Local search.json", f"missing at {search_path}")
        local_search = None
        local_search_bytes = 0
    else:
        local_search, local_search_bytes = _load_local_json(search_path)
        _ok(
            "Local search.json",
            f"{local_search_bytes:,} bytes | handles={len(local_search)}",
        )

    remote_checks = [
        ("Remote /api/data", f"{args.base_url.rstrip('/')}/api/data"),
        ("Remote /api/search", f"{args.base_url.rstrip('/')}/api/search"),
    ]

    remote_payloads: dict[str, Any] = {}

    for label, url in remote_checks:
        try:
            status, payload, body_bytes = _fetch_json(url, args.timeout_s)
        except urllib.error.HTTPError as error:
            failures += 1
            body = error.read().decode("utf-8", errors="replace")
            _fail(label, f"HTTP {error.code} from {url} | body={body[:200]}")
            continue
        except Exception as error:  # pragma: no cover - network failures are environment-specific
            failures += 1
            _fail(label, f"{url} failed: {error}")
            continue

        remote_payloads[label] = payload
        if label.endswith("/api/data"):
            counts = payload.get("meta", {}).get("counts", {})
            _ok(
                label,
                f"HTTP {status} | {body_bytes:,} bytes | "
                f"communities={counts.get('communities')} | "
                f"accounts={counts.get('total_accounts')} | "
                f"searchable={counts.get('total_searchable')}",
            )
        else:
            _ok(label, f"HTTP {status} | {body_bytes:,} bytes | handles={len(payload)}")

    if local_data is not None and "Remote /api/data" in remote_payloads:
        remote_data = remote_payloads["Remote /api/data"]
        local_counts = local_data.get("meta", {}).get("counts", {})
        remote_counts = remote_data.get("meta", {}).get("counts", {})
        if local_counts == remote_counts:
            _ok("Count parity", f"local and remote data counts match: {local_counts}")
        else:
            failures += 1
            _fail("Count parity", f"local={local_counts} remote={remote_counts}")

    if local_search is not None and "Remote /api/search" in remote_payloads:
        remote_search = remote_payloads["Remote /api/search"]
        if len(local_search) == len(remote_search):
            _ok("Search parity", f"local and remote search sizes match: {len(local_search)}")
        else:
            failures += 1
            _fail("Search parity", f"local={len(local_search)} remote={len(remote_search)}")

    print("")
    if failures:
        print("Next steps:")
        print("- Re-run the export if local files are missing or stale.")
        print("- Run the Blob upload helper from tpot-analyzer/public-site.")
        print("- Redeploy the public site if the API routes are not yet live.")
        return 1

    print("Next steps:")
    print("- Open the site and confirm search + community pages render against /api/data and /api/search.")
    print("- Paste this output into chat if you want a quick deployment sanity check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
