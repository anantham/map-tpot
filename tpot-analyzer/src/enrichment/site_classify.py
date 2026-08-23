"""Classify a bio link by what kind of page it is.

Pure scoring over :class:`SiteFeatures`. Deliberately *not* an LLM call: the
result must be auditable, so every verdict carries the reasons that produced it
and a human can see exactly which signal fired. Ambiguous pages return
``unknown`` rather than a confident guess — an abstention we can measure is
worth more than a label we cannot trust.

Nothing here decides community membership. It decides whether a URL is worth a
human's attention, and what kind of evidence it is likely to contain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .site_features import SiteFeatures

SITE_TYPES = (
    "personal", "blog", "newsletter", "portfolio", "academic",
    "company", "aggregator", "creator", "code", "community", "dead", "unknown",
)

# Phrases that mark a page as speaking for an organisation rather than a person.
_CORPORATE = (
    "our team", "our mission", "our customers", "our platform", "we build",
    "we help", "we're hiring", "we are hiring", "join our", "careers",
    "book a demo", "request a demo", "contact sales", "pricing",
    "all rights reserved", "terms of service", "privacy policy",
    "trusted by", "enterprise", "our clients", "case studies",
)
# Phrases that mark a page as speaking in a single human voice.
_FIRST_PERSON = (
    "about me", "i'm a ", "i am a ", "my name is", "my work", "my writing",
    "my projects", "i write", "i build", "i research", "i study",
    "things i", "my blog", "hi, i", "hello, i", "currently i",
)
_ACADEMIC = (
    "publications", "curriculum vitae", "google scholar", "phd student",
    "postdoc", "preprint", "peer-reviewed", "dissertation", "my research",
)
_BLOG_PATHS = ("/blog", "/posts", "/post", "/writing", "/essays", "/notes",
               "/archive", "/articles", "/journal")
_PORTFOLIO_PATHS = ("/projects", "/work", "/portfolio", "/case-studies", "/built")
_PERSONAL_PATHS = ("/about", "/now", "/uses", "/contact", "/me", "/colophon",
                   "/reading", "/bookshelf")
_DEAD = (
    "domain is for sale", "buy this domain", "parked", "coming soon",
    "under construction", "404 not found", "page not found",
    "this site can't be reached", "account suspended", "default web page",
)


@dataclass(frozen=True)
class SiteVerdict:
    site_type: str
    confidence: float
    reasons: tuple[str, ...]
    scores: dict
    person_signal: float
    is_reviewable: bool


def _hits(text: str, needles) -> list[str]:
    return [n for n in needles if n in text]


def _path_hits(paths, prefixes) -> list[str]:
    out = []
    for p in paths:
        low = p.lower()
        for pre in prefixes:
            if low == pre or low.startswith(pre + "/") or low.startswith(pre):
                out.append(p)
                break
    return out


def classify(f: SiteFeatures) -> SiteVerdict:
    """Score a page into one of :data:`SITE_TYPES` with auditable reasons."""
    text = (f.text or "").lower()
    title = (f.title or "").lower()
    blob = f"{title} {(f.description or '').lower()} {text}"
    scores: dict[str, float] = {t: 0.0 for t in SITE_TYPES}
    reasons: list[str] = []

    # --- dead / empty ------------------------------------------------------
    dead_hits = _hits(blob, _DEAD)
    if dead_hits:
        scores["dead"] += 6
        reasons.append(f"parked/error copy: {dead_hits[0]!r}")
    if f.text_len < 120 and not f.images and not f.outbound:
        scores["dead"] += 4
        reasons.append(f"almost no content ({f.text_len} chars, no images/links)")

    # --- platform domain is the strongest single signal --------------------
    if f.platform:
        scores[f.platform] = scores.get(f.platform, 0.0) + 5
        reasons.append(f"host is a known {f.platform} platform")

    # --- voice -------------------------------------------------------------
    corp = _hits(blob, _CORPORATE)
    first = _hits(blob, _FIRST_PERSON)
    if corp:
        scores["company"] += min(5.0, 1.6 * len(corp))
        reasons.append(f"organisational voice ×{len(corp)}: {', '.join(corp[:3])}")
    if first:
        scores["personal"] += min(5.0, 1.8 * len(first))
        reasons.append(f"first-person voice ×{len(first)}: {', '.join(first[:3])}")

    # --- structure ---------------------------------------------------------
    blog_paths = _path_hits(f.internal_paths, _BLOG_PATHS)
    port_paths = _path_hits(f.internal_paths, _PORTFOLIO_PATHS)
    pers_paths = _path_hits(f.internal_paths, _PERSONAL_PATHS)
    if blog_paths:
        scores["blog"] += min(4.0, 1.5 * len(blog_paths))
        reasons.append(f"writing sections: {', '.join(sorted(set(blog_paths))[:3])}")
    if f.feed_urls:
        scores["blog"] += 2.5
        reasons.append("publishes an RSS/Atom feed")
    if port_paths:
        scores["portfolio"] += min(3.5, 1.5 * len(port_paths))
        reasons.append(f"project sections: {', '.join(sorted(set(port_paths))[:3])}")
    if pers_paths:
        scores["personal"] += min(3.0, 1.2 * len(pers_paths))
        reasons.append(f"personal-site conventions: {', '.join(sorted(set(pers_paths))[:3])}")

    # --- academic ----------------------------------------------------------
    acad = _hits(blob, _ACADEMIC)
    if acad:
        scores["academic"] += min(4.0, 1.6 * len(acad))
        reasons.append(f"scholarly markers: {', '.join(acad[:3])}")

    # --- aggregator shape: many outbound, almost no prose ------------------
    if len(f.outbound) >= 5 and f.text_len < 700 and not f.internal_paths:
        scores["aggregator"] += 3.5
        reasons.append(f"link-list shape ({len(f.outbound)} outbound, {f.text_len} chars of text)")

    # --- outbound identity signals ----------------------------------------
    if f.signal_links:
        hosts = sorted({(h.split("/")[2] if "//" in h else h).replace("www.", "")
                        for h in f.signal_links})
        reasons.append(f"links out to {', '.join(hosts[:5])}")
        scores["personal"] += 1.0
        if any("github.com" in h or "huggingface" in h for h in hosts):
            scores["code"] += 1.5
        if any("arxiv" in h or "orcid" in h or "scholar" in h for h in hosts):
            scores["academic"] += 2.0

    # --- verdict -----------------------------------------------------------
    best = max(scores, key=lambda k: scores[k])
    top = scores[best]
    if top < 2.0:
        best, top = "unknown", top
        reasons.append("no signal cleared the threshold — needs a human look")

    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)
    confidence = 0.0 if best == "unknown" else round(
        min(0.95, 0.35 + 0.08 * top + 0.06 * margin), 2)

    # How much this page reads like one identifiable person, 0..1.
    person = scores["personal"] + scores["blog"] + scores["portfolio"] + scores["academic"]
    person_signal = round(max(0.0, min(1.0, (person - scores["company"]) / 8.0)), 2)

    reviewable = best not in ("dead",) and f.text_len >= 120

    return SiteVerdict(
        site_type=best, confidence=confidence, reasons=tuple(reasons),
        scores={k: round(v, 2) for k, v in scores.items() if v},
        person_signal=person_signal, is_reviewable=reviewable,
    )


def summarise(f: SiteFeatures, v: SiteVerdict, width: int = 220) -> str:
    """One-line human summary for the console and the review page."""
    bits = [f"{v.site_type}({v.confidence:.2f})"]
    if f.title:
        bits.append(re.sub(r"\s+", " ", f.title)[:70])
    if f.signal_links:
        bits.append(f"{len(f.signal_links)} identity links")
    if f.images:
        bits.append(f"{len(f.images)} img")
    return " · ".join(bits)[:width]
