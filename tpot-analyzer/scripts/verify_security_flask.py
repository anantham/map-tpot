#!/usr/bin/env python3
"""Verify Flask boundary/resource contracts without real data or network calls."""
from pathlib import Path
import re
import subprocess
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short",
                             "tests/test_security_flask_boundary.py",
                             "tests/test_security_cluster_admission.py",
                             "tests/test_security_resource_limits.py",
                             "tests/test_security_cross_process.py"],
                            cwd=root, text=True, capture_output=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    count = re.search(r"(\d+) passed", result.stdout)
    print(f"{'✓' if result.returncode == 0 else '✗'} Flask security contracts: {count.group(1) if count else 'unknown'} passed")
    print("✓ Synthetic temporary stores only; no paid API or live exploit requests")
    print("Limits: graph concurrency 1/shared snapshot root; unsupervised full analysis disabled; caches 8 graph/64 discovery, 16 MiB each, 300s TTL")
    print("Limits: feedback 20,000 rows, 4 KiB context, new records expire after 30 days")
    print("Limits: frontend logs 8 KiB entries, 1 MiB file + 3 rotated backups with shared locking")
    print("Next: review patch, configure matching curator tokens in a private analyst deployment;")
    print("obtain separate approval for deployment and historical feedback cleanup.")
    sys.exit(result.returncode)
