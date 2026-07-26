"""Git, toolchain, and reporting helpers for the assumption baseline verifier."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Report:
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    metrics: list[str] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str) -> None:
        print(f"{'✓' if ok else '✗'} {name}: {detail}")
        if ok:
            self.passed += 1
        else:
            self.failed += 1

    def warn(self, name: str, detail: str) -> None:
        print(f"⚠ {name}: {detail}")
        self.warnings += 1


def command_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def inspect_toolchain(root: Path, report: Report) -> None:
    expected_python = (root / ".python-version").read_text(encoding="utf-8").strip()
    actual_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    report.check(
        "Python runtime",
        actual_python == expected_python,
        f"running {actual_python}; repository expects {expected_python}",
    )

    expected_node = (root / ".nvmrc").read_text(encoding="utf-8").strip()
    try:
        actual_node = command_output(root, "node", "--version").lstrip("v")
        report.check(
            "Node runtime",
            actual_node.split(".", 1)[0] == expected_node,
            f"running {actual_node}; CI/repository expect major {expected_node}",
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        report.check("Node runtime", False, str(exc))

    for relative in (
        "requirements.txt",
        "graph-explorer/package-lock.json",
        "public-site/package-lock.json",
    ):
        path = root / relative
        report.check("dependency lock", path.is_file(), relative)
        if path.is_file():
            report.metrics.append(f"{relative}_sha256: {sha256(path)[:16]}")


def inspect_git(root: Path, report: Report, require_clean: bool) -> None:
    try:
        commit = command_output(root, "git", "rev-parse", "HEAD")
        branch = command_output(root, "git", "branch", "--show-current") or "(detached)"
        unmerged = command_output(
            root, "git", "diff", "--name-only", "--diff-filter=U"
        )
        status = command_output(root, "git", "status", "--porcelain=v1")
        untracked = command_output(
            root, "git", "ls-files", "--others", "--exclude-standard"
        ).splitlines()
        conflicts = [path for path in untracked if "sync-conflict" in path]
        report.check("Git has no unmerged paths", not unmerged, unmerged or "none")
        report.check(
            "Git has no sync-conflict artifacts",
            not conflicts,
            f"{len(conflicts)} found",
        )
        changed = len(status.splitlines()) if status else 0
        if require_clean:
            report.check("Git worktree clean", changed == 0, f"{changed} changed paths")
        elif changed:
            report.warn("Git worktree", f"{changed} changed paths (allowed)")
        else:
            report.check("Git worktree clean", True, "no changes")
        report.metrics.extend((f"git_branch: {branch}", f"git_commit: {commit}"))
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        report.check("Git metadata", False, str(exc))
