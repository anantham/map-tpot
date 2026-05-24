"""Driver lifecycle + login methods for SeleniumWorker.

Mixin pattern: state lives on the coordinator (SeleniumWorker) — this class
assumes `self._driver`, `self._config`, `self._pause_callback`,
`self._shutdown_callback` are initialized by the coordinator's __init__.
"""
from __future__ import annotations

import pickle
import random
import select
import signal
import sys
import time
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from ._types import LOGGER, _resolve_chrome_binary_from_env


class DriverLifecycleMixin:
    """Browser driver init, cookie login, login-state check, quit."""

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def set_pause_callback(self, callback: Callable[[], bool]) -> None:
        """Set callback to check if pause is requested."""
        self._pause_callback = callback

    def set_shutdown_callback(self, callback: Callable[[], bool]) -> None:
        """Set callback to check if shutdown is requested."""
        self._shutdown_callback = callback

    def _init_driver(self) -> None:
        if self._driver:
            self._driver.quit()
        options = webdriver.ChromeOptions()
        chrome_binary = self._config.chrome_binary or _resolve_chrome_binary_from_env()
        if chrome_binary:
            options.binary_location = str(chrome_binary)
            LOGGER.info("Using Chrome/Chromium binary: %s", chrome_binary)
        if self._config.headless:
            options.add_argument("--headless=new")
        options.add_argument(f"--window-size={self._config.window_size}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # CRITICAL: Temporarily ignore SIGINT when creating driver to prevent chromedriver
        # from receiving the signal when user presses Ctrl+C (which would kill it immediately)
        old_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            self._driver = webdriver.Chrome(options=options)
        finally:
            # Restore original SIGINT handler so Python can catch Ctrl+C
            signal.signal(signal.SIGINT, old_sigint_handler)

        self._driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        # Force page visibility to prevent Twitter from throttling when window loses focus
        self._inject_visibility_override()

    def _inject_visibility_override(self) -> None:
        """Override page visibility APIs to prevent Twitter from detecting when window loses focus.

        This fixes the issue where Twitter stops loading content when the browser tab is not visible,
        resulting in only ~11 accounts being captured instead of the full list.
        """
        if not self._driver:
            return

        visibility_script = """
        // Override document.hidden to always return false (page is "visible")
        Object.defineProperty(document, 'hidden', {
            get: function() { return false; },
            configurable: true
        });

        // Override document.visibilityState to always return 'visible'
        Object.defineProperty(document, 'visibilityState', {
            get: function() { return 'visible'; },
            configurable: true
        });

        // Prevent visibilitychange events from firing
        var originalAddEventListener = document.addEventListener;
        document.addEventListener = function(type, listener, options) {
            if (type === 'visibilitychange') {
                // Silently ignore visibility change listeners
                return;
            }
            return originalAddEventListener.call(this, type, listener, options);
        };

        console.log('[INJECTED] Page visibility override active - infinite scroll will work when unfocused');
        """

        try:
            self._driver.execute_script(visibility_script)
            LOGGER.debug("✓ Injected visibility override to maintain scroll performance when window loses focus")
        except Exception as exc:
            LOGGER.warning("Failed to inject visibility override: %s", exc)

    def _restore_browser_focus(self) -> None:
        """Restore browser focus through simulated mouse movements and clicks.

        This is a defensive measure to wake up the browser when Twitter throttling is detected.
        Performs random mouse movements and clicks to simulate user interaction.
        """
        if not self._driver:
            return

        try:
            LOGGER.info("\U0001f5b1️  Performing focus restoration: mouse movements + clicks...")

            # Get window size for random positioning
            window_size = self._driver.get_window_size()
            width = window_size['width']
            height = window_size['height']

            # Create action chain
            actions = ActionChains(self._driver)

            # Perform several random mouse movements
            for i in range(3):
                x_offset = random.randint(100, width - 100)
                y_offset = random.randint(100, height - 100)
                actions.move_by_offset(x_offset - (width // 2), y_offset - (height // 2))
                actions.pause(random.uniform(0.3, 0.8))

            # Click in a safe area (middle of screen, away from buttons)
            try:
                # Find the main timeline section and click on it
                timeline = self._driver.find_element(By.CSS_SELECTOR, 'section[role="region"]')
                actions.move_to_element(timeline).pause(0.5)
                actions.click().pause(0.5)
            except Exception:
                # Fallback: click on body
                body = self._driver.find_element(By.TAG_NAME, 'body')
                actions.move_to_element(body).click()

            # Right-click to trigger context menu (strong focus signal)
            actions.context_click().pause(0.3)

            # Escape to dismiss context menu
            actions.send_keys('')  # ESC key

            # Execute all actions
            actions.perform()

            # Small delay to let browser process focus events
            time.sleep(1.5)

            LOGGER.info("✓ Focus restoration complete")

        except Exception as exc:
            LOGGER.warning("Failed to restore browser focus: %s", exc)

    def _ensure_driver(self) -> bool:
        if not self._driver:
            self._init_driver()
            if not self._login_with_cookies():
                self.quit()
                return False
        return True

    def _login_with_cookies(self) -> bool:
        assert self._driver is not None
        self._driver.get("https://twitter.com")
        self._apply_delay("post-login-load")
        try:
            with self._config.cookies_path.open("rb") as fh:
                cookies = pickle.load(fh)
        except FileNotFoundError:
            LOGGER.error("Cookie file missing at %s", self._config.cookies_path)
            return False

        for cookie in cookies:
            self._driver.add_cookie(cookie)
            self._apply_delay("add-cookie", short=True)
        self._driver.refresh()
        self._apply_delay("post-refresh")
        if not self._check_logged_in():
            LOGGER.error(
                "❌ SESSION NOT AUTHENTICATED — cookies have expired or are invalid.\n"
                "   The browser shows the 'New to X?' / logged-out screen.\n"
                "   Fix: run  .venv/bin/python3 -m scripts.setup_cookies  to refresh your session,\n"
                "   then retry enrichment."
            )
            return False
        if self._config.require_confirmation:
            prompt = "Cookies loaded. Please log in or verify the session in the browser window, then press Enter to continue..."
            print(prompt)
            user_input = self._wait_for_input(timeout=10.0)
            if user_input is None:
                LOGGER.info("No user input detected after 10 seconds; continuing automatically.")
        return True

    def _check_logged_in(self) -> bool:
        """Return True if the current browser session is authenticated.

        Looks for the account-switcher button that only appears in the
        left sidebar when a user is logged in.  A 'New to X?' / signup
        panel or a visible Log-in button means the session has expired.
        """
        assert self._driver is not None
        try:
            # Logged-in indicator: user avatar / account switcher in left nav
            logged_in = bool(
                self._driver.find_elements(
                    By.CSS_SELECTOR, '[data-testid="SideNav_AccountSwitcher_Button"]'
                )
            )
            # Belt-and-suspenders: also check for the logged-out login button
            login_prompt = bool(
                self._driver.find_elements(
                    By.CSS_SELECTOR, '[data-testid="loginButton"], a[href="/login"]'
                )
            )
            if login_prompt and not logged_in:
                return False
            return logged_in
        except Exception as exc:
            LOGGER.warning("Could not determine login state: %s", exc)
            return True  # assume logged in rather than abort on transient DOM errors

    @staticmethod
    def _wait_for_input(timeout: float) -> Optional[str]:
        """Wait for user input up to timeout seconds; return None on timeout."""
        if timeout <= 0:
            try:
                return input()
            except EOFError:
                return None

        # Use selectors for portability without blocking main thread.
        inputs, _, _ = select.select([sys.stdin], [], [], timeout)
        if inputs:
            try:
                return sys.stdin.readline().rstrip("\n")
            except EOFError:
                return None
        return None

    def quit(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None
        self._profile_overviews.clear()
