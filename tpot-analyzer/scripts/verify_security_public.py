#!/usr/bin/env python3
"""Verify public security contracts against an explicitly disposable Redis only."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public-site"
TESTS = ["__tests__/api/card-admission-security.test.js",
         "__tests__/api/card-budget-corruption.test.js",
         "__tests__/api/generate-card.test.js",
         "__tests__/api/generate-card-prompt-semantics.test.js",
         "__tests__/api/card-status.test.js", "__tests__/api/gallery.test.js",
         "__tests__/api/gallery-security.test.js", "__tests__/api/image-policy.test.js",
         "__tests__/api/gallery-policy.integration.test.js",
         "__tests__/api/blob-site-data.test.js", "src/cardCapabilities.test.js",
         "src/cardTransport.test.js", "src/GenerateCard.test.js",
         "src/GenerateCard.publication.test.jsx", "src/galleryPages.test.js",
         "src/CardGallery.pagination.test.jsx"]
MODULES = ["api/_cardAdmission.js", "api/_cardBudget.js", "api/_cardCache.js",
           "api/_cardRequest.js", "api/_cardProvider.js", "api/generate-card.js",
           "api/card-status.js", "api/_galleryPolicy.js", "api/_galleryScripts.js",
           "api/_imagePolicy.js", "src/cardTransport.js", "src/cardCache.js",
           "src/cardCapabilities.js", "src/CardGrantInput.jsx", "src/GenerateCard.jsx"]


def mark(ok: bool, message: str) -> bool:
    print(f"{'✓' if ok else '✗'} {message}", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-socket", default=os.environ.get("TPOT_TEST_REDIS_SOCKET"))
    args = parser.parse_args()
    env = os.environ.copy()
    socket = args.redis_socket
    ci = env.get("CI") == "true" and env.get("TPOT_TEST_REDIS_URL") == "redis://127.0.0.1:6379"
    valid_socket = bool(socket and re.fullmatch(r"/tmp/tpot-security-redis-[a-zA-Z0-9_-]+\.sock", socket))
    if not mark(valid_socket or ci, "Explicit disposable Redis configured; production targets rejected"):
        print("Next: start temporary Redis with persistence disabled, supply its allowed /tmp socket, or use the CI service.")
        return 1
    if valid_socket:
        env["TPOT_TEST_REDIS_SOCKET"] = socket
    ok = True
    for name in MODULES:
        lines = len((PUBLIC / name).read_text().splitlines())
        ok = mark(lines <= 300, f"{name}: {lines} LOC, limit300") and ok
    result = subprocess.run(["node", "node_modules/vitest/vitest.mjs", "run", *TESTS,
                             "--configLoader", "runner"], cwd=PUBLIC, env=env,
                            text=True, capture_output=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    no_skips = not re.search(r"\d+ skipped", result.stdout)
    ok = mark(result.returncode == 0 and no_skips,
              "Paid admission, real Lua reservations, raster decoder and public UI contracts (no skipped Redis checks)") and ok
    result = subprocess.run(["node", "--test", "scripts/publication-policy.node-test.mjs"], cwd=PUBLIC, env=env)
    ok = mark(result.returncode == 0, "Strict immutable publication and exact-digest approval contracts") and ok
    print("Ceilings: 2 paid calls; conservative0.50USD reservations against5USD daily ledger; no refunds on uncertain failures.")
    print("Gallery: 500handles, 3versions,90days visibility,100/day global,5/day handle,1500lifetime uploads.")
    print("Next: review patch and migrations; sponsored generation stays disabled until pricing/reservation assurance is approved.")
    print("No paid provider, production Redis, Blob writes or deployment are used by these synthetic tests.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
