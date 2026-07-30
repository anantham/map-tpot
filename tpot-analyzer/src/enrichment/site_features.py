"""Extract structured features from a fetched HTML page.

Pure functions only — HTML string in, features out. No network, no database.
The caller (``scripts/resolve_bio_links.py``) owns fetching via the existing
SSRF-guarded ``safe_urlopen``.

Why not reuse ``src/api/tweet_enrichment.fetch_link_content``: that helper is on
the live tweet-interpretation path and returns only title/description/body. Bio
links need images and outbound links too — the outbound links are the point,
because a personal site's links to GitHub/Substack/arXiv are affiliation and
competence evidence that the X follow graph structurally cannot contain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape as _unescape
from typing import Optional
from urllib.parse import urljoin, urlparse

# Platforms whose domain alone tells us what kind of page this is.
PLATFORM_DOMAINS: dict[str, str] = {
    "linktr.ee": "aggregator", "bio.link": "aggregator", "beacons.ai": "aggregator",
    "carrd.co": "aggregator", "linkin.bio": "aggregator", "solo.to": "aggregator",
    "substack.com": "newsletter", "buttondown.email": "newsletter",
    "ghost.io": "blog", "medium.com": "blog", "wordpress.com": "blog",
    "bearblog.dev": "blog", "mataroa.blog": "blog", "write.as": "blog",
    "blogspot.com": "blog", "tumblr.com": "blog", "posthaven.com": "blog",
    "github.io": "personal", "gitlab.io": "personal", "neocities.org": "personal",
    "notion.site": "personal", "super.site": "personal", "vercel.app": "personal",
    "netlify.app": "personal", "pages.dev": "personal",
    "patreon.com": "creator", "ko-fi.com": "creator", "gumroad.com": "creator",
    "youtube.com": "creator", "twitch.tv": "creator",
    "arxiv.org": "academic", "orcid.org": "academic", "scholar.google.com": "academic",
    "researchgate.net": "academic", "semanticscholar.org": "academic",
    "lesswrong.com": "community", "eaforum.org": "community",
    "goodreads.com": "community", "dharmaoverground.org": "community",
    "github.com": "code", "gitlab.com": "code", "huggingface.co": "code",
}

# Outbound destinations worth recording as identity / competence evidence.
SIGNAL_HOSTS: tuple[str, ...] = (
    "github.com", "gitlab.com", "huggingface.co", "kaggle.com",
    "substack.com", "medium.com", "lesswrong.com", "eaforum.org",
    "arxiv.org", "orcid.org", "scholar.google.com", "semanticscholar.org",
    "linkedin.com", "goodreads.com", "bsky.app", "mastodon.social",
    "patreon.com", "ko-fi.com", "buymeacoffee.com", "calendly.com",
    "dharmaoverground.org", "insighttimer.com", "meetup.com",
)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class SiteFeatures:
    """Everything we can learn from one page without an LLM."""

    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    site_name: Optional[str] = None
    og_type: Optional[str] = None
    og_image: Optional[str] = None
    images: tuple[str, ...] = ()
    outbound: tuple[str, ...] = ()
    signal_links: tuple[str, ...] = ()
    internal_paths: tuple[str, ...] = ()
    platform: Optional[str] = None
    text: str = ""
    feed_urls: tuple[str, ...] = ()
    meta: dict = field(default_factory=dict)

    @property
    def text_len(self) -> int:
        return len(self.text)

    @property
    def host(self) -> str:
        return safe_host(self.url).removeprefix("www.")


# Parens are deliberately allowed through: Wikipedia-style paths carry them
# legitimately, so the balance check below decides, not the character class.
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'‘’“”]+", re.I)
# Hosts that are never a personal site — X's own shorteners and the platforms
# we already have first-class edges for. Mining these adds noise, not evidence.
_URL_STOP_HOSTS = frozenset({
    "twitter.com", "x.com", "mobile.twitter.com", "pic.twitter.com",
})


def urls_in_text(text: Optional[str], *, limit: int = 4) -> tuple[str, ...]:
    """Pull candidate site URLs out of free text such as a profile bio.

    Bios carry the link far more often than the ``website`` column does: 1,369
    of 7,588 stored bios contain a URL, against 230 populated website fields.
    Trailing punctuation is stripped because bios end sentences with the link.
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
        if len(found) >= limit:
            break
    return tuple(found)


_REDIRECT_PATTERNS = (
    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*?url=([^"\']+)',
    r'location\.replace\(["\']([^"\']+)["\']\)',
    r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']',
)


def redirect_target(html: str, *, base: Optional[str] = None) -> Optional[str]:
    """Destination of a client-side redirect interstitial, if the page is one.

    ``t.co`` does not issue an HTTP 301 to browser user agents — it returns 200
    with a meta-refresh plus ``location.replace()``. Following redirects at the
    HTTP layer therefore silently fails to resolve, and worse, any error from the
    *destination* gets reported as "the shortener did not resolve".

    Reading the interstitial resolves the target without contacting the
    destination at all, so a dead or hostile destination still yields the URL the
    account actually pointed at — which is evidence in its own right.
    """
    if not html or len(html) > 8000:      # interstitials are tiny; real pages are not
        return None
    for pattern in _REDIRECT_PATTERNS:
        m = re.search(pattern, html, re.I)
        if not m:
            continue
        target = _unescape(m.group(1).strip()).replace("\\/", "/")
        if not target or target.startswith("#"):
            continue
        absolute = _safe_join(base, target) if base else target
        if absolute and safe_host(absolute):
            return absolute
    return None


def _meta(html: str, key: str) -> Optional[str]:
    """Read one meta tag, tolerating attribute order and quote style."""
    for pat in (
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]*?content=["\']([^"\']*)["\']',
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*?(?:property|name)=["\']{re.escape(key)}["\']',
    ):
        m = re.search(pat, html, re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def safe_host(url: str) -> str:
    """Hostname of ``url``, or ``""`` if it cannot be parsed at all.

    Every ``urlparse`` in this module goes through here — the ValueError is
    raised by ``urlsplit`` itself, so any unguarded call is the same latent bug.
    """
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _safe_join(base: str, href: str) -> Optional[str]:
    """``urljoin`` that survives hostile markup.

    ``urlsplit`` raises ``ValueError('Invalid IPv6 URL')`` on an href whose
    netloc contains an unbalanced ``[`` — real pages in the wild do this, and it
    crashed a 230-page run at item 119. A bad href is not worth an exception.
    """
    try:
        # Attributes arrive HTML-escaped: a query string reads "a=1&amp;b=2" in
        # the source. Left undecoded it corrupted 201 image URLs and 23 identity
        # links, which then 404 or fail TLS for no reason.
        return urljoin(base, _unescape(href))
    except ValueError:
        return None


def platform_for(url: str) -> Optional[str]:
    """Classify a URL by its host alone. Longest suffix wins."""
    host = safe_host(url)
    if not host:
        return None
    best: Optional[str] = None
    best_len = -1
    for domain, kind in PLATFORM_DOMAINS.items():
        if (host == domain or host.endswith("." + domain)) and len(domain) > best_len:
            best, best_len = kind, len(domain)
    return best


def visible_text(html: str, limit: int = 6000) -> str:
    """Strip markup and collapse whitespace. Drops script/style/nav chrome."""
    clean = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html,
                   flags=re.DOTALL | re.I)
    clean = re.sub(r"<!--.*?-->", " ", clean, flags=re.DOTALL)
    clean = _TAG.sub(" ", clean)
    clean = (clean.replace("&nbsp;", " ").replace("&amp;", "&")
             .replace("&quot;", '"').replace("&#39;", "'")
             .replace("&lt;", "<").replace("&gt;", ">"))
    return _WS.sub(" ", clean).strip()[:limit]


def extract(html: str, url: str, *, max_images: int = 8,
            max_links: int = 60) -> SiteFeatures:
    """Parse one page into :class:`SiteFeatures`. Never raises on bad markup."""
    title_tag = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
    title = _meta(html, "og:title") or (
        _WS.sub(" ", _TAG.sub("", title_tag.group(1))).strip() if title_tag else None)
    description = _meta(html, "og:description") or _meta(html, "description")
    og_image = _meta(html, "og:image")
    if og_image:
        og_image = _safe_join(url, og_image)

    images, seen_img = [], set()
    if og_image:
        images.append(og_image)
        seen_img.add(og_image)
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
        src = _safe_join(url, m.group(1).strip())
        if not src or src.startswith("data:") or src in seen_img:
            continue
        seen_img.add(src)
        images.append(src)
        if len(images) >= max_images:
            break

    host = safe_host(url)
    outbound, internal, seen_link = [], [], set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.I):
        href = m.group(1).strip()
        if href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = _safe_join(url, href)
        if not absolute or absolute in seen_link:
            continue
        seen_link.add(absolute)
        try:
            parsed = urlparse(absolute)
        except ValueError:
            continue
        target = (parsed.hostname or "").lower()
        if not target or target == host or target == "www." + host:
            path = parsed.path.rstrip("/")
            if path and path not in internal:
                internal.append(path)
        elif len(outbound) < max_links:
            outbound.append(absolute)

    signal = [u for u in outbound
              if any(h in safe_host(u) for h in SIGNAL_HOSTS)]

    feeds = [j for m in re.finditer(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.I) if (j := _safe_join(url, m.group(1)))]

    return SiteFeatures(
        url=url, title=title, description=description,
        site_name=_meta(html, "og:site_name"), og_type=_meta(html, "og:type"),
        og_image=og_image, images=tuple(images), outbound=tuple(outbound),
        signal_links=tuple(dict.fromkeys(signal)), internal_paths=tuple(internal[:40]),
        platform=platform_for(url), text=visible_text(html),
        feed_urls=tuple(dict.fromkeys(feeds)),
    )
