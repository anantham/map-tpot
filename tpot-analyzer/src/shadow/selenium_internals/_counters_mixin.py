"""Follower / following counter extraction methods for SeleniumWorker.

Walks header anchors + href variants to recover claimed totals from a
profile page, with canonical-handle resolution as a fallback path.

Mixin: coordinator owns `self._driver`. Cross-mixin: calls
`self._wait_for_counter` (list_capture_mixin), `self._handle_from_href`,
`self._normalize_href_path`, `self._counter_priority`,
`self._parse_compact_count` (parser wrappers on coordinator).
"""
from __future__ import annotations

from typing import List, Optional, Set

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from ._types import LOGGER


class CounterExtractionMixin:
    """Follower/following counter extraction + canonical handle resolution."""

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
    ) -> List[tuple]:
        target_label = "followers" if list_type.startswith("followers") else "following"
        matches: List[tuple] = []

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
