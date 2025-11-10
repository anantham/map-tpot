"""Unit tests for logging utilities.

Tests colored formatters, console filters, and logging setup.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.logging_utils import (
    ColoredFormatter,
    Colors,
    ConsoleFilter,
    setup_enrichment_logging,
)


# ==============================================================================
# Colors Tests
# ==============================================================================

@pytest.mark.unit
def test_colors_constants_defined():
    """Colors class should have all expected color constants."""
    assert hasattr(Colors, "RESET")
    assert hasattr(Colors, "BOLD")
    assert hasattr(Colors, "RED")
    assert hasattr(Colors, "GREEN")
    assert hasattr(Colors, "YELLOW")
    assert hasattr(Colors, "BLUE")
    assert hasattr(Colors, "MAGENTA")
    assert hasattr(Colors, "CYAN")
    assert hasattr(Colors, "WHITE")


@pytest.mark.unit
def test_colors_are_ansi_codes():
    """Color constants should be ANSI escape codes."""
    assert Colors.RESET.startswith("\033[")
    assert Colors.RED.startswith("\033[")
    assert Colors.GREEN.startswith("\033[")


# ==============================================================================
# ColoredFormatter Tests
# ==============================================================================

@pytest.mark.unit
def test_colored_formatter_formats_debug():
    """ColoredFormatter should add color to DEBUG messages."""
    formatter = ColoredFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="Debug message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert Colors.CYAN in formatted
    assert Colors.RESET in formatted
    assert "Debug message" in formatted


@pytest.mark.unit
def test_colored_formatter_formats_info():
    """ColoredFormatter should add color to INFO messages."""
    formatter = ColoredFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Info message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert Colors.GREEN in formatted
    assert Colors.RESET in formatted
    assert "Info message" in formatted


@pytest.mark.unit
def test_colored_formatter_formats_warning():
    """ColoredFormatter should add color to WARNING messages."""
    formatter = ColoredFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Warning message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert Colors.YELLOW in formatted
    assert Colors.RESET in formatted
    assert "Warning message" in formatted


@pytest.mark.unit
def test_colored_formatter_formats_error():
    """ColoredFormatter should add color to ERROR messages."""
    formatter = ColoredFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Error message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert Colors.RED in formatted
    assert Colors.RESET in formatted
    assert "Error message" in formatted


@pytest.mark.unit
def test_colored_formatter_formats_critical():
    """ColoredFormatter should add bold red to CRITICAL messages."""
    formatter = ColoredFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.CRITICAL,
        pathname="",
        lineno=0,
        msg="Critical message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert Colors.BOLD in formatted
    assert Colors.RED in formatted
    assert Colors.RESET in formatted
    assert "Critical message" in formatted


# ==============================================================================
# ConsoleFilter Tests
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
def test_console_filter_allows_selenium_worker_visiting():
    """ConsoleFilter should allow selenium_worker VISITING messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="src.shadow.selenium_worker",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="🔍 VISITING @user → FOLLOWING",
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
def test_console_filter_allows_enricher_seed_tracking():
    """ConsoleFilter should allow enricher SEED tracking messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="src.shadow.enricher",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="🔹 SEED 1/10: @alice",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


@pytest.mark.unit
def test_console_filter_allows_enricher_skipped():
    """ConsoleFilter should allow enricher SKIPPED messages."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="src.shadow.enricher",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="⏭️ SKIPPED @bob (already enriched)",
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


@pytest.mark.unit
def test_console_filter_allows_enrich_shadow_graph_script():
    """ConsoleFilter should allow messages from enrich_shadow_graph script."""
    console_filter = ConsoleFilter()
    record = logging.LogRecord(
        name="scripts.enrich_shadow_graph",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Starting enrichment run",
        args=(),
        exc_info=None,
    )

    assert console_filter.filter(record) is True


# ==============================================================================
# setup_enrichment_logging() Tests
# ==============================================================================

@pytest.mark.unit
def test_setup_enrichment_logging_creates_handlers():
    """setup_enrichment_logging should create console and file handlers."""
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

            setup_enrichment_logging()

            # Should have 2 handlers: console + file
            assert len(root_logger.handlers) == 2


@pytest.mark.unit
def test_setup_enrichment_logging_quiet_mode():
    """setup_enrichment_logging with quiet=True should skip console handler."""
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
def test_setup_enrichment_logging_sets_root_level():
    """setup_enrichment_logging should set root logger to DEBUG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.logging_utils.Path") as mock_path:
            mock_log_dir = MagicMock()
            mock_log_dir.mkdir = MagicMock()
            mock_log_dir.__truediv__ = lambda self, other: Path(tmpdir) / other
            mock_path.return_value = mock_log_dir

            setup_enrichment_logging()

            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG


@pytest.mark.unit
def test_setup_enrichment_logging_creates_log_directory():
    """setup_enrichment_logging should create logs directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / "logs"

        with patch("src.logging_utils.Path") as mock_path:
            mock_path.return_value = log_dir

            setup_enrichment_logging()

            # Directory should be created
            assert log_dir.exists()


@pytest.mark.unit
def test_setup_enrichment_logging_removes_existing_handlers():
    """setup_enrichment_logging should remove existing handlers first."""
    root_logger = logging.getLogger()

    # Add a dummy handler
    dummy_handler = logging.StreamHandler()
    root_logger.addHandler(dummy_handler)
    initial_count = len(root_logger.handlers)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.logging_utils.Path") as mock_path:
            mock_log_dir = MagicMock()
            mock_log_dir.mkdir = MagicMock()
            mock_log_dir.__truediv__ = lambda self, other: Path(tmpdir) / other
            mock_path.return_value = mock_log_dir

            setup_enrichment_logging()

            # Old handlers should be removed
            assert dummy_handler not in root_logger.handlers


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


@pytest.mark.unit
def test_setup_enrichment_logging_custom_levels():
    """setup_enrichment_logging should respect custom log levels."""
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

            setup_enrichment_logging(console_level=logging.ERROR, file_level=logging.INFO)

            # Find console handler
            console_handlers = [
                h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)
            ]

            if console_handlers:
                assert console_handlers[0].level == logging.ERROR


# ==============================================================================
# Integration Tests
# ==============================================================================

@pytest.mark.integration
def test_colored_formatter_with_real_logger():
    """ColoredFormatter should work with real logger."""
    logger = logging.getLogger("test_colored")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add handler with ColoredFormatter
    handler = logging.StreamHandler()
    formatter = ColoredFormatter("%(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Should not raise
    logger.info("Test message")
    logger.warning("Warning message")
    logger.error("Error message")


@pytest.mark.integration
def test_console_filter_with_real_logger():
    """ConsoleFilter should work with real logger."""
    logger = logging.getLogger("test_filter")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add handler with ConsoleFilter
    handler = logging.StreamHandler()
    handler.addFilter(ConsoleFilter())
    logger.addHandler(handler)

    # Should not raise
    logger.info("This should be filtered")
    logger.warning("This should appear")
    logger.error("This should appear")


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
