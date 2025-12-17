"""Tail TPOT log files with simple filtering.

Usage examples:
  python3 -m scripts.tail_cluster_logs --clusters
  python3 -m scripts.tail_cluster_logs --req 9bed43c6
  python3 -m scripts.tail_cluster_logs --contains "http GET /api/clusters" --no-follow
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass
class WatchedFile:
    name: str
    path: Path
    inode: int | None = None
    offset: int = 0
    handle = None


def _default_log_dir() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    return Path(os.getenv("TPOT_LOG_DIR") or (project_root / "logs"))


def _iter_tail_lines(path: Path, *, max_lines: int) -> Iterator[str]:
    lines: deque[str] = deque(maxlen=max_lines)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                lines.append(line.rstrip("\n"))
    except FileNotFoundError:
        return iter(())

    return iter(lines)


def _prefix(name: str, line: str) -> str:
    return f"[{name}] {line}"


def _match_line(line: str, *, req: str | None, contains: list[str]) -> bool:
    if req:
        req_markers = (f"req={req}", f"reqId={req}", f"\"req_id\": \"{req}\"", f"\"reqId\": \"{req}\"")
        if not any(marker in line for marker in req_markers):
            return False
    return all(token in line for token in contains)


def _open_watcher(w: WatchedFile) -> None:
    w.handle = w.path.open("r", encoding="utf-8", errors="replace")
    stat = w.path.stat()
    w.inode = stat.st_ino
    w.offset = stat.st_size
    w.handle.seek(w.offset)


def _maybe_reopen(w: WatchedFile) -> None:
    try:
        stat = w.path.stat()
    except FileNotFoundError:
        return

    inode = stat.st_ino
    size = stat.st_size
    if w.handle is None:
        _open_watcher(w)
        return

    if w.inode != inode or size < w.offset:
        try:
            w.handle.close()
        except Exception:
            pass
        _open_watcher(w)


def _read_new_lines(w: WatchedFile) -> list[str]:
    if w.handle is None:
        return []
    lines = []
    while True:
        line = w.handle.readline()
        if not line:
            break
        lines.append(line.rstrip("\n"))
    try:
        w.offset = w.handle.tell()
    except Exception:
        pass
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tail TPOT log files with filtering.")
    parser.add_argument("--log-dir", type=Path, default=_default_log_dir(), help="Directory containing log files.")
    parser.add_argument("--tail", type=int, default=200, help="Number of last lines to print before following.")
    parser.add_argument("--follow", dest="follow", action="store_true", help="Follow logs (default).")
    parser.add_argument("--no-follow", dest="follow", action="store_false", help="Print tail and exit.")
    parser.set_defaults(follow=True)
    parser.add_argument("--req", help="Filter by request id (matches 'req=<id>' or JSON fields).")
    parser.add_argument(
        "--contains",
        action="append",
        default=[],
        help="Filter by substring (can be repeated; all must match).",
    )
    parser.add_argument("--clusters", action="store_true", help="Convenience filter for cluster-related lines.")
    parser.add_argument("--api", action="store_true", help="Include api.log.")
    parser.add_argument("--frontend", action="store_true", help="Include frontend.log (POST /api/log).")
    parser.add_argument("--backend", action="store_true", help="Include backend.log (backend stdout/stderr).")
    parser.add_argument("--vite", action="store_true", help="Include vite.log (frontend dev server stdout/stderr).")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    contains = list(args.contains)
    if args.clusters:
        contains.extend(["/api/clusters"])

    selected = args.api or args.frontend or args.backend or args.vite
    watchers = []
    if not selected or args.api:
        watchers.append(WatchedFile("api", args.log_dir / "api.log"))
    if not selected or args.frontend:
        watchers.append(WatchedFile("frontend", args.log_dir / "frontend.log"))
    if args.backend:
        watchers.append(WatchedFile("backend", args.log_dir / "backend.log"))
    if args.vite:
        watchers.append(WatchedFile("vite", args.log_dir / "vite.log"))

    missing = [w.path for w in watchers if not w.path.exists()]
    if missing:
        print("⚠️  Missing log files:")
        for path in missing:
            print(f"   - {path}")
        print("")

    for w in watchers:
        for line in _iter_tail_lines(w.path, max_lines=args.tail):
            if _match_line(line, req=args.req, contains=contains):
                print(_prefix(w.name, line))

    if not args.follow:
        return 0

    for w in watchers:
        try:
            if w.path.exists():
                _open_watcher(w)
        except Exception as exc:
            print(f"⚠️  Failed to watch {w.path}: {exc}", file=sys.stderr)

    try:
        while True:
            did_print = False
            for w in watchers:
                _maybe_reopen(w)
                for line in _read_new_lines(w):
                    if _match_line(line, req=args.req, contains=contains):
                        print(_prefix(w.name, line))
                        did_print = True
            if not did_print:
                time.sleep(0.2)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

