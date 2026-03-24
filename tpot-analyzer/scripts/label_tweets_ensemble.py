"""
3-model LLM ensemble labeler for tweet community-evidence tagging.

Each tweet is independently labeled by 3 models via OpenRouter, then
a consensus is computed: 3/3 → median, 2/3 → conservative (lower),
1/3 → discarded.

Functions:
    parse_label_json   – robust JSON extraction from LLM output
    validate_bits      – check bits tags against known communities
    validate_simulacrum – check simulacrum distribution
    build_consensus    – merge 3 model outputs into one label
    build_prompt       – construct system+user prompt
    call_model         – POST to OpenRouter
    store_labels       – persist to tweet_tags / tweet_label_set / tweet_label_prob
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "x-ai/grok-4.1-fast",
    "deepseek/deepseek-v3.2",
    "google/gemini-3.1-flash-lite-preview",
]

# Hardcoded for tests; production should load from DB.
VALID_SHORT_NAMES: set[str] = {
    "AI-Creativity",
    "AI-Safety",
    "Collective-Intelligence",
    "Contemplative-Practitioners",
    "Core-TPOT",
    "Internet-Intellectuals",
    "LLM-Whisperers",
    "NYC-Institution-Builders",
    "Qualia-Research",
    "Queer-TPOT",
    "Quiet-Creatives",
    "Relational-Explorers",
    "Tech-Intellectuals",
    "TfT-Coordination",
    "highbies",
}


def load_short_names_from_db(db_path: str) -> set[str]:
    """Load community short_names from the archive_tweets database."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT short_name FROM community").fetchall()
        return {r[0] for r in rows if r[0]}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Parsing
# ═══════════════════════════════════════════════════════════════════════════


def parse_label_json(raw: str) -> Optional[dict]:
    """Parse LLM output into a structured dict.

    Handles:
      - Clean JSON
      - JSON wrapped in markdown fences (```json ... ```)
      - Nested/doubled fences
      - Regex fallback to extract first JSON object
    Returns None on failure (never raises).
    """
    if not raw or not raw.strip():
        return None

    # Strategy 1: direct parse
    try:
        return json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: strip markdown fences (possibly nested)
    stripped = raw.strip()
    # Remove outer fences repeatedly
    for _ in range(3):
        match = re.match(r"^```(?:json)?\s*\n?([\s\S]*?)\n?\s*```$", stripped)
        if match:
            stripped = match.group(1).strip()
        else:
            break
    if stripped != raw.strip():
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: regex fallback – find first { ... } block
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════


def validate_bits(bits_list: list[str], valid_names: set[str]) -> list[str]:
    """Validate bits tags against format ``bits:ShortName:+/-N``.

    Returns list of error strings (empty means all valid).
    """
    errors: list[str] = []
    for tag in bits_list:
        if not tag.startswith("bits:"):
            errors.append(f"Missing 'bits:' prefix: {tag}")
            continue

        parts = tag.split(":")
        if len(parts) != 3:
            errors.append(f"Expected 3 colon-separated parts: {tag}")
            continue

        _, community, value_str = parts

        if community not in valid_names:
            errors.append(f"Unknown community '{community}' in: {tag}")
            continue

        # Value must be an integer (possibly with +/- prefix)
        try:
            int(value_str)
        except ValueError:
            errors.append(f"Non-integer value '{value_str}' in: {tag}")

    return errors


def validate_simulacrum(sim_dict: dict) -> list[str]:
    """Check that l1-l4 are present, numeric, and sum to ~1.0 (0.95–1.05)."""
    errors: list[str] = []
    required = {"l1", "l2", "l3", "l4"}
    present = set(sim_dict.keys()) if isinstance(sim_dict, dict) else set()
    missing = required - present

    if missing:
        errors.append(f"Missing simulacrum keys: {sorted(missing)}")
        return errors  # can't check sum if keys missing

    for key in required:
        val = sim_dict[key]
        if not isinstance(val, (int, float)):
            errors.append(f"Non-numeric simulacrum value for {key}: {val}")
            return errors

    total = sum(sim_dict[k] for k in required)
    if not (0.95 <= total <= 1.05):
        errors.append(f"Simulacrum sum {total:.4f} outside [0.95, 1.05]")

    return errors


# ═══════════════════════════════════════════════════════════════════════════
# Consensus
# ═══════════════════════════════════════════════════════════════════════════


def _parse_bits_tag(tag: str) -> tuple[str, int] | None:
    """Parse ``bits:ShortName:+N`` → (ShortName, N) or None."""
    parts = tag.split(":")
    if len(parts) != 3 or parts[0] != "bits":
        return None
    try:
        return (parts[1], int(parts[2]))
    except ValueError:
        return None


def build_consensus(label_dicts: list[dict]) -> dict:
    """Merge outputs from multiple models into a single consensus label.

    Bits consensus:
      - 3/3 models → median value
      - 2/3 models → lower of the two values (conservative)
      - 1/3 models → discarded
    Themes/domains/postures: union across all models.
    Simulacrum: element-wise average.
    """
    n = len(label_dicts)

    # --- Bits consensus ---
    # community → list of integer values across models
    community_values: dict[str, list[int]] = {}
    for ld in label_dicts:
        for tag in ld.get("bits", []):
            parsed = _parse_bits_tag(tag)
            if parsed:
                community, val = parsed
                community_values.setdefault(community, []).append(val)

    consensus_bits: list[str] = []
    for community, values in sorted(community_values.items()):
        count = len(values)
        if count >= 3:
            # 3/3 → median
            med = int(statistics.median(values))
            sign = f"+{med}" if med >= 0 else str(med)
            consensus_bits.append(f"bits:{community}:{sign}")
        elif count == 2:
            # 2/3 → conservative (lower absolute? spec says lower of the two)
            lower = min(values)
            sign = f"+{lower}" if lower >= 0 else str(lower)
            consensus_bits.append(f"bits:{community}:{sign}")
        # count == 1 → discard

    # --- Union of set-type fields ---
    themes: set[str] = set()
    domains: set[str] = set()
    postures: set[str] = set()
    new_community_signals: set[str] = set()

    for ld in label_dicts:
        themes.update(ld.get("themes", []))
        domains.update(ld.get("domains", []))
        postures.update(ld.get("postures", []))
        new_community_signals.update(ld.get("new_community_signals", []))

    # --- Averaged simulacrum ---
    sim_keys = ["l1", "l2", "l3", "l4"]
    avg_sim: dict[str, float] = {}
    for key in sim_keys:
        vals = [ld["simulacrum"][key] for ld in label_dicts if "simulacrum" in ld and key in ld.get("simulacrum", {})]
        if vals:
            avg_sim[key] = round(sum(vals) / len(vals), 4)
        else:
            avg_sim[key] = 0.0

    # --- Notes: concatenate non-empty ---
    notes = [ld.get("note", "") for ld in label_dicts if ld.get("note")]
    combined_note = " | ".join(notes) if notes else ""

    # --- Signal strength: majority vote ---
    strengths = [ld.get("signal_strength", "medium") for ld in label_dicts]
    signal_strength = max(set(strengths), key=strengths.count)

    return {
        "bits": consensus_bits,
        "themes": sorted(themes),
        "domains": sorted(domains),
        "postures": sorted(postures),
        "simulacrum": avg_sim,
        "note": combined_note,
        "signal_strength": signal_strength,
        "new_community_signals": sorted(new_community_signals),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Prompt construction
# ═══════════════════════════════════════════════════════════════════════════


def _load_glossary() -> dict | None:
    """Load community glossary from config file if available."""
    glossary_path = Path(__file__).resolve().parents[1] / "config" / "community_glossary.json"
    if glossary_path.exists():
        import json as _json
        with open(glossary_path) as f:
            return _json.load(f)
    return None


_GLOSSARY_CACHE: dict | None = None


def _get_glossary() -> dict | None:
    global _GLOSSARY_CACHE
    if _GLOSSARY_CACHE is None:
        _GLOSSARY_CACHE = _load_glossary()
    return _GLOSSARY_CACHE


def build_prompt(
    username: str,
    bio: str,
    graph_signal: str,
    other_tweets: str,
    tweet_text: str,
    engagement: str,
    mentions: str,
    engagement_context: str,
    community_descriptions: dict[str, str],
    community_short_names: list[str],
) -> str:
    """Build the combined system+user prompt for a single tweet labeling call.

    If config/community_glossary.json exists, uses its rich descriptions,
    emerging clusters, themes, anti-patterns, and account calibrations.
    Falls back to basic community descriptions if glossary not available.
    """
    glossary = _get_glossary()

    if glossary and "communities" in glossary:
        # Rich prompt from glossary
        community_block_lines = []
        for name in community_short_names:
            g = glossary["communities"].get(name, {})
            if isinstance(g, dict):
                look_for = g.get("look_for", community_descriptions.get(name, ""))
                not_this = g.get("not_this", "")
                line = f"  - {name}: {look_for}"
                if not_this:
                    line += f"\n    NOT: {not_this}"
                community_block_lines.append(line)
            else:
                community_block_lines.append(f"  - {name}: {community_descriptions.get(name, g)}")
        community_block = "\n".join(community_block_lines)

        # Emerging clusters
        emerging = glossary.get("emerging_clusters", {})
        emerging_lines = []
        for name, desc in emerging.items():
            if name.startswith("_"):
                continue
            emerging_lines.append(f"  - {name}: {desc[:120]}")
        emerging_block = "\n".join(emerging_lines)

        # Canonical themes
        themes_data = glossary.get("themes", {})
        established_themes = themes_data.get("established", [])
        new_themes = themes_data.get("new_from_audit", [])
        theme_list = ", ".join(established_themes[:15] + new_themes[:10])

        # Anti-patterns
        anti = glossary.get("anti_patterns", {})
        anti_lines = []
        for name, desc in anti.items():
            if name.startswith("_"):
                continue
            anti_lines.append(f"  - {desc}")
        anti_block = "\n".join(anti_lines)

        # Dedup rules
        dedup = themes_data.get("do_not_duplicate", {})
        dedup_lines = []
        for canonical, dupes in dedup.items():
            if canonical.startswith("_"):
                continue
            dedup_lines.append(f"  - {canonical} (NOT: {', '.join(dupes[:3])}...)")
        dedup_block = "\n".join(dedup_lines)

    else:
        # Fallback: basic descriptions
        community_block_lines = []
        for name in community_short_names:
            desc = community_descriptions.get(name, "(no description)")
            community_block_lines.append(f"  - {name}: {desc}")
        community_block = "\n".join(community_block_lines)
        emerging_block = ""
        theme_list = ""
        anti_block = ""
        dedup_block = ""

    system_prompt = f"""\
You are a community-evidence tagger for the TPOT (This Part Of Twitter) ecosystem.

COMMUNITIES (use these short_names for bits:ShortName:+N tags):
{community_block}

{"EMERGING CLUSTERS (use new-community-signal:Name for these ONLY):" + chr(10) + emerging_block if emerging_block else ""}

BITS SCALE (per-tweet, prior-independent):
  +1 = weak signal (could be coincidence)
  +2 = moderate signal (intentional alignment)
  +3 = strong signal (core topic/style)
  +4 = diagnostic (almost uniquely identifies this community)
  Negative values indicate counter-evidence (-1 to -4, same scale inverted).

{"CANONICAL THEMES (prefer these over inventing new ones):" + chr(10) + "  " + theme_list if theme_list else ""}

{"TAG DEDUPLICATION (use ONLY the canonical form):" + chr(10) + dedup_block if dedup_block else ""}

RULES:
  - EVERY non-noise tweet MUST have at least 2 bits assignments.
  - Bits are per-TWEET evidence, independent of any prior community assignment.
  - Engagement context (likes, replies) is independent evidence — use it.
  - Return ONLY a JSON object, no commentary.
  - If the tweet is a RETWEET (starts with "RT @"), assign bits with REDUCED confidence
    (-1 from what you'd normally give). Retweets signal interest, not identity.

{"AVOID THESE MISTAKES:" + chr(10) + anti_block if anti_block else ""}

NEW-COMMUNITY SIGNALS:
  - Do NOT create new-community-signal for things that match existing communities.
  - Only use names from the EMERGING CLUSTERS list above, or genuinely novel clusters.

OUTPUT FORMAT (JSON):
{{
  "bits": ["bits:CommunityName:+N", ...],
  "themes": ["theme:descriptor", ...],
  "domains": ["domain:descriptor", ...],
  "postures": ["posture:descriptor", ...],
  "simulacrum": {{"l1": float, "l2": float, "l3": float, "l4": float}},
  "note": "brief interpretive note",
  "signal_strength": "high|medium|low",
  "new_community_signals": ["new-community-signal:Name", ...]
}}

Simulacrum levels must sum to ~1.0:
  l1 = propositional truth-seeking
  l2 = social positioning / group signaling
  l3 = aesthetic / narrative / vibe
  l4 = pure memetic / absurdist
"""

    user_prompt = f"""\
ACCOUNT: @{username}
BIO: {bio}
GRAPH SIGNAL: {graph_signal}
OTHER TWEETS: {other_tweets}

TWEET TEXT:
{tweet_text}

ENGAGEMENT: {engagement}
MENTIONS: {mentions}
ENGAGEMENT CONTEXT: {engagement_context}
"""

    return system_prompt + "\n---\n\n" + user_prompt


# ═══════════════════════════════════════════════════════════════════════════
# OpenRouter API
# ═══════════════════════════════════════════════════════════════════════════


def call_model(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
) -> str:
    """POST to OpenRouter and return the raw content string.

    Raises httpx.HTTPStatusError on non-2xx responses.
    """
    resp = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════════════════
# Storage
# ═══════════════════════════════════════════════════════════════════════════


def store_labels(
    conn: sqlite3.Connection,
    tweet_id: str,
    label_dict: dict,
    reviewer: str,
) -> None:
    """Persist a label dict to tweet_tags, tweet_label_set, and tweet_label_prob.

    Tables written:
      tweet_tags      – one row per tag (bits, thematic, domain, posture, new-community)
      tweet_label_set – one row linking tweet to axis/reviewer/note
      tweet_label_prob – one row per simulacrum level (l1–l4)
    """
    now = datetime.now(timezone.utc).isoformat()

    # --- tweet_tags ---
    tag_rows: list[tuple[str, str, str, str, str]] = []

    for tag in label_dict.get("bits", []):
        tag_rows.append((tweet_id, tag, "bits", reviewer, now))
    for tag in label_dict.get("themes", []):
        tag_rows.append((tweet_id, tag, "thematic", reviewer, now))
    for tag in label_dict.get("domains", []):
        tag_rows.append((tweet_id, tag, "domain", reviewer, now))
    for tag in label_dict.get("postures", []):
        tag_rows.append((tweet_id, tag, "posture", reviewer, now))
    for tag in label_dict.get("new_community_signals", []):
        tag_rows.append((tweet_id, tag, "new-community", reviewer, now))

    conn.executemany(
        "INSERT OR IGNORE INTO tweet_tags (tweet_id, tag, category, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
        tag_rows,
    )

    # --- tweet_label_set ---
    # Check if already labeled (idempotent re-runs)
    existing = conn.execute(
        "SELECT id FROM tweet_label_set WHERE tweet_id = ? AND axis = ? AND reviewer = ?",
        (tweet_id, "active_learning", reviewer),
    ).fetchone()
    if existing:
        return  # already labeled, skip

    cursor = conn.execute(
        "INSERT INTO tweet_label_set (tweet_id, axis, reviewer, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (tweet_id, "active_learning", reviewer, label_dict.get("note", ""), now),
    )
    label_set_id = cursor.lastrowid

    # --- tweet_label_prob ---
    sim = label_dict.get("simulacrum", {})
    prob_rows = [(label_set_id, level, sim.get(level, 0.0)) for level in ("l1", "l2", "l3", "l4")]
    conn.executemany(
        "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
        prob_rows,
    )

    conn.commit()
