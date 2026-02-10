"""Append-only firehose writer for extension feed events."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedFirehoseWriter:
    """Write normalized feed events to an append-only NDJSON stream."""

    def __init__(self, default_path: Path) -> None:
        self.default_path = default_path

    def _resolve_path(self, override_path: Optional[str]) -> Path:
        if override_path and str(override_path).strip():
            return Path(str(override_path)).expanduser().resolve()
        return self.default_path

    def append_events(
        self,
        *,
        workspace_id: str,
        ego: str,
        events: Iterable[Dict[str, Any]],
        override_path: Optional[str] = None,
        source: str = "extension.feed_events",
    ) -> Dict[str, Any]:
        path = self._resolve_path(override_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                envelope = {
                    "eventType": "feed_impression",
                    "source": source,
                    "workspaceId": workspace_id,
                    "ego": ego,
                    "capturedAt": _utc_now_iso(),
                    "payload": event,
                }
                handle.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                written += 1

        return {
            "enabled": True,
            "path": str(path),
            "written": written,
        }
