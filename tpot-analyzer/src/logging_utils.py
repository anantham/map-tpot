
"""Colored, filtered console logging for enrichment scripts.""" 
import logging
import logging.handlers
import re
from pathlib import Path

class Colors:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

class ColoredFormatter(logging.Formatter):
    """A logging formatter that adds colors to the output."""

    LOG_LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD + Colors.RED,
    }

    def format(self, record):
        color = self.LOG_LEVEL_COLORS.get(record.levelno)
        message = super().format(record)
        if color:
            # Color the whole line
            return color + message + Colors.RESET
        return message

class ConsoleFilter(logging.Filter):
    """A logging filter that allows only specific messages to the console."""

    def filter(self, record):
        # Always allow warnings and above
        if record.levelno >= logging.WARNING:
            return True

        # Allow specific INFO messages
        if record.levelno == logging.INFO:
            if record.name == 'src.shadow.selenium_worker':
                msg = record.getMessage()
                # Allow numbered extraction logs (e.g., "  1. ✓ @handle...")
                # Allow capture summaries (e.g., "✅ CAPTURED 53 unique accounts...")
                # Allow section headers (e.g., "🔍 VISITING @user → FOLLOWING")
                # Allow separator lines (e.g., "════════")
                if any(pattern in msg for pattern in [
                    "✓ @",           # Numbered extraction logs
                    "CAPTURED",      # Summary logs
                    "VISITING",      # Section headers
                    "===",           # Separator lines
                    "Extracted:",    # Legacy format (if any)
                    "Already captured"  # Legacy format (if any)
                ]):
                    return True
            
            if record.name == 'src.shadow.enricher':
                msg = record.getMessage()
                # Allow DB operations, seed tracking, skip messages, and summaries
                if any(pattern in msg for pattern in [
                    "Writing to DB",      # DB operations
                    "DB write complete",  # DB operations
                    "🔹 SEED",            # Seed counter
                    "⏭️",                 # Skip messages
                    "SKIPPED",            # Skip messages
                    "COMPLETE",           # Completion summaries
                    "━",                  # Separator lines
                    "═",                  # Separator lines
                    "Starting enrichment" # Run start
                ]):
                    return True
            
            # Allow messages from the main script runner
            if 'enrich_shadow_graph' in record.name:
                return True

        return False

def setup_enrichment_logging(console_level=logging.INFO, file_level=logging.DEBUG, quiet=False):
    """
    Set up logging for enrichment scripts with a colored, filtered console
    handler and a verbose file handler.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (colored and filtered)
    if not quiet:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        
        console_formatter = ColoredFormatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(ConsoleFilter())
        root_logger.addHandler(console_handler)

    # File handler (verbose)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "enrichment.log"
    
    # Use RotatingFileHandler from logging.handlers
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(file_level)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Colored and filtered logging initialized.")
