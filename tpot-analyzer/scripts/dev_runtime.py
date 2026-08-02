"""Resolve a reproducible, local-only Research Notes development runtime."""
from __future__ import annotations

import argparse
import os
import shlex
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence
from urllib.parse import quote

UI_ORIGIN = "http://localhost:5184"
API_ORIGIN = "http://localhost:5001"
_ARCHIVE_TABLES = frozenset({"profiles", "tweets"})
_ARCHIVE_COLUMNS = {
    "profiles": frozenset(
        "account_id username display_name bio location website fetched_at".split()
    ),
    "tweets": frozenset(
        "tweet_id account_id full_text created_at favorite_count "
        "retweet_count fetched_at".split()
    ),
}


class DevRuntimeError(RuntimeError):
    """Raised when local development inputs are absent or unsafe to use."""


@dataclass(frozen=True)
class DevRuntime:
    archive_db: Path
    snapshot_dir: Path
    account_tags_db: Path
    ui_origin: str
    api_origin: str
    cors_origins: tuple[str, ...]
    primary_project_root: Optional[Path]


def _discover_common_git_dir(project_root: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    raw = result.stdout.strip()
    return Path(raw).resolve() if raw else None


def _primary_project_root(common_git_dir: Optional[Path]) -> Optional[Path]:
    if common_git_dir is None:
        return None
    repository_root = common_git_dir.resolve().parent
    candidate = repository_root / "tpot-analyzer"
    return candidate if candidate.is_dir() else None


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    encoded = quote(str(path.resolve()), safe="/")
    return sqlite3.connect(f"file:{encoded}?mode=ro", uri=True, timeout=5)


def _archive_problem(path: Path) -> Optional[str]:
    if not path.is_file():
        return "file does not exist"
    if path.stat().st_size == 0:
        return "file is empty"
    try:
        with _sqlite_readonly(path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {str(row[0]) for row in rows}
            missing = sorted(_ARCHIVE_TABLES - tables)
            if missing:
                return f"missing required tables: {', '.join(missing)}"
            for table, required in _ARCHIVE_COLUMNS.items():
                columns = {
                    str(row[1])
                    for row in conn.execute(f"PRAGMA table_info({table})")
                }
                absent = sorted(required - columns)
                if absent:
                    return (
                        f"table {table} is missing columns: {', '.join(absent)}"
                    )
    except sqlite3.DatabaseError as exc:
        return f"not a readable SQLite database ({exc})"
    return None


def _resolve_archive(
    project_root: Path,
    environ: Mapping[str, str],
    primary_root: Optional[Path],
) -> Path:
    explicit = (environ.get("ARCHIVE_DB_PATH") or "").strip()
    if explicit:
        selected = Path(explicit).expanduser().resolve()
        problem = _archive_problem(selected)
        if problem:
            raise DevRuntimeError(
                f"ARCHIVE_DB_PATH '{selected}' is unusable: {problem}"
            )
        return selected

    candidates = [project_root / "data" / "archive_tweets.db"]
    if primary_root is not None:
        candidates.append(primary_root / "data" / "archive_tweets.db")
    checked: list[str] = []
    seen: set[Path] = set()
    for raw_candidate in candidates:
        candidate = raw_candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        problem = _archive_problem(candidate)
        if problem is None:
            return candidate
        checked.append(f"{candidate} ({problem})")
    details = "; ".join(checked) or "no candidates were discoverable"
    raise DevRuntimeError(
        "No usable Research Notes archive was found. "
        f"Checked: {details}. Set ARCHIVE_DB_PATH to a SQLite archive "
        "containing profiles and tweets."
    )


def _resolve_snapshot_dir(
    project_root: Path,
    environ: Mapping[str, str],
) -> Path:
    explicit = (environ.get("SNAPSHOT_DIR") or "").strip()
    selected = (
        Path(explicit).expanduser().resolve()
        if explicit
        else (project_root / "data").resolve()
    )
    if not selected.exists():
        label = "SNAPSHOT_DIR" if explicit else "default snapshot directory"
        raise DevRuntimeError(f"{label} '{selected}' does not exist")
    if not selected.is_dir():
        raise DevRuntimeError(f"SNAPSHOT_DIR '{selected}' is not a directory")
    if not os.access(selected, os.R_OK | os.W_OK | os.X_OK):
        raise DevRuntimeError(
            f"SNAPSHOT_DIR '{selected}' must be readable and writable"
        )
    return selected


def _validate_tag_path(path: Path) -> None:
    if path.exists() and not path.is_file():
        raise DevRuntimeError(f"account tag database '{path}' is not a file")
    if path.exists() and path.stat().st_size:
        try:
            with _sqlite_readonly(path) as conn:
                verdict = conn.execute("PRAGMA quick_check(1)").fetchone()
        except sqlite3.DatabaseError as exc:
            raise DevRuntimeError(
                f"account tag database '{path}' is not valid SQLite: {exc}"
            ) from exc
        if not verdict or verdict[0] != "ok":
            raise DevRuntimeError(
                f"account tag database '{path}' failed SQLite quick_check"
            )
    if path.exists() and not os.access(path, os.R_OK | os.W_OK):
        raise DevRuntimeError(
            f"account tag database '{path}' must be readable and writable"
        )


def _cors_origins(environ: Mapping[str, str]) -> tuple[str, ...]:
    configured = (environ.get("CORS_ORIGINS") or "").split(",")
    ordered = [origin.strip() for origin in configured if origin.strip()]
    ordered.append(UI_ORIGIN)
    return tuple(dict.fromkeys(ordered))


def resolve_dev_runtime(
    project_root: Path,
    *,
    environ: Optional[Mapping[str, str]] = None,
    common_git_dir: Optional[Path] = None,
) -> DevRuntime:
    """Resolve and validate every local path used by Research Notes."""

    root = Path(project_root).expanduser().resolve()
    env = os.environ if environ is None else environ
    common_dir = common_git_dir or _discover_common_git_dir(root)
    primary_root = _primary_project_root(common_dir)
    snapshot_dir = _resolve_snapshot_dir(root, env)
    archive_db = _resolve_archive(root, env, primary_root)
    account_tags_db = (snapshot_dir / "account_tags.db").resolve()
    _validate_tag_path(account_tags_db)
    return DevRuntime(
        archive_db=archive_db,
        snapshot_dir=snapshot_dir,
        account_tags_db=account_tags_db,
        ui_origin=UI_ORIGIN,
        api_origin=API_ORIGIN,
        cors_origins=_cors_origins(env),
        primary_project_root=primary_root,
    )


def render_shell_assignments(runtime: DevRuntime) -> str:
    """Render shell-safe, non-secret assignments consumed by start_dev.sh."""

    values: Sequence[tuple[str, str]] = (
        ("ARCHIVE_DB_PATH", str(runtime.archive_db)),
        ("SNAPSHOT_DIR", str(runtime.snapshot_dir)),
        ("TPOT_DEV_ACCOUNT_TAGS_DB_PATH", str(runtime.account_tags_db)),
        ("TPOT_DEV_UI_ORIGIN", runtime.ui_origin),
        ("TPOT_DEV_API_ORIGIN", runtime.api_origin),
        ("CORS_ORIGINS", ",".join(runtime.cors_origins)),
        ("VITE_API_URL", runtime.api_origin),
        (
            "TPOT_PRIMARY_PROJECT_ROOT",
            str(runtime.primary_project_root or ""),
        ),
    )
    return "\n".join(f"{name}={shlex.quote(value)}" for name, value in values)


def _human_report(runtime: DevRuntime) -> str:
    archive_mib = runtime.archive_db.stat().st_size / (1024 * 1024)
    return "\n".join(
        (
            f"✓ archive (read-only): {runtime.archive_db} ({archive_mib:,.1f} MiB)",
            f"✓ snapshot/state dir: {runtime.snapshot_dir}",
            f"✓ persistent tag DB: {runtime.account_tags_db}",
            f"✓ backend: {runtime.api_origin}",
            f"✓ frontend/CORS: {runtime.ui_origin}",
            "✓ curator token: generated/shared by start_dev.sh; never printed",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve local Research Notes development inputs"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--format", choices=("shell", "human"), default="human")
    args = parser.parse_args()
    try:
        runtime = resolve_dev_runtime(args.project_root)
    except DevRuntimeError as exc:
        parser.exit(2, f"✗ development runtime is not ready: {exc}\n")
    if args.format == "shell":
        print(render_shell_assignments(runtime))
    else:
        print(_human_report(runtime))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
