"""Headless Selenium helper for extracting follower/following handles."""
from __future__ import annotations

import logging
import pickle
import random
import re
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
    scroll_delay_min: float = 4.0
    scroll_delay_max: float = 9.0
    max_no_change_scrolls: int = 6
    window_size: str = "1080,1280"
    action_delay_min: float = 4.0
    action_delay_max: float = 9.0
    chrome_binary: Optional[Path] = None
    require_confirmation: bool = True


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


class SeleniumWorker:
    """Minimal Selenium-based scroller for Twitter lists."""

    def __init__(self, config: SeleniumConfig) -> None:
        self._config = config
        self._driver: webdriver.Chrome | None = None
        self._profile_overviews: Dict[str, ProfileOverview] = {}

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
            input(
                "Cookies loaded. Please log in or verify the session in the browser window, then press Enter to continue..."
            )
        return True

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

    def _collect_user_list(self, *, username: str, list_type: str) -> UserListCapture:
        if not self._ensure_driver():
            return UserListCapture(list_type, [], None, "", None)
        assert self._driver is not None

        url = f"https://twitter.com/{username}/{list_type}"
        LOGGER.debug("Navigating to %s", url)
        self._driver.get(url)
        self._apply_delay(f"load-{list_type}-page")
        try:
            WebDriverWait(self._driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'section[role="region"]'))
            )
        except TimeoutException:
            LOGGER.error("Timed out waiting for %s list for @%s", list_type, username)
            return UserListCapture(list_type, [], None, url, None)
        self._apply_delay(f"{list_type}-viewport-ready")

        profile_overview = self._profile_overviews.get(username)
        if not profile_overview:
            profile_overview = self._extract_profile_overview(username)
            if profile_overview:
                self._profile_overviews[username] = profile_overview

        claimed_total = self._extract_claimed_total(username, list_type)

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
                    if not existing.display_name and display_name:
                        existing.display_name = display_name
                    if not existing.bio and bio:
                        existing.bio = bio
                    if not existing.website and website:
                        existing.website = website
                    if not existing.profile_image_url and profile_image_url:
                        existing.profile_image_url = profile_image_url
                    continue
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
        return UserListCapture(
            list_type=list_type,
            entries=captured_entries,
            claimed_total=claimed_total,
            page_url=url,
            profile_overview=profile_overview,
        )

    def _apply_delay(self, label: str, *, short: bool = False) -> None:
        low = 0.5 if short else self._config.action_delay_min
        high = 1.5 if short else self._config.action_delay_max
        delay = random.uniform(low, high)
        LOGGER.debug("Delay %.2fs (%s)", delay, label)
        time.sleep(delay)

    @staticmethod
    def _extract_handle(cell) -> str | None:
        links = cell.find_elements(By.TAG_NAME, "a")
        if LOGGER.isEnabledFor(logging.DEBUG):
            href_samples = [link.get_attribute("href") for link in links[:3]]
            LOGGER.debug(
                "Inspecting cell links count=%s href_samples=%s",
                len(links),
                href_samples,
            )
        for link in links:
            href = link.get_attribute("href")
            handle = SeleniumWorker._handle_from_href(href)
            if handle:
                return handle
        text = cell.text or ""
        for token in text.split():
            if token.startswith("@"):
                return token[1:]
        return None

    @staticmethod
    def _extract_display_name(cell) -> str | None:
        # Try structured approach: display name is in UserName div, before the handle
        try:
            username_div = cell.find_element(By.CSS_SELECTOR, "div[data-testid='UserName']")
            spans = username_div.find_elements(By.TAG_NAME, "span")
            for span in spans:
                value = span.text.strip()
                # Display name doesn't start with @, handle does
                if value and not value.startswith("@") and len(value) <= 80:
                    return value
        except NoSuchElementException:
            pass

        # Fallback: look for first non-@ text in the cell
        text_lines = [line.strip() for line in (cell.text or "").splitlines() if line.strip()]
        for line in text_lines:
            if not line.startswith("@") and line not in {"Follow", "Following"}:
                return line
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
        else:
            return None
        cleaned = cleaned.split("?")[0].split("#")[0].rstrip("/")
        if not cleaned or "/" in cleaned:
            return None
        if cleaned.startswith("@"):  # defensive; some anchors include @ prefix
            cleaned = cleaned[1:]
        if not cleaned or cleaned.startswith("i") or len(cleaned) >= 40:
            return None
        return cleaned

    @staticmethod
    def _extract_bio(cell) -> Optional[str]:
        # Try 1: UserDescription testid (works on profile pages, not in UserCells)
        bio_nodes = cell.find_elements(By.CSS_SELECTOR, "div[data-testid='UserDescription']")
        if bio_nodes:
            value = bio_nodes[0].text.strip()
            if value:
                return value

        # Try 2: Look for bio div by structure - it's the last text div after user info
        # Bio is in a div with overflow:hidden, contains a span with the bio text
        # Pattern: <div dir="auto" style="...overflow: hidden..."><span>bio text</span></div>
        try:
            bio_divs = cell.find_elements(By.CSS_SELECTOR, "div[dir='auto']")
            for div in bio_divs:
                # Check if it has overflow:hidden style (bio characteristic)
                style = div.get_attribute("style") or ""
                if "overflow" in style and "hidden" in style:
                    text = div.text.strip()
                    # Bio shouldn't be a button or handle
                    if text and text not in {"Follow", "Following", "Follows you"} and not text.startswith("@"):
                        return text
        except Exception:
            pass

        # Try 3: Look for spans outside UserName div that contain bio-like text
        try:
            all_spans = cell.find_elements(By.TAG_NAME, "span")
            username_div = cell.find_element(By.CSS_SELECTOR, "div[data-testid='UserName']")
            username_spans = set(username_div.find_elements(By.TAG_NAME, "span"))

            for span in all_spans:
                if span in username_spans:
                    continue
                text = span.text.strip()
                # Bio characteristics: non-empty, not UI text, reasonable length
                if (
                    text
                    and len(text) > 5
                    and text not in {"Follow", "Following", "Follows you", "Click to Follow"}
                    and not text.startswith("@")
                    and not text.startswith("Click to")
                ):
                    return text
        except NoSuchElementException:
            pass

        return None

    @staticmethod
    def _extract_website(cell) -> Optional[str]:
        anchors = cell.find_elements(By.CSS_SELECTOR, "a[data-testid='UserUrl']")
        if not anchors:
            anchors = cell.find_elements(By.CSS_SELECTOR, "a[href]")
        for anchor in anchors:
            href = (anchor.get_attribute("href") or "").strip()
            if not href:
                continue
            if "twitter.com" in href or href.startswith("/"):
                continue
            return href
        return None

    @staticmethod
    def _extract_profile_image_url(cell) -> Optional[str]:
        images = cell.find_elements(By.CSS_SELECTOR, "img[src]")
        for img in images:
            src = (img.get_attribute("src") or "").strip()
            if not src:
                continue
            if "twimg.com" in src or "profile_images" in src:
                return src
        return None

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
            website = website_node.get_attribute("href") or website_node.text or None
        except NoSuchElementException:
            LOGGER.debug("Could not find website for @%s", username)
            website = None
        try:
            join_date_node = self._driver.find_element(By.CSS_SELECTOR, "span[data-testid='UserJoinDate']")
            joined_date = join_date_node.text.strip() or None
        except NoSuchElementException:
            LOGGER.debug("Could not find join date for @%s", username)
            joined_date = None

        followers_total = self._extract_claimed_total(username, "followers")
        following_total = self._extract_claimed_total(username, "following")

        return ProfileOverview(
            username=username,
            display_name=display_name,
            bio=bio,
            location=location,
            website=website,
            followers_total=followers_total,
            following_total=following_total,
            joined_date=joined_date,
        )

    def _extract_claimed_total(self, username: str, list_type: str) -> Optional[int]:
        assert self._driver is not None

        # The user's HTML shows that the link for followers can be 'verified_followers'
        # We will check for the standard list_type first, then fall back to other variants.
        href_variants = [
            f"/{username}/{list_type.lower()}",
            f"/{username}/verified_followers" if list_type == "followers" else f"/{username}/{list_type.lower()}",
            f"/{username}/{list_type.replace('_', '')}",
        ]
        
        for href in href_variants:
            try:
                # New, more specific selector based on user-provided HTML
                count_span = self._driver.find_element(By.CSS_SELECTOR, f"a[href='{href}'] span span")
                value = self._parse_compact_count(count_span.text)
                if value is not None:
                    LOGGER.debug("Found count for href %s: %d", href, value)
                    return value
            except NoSuchElementException:
                LOGGER.debug("Could not find count for href %s with new specific selector.", href)

        # Fallback to the old, less specific method if the new one fails
        LOGGER.debug("Falling back to old method for _extract_claimed_total for user %s", username)
        for href in href_variants:
            try:
                anchors = self._driver.find_elements(By.CSS_SELECTOR, f"a[href='{href}']")
                for anchor in anchors:
                    # The first span is the number, the second is the label ("Following", "Followers")
                    spans = anchor.find_elements(By.TAG_NAME, "span")
                    if spans:
                        value = self._parse_compact_count(spans[0].text)
                        if value is not None:
                            return value
            except NoSuchElementException:
                continue
        
        LOGGER.warning("Could not extract claimed total for @%s, list_type: %s", username, list_type)
        return None

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
