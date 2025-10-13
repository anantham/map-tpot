"""Verify follower/following counters can be recovered from saved snapshots."""
from __future__ import annotations

import argparse
import sys
import warnings
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from src.shadow.selenium_worker import SeleniumWorker  # noqa: E402


@dataclass
class AnchorRecord:
    href: str
    text: str
    aria_label: str

    @property
    def path(self) -> str:
        return SeleniumWorker._normalize_href_path(self.href)


class AnchorCollector(HTMLParser):
    """Collect anchor tags for downstream filtering."""

    def __init__(self) -> None:
        super().__init__()
        self._anchor_stack: List[AnchorRecord] = []
        self.anchors: List[AnchorRecord] = []

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return

        attr_map: Dict[str, Optional[str]] = {name: value for name, value in attrs}
        record = AnchorRecord(
            href=attr_map.get("href") or "",
            text="",
            aria_label=attr_map.get("aria-label") or "",
        )
        self._anchor_stack.append(record)
        self.anchors.append(record)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_stack:
            self._anchor_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._anchor_stack:
            self._anchor_stack[-1].text += data


def _extract_handle_candidates(records: Iterable[AnchorRecord]) -> List[str]:
    handles: List[str] = []
    for record in records:
        segments = [segment for segment in record.path.split("/") if segment]
        if segments:
            handles.append(segments[0])
    return handles


def _resolve_counter(
    counters: Sequence[AnchorRecord],
    *,
    list_type: str,
    handles: Iterable[str],
) -> Optional[Tuple[int, AnchorRecord, int]]:
    target_label = "followers" if list_type == "followers" else "following"
    prefixes = {f"/{handle.strip('/')}".lower() for handle in handles if handle}

    candidates: List[Tuple[int, AnchorRecord, int]] = []

    for counter in counters:
        label_text = (counter.text or counter.aria_label or "").lower()
        path_lower = counter.path.lower()

        if target_label not in label_text and target_label not in path_lower:
            continue

        if list_type == "followers" and "follow" not in path_lower:
            continue
        if list_type == "following" and "following" not in path_lower:
            continue

        value = _parse_textual_count(counter)
        if value is None:
            continue

        priority = SeleniumWorker._counter_priority(path_lower, target_label)
        if prefixes and not any(path_lower.startswith(prefix) for prefix in prefixes):
            priority += 10

        candidates.append((priority, counter, value))

    if not candidates:
        return None

    return min(candidates, key=lambda item: (item[0], -item[2]))


def _parse_textual_count(counter: AnchorRecord) -> Optional[int]:
    for candidate in (counter.text, counter.aria_label):
        value = SeleniumWorker._parse_compact_count(candidate)
        if value is not None:
            return value
    return None


def _guess_username(path: Path) -> Optional[str]:
    stem_parts = path.stem.split("_")
    if len(stem_parts) >= 2 and stem_parts[1]:
        return stem_parts[1]
    return None


def verify_snapshot(path: Path) -> Dict[str, object]:
    html = path.read_text(encoding="utf-8", errors="replace")
    parser = AnchorCollector()
    parser.feed(html)

    handles = set(_extract_handle_candidates(parser.anchors))
    guessed = _guess_username(path)
    if guessed:
        handles.add(guessed)

    followers_result = _resolve_counter(
        parser.anchors,
        list_type="followers",
        handles=handles,
    )
    following_result = _resolve_counter(
        parser.anchors,
        list_type="following",
        handles=handles,
    )

    return {
        "file": path,
        "counters_scanned": len(parser.anchors),
        "handles": sorted(handles),
        "followers": followers_result,
        "following": following_result,
    }


def format_result(name: str, result: Optional[Tuple[int, AnchorRecord, int]]) -> str:
    if result is None:
        return f"✗ {name}: missing"

    priority, counter, value = result
    return (
        f"✓ {name}: {value:,} (href={counter.path or counter.href or 'n/a'}, "
        f"priority={priority})"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+", type=Path, help="HTML snapshot paths to inspect")
    args = parser.parse_args(argv)

    any_missing = False

    for snapshot in args.snapshots:
        report = verify_snapshot(snapshot)
        print(f"\nFile: {snapshot}")
        print(f"Handles observed: {', '.join(report['handles']) or 'none'}")
        print(format_result("followers", report["followers"]))
        print(format_result("following", report["following"]))
        print(f"Counters scanned: {report['counters_scanned']}")

        missing = report["followers"] is None or report["following"] is None
        any_missing = any_missing or missing
        if missing:
            print(
                "Next steps: inspect the snapshot in a browser, confirm counters render, and rerun the "
                "selenium enrichment after collecting fresh cookies."
            )
        else:
            print(
                "Next steps: rerun the selenium enrichment for these handles to persist the recovered "
                "counters, then archive this verification output in the worklog."
            )

    return 1 if any_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
