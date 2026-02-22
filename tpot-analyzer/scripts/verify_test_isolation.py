"""Verify SQLite resource hygiene and real-DB test isolation."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from src.data.fetcher import CachedDataFetcher


CHECK = "✓"
CROSS = "✗"
REAL_DB_TEST_ENV = "TPOT_RUN_REAL_DB_TESTS"
_REAL_DB_TRUE_VALUES = {"1", "true", "yes", "on"}


def _status(ok: bool, label: str) -> str:
    return f"{CHECK if ok else CROSS} {label}"


def _count_open_handles(path: Path) -> int | None:
    lsof = shutil.which("lsof")
    if not lsof:
        return None

    proc = subprocess.run(
        [lsof, "-p", str(os.getpid())],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None

    needle = str(path.resolve())
    return sum(1 for line in proc.stdout.splitlines() if needle in line)


def _verify_fetcher_handle_release(iterations: int = 20) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="tpot_fetcher_verify_") as tmp_dir:
        db_path = Path(tmp_dir) / "verify_cache.db"
        samples: list[int] = []
        max_handles = 0

        for _ in range(iterations):
            fetcher = CachedDataFetcher(cache_db=db_path)
            fetcher.close()
            handles = _count_open_handles(db_path)
            if handles is not None:
                samples.append(handles)
                max_handles = max(max_handles, handles)

    if not samples:
        return False, "could not sample file handles (`lsof` unavailable or failed)"

    preview = ",".join(str(v) for v in samples[:6])
    ok = max_handles == 0
    detail = (
        f"iterations={iterations} sample_handles=[{preview}] "
        f"max_handles={max_handles}"
    )
    return ok, detail


def _run_pytest_check(
    *,
    project_root: Path,
    python_bin: Path,
    tests: list[str],
    env: dict[str, str],
) -> tuple[int, int, float, str]:
    cmd = [str(python_bin), "-m", "pytest", "-q", *tests]
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    duration_s = time.perf_counter() - started
    output = f"{proc.stdout}\n{proc.stderr}".strip()
    return proc.returncode, int(round(duration_s, 2)), duration_s, output


def _parse_skipped(output: str) -> int:
    match = re.search(r"(\d+)\s+skipped", output)
    return int(match.group(1)) if match else 0


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    python_bin = project_root / ".venv" / "bin" / "python"
    data_cache_path = project_root / "data" / "cache.db"

    lines: list[str] = []
    failures = 0

    lines.append("TPOT Test Isolation Verification")
    lines.append(f"- project_root: {project_root}")
    lines.append(f"- python_bin: {python_bin}")
    lines.append("")

    python_ok = python_bin.exists()
    lines.append(_status(python_ok, "venv python exists"))
    if not python_ok:
        lines.append("")
        lines.append("Next steps:")
        lines.append(
            "- Create venv and deps: `cd tpot-analyzer && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`"
        )
        print("\n".join(lines))
        return 1

    # Check 1: verify fetcher lifecycle releases SQLite handles.
    handles_ok, handles_detail = _verify_fetcher_handle_release(iterations=20)
    lines.append(_status(handles_ok, "CachedDataFetcher.close releases SQLite handles"))
    lines.append(f"  metrics: {handles_detail}")
    if not handles_ok:
        failures += 1

    # Check 2: real-db tests should be skipped by default unless explicitly enabled.
    gated_tests = [
        "tests/test_shadow_coverage.py::test_low_coverage_detection",
        "tests/test_shadow_coverage.py::test_archive_vs_shadow_coverage",
        "tests/test_shadow_coverage.py::test_coverage_script_runs",
        "tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup::test_check_list_freshness_finds_shadow_id_records",
        "tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup::test_check_list_freshness_without_username_still_checks_real_id",
        "tests/test_shadow_enricher_utils.py::TestMultiRunFreshness::test_check_list_freshness_across_multiple_runs",
    ]

    env_default = os.environ.copy()
    env_default.pop(REAL_DB_TEST_ENV, None)
    rc, duration_rounded, _, output = _run_pytest_check(
        project_root=project_root,
        python_bin=python_bin,
        tests=gated_tests,
        env=env_default,
    )
    skipped = _parse_skipped(output)
    expected_skipped = len(gated_tests)
    skip_ok = rc == 0 and skipped == expected_skipped
    lines.append(
        _status(
            skip_ok,
            f"default run skips real-db tests when {REAL_DB_TEST_ENV} is unset",
        )
    )
    lines.append(
        "  metrics: "
        f"expected_skipped={expected_skipped} actual_skipped={skipped} "
        f"pytest_rc={rc} duration_s={duration_rounded}"
    )
    if not skip_ok:
        failures += 1
        tail = output.splitlines()[-15:]
        lines.append("  output_tail:")
        lines.extend(f"    {line}" for line in tail)

    # Check 3 (optional): if cache DB exists, run one opt-in real-db smoke test.
    smoke_env = os.environ.copy()
    smoke_env[REAL_DB_TEST_ENV] = "1"
    smoke_test = [
        "tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup::test_check_list_freshness_finds_shadow_id_records"
    ]
    if data_cache_path.exists():
        smoke_rc, smoke_duration_rounded, _, smoke_output = _run_pytest_check(
            project_root=project_root,
            python_bin=python_bin,
            tests=smoke_test,
            env=smoke_env,
        )
        smoke_ok = smoke_rc == 0
        lines.append(_status(smoke_ok, "opt-in real-db smoke test passes"))
        lines.append(
            "  metrics: "
            f"cache_db_size_mb={round(data_cache_path.stat().st_size / (1024 * 1024), 2)} "
            f"pytest_rc={smoke_rc} duration_s={smoke_duration_rounded}"
        )
        if not smoke_ok:
            failures += 1
            tail = smoke_output.splitlines()[-15:]
            lines.append("  output_tail:")
            lines.extend(f"    {line}" for line in tail)
    else:
        lines.append(_status(True, "opt-in real-db smoke test skipped (data/cache.db not present)"))
        lines.append("  metrics: cache_db_present=False")

    lines.append("")
    lines.append("Next steps:")
    lines.append(
        f"- Default CI/local suites should run without `{REAL_DB_TEST_ENV}` for determinism."
    )
    lines.append(
        f"- Run shared-db checks explicitly when needed: `{REAL_DB_TEST_ENV}=1 .venv/bin/python -m pytest tests/test_shadow_coverage.py tests/test_shadow_enricher_utils.py -q`."
    )
    lines.append("- If handle check fails, inspect other long-lived SQLAlchemy engines and ensure `.dispose()` is called.")

    print("\n".join(lines))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
