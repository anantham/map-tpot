"""Verify hybrid zoom logging in frontend.log.

This script is designed for humans to run and paste output into chat.

Usage (recommended):
  1) Enable logging in the browser (reload after):
     - Add ?hz_log=1 to the URL, OR
     - Run: localStorage.setItem('hybridZoomLog', '1')
  2) Run: python3 -m scripts.verify_hybrid_zoom_logging --mark
  3) Reproduce the scroll-to-expand behavior in the UI.
  4) Run: python3 -m scripts.verify_hybrid_zoom_logging --since-mark
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any


def status_line(ok: bool, msg: str) -> str:
    return f"{'✓' if ok else '✗'} {msg}"


def _default_log_dir() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    return Path(os.getenv("TPOT_LOG_DIR") or (project_root / "logs"))


def _marker_path(log_dir: Path) -> Path:
    return log_dir / "hybrid_zoom_log_cursor.json"


def _load_marker(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def _write_marker(path: Path, *, file_size: int) -> None:
    payload = {
        "bytes": file_size,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_from_offset(path: Path, offset: int) -> list[str]:
    if offset < 0:
        offset = 0
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line.strip()]


def _tail_lines(path: Path, count: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return [line.rstrip("\n") for line in deque(f, maxlen=count)]


def _parse_entries(lines: list[str]) -> list[dict[str, Any]]:
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _match(entries: list[dict[str, Any]], needle: str) -> list[dict[str, Any]]:
    return [entry for entry in entries if needle in (entry.get("message") or "")]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify hybrid zoom logs in frontend.log.")
    parser.add_argument("--log-dir", type=Path, default=_default_log_dir(), help="Directory containing log files.")
    parser.add_argument("--mark", action="store_true", help="Record the current frontend.log size as a baseline.")
    parser.add_argument("--since-mark", action="store_true", help="Read logs written after the last --mark.")
    parser.add_argument("--tail-lines", type=int, default=400, help="Lines to scan when no marker is available.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    log_dir: Path = args.log_dir
    frontend_log = log_dir / "frontend.log"
    marker_path = _marker_path(log_dir)

    lines: list[str] = []
    lines.append("Hybrid Zoom Logging Verification")
    lines.append(f"- log_dir:  {log_dir}")
    lines.append(f"- log_file: {frontend_log}")
    lines.append("")

    if args.mark:
        if not frontend_log.exists():
            lines.append(status_line(False, f"frontend.log missing ({frontend_log})"))
            lines.append("")
            lines.append("Next steps:")
            lines.append("- Start backend: `cd tpot-analyzer && ./scripts/start_dev.sh`")
            lines.append("- Open the UI and trigger any cluster action to emit logs.")
            print("\n".join(lines))
            return 1
        size = frontend_log.stat().st_size
        _write_marker(marker_path, file_size=size)
        lines.append(status_line(True, f"Marked current log size ({size} bytes)"))
        lines.append(f"- marker: {marker_path}")
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Reproduce scroll-to-expand in the UI.")
        lines.append("- Run: `python3 -m scripts.verify_hybrid_zoom_logging --since-mark`")
        print("\n".join(lines))
        return 0

    if not frontend_log.exists():
        lines.append(status_line(False, f"frontend.log missing ({frontend_log})"))
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Start backend: `cd tpot-analyzer && ./scripts/start_dev.sh`")
        lines.append("- Ensure UI is posting logs to /api/log.")
        print("\n".join(lines))
        return 1

    raw_lines: list[str] = []
    marker = _load_marker(marker_path) if args.since_mark else None
    if marker and isinstance(marker.get("bytes"), int):
        offset = int(marker["bytes"])
        current_size = frontend_log.stat().st_size
        if current_size < offset:
            offset = 0
        raw_lines = _read_from_offset(frontend_log, offset)
        lines.append(status_line(True, f"Loaded logs since marker ({len(raw_lines)} lines)"))
    else:
        raw_lines = _tail_lines(frontend_log, args.tail_lines)
        lines.append(status_line(True, f"Loaded tail of frontend.log ({len(raw_lines)} lines)"))

    entries = _parse_entries(raw_lines)
    lines.append(status_line(bool(entries), f"Parsed JSON entries ({len(entries)})"))

    wheel_entries = _match(entries, "HybridZoom wheel")
    centered_entries = _match(entries, "HybridZoom centered diagnostics")
    expand_ready_entries = _match(entries, "HybridZoom EXPAND-READY")
    expanding_entries = _match(entries, "HybridZoom EXPANDING")
    modifier_entries = _match(entries, "HybridZoom modifier zoom")

    lines.append(status_line(len(wheel_entries) > 0, f"Wheel events logged ({len(wheel_entries)})"))
    lines.append(status_line(len(centered_entries) > 0, f"Centered diagnostics logged ({len(centered_entries)})"))
    lines.append(status_line(len(expand_ready_entries) > 0, f"Expand-ready events logged ({len(expand_ready_entries)})"))
    lines.append(status_line(len(expanding_entries) > 0, f"Expanding events logged ({len(expanding_entries)})"))
    lines.append(status_line(len(modifier_entries) > 0, f"Modifier-zoom events logged ({len(modifier_entries)})"))

    # Summaries
    if wheel_entries:
        last = wheel_entries[-1]
        payload = last.get("payload") or {}
        lines.append("")
        lines.append("Last wheel payload:")
        lines.append(f"- deltaY: {payload.get('deltaY')} (mode={payload.get('deltaMode')})")
        lines.append(f"- ctrlKey: {payload.get('ctrlKey')} metaKey: {payload.get('metaKey')}")
        lines.append(f"- scrollingIn: {payload.get('scrollingIn')} scrollingOut: {payload.get('scrollingOut')}")
        lines.append(f"- scale: {payload.get('scale')} effectiveFont: {payload.get('effectiveFont')}")
        lines.append(f"- zoomMode: {payload.get('zoomMode')} computedMode: {payload.get('computedMode')}")

    if centered_entries:
        last = centered_entries[-1]
        payload = last.get("payload") or {}
        lines.append("")
        lines.append("Last centered diagnostics:")
        lines.append(f"- centeredId: {payload.get('centeredId')} label: {payload.get('label')}")
        lines.append(f"- canExpand: {payload.get('canExpand')} isLeaf: {payload.get('isLeaf')} childCount: {payload.get('childCount')}")
        lines.append(f"- screen: {payload.get('screen')} inViewport: {payload.get('inViewport')}")
        lines.append(f"- distToCenterPx: {payload.get('distToCenterPx')} viewport: {payload.get('viewport')}")

    lines.append("")
    lines.append("Next steps:")
    lines.append("- If no logs appear, enable debug logging with ?hz_log=1 or localStorage.hybridZoomLog=1 and reload.")
    lines.append("- If modifier-zoom events are present, try a mouse wheel (trackpad pinch can set ctrlKey).")
    lines.append("- If centered diagnostics show inViewport=false, pan so the target node is near screen center.")
    lines.append("- If logs still do not appear, run: `python3 -m scripts.verify_api_observability`.")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
