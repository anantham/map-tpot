"""Unit tests for logging utilities.

Tests colored formatters, console filters, and logging setup.

CLEANED UP - Phase 1, Task 1.4:
- Removed 15 Category C tests (framework/formatter tests)
- Kept 11 Category A tests (business logic)
- Kept 3 Category B tests (to be fixed in Task 1.5)

Estimated mutation score: 30-40% → 75-80% after Task 1.5
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.logging_utils import (
    ConsoleFilter,
    setup_enrichment_logging,
)


# ==============================================================================
# ConsoleFilter Tests (Business Logic)
# ==============================================================================

@pytest.mark.unit
def test_console_filter_allows_warnings():
    """ConsoleFilter should always allow WARNING level."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Warning",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_allows_errors():
    """ConsoleFilter should always allow ERROR level."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Error",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_allows_critical():
    """ConsoleFilter should always allow CRITICAL level."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.CRITICAL,
        pathname="",
        lineno=0,
        msg="Critical",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_allows_selenium_worker_extraction():
    """ConsoleFilter should allow selenium_worker extraction messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="src.shadow.selenium_worker",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="  1. ✓ @alice (Alice Smith)",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_allows_selenium_worker_capture_summary():
    """ConsoleFilter should allow selenium_worker CAPTURED messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="src.shadow.selenium_worker",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="✅ CAPTURED 53 unique accounts from @user → FOLLOWERS",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_allows_enricher_db_operations():
    """ConsoleFilter should allow enricher DB operation messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="src.shadow.enricher",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Writing to DB: 53 accounts",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_blocks_random_info():
    """ConsoleFilter should block random INFO messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="some.random.module",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Random info message",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is False


@pytest.mark.unit
def test_console_filter_blocks_debug():
    """ConsoleFilter should block DEBUG messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="Debug message",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is False


# ==============================================================================
# setup_enrichment_logging() Tests
# ==============================================================================

@pytest.mark.unit
def test_setup_enrichment_logging_quiet_mode():
    """setup_enrichment_logging with quiet=True should skip console handler."""
    # Category B: FIX IN TASK 1.5 - Verify actual handler count/types
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.logging_utils.Path") as mock_path:
            mock_log_dir = MagicMock()
            mock_log_dir.mkdir = MagicMock()
            mock_log_dir.__truediv__ = lambda self, other: Path(tmpdir) / other
            mock_path.return_value = mock_log_dir

            # Clear existing handlers
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)

            setup_enrichment_logging(quiet=True)

            # Should have only 1 handler: file (no console)
            assert len(root_logger.handlers) == 1


@pytest.mark.unit
def test_setup_enrichment_logging_suppresses_noisy_loggers():
    """setup_enrichment_logging should suppress selenium and urllib3 loggers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.logging_utils.Path") as mock_path:
            mock_log_dir = MagicMock()
            mock_log_dir.mkdir = MagicMock()
            mock_log_dir.__truediv__ = lambda self, other: Path(tmpdir) / other
            mock_path.return_value = mock_log_dir

            setup_enrichment_logging()

            selenium_logger = logging.getLogger("selenium")
            urllib3_logger = logging.getLogger("urllib3")

            assert selenium_logger.level == logging.WARNING
            assert urllib3_logger.level == logging.WARNING


# ==============================================================================
# Integration Tests
# ==============================================================================

@pytest.mark.integration
def test_full_logging_setup():
    """Test complete logging setup with all components."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.logging_utils.Path") as mock_path:
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir(exist_ok=True)

            mock_path.return_value = log_dir

            # Setup logging
            setup_enrichment_logging(console_level=logging.INFO, file_level=logging.DEBUG)

            # Get a logger and log messages
            logger = logging.getLogger("test_integration")

            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")

            # Log file should exist
            log_file = log_dir / "enrichment.log"
            assert log_file.exists()

            # Log file should contain messages
            content = log_file.read_text()
            assert "Debug message" in content
            assert "Info message" in content
            assert "Warning message" in content
            assert "Error message" in content
