"""Profile-extraction methods for SeleniumWorker.

Covers: account-status detection, profile overview extraction (header DOM +
JSON-LD schema fallback), per-cell display name and bio extraction,
and the public fetch_profile_overview entry point.

Mixin: coordinator owns `self._driver`, `self._config`,
`self._profile_overviews`.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.shadow.silent_failures import tracker as silent_failures

from ._types import LOGGER, AccountStatusInfo, ProfileOverview, _shorten_text


class ProfileMixin:
    """Profile fetch + account-status detection + cell display name/bio."""

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

                # Check account status
                status_info = self._check_account_exists(username)

                if status_info.status != "active":
                    LOGGER.error(
                        "Account @%s status: %s - marking with status marker",
                        username,
                        status_info.status
                    )
                    self._save_page_snapshot(username, f"{status_info.status.upper()}_ACCOUNT")

                    # Return ProfileOverview with status marker
                    # This triggers special handling in enricher.py
                    status_profile = ProfileOverview(
                        username=username,
                        display_name=f"[{status_info.status.upper()}]",
                        bio=f"[ACCOUNT {status_info.status.upper()}]",  # Marker for enricher
                        location=None,
                        website=None,
                        followers_total=0,
                        following_total=0,
                        joined_date=None,
                        profile_image_url=None,
                    )
                    self._profile_overviews[username] = status_profile
                    return status_profile

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

    def _extract_display_name(self, cell) -> Optional[str]:
        # Try structured approach first
        try:
            username_div = cell.find_element(By.CSS_SELECTOR, "div[data-testid='UserName']")
            spans = username_div.find_elements(By.TAG_NAME, "span")
            for span in spans:
                try:
                    value = span.text.strip()
                    if value and not value.startswith("@") and len(value) <= 80:
                        return value
                except StaleElementReferenceException as exc:
                    silent_failures.track("extract_display_name.stale_span", exc)
                    continue
        except (NoSuchElementException, StaleElementReferenceException) as exc:
            silent_failures.track("extract_display_name.no_username_div", exc)
            # Fallback to text parsing

        # Fallback: parse the text block
        try:
            text_lines = [line.strip() for line in (cell.text or "").splitlines() if line.strip()]
            if text_lines and not text_lines[0].startswith("@"):
                return text_lines[0]
        except StaleElementReferenceException as exc:
            LOGGER.debug("Cell became stale while extracting display name")
            silent_failures.track("extract_display_name.stale_cell_fallback", exc)
        return None

    def _extract_bio(self, cell) -> Optional[str]:
        # Try structured approach first
        try:
            bio_nodes = cell.find_elements(By.CSS_SELECTOR, "div[data-testid='UserDescription']")
            if bio_nodes and bio_nodes[0].text.strip():
                raw_bio = bio_nodes[0].text.strip()
                return self._clean_bio_text(raw_bio)
        except (NoSuchElementException, StaleElementReferenceException) as exc:
            silent_failures.track("extract_bio.no_description_div", exc)
            # Fallback to text parsing

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
        except StaleElementReferenceException as exc:
            LOGGER.debug("Cell became stale while extracting bio")
            silent_failures.track("extract_bio.stale_cell_fallback", exc)

        return None

    def _check_account_exists(self, username: str) -> AccountStatusInfo:
        """Check account status and return detailed info.

        Args:
            username: The username being checked (for logging/snapshots)

        Returns:
            AccountStatusInfo with status: active/deleted/suspended/protected
        """
        assert self._driver is not None
        now = datetime.utcnow()

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
                    text_normalized = text.lower().replace('’', "'").replace('‘', "'")

                    if "doesn't exist" in text_normalized or "account doesn't exist" in text_normalized:
                        LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED: '%s'", text)
                        return AccountStatusInfo(
                            status="deleted",
                            detected_at=now,
                            message=text
                        )
                else:
                    # Fallback: check ALL text content inside emptyState
                    LOGGER.warning("  ➜ No header_text element found, checking all text in emptyState")
                    empty_state_text = empty_state[0].text.strip()
                    LOGGER.warning("  ➜ EmptyState full text: '%s'", empty_state_text)

                    # Normalize apostrophes for fallback check too
                    empty_state_normalized = empty_state_text.lower().replace('’', "'").replace('‘', "'")

                    if "doesn't exist" in empty_state_normalized:
                        LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED (in full text): '%s'", empty_state_text)
                        return AccountStatusInfo(
                            status="deleted",
                            detected_at=now,
                            message=empty_state_text
                        )
                    else:
                        LOGGER.warning("  ⚠️ EmptyState exists but doesn't contain 'doesn't exist' - might be different error")

            # Check for suspended account message
            suspended_elements = self._driver.find_elements(By.XPATH, "//*[contains(text(), 'Account suspended')]")
            if suspended_elements:
                LOGGER.warning("  ✅ SUSPENDED ACCOUNT DETECTED")
                self._save_page_snapshot(username, "SUSPENDED")
                return AccountStatusInfo(
                    status="suspended",
                    detected_at=now,
                    message="Account suspended"
                )

            # 3. NEW: Check for protected account
            # Text search is robust against DOM structure changes
            try:
                body = self._driver.find_element(By.TAG_NAME, 'body')
                page_text = body.text

                if "These posts are protected" in page_text:
                    LOGGER.warning("  ✅ PROTECTED ACCOUNT DETECTED")
                    self._save_page_snapshot(username, "PROTECTED_ACCOUNT")
                    return AccountStatusInfo(
                        status="protected",
                        detected_at=now,
                        message="These posts are protected"
                    )
            except Exception as e:
                LOGGER.debug("  Error checking for protected status: %s", e)

        except Exception as e:
            LOGGER.error("  ❌ Error checking account existence: %s (assuming account exists)", e)
            # If check fails, assume account exists and continue normal processing
            import traceback
            LOGGER.error("  Traceback: %s", traceback.format_exc())
            pass

        LOGGER.warning("  ➜ Account appears to exist and is accessible")
        return AccountStatusInfo(
            status="active",
            detected_at=now,
            message=None
        )

    def _extract_profile_overview(self, username: str) -> Optional[ProfileOverview]:
        assert self._driver is not None
        try:
            name_node = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserName'] span")
            display_name = name_node.text.strip() or None
        except NoSuchElementException as exc:
            LOGGER.debug("Could not find display name for @%s", username)
            silent_failures.track("profile_overview.display_name", exc)
            display_name = None
        try:
            bio_node = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid='UserDescription']")
            bio = bio_node.text.strip() or None
        except NoSuchElementException as exc:
            LOGGER.debug("Could not find bio for @%s using data-testid. Falling back to XPath.", username)
            silent_failures.track("profile_overview.bio_testid", exc)
            try:
                bio_node = self._driver.find_element(By.XPATH, "/html/body/div[1]/div/div/div[2]/main/div/div/div/div/div/div[3]/div/div/div[1]/div[1]/div[3]/div")
                bio = bio_node.text.strip() or None
            except NoSuchElementException as exc2:
                LOGGER.debug("Could not find bio for @%s using XPath fallback.", username)
                silent_failures.track("profile_overview.bio_xpath_fallback", exc2)
                bio = None
        try:
            location_node = self._driver.find_element(By.CSS_SELECTOR, "span[data-testid='UserLocation']")
            location = location_node.text.strip() or None
        except NoSuchElementException as exc:
            LOGGER.debug("Could not find location for @%s", username)
            silent_failures.track("profile_overview.location", exc)
            location = None
        try:
            website_node = self._driver.find_element(By.CSS_SELECTOR, "a[data-testid='UserUrl']")
            website = website_node.text or website_node.get_attribute("href")
        except NoSuchElementException as exc:
            LOGGER.debug("Could not find website for @%s", username)
            silent_failures.track("profile_overview.website", exc)
            website = None
        try:
            join_date_node = self._driver.find_element(By.CSS_SELECTOR, "span[data-testid='UserJoinDate']")
            joined_date = join_date_node.text.strip() or None
        except NoSuchElementException as exc:
            LOGGER.debug("Could not find join date for @%s", username)
            silent_failures.track("profile_overview.joined_date", exc)
            joined_date = None
        try:
            avatar_container = self._driver.find_element(By.CSS_SELECTOR, "div[data-testid^='UserAvatar-Container']")
            image_node = avatar_container.find_element(By.TAG_NAME, "img")
            profile_image_url = image_node.get_attribute("src")
        except NoSuchElementException as exc:
            LOGGER.debug("Could not find profile image for @%s", username)
            silent_failures.track("profile_overview.profile_image", exc)
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
