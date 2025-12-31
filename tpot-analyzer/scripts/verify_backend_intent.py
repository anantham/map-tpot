"""Verify backend testability improvements (fixtures + helper coverage).

This script is designed for humans to run and paste output into chat.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


CHECKMARK = "\u2713"
CROSS = "\u2717"


def status_line(ok: bool, msg: str) -> str:
    return f"{CHECKMARK if ok else CROSS} {msg}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify backend testability improvements.")
    parser.add_argument("--run-tests", action="store_true", help="Run targeted pytest checks.")
    return parser.parse_args(argv)


def _count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return int(cursor.fetchone()[0])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    lines: list[str] = []
    lines.append("TPOT Backend Verification")
    lines.append(f"- root: {project_root}")
    lines.append("")

    ok_fixture = False
    fixture_counts = {}
    try:
        from tests.fixtures.create_test_cache_db import create_test_cache_db
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            cache_path = tmp_path / "cache.db"
            counts = create_test_cache_db(cache_path)
            fixture_counts = counts.as_dict()

            row_counts = {
                "account": _count_rows(cache_path, "account"),
                "profile": _count_rows(cache_path, "profile"),
                "followers": _count_rows(cache_path, "followers"),
                "following": _count_rows(cache_path, "following"),
            }
            ok_fixture = all(value > 0 for value in row_counts.values())
    except Exception as exc:
        lines.append(status_line(False, f"Fixture cache.db creation failed: {exc}"))
        ok_fixture = False

    if ok_fixture:
        lines.append(status_line(True, "Deterministic cache.db fixture created"))
        lines.append(f"  Counts: {fixture_counts}")
    else:
        lines.append(status_line(False, "Deterministic cache.db fixture created"))

    ok_helper = False
    try:
        from src.shadow.enricher import HybridShadowEnricher
        ok_helper = HybridShadowEnricher._compute_skip_coverage_percent(0, 0) == 100.0
    except Exception as exc:
        lines.append(status_line(False, f"Skip coverage helper check failed: {exc}"))
        ok_helper = False

    lines.append(status_line(ok_helper, "Skip coverage helper returns 100% for 0/0"))

    ok_tests = False
    if args.run_tests:
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::test_graph_data_endpoint",
            "tests/test_api.py::test_compute_metrics_endpoint",
            "tests/test_shadow_enricher_utils.py::TestZeroCoverageEdgeCase",
            "tests/test_cluster_routes.py::TestClusterLabelEndpoints",
            "-q",
        ]
        lines.append("")
        lines.append(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        ok_tests = result.returncode == 0
        lines.append(status_line(ok_tests, "Targeted pytest checks"))
        if result.stdout.strip():
            lines.append("  stdout:")
            lines.extend([f"  {line}" for line in result.stdout.splitlines()])
        if result.stderr.strip():
            lines.append("  stderr:")
            lines.extend([f"  {line}" for line in result.stderr.splitlines()])
    else:
        lines.append(status_line(False, "Targeted pytest checks (use --run-tests)"))

    lines.append("")
    lines.append("Next steps:")
    lines.append("- Run with `--run-tests` to exercise the updated fixtures/tests.")
    lines.append("- If cache.db fixture fails, inspect `tests/fixtures/create_test_cache_db.py`.")
    lines.append("- If helper check fails, confirm `_compute_skip_coverage_percent` is in use.")

    print("\n".join(lines))
    checks_ok = ok_fixture and ok_helper and ok_tests
    return 0 if checks_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
