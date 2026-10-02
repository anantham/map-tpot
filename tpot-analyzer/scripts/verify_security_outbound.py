#!/usr/bin/env python3
"""Verify T13/T14 using source metrics and synthetic outbound regression tests.

Run with the project's Python after installing requirements. No URL probes,
private data, production database access or paid API calls are performed.
"""
from __future__ import annotations

import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("url_guard", "outbound_dns", "outbound_transport", "response_limits", "enrichment_fetch", "enrichment_cache", "tweet_enrichment")
TESTS = ("test_url_guard", "test_outbound_transport", "test_outbound_response_edges", "test_outbound_deadlines", "test_enrichment_fetch")


def status(ok, message):
    print(f"{'✓' if ok else '✗'} {message}", flush=True)
    return ok


def main():
    ok = True
    for name in MODULES:
        path = ROOT / "src/api" / f"{name}.py"
        text = path.read_text()
        ast.parse(text)
        count = len(text.splitlines())
        ok = status(count <= 300, f"{path.relative_to(ROOT)}: {count} LOC (limit 300)") and ok
    declared = "Pillow==12.3.0" in (ROOT / "requirements.txt").read_text()
    try:
        version = importlib.metadata.version("Pillow")
    except importlib.metadata.PackageNotFoundError:
        version = "not installed"
    ok = status(declared and version == "12.3.0", f"Declared/installed raster decoder: Pillow {version}") and ok
    print("Budgets: HTML 100,000 bytes; syndication 1 MiB; images 5 MiB / 16,000,000 pixels / one frame.")
    print("Transport: ≤5 redirects, ≤4 in-flight DNS workers/no queue, pinned peer, original TLS hostname/Host.")
    print("Work: ≤5 short links / ≤3 images; compressed + decoded caps; HTTP framing overhead ≤64 KiB.")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *(f"tests/{name}.py" for name in TESTS)], cwd=ROOT)
    ok = status(result.returncode == 0, "Synthetic socket, TLS, framing, compression, image and cache contracts") and ok
    print("Next: review patch; install requirements; restart local Flask only after approval. No deployment was performed.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
