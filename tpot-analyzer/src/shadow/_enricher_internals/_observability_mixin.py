"""Observability: pre-run summary, phase timings, signal/pause handling."""
from __future__ import annotations

import logging
import signal
import time
from contextlib import contextmanager
from typing import Optional

LOGGER = logging.getLogger("src.shadow.enricher")


class ObservabilityMixin:
    """Logging + timing + signal/pause for the enrichment loop.

    Required state on coordinator:
      self._store, self._current_phase_timings (dict),
      self._pause_requested, self._shutdown_requested, self._original_sigint_handler.
    """

    def _log_pre_run_summary(self, seed):
        logger = logging.getLogger(__name__)
        logger.info(f"--- Pre-run DB status for @{seed.username} ---")

        # Get account info
        account = self._store.get_shadow_account(seed.account_id)
        if account:
            logger.info(f"  Account found: followers={account.followers_count}, following={account.following_count}, fetched_at={account.fetched_at}")
        else:
            logger.info("  Account not found in DB.")

        # Get last scrape metrics
        metrics = self._store.get_last_scrape_metrics(seed.account_id)
        if metrics:
            logger.info(f"  Last scrape: run_at={metrics.run_at}, following_captured={metrics.following_captured}, followers_captured={metrics.followers_captured}")
        else:
            logger.info("  No previous scrape metrics found.")

        # Get edge summary
        edge_summary = self._store.edge_summary_for_seed(seed.account_id)
        logger.info(f"  Edge counts: following={edge_summary['following']}, followers={edge_summary['followers']}")
        logger.info("-------------------------------------------------")

    @contextmanager
    def _time_phase(self, group: str, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            bucket = self._current_phase_timings.setdefault(group, {})
            bucket[name] = bucket.get(name, 0.0) + duration
            LOGGER.debug("[timing] %-15s %-24s %.3fs", group, name, duration)

    def _phase_snapshot(self) -> Optional[dict]:
        if not self._current_phase_timings:
            return None
        return {
            group: {phase: round(duration, 4) for phase, duration in phases.items()}
            for group, phases in self._current_phase_timings.items()
        }

    def _log_phase_summary(self, identifier: str) -> None:
        snapshot = self._phase_snapshot()
        if not snapshot:
            return
        LOGGER.debug("[timing] summary for %s: %s", identifier, snapshot)

    # ------------------------------------------------------------------
    # Pause/Resume Helpers
    # ------------------------------------------------------------------
    def _setup_signal_handler(self) -> None:
        """Setup signal handler for graceful pause on Ctrl+C."""
        def signal_handler(signum, frame):
            if self._pause_requested:
                # Second Ctrl+C - immediate shutdown
                LOGGER.warning("\n⚠️  Second Ctrl+C detected - forcing shutdown...")
                self._shutdown_requested = True
                # Restore original handler and re-raise to trigger immediate exit
                signal.signal(signal.SIGINT, self._original_sigint_handler)
                raise KeyboardInterrupt
            else:
                # First Ctrl+C - request pause after current seed
                LOGGER.warning("\n⏸️  Pause requested (Ctrl+C). Will pause after current seed completes...")
                LOGGER.warning("   Press Ctrl+C again to force immediate shutdown.")
                self._pause_requested = True

        self._original_sigint_handler = signal.signal(signal.SIGINT, signal_handler)

    def _restore_signal_handler(self) -> None:
        """Restore original signal handler."""
        if self._original_sigint_handler:
            signal.signal(signal.SIGINT, self._original_sigint_handler)

    def _handle_pause_menu(self, current_seed_idx: int, total_seeds: int) -> str:
        """Show pause menu and return user choice.

        Returns:
            'resume' - Continue enrichment
            'shutdown' - Exit cleanly
            'skip' - Skip remaining seeds
        """
        print("\n" + "=" * 80)
        print("⏸️  ENRICHMENT PAUSED")
        print("=" * 80)
        print(f"Progress: {current_seed_idx}/{total_seeds} seeds completed")
        print(f"Remaining: {total_seeds - current_seed_idx} seeds")
        print("\nOptions:")
        print("  [r] Resume enrichment")
        print("  [s] Shutdown and save progress")
        print("  [q] Quit (same as shutdown)")
        print("=" * 80)

        while True:
            try:
                response = input("\nYour choice [r/s/q]: ").strip().lower()
                if response in ('r', 'resume'):
                    print("▶️  Resuming enrichment...\n")
                    return 'resume'
                elif response in ('s', 'shutdown', 'q', 'quit'):
                    print("🛑 Shutting down gracefully...\n")
                    return 'shutdown'
                else:
                    print("Invalid choice. Please enter 'r' (resume) or 's' (shutdown).")
            except (KeyboardInterrupt, EOFError):
                # Handle Ctrl+C or Ctrl+D during menu
                print("\n🛑 Shutdown requested during pause menu...\n")
                return 'shutdown'
