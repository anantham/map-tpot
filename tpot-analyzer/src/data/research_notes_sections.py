"""Extract exact account-owned blocks from a messy Research Notes document."""
from __future__ import annotations

import re
from dataclasses import dataclass


_PROFILE_URL = re.compile(
    r"^\s*(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/"
    r"([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_])(?:[/?#][^\s]*)?\s*$",
    re.IGNORECASE,
)
_MENTION = re.compile(r"^\s*@([A-Za-z0-9_]{1,15})\s*[,.;:]?\s*$")
_CONTINUATION = re.compile(
    r"^\s*same\s+with\s+@([A-Za-z0-9_]{1,15})\s*[,.;:]?\s*$",
    re.IGNORECASE,
)
_SEPARATOR = re.compile(r"^\s*-{3,}\s*$")


@dataclass(frozen=True)
class _Line:
    text: str
    start: int
    content_end: int


@dataclass(frozen=True)
class _Header:
    handle: str
    line_index: int
    block_start: int


def _source_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    start = 0
    for match in re.finditer(r"\r\n|\n|\r", text):
        lines.append(_Line(text[start:match.start()], start, match.start()))
        start = match.end()
    lines.append(_Line(text[start:], start, len(text)))
    return lines


def _is_boundary(value: str) -> bool:
    return not value.strip() or _SEPARATOR.fullmatch(value) is not None


def _is_display_name(value: str) -> bool:
    stripped = value.strip()
    words = stripped.split()
    return (
        2 <= len(words) <= 5
        and len(stripped) <= 80
        and stripped[:1].isupper()
        and all(character not in stripped for character in "@:/")
    )


def _header_at(lines: list[_Line], index: int) -> _Header | None:
    value = lines[index].text
    url_match = _PROFILE_URL.fullmatch(value)
    if url_match:
        return _Header(url_match.group(1).casefold(), index, index)
    mention_match = _MENTION.fullmatch(value)
    if not mention_match:
        return None
    if index == 0 or _is_boundary(lines[index - 1].text):
        return _Header(mention_match.group(1).casefold(), index, index)
    has_display_name = _is_display_name(lines[index - 1].text)
    display_name_is_bounded = index == 1 or _is_boundary(lines[index - 2].text)
    if has_display_name and display_name_is_bounded:
        return _Header(mention_match.group(1).casefold(), index, index - 1)
    return None


def source_sections_by_handle(text: str) -> dict[str, tuple[str, ...]]:
    """Return exact source blocks for primary and ``same with`` subjects."""
    if not isinstance(text, str) or not text:
        return {}
    lines = _source_lines(text)
    headers = [
        header for index in range(len(lines))
        if (header := _header_at(lines, index)) is not None
    ]
    sections: dict[str, list[str]] = {}
    for position, header in enumerate(headers):
        end_line = headers[position + 1].block_start if position + 1 < len(headers) else len(lines)
        while end_line > header.block_start + 1 and _is_boundary(lines[end_line - 1].text):
            end_line -= 1
        start = lines[header.block_start].start
        end = lines[end_line - 1].content_end
        block = text[start:end]
        subjects = {header.handle}
        for line in lines[header.line_index + 1:end_line]:
            if match := _CONTINUATION.fullmatch(line.text):
                subjects.add(match.group(1).casefold())
        for subject in subjects:
            sections.setdefault(subject, []).append(block)
    return {handle: tuple(blocks) for handle, blocks in sections.items()}
