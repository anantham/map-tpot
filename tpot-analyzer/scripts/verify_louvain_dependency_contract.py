#!/usr/bin/env python3
"""Verify Louvain dependency contract for expansion strategy."""
from __future__ import annotations

import platform
import re
import sys
from pathlib import Path

import networkx as nx


def _print_result(name: str, passed: bool, detail: str) -> bool:
    status = "✓" if passed else "✗"
    print(f"{status} {name}: {detail}")
    return passed


def _requirements_pin(requirements_path: Path) -> tuple[bool, str]:
    text = requirements_path.read_text(encoding="utf-8")
    match = re.search(r"^python-louvain==([^\s]+)\s*$", text, re.MULTILINE)
    if not match:
        return False, "python-louvain pin missing"
    return True, f"python-louvain=={match.group(1)}"


def _import_and_execute_louvain() -> tuple[bool, str]:
    try:
        from community import community_louvain  # type: ignore
    except Exception as exc:  # pragma: no cover - explicit diagnostic path
        return False, f"import failed: {exc}"

    graph = nx.Graph()
    graph.add_edges_from(
        [
            ("a1", "a2"),
            ("a2", "a3"),
            ("b1", "b2"),
            ("b2", "b3"),
            ("a1", "b1"),  # sparse bridge between dense groups
        ]
    )
    try:
        partition = community_louvain.best_partition(graph, random_state=42)
    except Exception as exc:  # pragma: no cover - explicit diagnostic path
        return False, f"best_partition failed: {exc}"

    if len(partition) != graph.number_of_nodes():
        return False, f"partition size mismatch nodes={graph.number_of_nodes()} got={len(partition)}"
    return True, f"partitioned {len(partition)} nodes into {len(set(partition.values()))} groups"


def main() -> int:
    print("Louvain Dependency Contract Verification")
    print("=" * 40)
    print(f"- interpreter: {sys.executable}")
    print(f"- python: {platform.python_version()}")

    checks_passed = 0
    total_checks = 0

    req_path = Path(__file__).resolve().parent.parent / "requirements.txt"

    total_checks += 1
    pin_ok, pin_detail = _requirements_pin(req_path)
    if _print_result("requirements-pin", pin_ok, pin_detail):
        checks_passed += 1

    total_checks += 1
    import_ok, import_detail = _import_and_execute_louvain()
    if _print_result("import-and-execute", import_ok, import_detail):
        checks_passed += 1

    print("\nMetrics")
    print(f"- checks_passed: {checks_passed}/{total_checks}")

    if checks_passed == total_checks:
        print("\nNext steps: run `.venv/bin/python -m pytest tests/test_expansion_strategy.py -q`.")
        return 0

    print("\nNext steps: install dependencies via `.venv/bin/python -m pip install -r requirements.txt` and rerun this script.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
