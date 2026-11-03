"""Offline URL-like bio mentions, with explicit normalization provenance.

Recognition is not DNS validation, ownership or contact verification. Bare
domains can also resemble filenames; the literal text remains inspectable.
"""
from __future__ import annotations

import re
from html import unescape as _unescape
from ipaddress import ip_address
from threading import Lock
from typing import Optional
from urllib.parse import urlparse, urlsplit

from linkify_it import LinkifyIt
from linkify_it.tlds import TLDS

RECOGNIZER = 'legacy-http-v1+linkify-it-py/2.2.0'
_parser = LinkifyIt(options={'fuzzy_email': False, 'fuzzy_ip': False}).tlds(TLDS)
_lock = Lock()  # LinkifyIt caches mutable match state; Flask readers may overlap.
# Preserve the existing explicit-HTTP scanner, including URLs glued to prose.
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'‘’“”]+", re.I)
_URL_STOP_HOSTS = frozenset({
    "twitter.com", "x.com", "mobile.twitter.com", "pic.twitter.com",
})


def safe_host(url: str) -> str:
    """Hostname of ``url``, or ``""`` if it cannot be parsed at all.

    Every ``urlparse`` in this module goes through here — the ValueError is
    raised by ``urlsplit`` itself, so any unguarded call is the same latent bug.
    """
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def urls_in_text(text: Optional[str], *, limit: int | None = 4) -> tuple[str, ...]:
    """Pull candidate site URLs out of free text such as a profile bio.

    Bios carry the link far more often than the ``website`` column does: 1,369
    of 7,588 stored bios contain a URL, against 230 populated website fields.
    Trailing punctuation is stripped because bios end sentences with the link.
    ``limit=None`` preserves all candidates for evidence projection, not display.
    """
    if not text:
        return ()
    found: list[str] = []
    for raw in _URL_IN_TEXT.findall(_unescape(text)):
        url = raw.rstrip(".,;:!?…")
        while url.endswith(")") and url.count("(") < url.count(")"):
            url = url[:-1]
        host = safe_host(url)
        if not host or host.removeprefix("www.") in _URL_STOP_HOSTS:
            continue
        if url not in found:
            found.append(url)
        if limit is not None and len(found) >= limit:
            break
    return tuple(found)


def normalize_bio_url(literal, scheme_assumed):
    """Normalize only a supplied mention; do not resolve DNS or fetch a site."""
    if not isinstance(literal, str) or type(scheme_assumed) is not bool:
        return None
    value = _unescape(literal)
    if not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    if scheme_assumed:
        if value.lower().startswith(('http:', 'https:')):
            return None
        value = 'https:' + value if value.startswith('//') else 'https://' + value
    elif not value.lower().startswith(('http://', 'https://')):
        return None
    else:
        explicit=urls_in_text(literal,limit=None)
        if len(explicit)!=1:return None
        value=explicit[0]
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        parsed.port  # Refuse malformed ports before they become clickable.
        if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password:
            return None
        if host.removeprefix('www.') in _URL_STOP_HOSTS or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            return None
        try:
            if not ip_address(host).is_global:
                return None
        except ValueError:
            # Browsers also interpret shortened/octal/hex numeric hosts as IPs.
            # Only canonical global IPs above or non-numeric DNS suffixes qualify.
            if '.' not in host or host.rsplit('.',1)[-1][:1].isdigit():
                return None
    except ValueError:
        return None
    return value


def bio_url_mentions(text):
    """Return qualified literal mentions; never turn an email into a web link."""
    if text is None:
        return []
    if not isinstance(text, str):
        raise ValueError('Stored profile bio must be text or unknown')
    with _lock:
        matches = _parser.match(text) or []
    explicit=list(_URL_IN_TEXT.finditer(text))
    candidates=[(match.start(),match.group(),False) for match in explicit]
    for match in matches:
        if match.schema not in ('','//'):continue
        if any(start.start()<match.last_index and match.index<start.end() for start in explicit):continue
        candidates.append((match.index,match.raw,True))
    mentions, seen = [], set()
    for _,literal,assumed in sorted(candidates,key=lambda item:item[0]):
        url = normalize_bio_url(literal, assumed)
        key = (url, literal, assumed)
        if url and key not in seen:
            mentions.append({'url': url, 'literal': literal, 'schemeAssumed': assumed})
            seen.add(key)
    return mentions
