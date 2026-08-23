"""Describe a site's main image with a local vision model.

Runs against the ollama server already on this machine (``:11434``), so there is
no API spend and no data leaves the box — which matters, because these are real
people's personal pages.

Scope discipline: this is a *second opinion*, never an override. The text
classifier's verdict and the vision verdict are stored separately with their own
provenance, because "the HTML says company" and "the picture shows one person"
are different claims and collapsing them would hide disagreement — the same
mistake the project already made by calling five different quantities
"membership".

Vision earns its cost only where text failed: 386 pages classify as ``unknown``
and 333 of those have an image. Captioning all ~1,150 successful fetches would
mostly produce "a logo" over and over.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Optional

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"

IMAGE_KINDS = (
    "portrait", "group-photo", "product-ui", "logo", "artwork",
    "landscape", "diagram", "text-card", "screenshot", "other",
)
SUGGESTS = ("personal", "company", "creator", "academic", "unclear")

PROMPT = """You are shown the main image from a website that belongs to a person or an organisation.

Return ONLY a JSON object, no prose:
{"caption": "<one factual sentence>",
 "kind": "<portrait|group-photo|product-ui|logo|artwork|landscape|diagram|text-card|screenshot|other>",
 "shows_person": <true|false>,
 "visible_text": "<legible text in the image, or empty string>",
 "suggests": "<personal|company|creator|academic|unclear>",
 "confidence": <0.0-1.0>}

Rules:
- Describe only what you can see. Do not guess who the person is or name them.
- A bare logo, wordmark, stock photo or generic social-share card suggests nothing: use "unclear".
- "personal" requires a human portrait or an obviously individual, hand-made page.
- "company" requires product UI, team photos, or corporate branding.
- "creator" fits original artwork, music, illustration or craft.
- "academic" fits papers, charts, lab or conference imagery.
- Prefer "unclear" over a weak guess."""


@dataclass(frozen=True)
class ImageVerdict:
    caption: str
    kind: str
    shows_person: bool
    visible_text: str
    suggests: str
    confidence: float
    model: str
    error: Optional[str] = None

    @property
    def is_informative(self) -> bool:
        """True when the image actually carries signal about who this is.

        An empty caption disqualifies the row no matter what confidence the model
        reports: gemma4 was observed returning ``confidence: 1.0`` alongside an
        empty description, which is confident emptiness, not evidence.
        """
        return (self.error is None
                and bool(self.caption.strip())
                and self.suggests != "unclear"
                and self.confidence >= 0.5)


def _clip(value: str, allowed: tuple[str, ...], fallback: str) -> str:
    v = (value or "").strip().lower()
    return v if v in allowed else fallback


def parse_verdict(raw: str, *, model: str = DEFAULT_MODEL) -> ImageVerdict:
    """Parse a model reply into an :class:`ImageVerdict`. Never raises.

    Small local models wrap JSON in prose or fences despite instructions, so the
    first balanced object in the reply is extracted rather than trusting the
    whole string to parse.
    """
    if not raw or not raw.strip():
        return ImageVerdict("", "other", False, "", "unclear", 0.0, model,
                            error="empty reply")
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return ImageVerdict("", "other", False, "", "unclear", 0.0, model,
                            error=f"unparseable reply: {text[:80]}")

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    shows = data.get("shows_person")
    if isinstance(shows, str):
        shows = shows.strip().lower() in ("true", "yes", "1")

    return ImageVerdict(
        caption=str(data.get("caption") or "").strip()[:400],
        kind=_clip(str(data.get("kind", "")), IMAGE_KINDS, "other"),
        shows_person=bool(shows),
        visible_text=str(data.get("visible_text") or "").strip()[:300],
        suggests=_clip(str(data.get("suggests", "")), SUGGESTS, "unclear"),
        confidence=max(0.0, min(1.0, confidence)),
        model=model,
    )


def describe(image_b64: str, *, model: str = DEFAULT_MODEL,
             host: str = OLLAMA_HOST, timeout: int = 120) -> ImageVerdict:
    """Caption one image. ``image_b64`` may be raw base64 or a data: URL."""
    payload = image_b64.split(",", 1)[1] if image_b64.startswith("data:") else image_b64
    body = json.dumps({
        "model": model, "prompt": PROMPT, "images": [payload],
        "stream": False, "format": "json",
        "options": {"temperature": 0.1, "num_predict": 400},
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            reply = json.loads(resp.read()).get("response", "")
    except Exception as exc:  # noqa: BLE001 — surfaced, never swallowed
        return ImageVerdict("", "other", False, "", "unclear", 0.0, model,
                            error=f"{type(exc).__name__}: {exc}"[:160])
    return parse_verdict(reply, model=model)


def reconcile(site_type: str, site_confidence: float,
              verdict: ImageVerdict) -> tuple[str, str]:
    """Combine the text verdict with the image verdict without hiding conflict.

    Returns ``(status, note)`` where status is one of ``agree``, ``resolves``,
    ``conflict`` or ``no-signal``. Nothing is silently overwritten: a conflict
    stays visible so a human can adjudicate it.
    """
    if not verdict.is_informative:
        return "no-signal", "image carries no identity signal"
    person_like = {"personal", "blog", "portfolio", "academic"}
    image_person = verdict.suggests in {"personal", "academic", "creator"}
    site_person = site_type in person_like

    if site_type == "unknown":
        return "resolves", f"text was undecided; image suggests {verdict.suggests}"
    if site_person == image_person:
        return "agree", f"image agrees ({verdict.suggests})"
    if site_confidence < 0.55:
        return "resolves", (f"text weakly said {site_type}; "
                            f"image suggests {verdict.suggests}")
    return "conflict", (f"text says {site_type} ({site_confidence:.2f}) but "
                        f"image suggests {verdict.suggests} — needs a human")


ENSEMBLE_MODELS = ("qwen2.5vl:7b", "gemma4:latest")


@dataclass(frozen=True)
class Consensus:
    """Agreement across independent vision models."""

    suggests: str
    agreement: str            # unanimous | majority | split | single | none
    voters: int
    informative: int
    captions: tuple[str, ...]
    note: str

    @property
    def is_trustworthy(self) -> bool:
        """Only unanimous multi-model agreement counts as a usable signal.

        A model's self-reported confidence is not evidence — gemma4 returned
        ``1.0`` on an empty caption. Independent agreement is, which is why this
        gates on voters rather than on confidence, mirroring the 2-of-3 consensus
        rule already used by ``scripts/label_tweets_ensemble.py``.
        """
        return self.agreement in ("unanimous", "majority") and self.voters >= 2


def consensus(verdicts: "list[ImageVerdict]") -> Consensus:
    """Combine independent model verdicts. Disagreement is preserved, not averaged."""
    usable = [v for v in verdicts if v.is_informative]
    captions = tuple(v.caption for v in usable if v.caption)
    if not usable:
        return Consensus("unclear", "none", 0, 0, captions,
                         "no model produced a usable verdict")
    tally: dict[str, int] = {}
    for v in usable:
        tally[v.suggests] = tally.get(v.suggests, 0) + 1
    top = max(tally, key=lambda k: tally[k])
    votes = tally[top]

    if len(usable) == 1:
        return Consensus(top, "single", 1, 1, captions,
                         f"only {usable[0].model} had a view — weak signal")
    if votes == len(usable):
        return Consensus(top, "unanimous", len(usable), len(usable), captions,
                         f"{len(usable)} models independently agree: {top}")
    if votes > len(usable) / 2:
        return Consensus(top, "majority", len(usable), len(usable), captions,
                         f"{votes}/{len(usable)} say {top}")
    disagreement = ", ".join(f"{v.model}={v.suggests}" for v in usable)
    return Consensus("unclear", "split", len(usable), len(usable), captions,
                     f"models disagree ({disagreement}) — needs a human")
