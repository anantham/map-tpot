#!/usr/bin/env python3
"""Human-readable, no-service verification for the Research Notes runtime."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dev_runtime import DevRuntimeError, resolve_dev_runtime


def _check(label: str, passed: bool, detail: str) -> bool:
    print(f"{'✓' if passed else '✗'} {label}: {detail}")
    return passed


def _vite_server_config() -> dict:
    command = (
        "const c=(await import('./vite.config.js')).default;"
        "const v=typeof c==='function'?c({command:'serve',mode:'development'}):c;"
        "console.log(JSON.stringify(v.server))"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", command],
        cwd=PROJECT_ROOT / "graph-explorer",
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return json.loads(result.stdout)


def _default_cors_accepts_ui() -> bool:
    prior = {
        name: os.environ.get(name)
        for name in ("CORS_ORIGINS", "SNAPSHOT_DIR", "TPOT_LOG_DIR")
    }
    try:
        with tempfile.TemporaryDirectory(prefix="tpot-runtime-verify-") as raw_tmp:
            tmp = Path(raw_tmp)
            os.environ.pop("CORS_ORIGINS", None)
            os.environ["SNAPSHOT_DIR"] = str(tmp)
            os.environ["TPOT_LOG_DIR"] = str(tmp / "logs")
            from src.api.server import create_app

            response = create_app({"TESTING": True}).test_client().options(
                "/api/research-notes/dossiers/example",
                headers={
                    "Origin": "http://localhost:5184",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-TPOT-Curator-Token",
                },
            )
            return (
                response.status_code == 200
                and response.headers.get("Access-Control-Allow-Origin")
                == "http://localhost:5184"
            )
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _tag_counts(path: Path) -> tuple[int, int]:
    if not path.exists() or path.stat().st_size == 0:
        return 0, 0
    with sqlite3.connect(path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        current = (
            conn.execute("SELECT COUNT(*) FROM account_tags").fetchone()[0]
            if "account_tags" in tables
            else 0
        )
        events = (
            conn.execute("SELECT COUNT(*) FROM account_tag_events").fetchone()[0]
            if "account_tag_events" in tables
            else 0
        )
    return int(current), int(events)


def main() -> int:
    print("Research Notes local runtime verification")
    print("=" * 41)
    checks: list[bool] = []
    try:
        runtime = resolve_dev_runtime(PROJECT_ROOT)
    except DevRuntimeError as exc:
        _check("runtime inputs", False, str(exc))
        print("\nNext: set ARCHIVE_DB_PATH and SNAPSHOT_DIR, then rerun.")
        return 1

    archive_gib = runtime.archive_db.stat().st_size / (1024**3)
    checks.append(
        _check(
            "archive",
            True,
            f"{archive_gib:.2f} GiB, read-only dossier source at {runtime.archive_db}",
        )
    )
    checks.append(_check("snapshot/state", True, str(runtime.snapshot_dir)))
    current, events = _tag_counts(runtime.account_tags_db)
    checks.append(
        _check(
            "persistent tags",
            True,
            f"current={current}, events={events}, path={runtime.account_tags_db}",
        )
    )

    check_env = dict(os.environ)
    check_env.pop("TPOT_CURATOR_TOKEN", None)
    check_env.pop("VITE_TPOT_CURATOR_TOKEN", None)
    preflight = subprocess.run(
        [str(PROJECT_ROOT / "scripts" / "start_dev.sh"), "--check"],
        cwd=PROJECT_ROOT,
        env=check_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    checks.append(
        _check(
            "launcher preflight",
            preflight.returncode == 0,
            "paths/dependencies and ephemeral token generation resolved",
        )
    )

    secret = "runtime-verifier-secret-must-not-leak"
    pinned_env = dict(check_env)
    pinned_env["TPOT_CURATOR_TOKEN"] = secret
    pinned = subprocess.run(
        [str(PROJECT_ROOT / "scripts" / "start_dev.sh"), "--check"],
        cwd=PROJECT_ROOT,
        env=pinned_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = pinned.stdout + pinned.stderr
    checks.append(
        _check(
            "token privacy",
            pinned.returncode == 0
            and secret not in combined
            and "value not printed" in combined,
            "backend/frontend token is shared without printing its value",
        )
    )

    try:
        vite = _vite_server_config()
        vite_ok = vite == {
            "host": "localhost",
            "port": 5184,
            "strictPort": True,
            "hmr": {"host": "localhost", "port": 5184, "protocol": "ws"},
        }
        checks.append(_check("Vite origin/HMR", vite_ok, json.dumps(vite)))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        checks.append(_check("Vite origin/HMR", False, str(exc)))

    checks.append(
        _check(
            "backend CORS",
            _default_cors_accepts_ui(),
            "OPTIONS permits http://localhost:5184 with curator header",
        )
    )
    passed = sum(checks)
    print(f"\nResult: {passed}/{len(checks)} checks passed")
    if passed == len(checks):
        print("Next: ./scripts/start_dev.sh, then open /?view=research-notes")
        return 0
    print("Next: repair the failed preflight before asking for more curation.")
    return 1


def _backend_python_returncode() -> int | None:
    """Re-run under the discovered project environment when Flask is absent."""
    try:
        import flask  # noqa: F401
        return None
    except ModuleNotFoundError:
        if os.environ.get("TPOT_RUNTIME_VERIFIER_REEXEC") == "1":
            print("✗ backend dependencies: Flask is unavailable", file=sys.stderr)
            return 1
        try:
            runtime = resolve_dev_runtime(PROJECT_ROOT)
        except DevRuntimeError as exc:
            print(f"✗ runtime inputs: {exc}", file=sys.stderr)
            return 1
        candidates = [PROJECT_ROOT / ".venv" / "bin" / "python"]
        if runtime.primary_project_root is not None:
            candidates.append(
                runtime.primary_project_root / ".venv" / "bin" / "python"
            )
        interpreter = next((path for path in candidates if path.is_file()), None)
        if interpreter is None:
            print("✗ no project Python environment found", file=sys.stderr)
            return 1
        child_env = dict(os.environ)
        child_env["TPOT_RUNTIME_VERIFIER_REEXEC"] = "1"
        return subprocess.run(
            [str(interpreter), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=PROJECT_ROOT,
            env=child_env,
            check=False,
        ).returncode


if __name__ == "__main__":
    delegated = _backend_python_returncode()
    raise SystemExit(main() if delegated is None else delegated)
