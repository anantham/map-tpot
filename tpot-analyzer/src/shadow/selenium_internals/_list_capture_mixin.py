"""List capture methods for SeleniumWorker.

Provides the public fetch_* methods plus internal scroll/extract helpers.
Mixin: assumes coordinator owns `self._driver`, `self._config`,
`self._pause_callback`, `self._shutdown_callback`, `self._profile_overviews`.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Dict, Optional

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import MaxRetryError, NewConnectionError

from src.shadow.silent_failures import tracker as silent_failures

from ._types import LOGGER, CapturedUser, ListOverview, UserListCapture


class ListCaptureMixin:
    """Follower/following/list-member page walking + scroll-and-collect."""

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

        silent_failures.log_summary(f"fetch_list_members list_id={list_id}")

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

        silent_failures.log_summary(f"_collect_user_list @{username} ({list_type})")

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
