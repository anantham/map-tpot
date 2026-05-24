"""Integration check: silent except blocks in selenium_worker feed the tracker.

These don't drive a real browser; they invoke the static extraction methods
with mock cell objects that raise StaleElementReferenceException, then verify
the global tracker recorded the failure under the expected operation name.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException

from src.shadow.selenium_worker import SeleniumWorker
from src.shadow.silent_failures import tracker as silent_failures


@pytest.fixture(autouse=True)
def _reset_tracker():
    silent_failures.reset()
    yield
    silent_failures.reset()


def _ops_seen() -> set[str]:
    return {row["operation"] for row in silent_failures.snapshot()}


@pytest.mark.unit
def test_extract_handle_tracks_stale_cell():
    cell = MagicMock()
    cell.find_elements.side_effect = StaleElementReferenceException("stale")

    worker = SeleniumWorker.__new__(SeleniumWorker)
    result = worker._extract_handle(cell)

    assert result is None
    assert "extract_handle.stale_cell" in _ops_seen()


@pytest.mark.unit
def test_extract_handle_tracks_stale_link():
    """When the cell's links throw stale, each one increments the counter."""
    cell = MagicMock()
    stale_link = MagicMock()
    stale_link.get_attribute.side_effect = StaleElementReferenceException("stale link")
    cell.find_elements.return_value = [stale_link, stale_link]
    # cell.text fallback returns nothing useful → returns None overall
    cell.text = ""

    worker = SeleniumWorker.__new__(SeleniumWorker)
    result = worker._extract_handle(cell)

    assert result is None
    snap = {row["operation"]: row["count"] for row in silent_failures.snapshot()}
    assert snap.get("extract_handle.stale_link", 0) == 2


@pytest.mark.unit
def test_extract_display_name_tracks_no_username_div():
    """When the structured UserName div isn't present, the fallback failure is tracked."""
    cell = MagicMock()
    cell.find_element.side_effect = NoSuchElementException("no UserName div")
    cell.text = "alice\n@alice\nthis is a bio"

    worker = SeleniumWorker.__new__(SeleniumWorker)
    result = worker._extract_display_name(cell)

    assert result == "alice"  # fallback parsing succeeded
    assert "extract_display_name.no_username_div" in _ops_seen()


@pytest.mark.unit
def test_extract_bio_tracks_no_description_div():
    cell = MagicMock()
    cell.find_elements.side_effect = NoSuchElementException("no UserDescription")
    cell.text = "Display Name\n@alice\nthis is a bio"

    worker = SeleniumWorker.__new__(SeleniumWorker)
    result = worker._extract_bio(cell)

    # Fallback parsing succeeds even when structured selector misses
    assert result == "this is a bio"
    assert "extract_bio.no_description_div" in _ops_seen()


@pytest.mark.unit
def test_extract_website_tracks_stale_anchor():
    cell = MagicMock()
    stale_anchor = MagicMock()
    stale_anchor.get_attribute.side_effect = StaleElementReferenceException("stale anchor")
    cell.find_elements.return_value = [stale_anchor]

    result = SeleniumWorker._extract_website(cell)

    assert result is None
    assert "extract_website.stale_anchor" in _ops_seen()


@pytest.mark.unit
def test_extract_profile_image_tracks_stale_img():
    cell = MagicMock()
    stale_img = MagicMock()
    stale_img.get_attribute.side_effect = StaleElementReferenceException("stale img")
    cell.find_elements.return_value = [stale_img]

    result = SeleniumWorker._extract_profile_image_url(cell)

    assert result is None
    assert "extract_profile_image.stale_img" in _ops_seen()


@pytest.mark.unit
def test_log_summary_called_at_end_of_main_scrape_methods():
    """Regression guard: a refactor that drops silent_failures.log_summary()
    from fetch_list_members or _collect_user_list would silently re-create
    the visibility gap the tracker was added to close.

    Uses ast-based inspection rather than running the methods (which need
    a real selenium driver), so this is a static check against the file's
    parse tree — robust to whitespace/comment changes, brittle only to
    actually removing the call.
    """
    import ast
    from pathlib import Path

    shadow_dir = Path(__file__).resolve().parent.parent / "src" / "shadow"
    source_paths = [
        shadow_dir / "selenium_worker.py",
        *(shadow_dir / "selenium_internals").glob("*.py"),
    ]

    methods_with_summary_call: set[str] = set()
    for source_path in source_paths:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "log_summary"
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "silent_failures"
                    ):
                        methods_with_summary_call.add(node.name)
                        break

    assert "fetch_list_members" in methods_with_summary_call, (
        "fetch_list_members must call silent_failures.log_summary(...) at "
        "the end of its scrape, otherwise per-list silent failure counts "
        "are not visible in logs/api.log."
    )
    assert "_collect_user_list" in methods_with_summary_call, (
        "_collect_user_list must call silent_failures.log_summary(...) at "
        "the end so following/followers/etc. scrapes report their silent "
        "failures per-account in logs."
    )


@pytest.mark.unit
def test_tracker_aggregates_across_extractions():
    """A scrape with many stale elements should produce a coherent summary."""
    cell = MagicMock()
    cell.find_elements.side_effect = StaleElementReferenceException("stale")

    worker = SeleniumWorker.__new__(SeleniumWorker)
    for _ in range(5):
        worker._extract_handle(cell)

    # Reset side_effect then trigger website extractor 3 times
    cell.find_elements.side_effect = None
    stale_anchor = MagicMock()
    stale_anchor.get_attribute.side_effect = StaleElementReferenceException("stale anchor")
    cell.find_elements.return_value = [stale_anchor]
    for _ in range(3):
        SeleniumWorker._extract_website(cell)

    snap = {row["operation"]: row["count"] for row in silent_failures.snapshot()}
    assert snap["extract_handle.stale_cell"] == 5
    assert snap["extract_website.stale_anchor"] == 3
    assert silent_failures.total_count() == 8
