"""Pure parsing helpers extracted from SeleniumWorker.

These functions used to live as `@staticmethod` members on
`src.shadow.selenium_worker.SeleniumWorker`. They were all pure (no
`self`, no hidden class state) so they're extractable as module-level
functions. The class still re-exports each one as a one-line wrapper
for backward compatibility with existing call sites.

Two flavors here:
- **Pure string/regex/dict parsers** (`handle_from_href`, `clean_bio_text`,
  `counter_priority`, `normalize_href_path`, `parse_compact_count`,
  `parse_profile_schema_payload`) — no Selenium dependency, trivially
  testable in isolation.
- **DOM extractors** (`extract_handle`, `extract_website`,
  `extract_profile_image_url`) — depend on Selenium WebElement API and
  the silent-failures tracker. Still pure in the "no shared state" sense.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By

from src.shadow.silent_failures import tracker as silent_failures


LOGGER = logging.getLogger(__name__)


def handle_from_href(href: Optional[str]) -> Optional[str]:
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


def clean_bio_text(bio: str) -> str:
    """Remove Twitter UI relationship indicators from bio text.

    Twitter adds badges like "Follows you" and "Following" as standalone elements.
    These appear at the start of the bio text, typically followed by whitespace or another badge.
    We need to be careful not to strip legitimate user content like "Following my dreams".
    """
    if not bio:
        return bio

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


def counter_priority(path_lower: str, target_label: str) -> int:
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


def normalize_href_path(href: str) -> str:
    if not href:
        return ""

    parsed = urlparse(href)
    path = parsed.path or ""
    if not path:
        path = href if href.startswith("/") else f"/{href}"
    return path


def parse_compact_count(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", "", raw.strip())

    # First, try to extract a number pattern (with optional K/M suffix) from the text.
    # This handles cases like "90.5K Followers" by extracting "90.5K" before parsing.
    number_pattern = re.search(r"([0-9][0-9.,]*[KkMm]?)", cleaned)
    if not number_pattern:
        return None

    number_text = number_pattern.group(1)

    # Parse the extracted number
    normalized = number_text.replace(",", "")
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


def parse_profile_schema_payload(payload: dict, target_username: str) -> Optional[dict]:
    main = payload.get("mainEntity") or {}
    if not main:
        return None

    def _normalize(handle: Optional[str]) -> Optional[str]:
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


# ---------------------------------------------------------------------------
# DOM extractors — depend on Selenium WebElement API + silent_failures tracker
# ---------------------------------------------------------------------------


def extract_handle(cell) -> Optional[str]:
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
                handle = handle_from_href(href)
                if handle:
                    return handle
            except StaleElementReferenceException as exc:
                # Element became stale, skip it
                LOGGER.debug("Stale link element encountered, skipping")
                silent_failures.track("extract_handle.stale_link", exc)
                continue
        # Fallback: try to get text from cell
        try:
            text = cell.text or ""
            for token in text.split():
                if token.startswith("@"):
                    return token[1:]
        except StaleElementReferenceException as exc:
            LOGGER.debug("Cell became stale while extracting text")
            silent_failures.track("extract_handle.stale_cell_text", exc)
    except StaleElementReferenceException as exc:
        LOGGER.debug("Cell is stale, cannot extract handle")
        silent_failures.track("extract_handle.stale_cell", exc)
    return None


def extract_website(cell) -> Optional[str]:
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
            except StaleElementReferenceException as exc:
                silent_failures.track("extract_website.stale_anchor", exc)
                continue
    except StaleElementReferenceException as exc:
        LOGGER.debug("Cell became stale while extracting website")
        silent_failures.track("extract_website.stale_cell", exc)
    return None


def extract_profile_image_url(cell) -> Optional[str]:
    try:
        images = cell.find_elements(By.CSS_SELECTOR, "img[src]")
        for img in images:
            try:
                src = (img.get_attribute("src") or "").strip()
                if not src:
                    continue
                if "twimg.com" in src or "profile_images" in src:
                    return src
            except StaleElementReferenceException as exc:
                silent_failures.track("extract_profile_image.stale_img", exc)
                continue
    except StaleElementReferenceException as exc:
        LOGGER.debug("Cell became stale while extracting profile image")
        silent_failures.track("extract_profile_image.stale_cell", exc)
    return None
