"""Headless Selenium helper for extracting follower/following handles."""
from __future__ import annotations

import json
import logging
import pickle
import random
import re
import select
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import MaxRetryError, NewConnectionError


LOGGER = logging.getLogger(__name__)


def _shorten_text(value: Optional[str], limit: int) -> str:
    """Return a trimmed, single-line representation for logging."""

    if value is None:
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    if len(text) <= limit:
        return text

    return text[: max(0, limit - 3)] + "..."


@dataclass(frozen=True)
class SeleniumConfig:
    cookies_path: Path
    headless: bool = False
    scroll_delay_min: float = 5.0
    scroll_delay_max: float = 40.0
    max_no_change_scrolls: int = 6
    window_size: str = "1080,1280"
    action_delay_min: float = 5.0
    action_delay_max: float = 40.0
    chrome_binary: Optional[Path] = None
    require_confirmation: bool = True
    retry_delays: List[float] = field(default_factory=lambda: [5.0, 15.0, 60.0])


@dataclass
class CapturedUser:
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    website: Optional[str] = None
    profile_image_url: Optional[str] = None
    list_types: Set[str] = field(default_factory=set)


@dataclass
class UserListCapture:
    list_type: str
    entries: List[CapturedUser]
    claimed_total: Optional[int]
    page_url: str
    profile_overview: Optional["ProfileOverview"] = None
    list_overview: Optional["ListOverview"] = None

@dataclass
class ListOverview:
    list_id: str
    name: Optional[str]
    description: Optional[str]
    owner_username: Optional[str]
    owner_display_name: Optional[str]
    owner_profile_url: Optional[str]
    members_total: Optional[int]
    followers_total: Optional[int]

@dataclass
class ProfileOverview:
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    location: Optional[str]
    website: Optional[str]
    followers_total: Optional[int]
    following_total: Optional[int]
    joined_date: Optional[str] = None
    profile_image_url: Optional[str] = None


class SeleniumWorker:
    """Minimal Selenium-based scroller for Twitter lists."""

    def __init__(self, config: SeleniumConfig) -> None:
        self._config = config
        self._driver: webdriver.Chrome | None = None
        self._profile_overviews: Dict[str, ProfileOverview] = {}
        self._snapshot_dir = Path("logs")
        self._snapshot_dir.mkdir(exist_ok=True)
        self._pause_callback: Optional[Callable[[], bool]] = None
        self._shutdown_callback: Optional[Callable[[], bool]] = None


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
        if self._config.chrome_binary:
            options.binary_location = str(self._config.chrome_binary)
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
            LOGGER.info("🖱️  Performing focus restoration: mouse movements + clicks...")

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
            actions.send_keys('\ue00c')  # ESC key

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
        if self._config.require_confirmation:
            prompt = "Cookies loaded. Please log in or verify the session in the browser window, then press Enter to continue..."
            print(prompt)
            user_input = self._wait_for_input(timeout=10.0)
            if user_input is None:
                LOGGER.info("No user input detected after 10 seconds; continuing automatically.")
        return True

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

    # ------------------------------------------------------------------
    # Scraping primitives
    # ------------------------------------------------------------------
    def fetch_following(self, username: str) -> UserListCapture:
        return self._collect_user_list(username=username, list_type="following")

    def fetch_followers(self, username: str) -> UserListCapture:
        return self._collect_user_list(username=username, list_type="followers")

    def fetch_followers_you_follow(self, username: str) -> UserListCapture:
        return self._collect_user_list(username=username, list_type="followers_you_follow")

    def fetch_verified_followers(self, username: str) -> UserListCapture:
        return self._collect_user_list(username=username, list_type="verified_followers")

    def fetch_list_members(self, list_id: str) -> UserListCapture:
        """Fetch members of a Twitter list by scrolling the members page.

        Args:
            list_id: Twitter list ID (numeric string)

        Returns:
            UserListCapture with list_overview containing metadata
        """
        if not self._ensure_driver():
            return UserListCapture(
                list_type="list_members",
                entries=[],
                claimed_total=None,
                page_url=f"https://twitter.com/i/lists/{list_id}/members",
                profile_overview=None,
                list_overview=None,
            )

        list_page_url = f"https://twitter.com/i/lists/{list_id}/members"
        list_type = "list_members"

        LOGGER.info("")
        LOGGER.info("="*80)
        LOGGER.info("🔍 VISITING LIST → MEMBERS (ID: %s)", list_id)
        LOGGER.info("="*80)

        try:
            self._driver.get(list_page_url)
        except Exception as exc:
            LOGGER.error("Failed to navigate to list %s: %s", list_id, exc)
            return UserListCapture(
                list_type=list_type,
                entries=[],
                claimed_total=None,
                page_url=list_page_url,
                profile_overview=None,
                list_overview=None,
            )

        self._apply_delay("list-page-load")

        # Wait for the page to load - try to find either members or error state
        try:
            WebDriverWait(self._driver, 30).until(
                lambda d: (
                    d.find_elements(By.CSS_SELECTOR, 'section[role="region"]')
                    or d.find_elements(By.CSS_SELECTOR, '[data-testid="emptyState"]')
                )
            )
        except TimeoutException:
            LOGGER.error("Timeout waiting for list page to load for list %s", list_id)
            self._save_page_snapshot(f"list_{list_id}", "load-timeout")
            return UserListCapture(
                list_type=list_type,
                entries=[],
                claimed_total=None,
                page_url=list_page_url,
                profile_overview=None,
                list_overview=None,
            )

        self._apply_delay("list-members-viewport-ready")

        # Switch to members tab (may already be there, but ensure it)
        self._switch_to_list_tab("members")

        # Extract list overview metadata
        list_overview = self._extract_list_overview(list_id)
        target_member_total = list_overview.members_total if list_overview else None

        # Wait for actual members to load in the main timeline (not just sidebar)
        LOGGER.info("⏳ Waiting for list members to load...")
        members_loaded = False
        for wait_attempt in range(10):
            try:
                # Check for UserCells that are NOT in the sidebar
                main_timeline_cells = self._driver.execute_script("""
                    const allCells = Array.from(document.querySelectorAll('[data-testid="UserCell"]'));
                    const mainCells = allCells.filter(cell => {
                        return cell.closest('aside[aria-label]') === null;
                    });
                    return mainCells.length;
                """)

                if main_timeline_cells > 0:
                    LOGGER.info("✅ Found %d members in main timeline", main_timeline_cells)
                    members_loaded = True
                    break
                else:
                    LOGGER.debug("Waiting for members... (attempt %d/10, sidebar cells only)", wait_attempt + 1)
                    time.sleep(2)
            except Exception as exc:
                LOGGER.debug("Error checking for members: %s", exc)
                time.sleep(2)

        if not members_loaded:
            LOGGER.warning("⚠️  Timeout waiting for list members to load - only sidebar content found")
            self._save_page_snapshot(f"list_{list_id}", "members-load-timeout")

        # Validate that the timeline actually loaded with content
        try:
            timeline_section = self._driver.find_element(By.CSS_SELECTOR, 'section[role="region"]')
            initial_cells = timeline_section.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')

            if len(initial_cells) == 0:
                empty_state_elements = self._driver.find_elements(By.CSS_SELECTOR, '[data-testid="emptyState"]')
                if empty_state_elements:
                    LOGGER.warning("⚠️  Timeline shows empty state for list %s - likely has 0 members", list_id)
                else:
                    LOGGER.warning("⚠️  No UserCells found in main timeline for list %s (after initial load)", list_id)
                    self._save_page_snapshot(f"list_{list_id}", "empty-timeline")
        except Exception as exc:
            LOGGER.warning("Could not validate timeline state for list %s: %s", list_id, exc)

        discovered: Dict[str, CapturedUser] = {}
        stagnant_scrolls = 0
        scroll_round = 0
        extraction_counter = 0

        # Find the scrollable container for the list members
        # Twitter shows list members in the main timeline section
        container_selector_used = None
        scroll_container = None

        candidate_selectors = [
            'div[aria-label="Timeline: List members"]',
            'div[aria-label^="Timeline: List members"]',
            'section[role="region"] div[aria-label^="Timeline: List members"]',
            'div[data-testid="primaryColumn"] section[role="region"][aria-label*="List members"]',
            'section[role="region"][aria-label*="List members"]',
            'div[data-testid="primaryColumn"] section[role="region"] div[data-testid="UserCell"]',
            'div[data-testid="primaryColumn"] section[role="region"]',
            'section[role="region"]',
        ]

        for selector in candidate_selectors:
            try:
                element = self._driver.find_element(By.CSS_SELECTOR, selector)
                if selector.endswith('div[data-testid="UserCell"]'):
                    element = element.find_element(By.XPATH, "./ancestor::section[@role='region']")
                scroll_container = element
                container_selector_used = selector
                LOGGER.debug("[list_members] using scroll container selector: %s", selector)
                break
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        if scroll_container is None:
            try:
                scroll_container = self._driver.find_element(By.CSS_SELECTOR, 'div[aria-label^="Timeline: List members"]')
                container_selector_used = 'div[aria-label^="Timeline: List members"] (fallback)'
                LOGGER.debug("[list_members] fallback to timeline div selector")
            except NoSuchElementException:
                scroll_container = None

        if scroll_container is None:
            try:
                scroll_container = self._driver.find_element(By.CSS_SELECTOR, 'div[data-testid="primaryColumn"]')
                container_selector_used = 'div[data-testid="primaryColumn"]'
                LOGGER.debug("[list_members] fallback to primaryColumn container")
            except NoSuchElementException:
                scroll_container = timeline_section
                container_selector_used = 'section[role="region"]'
                LOGGER.debug("[list_members] defaulting to section[role=\"region\"] scroll container")

        # Move mouse to container to ensure focus
        try:
            ActionChains(self._driver).move_to_element(scroll_container).perform()
        except Exception as exc:
            LOGGER.debug("[list_members] unable to move pointer to scroll container: %s", exc)

        LOGGER.info("📝 Starting scroll and extraction...")

        while stagnant_scrolls < self._config.max_no_change_scrolls:
            # Check for pause/shutdown
            if self._pause_callback and self._pause_callback():
                LOGGER.info("⏸️  Pause requested - stopping list member collection...")
                break
            if self._shutdown_callback and self._shutdown_callback():
                LOGGER.warning("🛑 Shutdown requested - stopping list member collection immediately...")
                raise KeyboardInterrupt("Shutdown requested")

            scroll_round += 1
            starting_seen = len(discovered)

            # Extract users from current viewport
            try:
                timeline_section = self._driver.find_element(By.CSS_SELECTOR, 'section[role="region"]')
                user_cells = timeline_section.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
            except Exception as exc:
                LOGGER.warning("[list_members] Could not find timeline section on scroll %s: %s", scroll_round, exc)
                user_cells = []

            for cell in user_cells:
                handle = self._extract_handle(cell)
                if not handle:
                    continue
                display_name = self._extract_display_name(cell) or handle
                bio = self._extract_bio(cell)
                profile_url = f"https://x.com/{handle}"
                website = self._extract_website(cell)
                profile_image_url = self._extract_profile_image_url(cell)

                if handle not in discovered:
                    extraction_counter += 1
                    LOGGER.info(
                        "    %d. ✓ @%s (%s) - \"%s\"",
                        extraction_counter,
                        handle,
                        display_name,
                        (bio or "no bio")[:70],
                    )

                captured = CapturedUser(
                    username=handle,
                    display_name=display_name,
                    bio=bio,
                    profile_url=profile_url,
                    website=website,
                    profile_image_url=profile_image_url,
                    list_types={list_type},
                )
                discovered[handle] = captured

            # Scroll the container (not the window!)
            try:
                if scroll_container:
                    self._driver.execute_script("arguments[0].scrollBy(0, 1200);", scroll_container)
                    LOGGER.debug("[list_members] scrolled container (%s) by 1200px", container_selector_used)
                else:
                    # Fallback to window scroll if container not found
                    self._driver.execute_script("window.scrollBy(0, 1200);")
                    LOGGER.debug("[list_members] scrolled window by 1200px (fallback)")
            except (ConnectionRefusedError, MaxRetryError, NewConnectionError) as exc:
                LOGGER.warning("Driver connection lost during scroll (likely pause/shutdown): %s", exc)
                raise KeyboardInterrupt("Driver connection lost during scroll") from exc

            time.sleep(random.uniform(self._config.scroll_delay_min, self._config.scroll_delay_max))

            new_seen = len(discovered)
            if new_seen == starting_seen:
                stagnant_scrolls += 1

                # Try alternative scroll methods
                try:
                    if scroll_container:
                        self._driver.execute_script("arguments[0].scrollBy(0, 800);", scroll_container)
                    else:
                        self._driver.execute_script("window.scrollBy(0, 800);")
                except Exception:
                    try:
                        # PAGE_DOWN key should work regardless since focus is on the modal
                        ActionChains(self._driver).send_keys(Keys.PAGE_DOWN).perform()
                    except Exception:
                        pass

                # Check if we're at bottom
                at_bottom = False
                try:
                    if scroll_container:
                        at_bottom = self._driver.execute_script(
                            "return Math.ceil(arguments[0].scrollTop + arguments[0].clientHeight) >= arguments[0].scrollHeight;",
                            scroll_container
                        )
                    else:
                        at_bottom = self._driver.execute_script(
                            "return Math.ceil(window.scrollY + window.innerHeight) >= document.documentElement.scrollHeight;"
                        )
                except Exception:
                    at_bottom = False

                LOGGER.debug(
                    "[list_members] scroll %s yielded no new members (%s/%s)%s",
                    scroll_round,
                    stagnant_scrolls,
                    self._config.max_no_change_scrolls,
                    " — reached end" if at_bottom else "",
                )
            else:
                stagnant_scrolls = 0

        captured_entries = list(discovered.values())

        LOGGER.info("="*80)
        LOGGER.info("✅ CAPTURED %d unique accounts from LIST MEMBERS (ID: %s)", len(captured_entries), list_id)
        LOGGER.info("="*80)

        if len(captured_entries) == 0:
            LOGGER.warning("[list_members] No members captured for list %s; saving snapshot for debugging", list_id)
            self._save_page_snapshot(f"list_{list_id}", "no-members-captured")

        return UserListCapture(
            list_type=list_type,
            entries=captured_entries,
            claimed_total=target_member_total,
            page_url=list_page_url,
            profile_overview=None,
            list_overview=list_overview,
        )

    def _switch_to_list_tab(self, tab: str) -> None:
        """Switch to a specific tab on a list page (posts, about, members)."""
        if self._driver is None:
            return

        tab = tab.lower()
        valid_tabs = {
            "posts": "/posts",
            "about": "/info",
            "members": "/members",
        }
        suffix = valid_tabs.get(tab)
        if not suffix:
            return

        try:
            tab_selector = f'a[role="tab"][href$="{suffix}"]'
            elements = self._driver.find_elements(By.CSS_SELECTOR, tab_selector)
            if not elements:
                LOGGER.debug("[list_members] tab '%s' not found via selector %s", tab, tab_selector)
                return
            target = elements[0]
            if target.get_attribute("aria-selected") == "true":
                LOGGER.debug("[list_members] tab '%s' already selected", tab)
                return
            LOGGER.debug("[list_members] clicking tab '%s'", tab)
            self._driver.execute_script("arguments[0].click();", target)
            self._apply_delay(f"open-list-tab-{tab}")
        except Exception as exc:
            LOGGER.debug("[list_members] failed to switch to tab '%s': %s", tab, exc)

    def _extract_list_overview(self, list_id: str) -> ListOverview:
        """Extract list metadata from the current list page."""
        if self._driver is None:
            return ListOverview(
                list_id=list_id,
                name=None,
                description=None,
                owner_username=None,
                owner_display_name=None,
                owner_profile_url=None,
                members_total=None,
                followers_total=None,
            )

        script = """
        const listId = arguments[0];
        const info = {};

        // Helper to normalize count strings like "1.2K" -> 1200
        const normalizeCount = (value) => {
            if (!value) return null;
            const text = value.trim();
            if (!text) return null;
            const lower = text.toLowerCase().replace(/,/g, '').replace(/\\s+/g, '');
            const matchSuffix = lower.match(/^(\\d+(?:\\.\\d+)?)([km]?)$/i);
            if (!matchSuffix) {
                return null;
            }
            let num = parseFloat(matchSuffix[1]);
            const suffix = matchSuffix[2];
            if (suffix === 'k') num *= 1000;
            if (suffix === 'm') num *= 1000000;
            return Math.floor(num);
        };

        // Extract list name
        const nameElement = document.querySelector('h2[role="heading"]');
        info.name = nameElement ? nameElement.textContent.trim() : null;

        // Extract description
        const descElements = document.querySelectorAll('div[data-testid="listDescription"]');
        info.description = descElements.length > 0 ? descElements[0].textContent.trim() : null;

        // Extract owner info
        const ownerLinks = Array.from(document.querySelectorAll('a[href^="/"]'));
        const ownerLink = ownerLinks.find(a => a.href.match(/^https?:\\/\\/[^/]+\\/[^/]+$/));
        if (ownerLink) {
            info.owner_profile_url = ownerLink.href;
            info.owner_username = ownerLink.href.split('/').pop();

            // Try to find display name near the link
            const parent = ownerLink.closest('[data-testid="UserCell"]') || ownerLink.parentElement;
            const displayNameSpans = parent ? parent.querySelectorAll('span') : [];
            for (const span of displayNameSpans) {
                const text = span.textContent.trim();
                if (text && text !== '@' + info.owner_username && !text.startsWith('@')) {
                    info.owner_display_name = text;
                    break;
                }
            }
        }

        // Extract counts - look for links with numbers
        const countLinks = Array.from(document.querySelectorAll('a[href*="/lists/"]'));
        for (const link of countLinks) {
            const href = link.href;
            const text = link.textContent.trim();
            const count = normalizeCount(text);

            if (href.includes('/members') && count !== null) {
                info.members_total = count;
            } else if (href.includes('/followers') && count !== null) {
                info.followers_total = count;
            }
        }

        return info;
        """

        try:
            result = self._driver.execute_script(script, list_id)

            return ListOverview(
                list_id=list_id,
                name=result.get("name"),
                description=result.get("description"),
                owner_username=result.get("owner_username"),
                owner_display_name=result.get("owner_display_name"),
                owner_profile_url=result.get("owner_profile_url"),
                members_total=result.get("members_total"),
                followers_total=result.get("followers_total"),
            )
        except Exception as exc:
            LOGGER.warning("Could not extract list overview for list %s: %s", list_id, exc)
            return ListOverview(
                list_id=list_id,
                name=None,
                description=None,
                owner_username=None,
                owner_display_name=None,
                owner_profile_url=None,
                members_total=None,
                followers_total=None,
            )

    def _wait_for_counter(self, href: str, timeout: float = 10.0) -> bool:
        """Wait until the follower/following counter link renders non-empty text."""

        if self._driver is None:
            return False

        try:
            WebDriverWait(self._driver, timeout).until(
                lambda driver: any(
                    (element.text or "").strip()
                    for element in driver.find_elements(By.CSS_SELECTOR, f"a[href='{href}'] span")
                )
            )
            return True
        except TimeoutException:
            LOGGER.debug("Counter %s not ready after %.1fs", href, timeout)
            return False

    def fetch_profile_overview(self, username: str) -> Optional[ProfileOverview]:
        if not self._ensure_driver():
            return None
        assert self._driver is not None

        main_profile_url = f"https://twitter.com/{username}"
        attempts = len(self._config.retry_delays) + 1

        for attempt in range(attempts):
            LOGGER.debug(
                "Navigating to %s for profile overview (attempt %s/%s)",
                main_profile_url,
                attempt + 1,
                attempts,
            )
            self._driver.get(main_profile_url)
            self._apply_delay("load-main-profile-page")
            try:
                WebDriverWait(self._driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="primaryColumn"]'))
                )

                # Check if account exists before trying to extract profile
                # Save snapshot BEFORE checking so we can debug
                self._save_page_snapshot(username, "before_existence_check")

                if not self._check_account_exists(username):
                    LOGGER.error("Account @%s doesn't exist or is suspended - marking as deleted", username)
                    self._save_page_snapshot(username, "DELETED_ACCOUNT")
                    # Return a special ProfileOverview marking this as deleted
                    deleted_profile = ProfileOverview(
                        username=username,
                        display_name="[ACCOUNT DELETED]",
                        bio="[ACCOUNT DELETED OR SUSPENDED]",
                        location=None,
                        website=None,
                        followers_total=0,
                        following_total=0,
                        joined_date=None,
                        profile_image_url=None,
                    )
                    self._profile_overviews[username] = deleted_profile
                    return deleted_profile

                profile_overview = self._extract_profile_overview(username)
                if profile_overview and profile_overview.followers_total is not None and profile_overview.following_total is not None:
                    self._profile_overviews[username] = profile_overview

                    LOGGER.info(
                        "Profile overview fetched for @%s — followers=%s, following=%s, location=%s, website=%s",
                        username,
                        profile_overview.followers_total,
                        profile_overview.following_total,
                        _shorten_text(profile_overview.location, 60),
                        _shorten_text(profile_overview.website, 80),
                    )

                    if profile_overview.bio:
                        LOGGER.info(
                            "Profile bio for @%s: %s",
                            username,
                            _shorten_text(profile_overview.bio, 160),
                        )

                    return profile_overview

                # Add detailed logging for incomplete data
                missing_fields = []
                if not profile_overview:
                    missing_fields.append("entire profile object")
                else:
                    if profile_overview.followers_total is None:
                        missing_fields.append("followers_total")
                    if profile_overview.following_total is None:
                        missing_fields.append("following_total")

                # Save snapshot showing incomplete data
                self._save_page_snapshot(username, f"INCOMPLETE_DATA_attempt{attempt+1}")

                LOGGER.warning(
                    "Profile data for @%s considered incomplete. Missing or failed to parse: %s.",
                    username,
                    ", ".join(missing_fields),
                )

                # Raise a timeout to trigger the retry logic if data is missing
                raise TimeoutException("Incomplete profile data")

            except TimeoutException:
                LOGGER.warning(
                    "Timed out or profile data incomplete for @%s (attempt %s/%s)",
                    username,
                    attempt + 1,
                    attempts,
                )
                if attempt < attempts - 1:
                    sleep_time = self._config.retry_delays[attempt]
                    LOGGER.warning(
                        "Retrying profile fetch for @%s in %.1fs",
                        username,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                else:
                    LOGGER.error(
                        "Failed to fetch complete profile for @%s after %s attempts",
                        username,
                        attempts,
                    )
                    self._save_page_snapshot(username, "profile-incomplete")
        return None

    def _collect_user_list(self, *, username: str, list_type: str) -> UserListCapture:
        if not self._ensure_driver():
            return UserListCapture(list_type, [], None, "", None)
        assert self._driver is not None

        # Ensure we have the profile overview by visiting the main profile page first if needed.
        profile_overview = self._profile_overviews.get(username)
        if not profile_overview:
            profile_overview = self.fetch_profile_overview(username)

        list_page_url = f"https://twitter.com/{username}/{list_type}"
        attempts = len(self._config.retry_delays) + 1

        # Display formatted list type
        list_type_display = {
            "following": "FOLLOWING",
            "followers": "FOLLOWERS",
            "verified_followers": "VERIFIED FOLLOWERS",
            "followers_you_follow": "FOLLOWERS YOU FOLLOW"
        }.get(list_type, list_type.upper())

        LOGGER.info("\n" + "="*80)
        LOGGER.info("🔍 VISITING @%s → %s", username, list_type_display)
        LOGGER.info("="*80)

        for attempt in range(attempts):
            LOGGER.debug("Navigating to %s (attempt %s/%s)", list_page_url, attempt + 1, attempts)
            self._driver.get(list_page_url)
            # Re-inject visibility override after page navigation (Twitter is a SPA)
            self._inject_visibility_override()
            self._apply_delay(f"load-{list_type}-page")
            try:
                WebDriverWait(self._driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'section[role="region"]'))
                )
                # If successful, break the loop and proceed
                break
            except TimeoutException:
                LOGGER.warning(
                    "Timed out waiting for %s list for @%s (attempt %s/%s)",
                    list_type,
                    username,
                    attempt + 1,
                    attempts,
                )
                if attempt < attempts - 1:
                    sleep_time = self._config.retry_delays[attempt]
                    LOGGER.warning(
                        "Retrying %s list fetch for @%s in %.1fs",
                        list_type,
                        username,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                else:
                    LOGGER.error(
                        "Timed out waiting for %s list for @%s after %s attempts",
                        list_type,
                        username,
                        attempts,
                    )
                    self._save_page_snapshot(f"{username}_list", f"{list_type}-timeout")
                    return UserListCapture(list_type, [], None, list_page_url, None)
        
        self._apply_delay(f"{list_type}-viewport-ready")

        # Validate that the timeline actually loaded with content
        # Check for empty state indicators (Twitter shows these when lists are truly empty)
        try:
            timeline_section = self._driver.find_element(By.CSS_SELECTOR, 'section[role="region"]')
            initial_cells = timeline_section.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')

            if len(initial_cells) == 0:
                # Check if there's an empty state message
                empty_state_elements = self._driver.find_elements(By.CSS_SELECTOR, '[data-testid="emptyState"]')
                if empty_state_elements:
                    LOGGER.warning(
                        "⚠️  Timeline shows empty state for @%s %s list - likely has 0 %s",
                        username, list_type, "following" if list_type == "following" else "followers"
                    )
                else:
                    LOGGER.warning(
                        "⚠️  No UserCells found in main timeline for @%s %s list (after initial load)",
                        username, list_type
                    )
                    # Save snapshot to debug timeline loading issues
                    self._save_page_snapshot(f"{username}_{list_type}", "empty-timeline")
        except Exception as exc:
            LOGGER.warning("Could not validate timeline state for @%s %s: %s", username, list_type, exc)

        discovered: Dict[str, CapturedUser] = {}
        try:
            last_height = self._driver.execute_script("return document.body.scrollHeight")
        except (ConnectionRefusedError, MaxRetryError, NewConnectionError) as exc:
            LOGGER.warning("Driver connection lost before scrolling (likely pause/shutdown): %s", exc)
            raise KeyboardInterrupt("Driver connection lost") from exc
        stagnant_scrolls = 0
        scroll_round = 0
        extraction_counter = 0

        LOGGER.info("📝 Starting scroll and extraction...")

        pause_pending = False

        while stagnant_scrolls < self._config.max_no_change_scrolls:
            # Check for pause/shutdown requests before continuing scroll
            if self._pause_callback and self._pause_callback():
                if not pause_pending:
                    LOGGER.info(
                        "⏸️  Pause requested during %s collection - finishing current seed before pausing...",
                        list_type,
                    )
                pause_pending = True
            if self._shutdown_callback and self._shutdown_callback():
                LOGGER.warning("🛑 Shutdown requested during %s collection - stopping immediately...", list_type)
                raise KeyboardInterrupt("Shutdown requested during collection")

            scroll_round += 1
            LOGGER.debug("[%s] scroll #%s (collected=%s)", list_type, scroll_round, len(discovered))

            # CRITICAL FIX: Scope UserCell search to main timeline only, exclude sidebar recommendations
            # Find the main timeline section (already verified to exist in line 301)
            try:
                timeline_section = self._driver.find_element(By.CSS_SELECTOR, 'section[role="region"]')
                # Search for UserCells ONLY within the main timeline, not the entire page
                user_cells = timeline_section.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
            except Exception as exc:
                LOGGER.warning("[%s] Could not find timeline section on scroll %s: %s", list_type, scroll_round, exc)
                user_cells = []
            if LOGGER.isEnabledFor(logging.DEBUG):
                sample_html = (
                    user_cells[0].get_attribute("outerHTML")[:500]
                    if user_cells
                    else "NONE"
                )
                LOGGER.debug(
                    "[%s] found %s user cells; sample HTML: %s",
                    list_type,
                    len(user_cells),
                    sample_html,
                )
            if not user_cells:
                LOGGER.debug("[%s] no user cells found on scroll %s", list_type, scroll_round)
            for cell in user_cells:
                handle = self._extract_handle(cell)
                if not handle:
                    continue
                display_name = self._extract_display_name(cell) or handle
                bio = self._extract_bio(cell)
                website = self._extract_website(cell)
                profile_image_url = self._extract_profile_image_url(cell)
                profile_url = f"https://x.com/{handle}"

                existing = discovered.get(handle)
                if existing:
                    existing.list_types.add(list_type)
                    updated_fields = []
                    if not existing.display_name and display_name:
                        existing.display_name = display_name
                        updated_fields.append(f"display_name={display_name}")
                    if not existing.bio and bio:
                        existing.bio = bio
                        bio_preview = (bio[:60] + "...") if len(bio) > 60 else bio
                        updated_fields.append(f"bio=\"{bio_preview}\"")
                    if not existing.website and website:
                        existing.website = website
                        updated_fields.append(f"website={website}")
                    if not existing.profile_image_url and profile_image_url:
                        existing.profile_image_url = profile_image_url
                        updated_fields.append(f"image={profile_image_url}")

                    if updated_fields:
                        LOGGER.debug("  [DUP] @%s (enriched: %s)", handle, ", ".join(updated_fields))
                    else:
                        LOGGER.debug("  [DUP] @%s", handle)
                    continue

                # Log the extracted data
                extraction_counter += 1
                bio_preview = (bio[:77] + "...") if bio and len(bio) > 80 else bio
                LOGGER.info(
                    "  %3d. ✓ @%s (%s) - \"%s\"",
                    extraction_counter,
                    handle,
                    display_name or "no name",
                    bio_preview or "no bio"
                )

                captured = CapturedUser(
                    username=handle,
                    display_name=display_name,
                    bio=bio,
                    profile_url=profile_url,
                    website=website,
                    profile_image_url=profile_image_url,
                    list_types={list_type},
                )
                discovered[handle] = captured

            try:
                self._driver.execute_script("window.scrollBy(0, 1200);")
            except (ConnectionRefusedError, MaxRetryError, NewConnectionError) as exc:
                LOGGER.warning("Driver connection lost during scroll (likely pause/shutdown): %s", exc)
                raise KeyboardInterrupt("Driver connection lost during scroll") from exc

            time.sleep(random.uniform(self._config.scroll_delay_min, self._config.scroll_delay_max))

            try:
                new_height = self._driver.execute_script("return document.body.scrollHeight")
            except (ConnectionRefusedError, MaxRetryError, NewConnectionError) as exc:
                LOGGER.warning("Driver connection lost checking scroll height (likely pause/shutdown): %s", exc)
                raise KeyboardInterrupt("Driver connection lost") from exc

            if new_height == last_height:
                stagnant_scrolls += 1
                LOGGER.debug("[%s] scroll %s no height change (%s/%s)", list_type, scroll_round, stagnant_scrolls, self._config.max_no_change_scrolls)
            else:
                stagnant_scrolls = 0
            last_height = new_height

        captured_entries = list(discovered.values())

        LOGGER.info("="*80)
        LOGGER.info("✅ CAPTURED %d unique accounts from @%s → %s", len(captured_entries), username, list_type_display)
        LOGGER.info("="*80 + "\n")

        final_overview = self._profile_overviews.get(username)
        claimed_total = None
        if final_overview:
            if list_type == "followers":
                claimed_total = final_overview.followers_total
            elif list_type == "following":
                claimed_total = final_overview.following_total

        # DEFENSIVE RETRY: Detect browser focus throttling (suspicious low capture count)
        # Only retry ONCE if we captured suspiciously few accounts (like the "11 captured" pattern)
        SUSPICIOUS_LOW_THRESHOLD = 13
        MIN_CLAIMED_FOR_RETRY = 50  # Only retry if claimed total suggests there should be more

        if (len(captured_entries) <= SUSPICIOUS_LOW_THRESHOLD and
            claimed_total and claimed_total > MIN_CLAIMED_FOR_RETRY):

            LOGGER.warning("="*80)
            LOGGER.warning("⚠️  BROWSER FOCUS THROTTLING DETECTED!")
            LOGGER.warning("   Captured: %d accounts", len(captured_entries))
            LOGGER.warning("   Claimed:  %d accounts", claimed_total)
            LOGGER.warning("   Gap:      %d accounts (%.1f%% missing)",
                          claimed_total - len(captured_entries),
                          (1 - len(captured_entries)/claimed_total) * 100)
            LOGGER.warning("   This matches the known pattern of browser window losing focus.")
            LOGGER.warning("   Attempting recovery: focus restoration + page reload...")
            LOGGER.warning("="*80)

            try:
                # Step 1: Restore browser focus with mouse movements and clicks
                self._restore_browser_focus()

                # Step 2: Reload the page to reset Twitter's state
                LOGGER.info("🔄 Reloading %s page...", list_type)
                self._driver.get(list_page_url)
                self._inject_visibility_override()
                self._apply_delay(f"reload-{list_type}-page")

                # Wait for timeline to load
                WebDriverWait(self._driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'section[role="region"]'))
                )

                # Step 3: Retry scroll and extraction
                LOGGER.info("🔁 RETRY: Starting scroll and extraction (attempt 2/2)...")

                retry_discovered: Dict[str, CapturedUser] = {}
                retry_last_height = self._driver.execute_script("return document.body.scrollHeight")
                retry_stagnant_scrolls = 0
                retry_scroll_round = 0
                retry_extraction_counter = 0

                retry_pause_pending = pause_pending

                while retry_stagnant_scrolls < self._config.max_no_change_scrolls:
                    # Check for pause/shutdown
                    if self._pause_callback and self._pause_callback():
                        if not retry_pause_pending:
                            LOGGER.info(
                                "⏸️  Pause requested during retry - finishing current seed before pausing..."
                            )
                        retry_pause_pending = True
                    if self._shutdown_callback and self._shutdown_callback():
                        LOGGER.warning("🛑 Shutdown requested during retry - stopping...")
                        break

                    retry_scroll_round += 1
                    LOGGER.debug("[RETRY %s] scroll #%s (collected=%s)", list_type, retry_scroll_round, len(retry_discovered))

                    # Extract users from current viewport
                    try:
                        timeline_section = self._driver.find_element(By.CSS_SELECTOR, 'section[role="region"]')
                        user_cells = timeline_section.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                    except Exception as exc:
                        LOGGER.warning("[RETRY %s] Could not find timeline: %s", list_type, exc)
                        user_cells = []

                    for cell in user_cells:
                        handle = self._extract_handle(cell)
                        if not handle or handle in retry_discovered:
                            continue

                        display_name = self._extract_display_name(cell) or handle
                        bio = self._extract_bio(cell)
                        website = self._extract_website(cell)
                        profile_image_url = self._extract_profile_image_url(cell)

                        retry_extraction_counter += 1
                        bio_preview = (bio[:77] + "...") if bio and len(bio) > 80 else bio
                        LOGGER.info(
                            "  %3d. ✓ @%s (%s) - \"%s\"",
                            retry_extraction_counter,
                            handle,
                            display_name or "no name",
                            bio_preview or "no bio"
                        )

                        retry_discovered[handle] = CapturedUser(
                            username=handle,
                            display_name=display_name,
                            bio=bio,
                            profile_url=f"https://x.com/{handle}",
                            website=website,
                            profile_image_url=profile_image_url,
                            list_types={list_type},
                        )

                    # Scroll
                    self._driver.execute_script("window.scrollBy(0, 1200);")
                    time.sleep(random.uniform(self._config.scroll_delay_min, self._config.scroll_delay_max))

                    # Check height
                    retry_new_height = self._driver.execute_script("return document.body.scrollHeight")
                    if retry_new_height == retry_last_height:
                        retry_stagnant_scrolls += 1
                    else:
                        retry_stagnant_scrolls = 0
                    retry_last_height = retry_new_height

                # Use retry results
                retry_entries = list(retry_discovered.values())

                LOGGER.warning("="*80)
                LOGGER.warning("🔁 RETRY COMPLETE:")
                LOGGER.warning("   First attempt:  %d accounts", len(captured_entries))
                LOGGER.warning("   Retry attempt:  %d accounts", len(retry_entries))
                LOGGER.warning("   Improvement:    %+d accounts (%.1f%% → %.1f%%)",
                              len(retry_entries) - len(captured_entries),
                              (len(captured_entries)/claimed_total*100) if claimed_total else 0,
                              (len(retry_entries)/claimed_total*100) if claimed_total else 0)

                if len(retry_entries) > len(captured_entries):
                    LOGGER.warning("   ✅ Retry successful - using retry results")
                    captured_entries = retry_entries
                else:
                    LOGGER.warning("   ⚠️  Retry did not improve results - keeping original")
                LOGGER.warning("="*80 + "\n")

            except Exception as exc:
                LOGGER.error("Failed during defensive retry: %s", exc, exc_info=True)
                LOGGER.warning("Continuing with original captured entries (%d accounts)", len(captured_entries))

        return UserListCapture(
            list_type=list_type,
            entries=captured_entries,
            claimed_total=claimed_total,
            page_url=list_page_url,
            profile_overview=final_overview,
        )

    def _apply_delay(self, label: str, *, short: bool = False) -> None:
        low = 0.5 if short else self._config.action_delay_min
        high = 1.5 if short else self._config.action_delay_max
        delay = random.uniform(low, high)
        LOGGER.debug("Delay %.2fs (%s)", delay, label)
        time.sleep(delay)

    @staticmethod
    def _extract_handle(cell) -> str | None:
        from selenium.common.exceptions import StaleElementReferenceException

        try:
            links = cell.find_elements(By.TAG_NAME, "a")
            if LOGGER.isEnabledFor(logging.DEBUG):
                # Extract hrefs carefully to avoid stale elements
                href_samples = []
                for link in links[:3]:
                    try:
                        href_samples.append(link.get_attribute("href"))
                    except StaleElementReferenceException:
                        href_samples.append("<stale>")
                LOGGER.debug(
                    "Inspecting cell links count=%s href_samples=%s",
                    len(links),
                    href_samples,
                )
            for link in links:
                try:
                    href = link.get_attribute("href")
                    handle = SeleniumWorker._handle_from_href(href)
                    if handle:
                        return handle
                except StaleElementReferenceException:
                    # Element became stale, skip it
                    LOGGER.debug("Stale link element encountered, skipping")
                    continue
            # Fallback: try to get text from cell
            try:
                text = cell.text or ""
                for token in text.split():
                    if token.startswith("@"):
                        return token[1:]
            except StaleElementReferenceException:
                LOGGER.debug("Cell became stale while extracting text")
        except StaleElementReferenceException:
            LOGGER.debug("Cell is stale, cannot extract handle")
        return None

    def _extract_display_name(self, cell) -> str | None:
        from selenium.common.exceptions import StaleElementReferenceException

        # Try structured approach first
        try:
            username_div = cell.find_element(By.CSS_SELECTOR, "div[data-testid='UserName']")
            spans = username_div.find_elements(By.TAG_NAME, "span")
            for span in spans:
                try:
                    value = span.text.strip()
                    if value and not value.startswith("@") and len(value) <= 80:
                        return value
                except StaleElementReferenceException:
                    continue
        except (NoSuchElementException, StaleElementReferenceException):
            pass  # Fallback to text parsing

        # Fallback: parse the text block
        try:
            text_lines = [line.strip() for line in (cell.text or "").splitlines() if line.strip()]
            if text_lines and not text_lines[0].startswith("@"):
                return text_lines[0]
        except StaleElementReferenceException:
            LOGGER.debug("Cell became stale while extracting display name")
        return None

    @staticmethod
    def _handle_from_href(href: str | None) -> str | None:
        if not href:
            return None
        cleaned = href.strip()
        if not cleaned:
            return None
        if cleaned.startswith("/"):
            cleaned = cleaned.lstrip("/")
        elif "twitter.com" in cleaned:
            cleaned = cleaned.split("twitter.com/")[-1]
        elif "x.com" in cleaned:
            cleaned = cleaned.split("x.com/")[-1]
        # else: bare username or other format - try to parse as-is

        cleaned = cleaned.split("?")[0].split("#")[0].rstrip("/")
        if not cleaned or "/" in cleaned:
            return None
        if cleaned.startswith("@"):  # defensive; some anchors include @ prefix
            cleaned = cleaned[1:]
        if not cleaned or cleaned.startswith("i") or len(cleaned) >= 40:
            return None
        return cleaned

    @staticmethod
    def _clean_bio_text(bio: str) -> str:
        """Remove Twitter UI relationship indicators from bio text.

        Twitter adds badges like "Follows you" and "Following" as standalone elements.
        These appear at the start of the bio text, typically followed by whitespace or another badge.
        We need to be careful not to strip legitimate user content like "Following my dreams".
        """
        if not bio:
            return bio

        import re

        # Twitter badges are typically standalone at the start, followed by:
        # - newline (\n)
        # - another badge
        # - end of string (when bio is empty)
        # - significant whitespace (multiple spaces)

        cleaned = bio.strip()

        # Pattern: "Follows you" or "Following" at start, followed by newline, another badge, or end
        # Use \s{2,} to match 2+ spaces (Twitter often uses multiple spaces between badges and content)
        pattern = r'^(Follows you|Following)(\s{2,}|\n|(?=Follows you)|(?=Following)|$)'

        # Keep removing badges until none remain
        prev_cleaned = None
        while prev_cleaned != cleaned:
            prev_cleaned = cleaned
            cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE).strip()

        return cleaned

    def _extract_bio(self, cell) -> Optional[str]:
        from selenium.common.exceptions import StaleElementReferenceException

        # Try structured approach first
        try:
            bio_nodes = cell.find_elements(By.CSS_SELECTOR, "div[data-testid='UserDescription']")
            if bio_nodes and bio_nodes[0].text.strip():
                raw_bio = bio_nodes[0].text.strip()
                return self._clean_bio_text(raw_bio)
        except (NoSuchElementException, StaleElementReferenceException):
            pass  # Fallback to text parsing

        # Fallback: parse the text block
        try:
            text_lines = [line.strip() for line in (cell.text or "").splitlines() if line.strip()]
            bio_start_index = -1
            for i, line in enumerate(text_lines):
                if line.startswith('@'):
                    # Bio starts after the handle and potentially a "Follow" line
                    if i + 1 < len(text_lines) and text_lines[i+1] in {"Follow", "Following"}:
                        bio_start_index = i + 2
                    else:
                        bio_start_index = i + 1
                    break

            if bio_start_index != -1 and bio_start_index < len(text_lines):
                raw_bio = " ".join(text_lines[bio_start_index:])
                return self._clean_bio_text(raw_bio)
        except StaleElementReferenceException:
            LOGGER.debug("Cell became stale while extracting bio")

        return None

    @staticmethod
    def _extract_website(cell) -> Optional[str]:
        from selenium.common.exceptions import StaleElementReferenceException

        try:
            anchors = cell.find_elements(By.CSS_SELECTOR, "a[data-testid='UserUrl']")
            if not anchors:
                anchors = cell.find_elements(By.CSS_SELECTOR, "a[href]")
            for anchor in anchors:
                try:
                    href = (anchor.get_attribute("href") or "").strip()
                    if not href:
                        continue
                    if "twitter.com" in href or href.startswith("/"):
                        continue
                    return href
                except StaleElementReferenceException:
                    continue
        except StaleElementReferenceException:
            LOGGER.debug("Cell became stale while extracting website")
        return None

    @staticmethod
    def _extract_profile_image_url(cell) -> Optional[str]:
        from selenium.common.exceptions import StaleElementReferenceException

        try:
            images = cell.find_elements(By.CSS_SELECTOR, "img[src]")
            for img in images:
                try:
                    src = (img.get_attribute("src") or "").strip()
                    if not src:
                        continue
                    if "twimg.com" in src or "profile_images" in src:
                        return src
                except StaleElementReferenceException:
                    continue
        except StaleElementReferenceException:
            LOGGER.debug("Cell became stale while extracting profile image")
        return None

    def _check_account_exists(self, username: str) -> bool:
        """Check if the account exists or shows a 'doesn't exist' message.

        Args:
            username: The username being checked (for logging/snapshots)

        Returns:
            True if account exists, False if deleted/suspended/doesn't exist
        """
        assert self._driver is not None

        LOGGER.warning("🔍 CHECKING EXISTENCE for @%s", username)

        try:
            # Check for "This account doesn't exist" empty state
            empty_state = self._driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="emptyState"]')
            LOGGER.warning("  ➜ Found %d emptyState elements", len(empty_state))

            if empty_state:
                # Save snapshot showing the emptyState
                self._save_page_snapshot(username, "emptyState_found")

                # Search INSIDE the emptyState element, not the whole page
                header_text = empty_state[0].find_elements(By.CSS_SELECTOR, 'div[data-testid="empty_state_header_text"]')
                LOGGER.warning("  ➜ Found %d empty_state_header_text elements inside emptyState", len(header_text))

                if header_text:
                    text = header_text[0].text.strip()
                    LOGGER.warning("  ➜ Empty state header text: '%s'", text)

                    # Normalize apostrophes: Twitter uses fancy Unicode apostrophe (U+2019 ')
                    # instead of regular apostrophe (U+0027 ')
                    text_normalized = text.lower().replace('\u2019', "'").replace('\u2018', "'")

                    if "doesn't exist" in text_normalized or "account doesn't exist" in text_normalized:
                        LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED: '%s'", text)
                        return False
                else:
                    # Fallback: check ALL text content inside emptyState
                    LOGGER.warning("  ➜ No header_text element found, checking all text in emptyState")
                    empty_state_text = empty_state[0].text.strip()
                    LOGGER.warning("  ➜ EmptyState full text: '%s'", empty_state_text)

                    # Normalize apostrophes for fallback check too
                    empty_state_normalized = empty_state_text.lower().replace('\u2019', "'").replace('\u2018', "'")

                    if "doesn't exist" in empty_state_normalized:
                        LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED (in full text): '%s'", empty_state_text)
                        return False
                    else:
                        LOGGER.warning("  ⚠️ EmptyState exists but doesn't contain 'doesn't exist' - might be different error")

            # Check for suspended account message
            suspended_elements = self._driver.find_elements(By.XPATH, "//*[contains(text(), 'Account suspended')]")
            if suspended_elements:
                LOGGER.warning("  ✅ SUSPENDED ACCOUNT DETECTED")
                self._save_page_snapshot(username, "SUSPENDED")
                return False

        except Exception as e:
            LOGGER.error("  ❌ Error checking account existence: %s (assuming account exists)", e)
            # If check fails, assume account exists and continue normal processing
            import traceback
            LOGGER.error("  Traceback: %s", traceback.format_exc())
            pass

        LOGGER.warning("  ➜ Account appears to exist (no deletion/suspension detected)")
        return True

    def _extract_profile_overview(self, username: str) -> Optional[ProfileOverview]:
        assert self._driver is not None
        try:
            name_node = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserName'] span")
            display_name = name_node.text.strip() or None
        except NoSuchElementException:
            LOGGER.debug("Could not find display name for @%s", username)
            display_name = None
        try:
            bio_node = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserDescription']")
            bio = bio_node.text.strip() or None
        except NoSuchElementException:
            LOGGER.debug("Could not find bio for @%s using data-testid. Falling back to XPath.", username)
            try:
                bio_node = self._driver.find_element(By.XPATH, "/html/body/div[1]/div/div/div[2]/main/div/div/div/div/div/div[3]/div/div/div[1]/div[1]/div[3]/div")
                bio = bio_node.text.strip() or None
            except NoSuchElementException:
                LOGGER.debug("Could not find bio for @%s using XPath fallback.", username)
                bio = None
        try:
            location_node = self._driver.find_element(By.CSS_SELECTOR, "span[data-testid='UserLocation']")
            location = location_node.text.strip() or None
        except NoSuchElementException:
            LOGGER.debug("Could not find location for @%s", username)
            location = None
        try:
            website_node = self._driver.find_element(By.CSS_SELECTOR, "a[data-testid='UserUrl']")
            website = website_node.text or website_node.get_attribute("href")
        except NoSuchElementException:
            LOGGER.debug("Could not find website for @%s", username)
            website = None
        try:
            join_date_node = self._driver.find_element(By.CSS_SELECTOR, "span[data-testid='UserJoinDate']")
            joined_date = join_date_node.text.strip() or None
        except NoSuchElementException:
            LOGGER.debug("Could not find join date for @%s", username)
            joined_date = None
        try:
            avatar_container = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid^='UserAvatar-Container']")
            image_node = avatar_container.find_element(By.TAG_NAME, "img")
            profile_image_url = image_node.get_attribute("src")
        except NoSuchElementException:
            LOGGER.debug("Could not find profile image for @%s", username)
            profile_image_url = None

        canonical_handle = self._resolve_canonical_handle(username)
        if canonical_handle and canonical_handle.lower() != username.lower():
            LOGGER.debug(
                "Resolved canonical handle for @%s → @%s",
                username,
                canonical_handle,
            )

        followers_total = self._extract_claimed_total(
            username,
            "followers",
            canonical_username=canonical_handle,
        )
        following_total = self._extract_claimed_total(
            username,
            "following",
            canonical_username=canonical_handle,
        )

        schema_fallback = None
        if (
            followers_total is None
            or following_total is None
            or not location
            or not website
            or not profile_image_url
            or not bio
        ):
            schema_target = canonical_handle or username
            schema_fallback = self._extract_profile_schema(schema_target)

        if schema_fallback:
            if followers_total is None and schema_fallback.get("followers_total") is not None:
                followers_total = schema_fallback["followers_total"]
                LOGGER.info(
                    "Recovered followers total for @%s from JSON-LD schema: %s",
                    username,
                    followers_total,
                )
            if following_total is None and schema_fallback.get("following_total") is not None:
                following_total = schema_fallback["following_total"]
                LOGGER.info(
                    "Recovered following total for @%s from JSON-LD schema: %s",
                    username,
                    following_total,
                )
            if not location and schema_fallback.get("location"):
                location = schema_fallback["location"]
            if not website and schema_fallback.get("website"):
                website = schema_fallback["website"]
            if not bio and schema_fallback.get("bio"):
                bio = schema_fallback["bio"]
            if not display_name and schema_fallback.get("display_name"):
                display_name = schema_fallback["display_name"]
            if not profile_image_url and schema_fallback.get("profile_image_url"):
                profile_image_url = schema_fallback["profile_image_url"]
            if joined_date is None and schema_fallback.get("joined_date"):
                joined_date = schema_fallback["joined_date"]

        profile_username = canonical_handle or username

        return ProfileOverview(
            username=profile_username,
            display_name=display_name,
            bio=bio,
            location=location,
            website=website,
            followers_total=followers_total,
            following_total=following_total,
            joined_date=joined_date,
            profile_image_url=profile_image_url,
        )

    def _extract_claimed_total(
        self,
        username: str,
        list_type: str,
        *,
        canonical_username: Optional[str] = None,
    ) -> Optional[int]:
        assert self._driver is not None
        handles = [username]
        if canonical_username and canonical_username.lower() not in {
            username.lower(),
        }:
            handles.append(canonical_username)

        href_variants: List[str] = []
        seen_hrefs: Set[str] = set()
        for handle in handles:
            for href in self._build_href_variants(handle, list_type):
                if href not in seen_hrefs:
                    href_variants.append(href)
                    seen_hrefs.add(href)

        for href in href_variants:
            value = self._extract_total_from_exact_href(href)
            if value is not None:
                LOGGER.debug("Found %s total via exact href %s", list_type, href)
                return value

        for href in href_variants:
            value = self._extract_total_case_insensitive(href)
            if value is not None:
                LOGGER.debug("Found %s total via case-insensitive href %s", list_type, href)
                return value

        header_value = self._extract_total_from_header(
            list_type,
            handles=set(handles),
        )
        if header_value is not None:
            return header_value

        LOGGER.debug(
            "Unable to resolve %s total for @%s using handles=%s",
            list_type,
            username,
            handles,
        )
        return None

    def _extract_total_from_exact_href(self, href: str) -> Optional[int]:
        assert self._driver is not None

        if not self._wait_for_counter(href):
            return None

        anchors = self._driver.find_elements(By.CSS_SELECTOR, f"a[href='{href}']")
        for anchor in anchors:
            value = self._extract_value_from_anchor(anchor)
            if value is not None:
                return value
        return None

    def _extract_total_case_insensitive(self, href: str) -> Optional[int]:
        assert self._driver is not None

        target = href.lower()
        safe_target = target.replace('"', '\\"')
        xpath = (
            "//a[translate(@href,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
            f"\"{safe_target}\"]"
        )
        try:
            anchors = self._driver.find_elements(By.XPATH, xpath)
        except Exception as exc:  # pragma: no cover - defensive against driver quirks
            LOGGER.debug("Case-insensitive lookup failed for %s: %s", href, exc)
            return None

        for anchor in anchors:
            value = self._extract_value_from_anchor(anchor)
            if value is not None:
                return value
        return None

    def _extract_total_from_header(
        self,
        list_type: str,
        *,
        handles: Set[str],
    ) -> Optional[int]:
        assert self._driver is not None

        try:
            header = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserProfileHeader_Items']")
        except NoSuchElementException:
            LOGGER.debug("Profile header counters not found")
            return None

        counters = header.find_elements(By.CSS_SELECTOR, "a[href]")
        handle_prefixes = {
            f"/{handle.strip('/')}".lower()
            for handle in handles
            if handle
        }

        candidates = self._collect_header_candidates(
            counters,
            list_type=list_type,
            handle_prefixes=handle_prefixes,
            require_handle=True,
        )
        if not candidates:
            candidates = self._collect_header_candidates(
                counters,
                list_type=list_type,
                handle_prefixes=handle_prefixes,
                require_handle=False,
            )

        if not candidates:
            return None

        priority, value, path, label = min(candidates, key=lambda item: (item[0], -item[1]))
        LOGGER.debug(
            "Header counter resolved %s via %s (label=%s, priority=%s)",
            list_type,
            path,
            label,
            priority,
        )
        return value

    def _collect_header_candidates(
        self,
        counters,
        *,
        list_type: str,
        handle_prefixes: Set[str],
        require_handle: bool,
    ) -> List[tuple[int, int, str, str]]:
        target_label = "followers" if list_type.startswith("followers") else "following"
        matches: List[tuple[int, int, str, str]] = []

        for counter in counters:
            label_text_raw = counter.text or counter.get_attribute("aria-label") or ""
            label_text = label_text_raw.lower()
            href_value = counter.get_attribute("href") or ""
            path = self._normalize_href_path(href_value)
            path_lower = path.lower()

            if target_label not in label_text and target_label not in path_lower:
                continue

            if require_handle and handle_prefixes:
                if not any(path_lower.startswith(prefix) for prefix in handle_prefixes):
                    continue

            value = self._extract_value_from_anchor(counter)
            if value is None:
                continue

            priority = self._counter_priority(path_lower, target_label)
            matches.append((priority, value, path, label_text_raw))

        return matches

    @staticmethod
    def _counter_priority(path_lower: str, target_label: str) -> int:
        if target_label == "followers":
            if "verified_followers" in path_lower:
                return 0
            if path_lower.endswith("/followers"):
                return 1
            if "followers_you_follow" in path_lower:
                return 2
        else:
            if path_lower.endswith("/following"):
                return 0
        return 5

    def _extract_value_from_anchor(self, anchor) -> Optional[int]:
        text = (anchor.text or "").strip()
        value = self._parse_compact_count(text)
        if value is not None:
            return value
        spans = anchor.find_elements(By.TAG_NAME, "span")
        for span in spans:
            value = self._parse_compact_count(span.text)
            if value is not None:
                return value
        return None

    @staticmethod
    def _normalize_href_path(href: str) -> str:
        if not href:
            return ""

        parsed = urlparse(href)
        path = parsed.path or ""
        if not path:
            path = href if href.startswith("/") else f"/{href}"
        return path

    def _build_href_variants(self, handle: str, list_type: str) -> List[str]:
        base = list_type
        variants = [
            f"/{handle}/{base}",
            f"/{handle}/{base.lower()}",
            f"/{handle}/{base.replace('_', '')}",
        ]
        if list_type == "followers":
            variants.append(f"/{handle}/verified_followers")
        return variants

    def _resolve_canonical_handle(self, fallback: str) -> Optional[str]:
        assert self._driver is not None

        current_url = ""
        try:
            current_url = self._driver.current_url or ""
        except Exception:  # pragma: no cover - guard against driver quirks
            current_url = ""

        handle = self._handle_from_href(current_url)
        if handle:
            return handle

        try:
            name_container = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserName']")
        except NoSuchElementException:
            name_container = None

        if name_container:
            links = name_container.find_elements(By.TAG_NAME, "a")
            for link in links:
                handle = self._handle_from_href(link.get_attribute("href"))
                if handle:
                    return handle

            spans = name_container.find_elements(By.TAG_NAME, "span")
            for span in spans:
                text = span.text.strip()
                if text.startswith("@") and len(text) > 1:
                    return text[1:]

        return None

    def _extract_profile_schema(self, username: str) -> Optional[dict]:
        """Parse JSON-LD profile schema to recover metadata when header parsing fails."""
        assert self._driver is not None
        target = username.lower()
        try:
            scripts = self._driver.find_elements(
                By.CSS_SELECTOR, "script[data-testid='UserProfileSchema-test']"
            )
        except Exception as exc:  # pragma: no cover - defensive against driver quirks
            LOGGER.debug("Schema lookup failed for @%s: %s", username, exc)
            return None

        for script in scripts:
            raw = (
                (script.get_attribute("innerHTML") or "").strip()
                or (script.get_attribute("textContent") or "").strip()
            )
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                LOGGER.debug("Invalid JSON-LD payload for @%s", username)
                continue
            parsed = self._parse_profile_schema_payload(payload, target)
            if parsed:
                return parsed
        return None

    @staticmethod
    def _parse_profile_schema_payload(payload: dict, target_username: str) -> Optional[dict]:
        main = payload.get("mainEntity") or {}
        if not main:
            return None

        def _normalize(handle: str | None) -> Optional[str]:
            if not handle:
                return None
            cleaned = str(handle).strip().lower()
            if not cleaned:
                return None
            if cleaned.startswith("http://") or cleaned.startswith("https://"):
                cleaned = cleaned.split("/")[-1]
            cleaned = cleaned.split("?")[0].split("#")[0]
            return cleaned.lstrip("@")

        candidate_names = {
            value
            for value in (
                _normalize(main.get("additionalName")),
                _normalize(main.get("name")),
                _normalize(main.get("url")),
            )
            if value
        }
        normalized_target = target_username.lower()
        if normalized_target not in candidate_names:
            identifier = _normalize(main.get("identifier"))
            if identifier != normalized_target:
                return None

        interaction_stats = main.get("interactionStatistic") or []
        followers_total = None
        following_total = None
        for stat in interaction_stats:
            name = str(stat.get("name", "")).lower()
            count = stat.get("userInteractionCount")
            if count is None:
                continue
            try:
                count_int = int(count)
            except (TypeError, ValueError):
                continue
            if "follow" in name and "friend" not in name:
                followers_total = count_int
            elif "friend" in name or "following" in name:
                following_total = count_int

        home = main.get("homeLocation") or {}
        image = main.get("image") or {}

        website = None
        related_links = payload.get("relatedLink") or main.get("relatedLink") or []
        if isinstance(related_links, (list, tuple)):
            website = next((link for link in related_links if link), None)
        elif isinstance(related_links, str) and related_links.strip():
            website = related_links

        joined_date = payload.get("dateCreated") or main.get("dateCreated")

        return {
            "display_name": main.get("name"),
            "bio": main.get("description"),
            "location": home.get("name") if isinstance(home, dict) else None,
            "website": website,
            "followers_total": followers_total,
            "following_total": following_total,
            "profile_image_url": image.get("contentUrl") if isinstance(image, dict) else None,
            "joined_date": joined_date,
        }

    @staticmethod
    def _parse_compact_count(raw: Optional[str]) -> Optional[int]:
        if not raw:
            return None
        cleaned = raw.strip()

        # First, try to extract a number pattern (with optional K/M suffix) from the text.
        # This handles cases like "90.5K Followers" by extracting "90.5K" before parsing.
        number_pattern = re.search(r"([0-9][0-9.,]*[KkMm]?)", cleaned)
        if not number_pattern:
            return None

        number_text = number_pattern.group(1)

        # Parse the extracted number
        normalized = number_text.replace(",", "").replace(" ", "")
        multiplier = 1
        if normalized.lower().endswith("k"):
            multiplier = 1_000
            normalized = normalized[:-1]
        elif normalized.lower().endswith("m"):
            multiplier = 1_000_000
            normalized = normalized[:-1]

        try:
            base = float(normalized)
        except ValueError:
            return None

        return int(base * multiplier)

    def _save_page_snapshot(self, username: str, label: str) -> None:
        assert self._driver is not None
        timestamp = int(time.time())
        safe_user = re.sub(r"[^A-Za-z0-9_-]+", "-", username) or "user"
        filename = self._snapshot_dir / f"snapshot_{safe_user}_{label}_{timestamp}.html"
        try:
            source = self._driver.page_source
            filename.write_text(source)
            LOGGER.warning("Saved page snapshot to %s", filename)
        except Exception as exc:
            LOGGER.error("Failed to save snapshot for @%s: %s", username, exc)
