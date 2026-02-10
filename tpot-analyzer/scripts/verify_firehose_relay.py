#!/usr/bin/env python3
"""Human-friendly verification for firehose relay worker."""
from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.firehose_relay.worker import RelayConfig, run_relay  # noqa: E402


CHECK = "✓"
CROSS = "✗"


class _RelayCaptureServer(HTTPServer):
    def __init__(self, server_address):
        super().__init__(server_address, _RelayCaptureHandler)
        self.captured: List[Dict[str, Any]] = []


class _RelayCaptureHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
        self.server.captured.append(payload)  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _status(ok: bool, message: str) -> str:
    return f"{CHECK if ok else CROSS} {message}"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify firehose relay behavior.")
    parser.add_argument(
        "--dry-run-only",
        action="store_true",
        help="Skip local mock HTTP server and verify dry-run relay only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    lines: list[str] = []
    ok_all = True

    with tempfile.TemporaryDirectory(prefix="tpot_firehose_verify_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        firehose_path = tmp_path / "feed_events.ndjson"
        checkpoint_path = tmp_path / "relay_checkpoint.json"

        firehose_path.write_text(
            "\n".join(
                [
                    json.dumps({"eventType": "feed_impression", "payload": {"engagementType": "spectator", "id": "a"}}),
                    json.dumps({"eventType": "feed_impression", "payload": {"engagementType": "participant", "id": "b"}}),
                    "not-json-line",
                    json.dumps({"eventType": "feed_impression", "payload": {"engagementType": "spectator", "id": "c"}}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        server: Optional[_RelayCaptureServer] = None
        server_thread: Optional[threading.Thread] = None
        endpoint_url = "http://localhost/dry-run"
        transport_mode = "dry-run"

        if not args.dry_run_only:
            try:
                server = _RelayCaptureServer(("127.0.0.1", 0))
                endpoint_url = f"http://127.0.0.1:{server.server_port}/ingest"
                transport_mode = "mock-http"
                server_thread = threading.Thread(target=server.serve_forever, daemon=True)
                server_thread.start()
            except OSError as exc:
                lines.append(_status(False, f"Local mock server unavailable ({exc}); falling back to dry-run"))
                transport_mode = "dry-run"

        checkpoint = run_relay(
            RelayConfig(
                firehose_path=firehose_path,
                checkpoint_path=checkpoint_path,
                endpoint_url=endpoint_url,
                batch_size=10,
                once=True,
                dry_run=(transport_mode == "dry-run"),
                allow_participant=False,
            )
        )

        if server is not None:
            server.shutdown()
            server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=2.0)

        lines.append("Firehose Relay Verification")
        lines.append(f"- mode: {transport_mode}")
        lines.append(f"- firehose_path: {firehose_path}")
        lines.append(f"- checkpoint_path: {checkpoint_path}")
        lines.append("")

        c1 = checkpoint.events_read_total == 3
        ok_all &= c1
        lines.append(_status(c1, f"events_read_total == 3 (actual={checkpoint.events_read_total})"))

        c2 = checkpoint.parse_errors_total == 1
        ok_all &= c2
        lines.append(_status(c2, f"parse_errors_total == 1 (actual={checkpoint.parse_errors_total})"))

        c3 = checkpoint.events_forwarded_total == 2
        ok_all &= c3
        lines.append(_status(c3, f"events_forwarded_total == 2 (actual={checkpoint.events_forwarded_total})"))

        c4 = checkpoint.events_skipped_participant_total == 1
        ok_all &= c4
        lines.append(
            _status(
                c4,
                "events_skipped_participant_total == 1 "
                f"(actual={checkpoint.events_skipped_participant_total})",
            )
        )

        c5 = checkpoint.byte_offset == firehose_path.stat().st_size
        ok_all &= c5
        lines.append(
            _status(
                c5,
                f"checkpoint offset advanced to EOF ({checkpoint.byte_offset}/{firehose_path.stat().st_size})",
            )
        )

        if server is not None:
            captured = len(server.captured)
            c6 = captured == 1 and len((server.captured[0] or {}).get("events") or []) == 2
            ok_all &= c6
            lines.append(_status(c6, f"mock endpoint received 1 batch with 2 events (actual batches={captured})"))

        lines.append("")
        lines.append("Metrics:")
        lines.append(f"- batches_sent_total: {checkpoint.batches_sent_total}")
        lines.append(f"- batches_failed_total: {checkpoint.batches_failed_total}")
        lines.append(f"- retries_total: {checkpoint.retries_total}")
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Run relay continuously: `.venv/bin/python scripts/relay_firehose_to_indra.py --endpoint-url <indra_url>`")
        lines.append("- Inspect checkpoint JSON for lag and forwarding health.")

    print("\n".join(lines))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
