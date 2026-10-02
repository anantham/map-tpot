"""Offline, synthetic verification of local trust and publication prevention.

Prints counts and next steps without opening private data or making live requests.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ["tests/test_archive_limits_security.py", "tests/test_cookie_store_security.py",
         "tests/test_artifact_io_security.py", "tests/test_publication_boundary_security.py",
         "tests/test_git_publication_boundary.py"]


def main() -> int:
    unsafe = []
    checked = 0
    for directory in (ROOT / "src", ROOT / "scripts"):
        for path in directory.rglob("*.py"):
            checked += 1
            source = path.read_text()
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Call):
                    continue
                pickle_call = (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                               and node.func.value.id == "pickle" and node.func.attr in {"load", "dump", "loads", "dumps"})
                allows_pickle = any(keyword.arg == "allow_pickle" and isinstance(keyword.value, ast.Constant)
                                    and keyword.value.value is True for keyword in node.keywords)
                if pickle_call or allows_pickle:
                    unsafe.append(str(path.relative_to(ROOT)))
                    break
    print(f"{'✗' if unsafe else '✓'} Executable deserialization audit: {checked} source files; {len(unsafe)} unsafe loaders/writers")
    if unsafe:
        print("Next: remove these unsafe paths before integration: " + ", ".join(unsafe))
        return 1
    result = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q"], cwd=ROOT)
    print(f"{'✓' if result.returncode == 0 else '✗'} Synthetic local security contracts: {len(TESTS)} test modules")
    if result.returncode:
        print("Next: resolve failed behavioral contracts before publishing any patch.")
        return result.returncode
    result = subprocess.run(["node", "--test", "public-site/scripts/publication-policy.node-test.mjs"], cwd=ROOT)
    print(f"{'✓' if result.returncode == 0 else '✗'} Exact-digest publication contracts: synthetic inputs and mocked Blob uploads")
    print("Next: recapture JSON cookies; rebuild safe artifacts from source; review exact candidate digest.")
    print("Historical public artifacts remain: owner approval is required for deletion/history cleanup and production deployment.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
