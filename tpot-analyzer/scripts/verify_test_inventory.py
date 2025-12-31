"""Inventory test goodharting signals and modularity risks.

This script is designed for humans to run and paste output into chat.
It reports potential goodhart patterns and oversized files with ✓/✗ lines,
plus counts and sample locations for quick follow-up.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


CHECKMARK = "\u2713"
CROSS = "\u2717"


@dataclass(frozen=True)
class Match:
    path: Path
    line_no: int
    line: str


def status_line(ok: bool, msg: str) -> str:
    return f"{CHECKMARK if ok else CROSS} {msg}"


def read_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for idx, line in enumerate(handle, start=1):
            yield idx, line.rstrip("\n")


def find_files(root: Path, patterns: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(root.rglob(pattern)))
    return files


def scan_patterns(files: Iterable[Path], regexes: Iterable[re.Pattern[str]]) -> list[Match]:
    matches: list[Match] = []
    for path in files:
        for line_no, line in read_lines(path):
            for regex in regexes:
                if regex.search(line):
                    matches.append(Match(path=path, line_no=line_no, line=line.strip()))
                    break
    return matches


def scan_internal_asserts(files: Iterable[Path]) -> list[Match]:
    matches: list[Match] = []
    private_attr = re.compile(r"\._[A-Za-z]")
    assert_line = re.compile(r"^\s*(assert|expect)\b")
    for path in files:
        for line_no, line in read_lines(path):
            if assert_line.search(line) and private_attr.search(line):
                matches.append(Match(path=path, line_no=line_no, line=line.strip()))
    return matches


def oversized_files(files: Iterable[Path], *, max_lines: int) -> list[tuple[Path, int]]:
    results: list[tuple[Path, int]] = []
    for path in files:
        try:
            line_count = sum(1 for _ in read_lines(path))
        except OSError:
            continue
        if line_count > max_lines:
            results.append((path, line_count))
    return sorted(results, key=lambda item: item[1], reverse=True)


def format_samples(matches: list[Match], *, limit: int) -> list[str]:
    lines: list[str] = []
    for match in matches[:limit]:
        lines.append(f"  - {match.path}:{match.line_no} {match.line}")
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory test goodhart patterns + modularity risks.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Project root.")
    parser.add_argument("--sample-limit", type=int, default=6, help="Sample matches per check.")
    parser.add_argument("--max-loc", type=int, default=300, help="Max LOC before flagging a file.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root: Path = args.root
    sample_limit: int = args.sample_limit

    tests_root = root / "tests"
    frontend_root = root / "graph-explorer" / "src"
    backend_root = root / "src"

    python_tests = find_files(tests_root, ["*.py"])
    js_tests = find_files(frontend_root, ["*.test.jsx", "*.test.tsx"])
    src_files = find_files(backend_root, ["*.py"]) + find_files(frontend_root, ["*.jsx", "*.js", "*.tsx", "*.ts"])

    skip_patterns = [
        re.compile(r"\bpytest\.skip\("),
        re.compile(r"@pytest\.mark\.skip\b"),
    ]
    mock_call_patterns = [
        re.compile(r"\.assert_called"),
        re.compile(r"\bassert\b.*\bcalled\b"),
    ]
    js_call_patterns = [
        re.compile(r"\.toHaveBeenCalled"),
        re.compile(r"\.mock\.calls"),
    ]
    reimplementation_patterns = [
        re.compile(r"re-?implement", re.IGNORECASE),
        re.compile(r"replicate", re.IGNORECASE),
        re.compile(r"matching .*implementation", re.IGNORECASE),
        re.compile(r"duplicate logic", re.IGNORECASE),
    ]

    skip_matches = scan_patterns(python_tests, skip_patterns)
    mock_call_matches = scan_patterns(python_tests, mock_call_patterns)
    js_call_matches = scan_patterns(js_tests, js_call_patterns)
    reimpl_matches = scan_patterns(python_tests + js_tests, reimplementation_patterns)
    internal_asserts = scan_internal_asserts(python_tests + js_tests)
    oversized = oversized_files(src_files, max_lines=args.max_loc)

    lines: list[str] = []
    lines.append("TPOT Test Inventory")
    lines.append(f"- root: {root}")
    lines.append(f"- python_tests: {len(python_tests)}")
    lines.append(f"- js_tests: {len(js_tests)}")
    lines.append("")

    ok_skip = len(skip_matches) == 0
    lines.append(status_line(ok_skip, f"Placeholder skips (pytest.skip/@pytest.mark.skip): {len(skip_matches)}"))
    if skip_matches:
        lines.extend(format_samples(skip_matches, limit=sample_limit))

    ok_mock_calls = len(mock_call_matches) == 0
    lines.append(status_line(ok_mock_calls, f"Mock call assertions (python): {len(mock_call_matches)}"))
    if mock_call_matches:
        lines.extend(format_samples(mock_call_matches, limit=sample_limit))

    ok_js_calls = len(js_call_matches) == 0
    lines.append(status_line(ok_js_calls, f"Call-count assertions (js): {len(js_call_matches)}"))
    if js_call_matches:
        lines.extend(format_samples(js_call_matches, limit=sample_limit))

    ok_reimpl = len(reimpl_matches) == 0
    lines.append(status_line(ok_reimpl, f"Reimplementation markers: {len(reimpl_matches)}"))
    if reimpl_matches:
        lines.extend(format_samples(reimpl_matches, limit=sample_limit))

    ok_internal = len(internal_asserts) == 0
    lines.append(status_line(ok_internal, f"Internal-state assertions: {len(internal_asserts)}"))
    if internal_asserts:
        lines.extend(format_samples(internal_asserts, limit=sample_limit))

    ok_oversized = len(oversized) == 0
    lines.append(status_line(ok_oversized, f"Files over {args.max_loc} LOC: {len(oversized)}"))
    if oversized:
        for path, count in oversized[:sample_limit]:
            lines.append(f"  - {path}:{count} lines")

    lines.append("")
    lines.append("Next steps:")
    lines.append("- Replace mock-call assertions with behavioral outcomes (persisted records, response payloads).")
    lines.append("- Remove or relocate reimplementation tests; extract shared utilities for direct testing.")
    lines.append("- Reduce internal-state assertions; prefer public API and payload checks.")
    lines.append("- Decompose oversized files into modules <300 LOC as per AGENTS.md.")
    lines.append("- Re-run after fixes to confirm counts drop toward zero.")

    print("\n".join(lines))

    checks_ok = all([ok_skip, ok_mock_calls, ok_js_calls, ok_reimpl, ok_internal, ok_oversized])
    return 0 if checks_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
