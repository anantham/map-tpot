"""Headless Selenium helper for extracting follower/following handles."""
from __future__ import annotations

import json
import logging
import pickle
import random
import re
import select
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


LOGGER = logging.getLogger(__name__)


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


    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
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
        self._driver = webdriver.Chrome(options=options)
        self._driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

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
                if not self._check_account_exists():
                    LOGGER.error("Account @%s doesn't exist or is suspended - marking as deleted", username)
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

        for attempt in range(attempts):
            LOGGER.debug("Navigating to %s (attempt %s/%s)", list_page_url, attempt + 1, attempts)
            self._driver.get(list_page_url)
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

        discovered: Dict[str, CapturedUser] = {}
        last_height = self._driver.execute_script("return document.body.scrollHeight")
        stagnant_scrolls = 0
        scroll_round = 0

        while stagnant_scrolls < self._config.max_no_change_scrolls:
            scroll_round += 1
            LOGGER.debug("[%s] scroll #%s (collected=%s)", list_type, scroll_round, len(discovered))
            user_cells = self._driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
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
                        LOGGER.info("[%s] Already captured @%s - updated: %s", list_type, handle, ", ".join(updated_fields))
                    else:
                        LOGGER.debug("[%s] Already captured @%s - no new fields", list_type, handle)
                    continue

                # Log the extracted data
                bio_preview = (bio[:80] + "...") if bio and len(bio) > 80 else bio
                LOGGER.info(
                    "Extracted: @%s (%s) - \"%s\" | website: %s | image: %s",
                    handle,
                    display_name or "(no name)",
                    bio_preview or "(no bio)",
                    website or "(none)",
                    profile_image_url or "(none)"
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

            self._driver.execute_script("window.scrollBy(0, 1200);")
            time.sleep(random.uniform(self._config.scroll_delay_min, self._config.scroll_delay_max))
            new_height = self._driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                stagnant_scrolls += 1
                LOGGER.debug("[%s] scroll %s no height change (%s/%s)", list_type, scroll_round, stagnant_scrolls, self._config.max_no_change_scrolls)
            else:
                stagnant_scrolls = 0
            last_height = new_height

        captured_entries = list(discovered.values())
        LOGGER.debug(
            "Collected %s %s entries for @%s", len(captured_entries), list_type, username
        )
        
        final_overview = self._profile_overviews.get(username)
        claimed_total = None
        if final_overview:
            if list_type == "followers":
                claimed_total = final_overview.followers_total
            elif list_type == "following":
                claimed_total = final_overview.following_total

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

    def _extract_bio(self, cell) -> Optional[str]:
        from selenium.common.exceptions import StaleElementReferenceException

        # Try structured approach first
        try:
            bio_nodes = cell.find_elements(By.CSS_SELECTOR, "div[data-testid='UserDescription']")
            if bio_nodes and bio_nodes[0].text.strip():
                return bio_nodes[0].text.strip()
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
                return " ".join(text_lines[bio_start_index:])
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

    def _check_account_exists(self) -> bool:
        """Check if the account exists or shows a 'doesn't exist' message.

        Returns:
            True if account exists, False if deleted/suspended/doesn't exist
        """
        assert self._driver is not None

        try:
            # Check for "This account doesn't exist" empty state
            empty_state = self._driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="emptyState"]')
            if empty_state:
                header_text = self._driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="empty_state_header_text"]')
                if header_text:
                    text = header_text[0].text.strip().lower()
                    if "doesn't exist" in text or "account doesn't exist" in text:
                        LOGGER.warning("Account doesn't exist (empty state detected)")
                        return False

            # Check for suspended account message
            suspended_elements = self._driver.find_elements(By.XPATH, "//*[contains(text(), 'Account suspended')]")
            if suspended_elements:
                LOGGER.warning("Account is suspended")
                return False

        except Exception as e:
            LOGGER.debug("Error checking account existence: %s", e)
            # If check fails, assume account exists and continue normal processing
            pass

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

        followers_total = self._extract_claimed_total(username, "followers")
        following_total = self._extract_claimed_total(username, "following")

        schema_fallback = None
        if (
            followers_total is None
            or following_total is None
            or not location
            or not website
            or not profile_image_url
            or not bio
        ):
            schema_fallback = self._extract_profile_schema(username)

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

        return ProfileOverview(
            username=username,
            display_name=display_name,
            bio=bio,
            location=location,
            website=website,
            followers_total=followers_total,
            following_total=following_total,
            joined_date=joined_date,
            profile_image_url=profile_image_url,
        )

    def _extract_claimed_total(self, username: str, list_type: str) -> Optional[int]:
        assert self._driver is not None

        href_variants = [
            f"/{username}/{list_type}",
            f"/{username}/{list_type.lower()}",
            f"/{username}/{list_type.replace('_', '')}",
        ]

        # Twitter now uses verified_followers instead of followers
        if list_type == "followers":
            href_variants.append(f"/{username}/verified_followers")

        for href in href_variants:
            anchors = self._driver.find_elements(By.CSS_SELECTOR, f"a[href='{href}']")
            if not anchors:
                continue
            for anchor in anchors:
                text = (anchor.text or "").strip()
                value = self._parse_compact_count(text)
                if value is not None:
                    LOGGER.debug("Found count for href %s: %d", href, value)
                    return value
                spans = anchor.find_elements(By.TAG_NAME, "span")
                for span in spans:
                    value = self._parse_compact_count(span.text)
                    if value is not None:
                        LOGGER.debug("Found count from span for href %s: %d", href, value)
                        return value

        # Fallback: walk the profile header counters and match by label text.
        try:
            header = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserProfileHeader_Items']")
            counters = header.find_elements(By.CSS_SELECTOR, "a[href]")
            target_label = "followers" if list_type.startswith("followers") else "following"
            for counter in counters:
                label_text = (counter.text or counter.get_attribute("aria-label") or "").lower()
                if target_label not in label_text:
                    continue
                spans = counter.find_elements(By.TAG_NAME, "span")
                span_texts = [span.text for span in spans if span.text.strip()]
                candidates = span_texts or [counter.text]
                for candidate in candidates:
                    value = self._parse_compact_count(candidate)
                    if value is not None:
                        LOGGER.debug(
                            "Fallback header counter matched '%s': %s => %d",
                            target_label,
                            candidate,
                            value,
                        )
                        return value
        except NoSuchElementException:
            LOGGER.debug("Profile header counters not found for @%s", username)

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
        match = re.match(r"^[0-9.,]+(?:[KkMm])?$", cleaned.replace(" ", ""))
        if match:
            normalized = cleaned.replace(",", "").replace(" ", "")
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
        digits = re.findall(r"[0-9,]+", cleaned)
        if digits:
            try:
                return int(digits[0].replace(",", ""))
            except ValueError:
                return None
        return None

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
