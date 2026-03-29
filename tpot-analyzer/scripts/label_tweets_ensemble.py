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
    # Promoted emerging clusters (ontology birth)
    "Open-Source-AI",
    "AI-Mystics",
    "d-acc-Builders",
    # Explicit non-TPOT classification
    "None",
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
            # 2/3 → conservative (lower of the two)
            lower = min(values)
            sign = f"+{lower}" if lower >= 0 else str(lower)
            consensus_bits.append(f"bits:{community}:{sign}")
        elif count == 1:
            # 1/3 → preserve at +1 max (weak signal, not discarded)
            # Prevents total information loss when models map to different
            # communities for the same domain (e.g., Open-Source-AI emerging)
            val = min(abs(values[0]), 1)  # cap at 1
            if val > 0:
                consensus_bits.append(f"bits:{community}:+{val}")

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
    content_profile: str = "",
    engagement_partners: str = "",
    mention_communities: str = "",
    rt_source: str = "",
    reply_communities: str = "",
    cofollowed: str = "",
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

    # Select top 6 emerging clusters (not all 13)
    top_emerging = []
    if glossary:
        emerging = glossary.get("emerging_clusters", {})
        # Prioritize the strongest signals
        priority = ["AI-Mystics", "Open-Source-AI", "d/acc-Builders", "Psychonauts", "Somatic-Coaching", "Post-Rationalist", "Girardian-Memetics"]
        for name in priority:
            if name in emerging:
                top_emerging.append(f"  - {name}: {emerging[name][:100]}")
        emerging_block = "\n".join(top_emerging[:6])
    else:
        emerging_block = ""

    # Detect if this tweet is a retweet
    is_rt = tweet_text.strip().startswith("RT @")

    system_prompt = f"""\
You are a precise community-evidence tagger for TPOT (This Part Of Twitter).
Tag THIS SPECIFIC TWEET only. Ignore what you know about the account — read the tweet text.

COMMUNITIES:
{community_block}

BITS: +1=weak, +2=moderate, +3=strong, +4=diagnostic (nearly uniquely identifies community).
  Assign 0-4 bits tags per tweet. Simple/ambiguous tweets may get 0-1. Do NOT force bits.
  +4 should be rare — tweets incomprehensible outside that specific community.

{"EMERGING (use new-community-signal:Name, only if clearly novel):" + chr(10) + emerging_block if emerging_block else ""}

CRITICAL RULES:
  - Tag THIS TWEET, not the account. Ignore bio/graph when assigning bits.
  - Pure retweets ("RT @someone: ...") get AT MOST one weak bit (+1) for interest. Do not tag the original author's community as the retweeter's identity.
  - Core-TPOT requires the STYLE (absurdist humor, personal essay, divine absurdity). Smart tweets ≠ Core-TPOT.
  - "institutions" ≠ NYC-Institution-Builders (that's literal NYC housing/schools).
  - "collective intelligence" as phrase ≠ Collective-Intelligence (that's DAOs/regen).
  - "mind"/"brain" ≠ Qualia-Research (that's consciousness geometry/valence formalism).
  - Mentioning AI tools by name (Claude, GPT, Gemini, Copilot, Cursor) ≠ LLM-Whisperers. LLM-Whisperers probe model PSYCHOLOGY — seeing agency, interiority, recursive self-awareness. Using AI as a productivity tool is neutral — 0 bits.
  - bits:None:+N means "this tweet is clearly NOT TPOT — mainstream tech, crypto finance, generic news, corporate AI." Use None when the content belongs to an adjacent ecosystem, not any TPOT community.

ADJACENT ECOSYSTEMS (assign bits:None:+2 or +3):
  Mainstream-AI-Twitter (benchmark results, corporate AI announcements), Crypto-Finance, Political-Commentary, Generic-Self-Help, Hustle-Culture, News-Media.

SUB-COMMUNITY FACETS (tag as theme:facet-name when you see them):
  Within AI-Safety: alignment-theory, mech-interp, agent-foundations, ai-governance, pause-ai, e-acc, d-acc, s-risk, forecasting, field-building
  Within Contemplative: jhana-practice, somatic-healing, nondual, psychedelic-integration, contemplative-science
  Within LLM-Whisperers: model-interiority, prompt-sorcery, open-source-ai, ai-art
  These are THEMES, not separate communities. Tag them alongside community bits to capture fine-grained signals.

FEW-SHOT EXAMPLES:

Tweet: "haha, it's like there's a little person in there!"
{{"bits": ["bits:LLM-Whisperers:+3"], "domains": ["domain:AI"], "themes": ["theme:model-interiority"], "postures": ["posture:playful-exploration"], "simulacrum": {{"l1": 0.2, "l2": 0.1, "l3": 0.4, "l4": 0.3}}, "signal_strength": "high", "note": "Anthropomorphizing AI — seeing agency in model output. Core LLM Whisperer move.", "new_community_signals": []}}

Tweet: "the fundamental problem with nonalcoholic cocktails is that you need something slightly repulsive in the drink to sip slowly. thats why i started putting creatine in mine"
{{"bits": ["bits:highbies:+3", "bits:Core-TPOT:+1"], "domains": ["domain:social"], "themes": ["theme:absurdist-humor"], "postures": ["posture:original-insight", "posture:playful-exploration"], "simulacrum": {{"l1": 0.35, "l2": 0.05, "l3": 0.4, "l4": 0.2}}, "signal_strength": "high", "note": "Viral observational humor with biohacking twist. Peak highbie.", "new_community_signals": []}}

Tweet: "RT @NousResearch: Did you feel that vibe shift anon? Open Source is in the air."
{{"bits": ["bits:LLM-Whisperers:+1"], "domains": ["domain:AI"], "themes": [], "postures": ["posture:signal-boost"], "simulacrum": {{"l1": 0.1, "l2": 0.3, "l3": 0.5, "l4": 0.1}}, "signal_strength": "low", "note": "Pure RT of org. Signals interest only.", "new_community_signals": []}}

Tweet: "Mad respect for Hofstadter for: updating instead of rationalizing, not shrinking from implications, being honest about uncertainty"
{{"bits": ["bits:AI-Safety:+3", "bits:Core-TPOT:+1"], "domains": ["domain:AI", "domain:philosophy"], "themes": ["theme:epistemic-practice"], "postures": ["posture:original-insight"], "simulacrum": {{"l1": 0.7, "l2": 0.1, "l3": 0.15, "l4": 0.05}}, "signal_strength": "high", "note": "Praising intellectual honesty on AI risk.", "new_community_signals": []}}

Tweet: "As a woman raised by codependents/narcissists I am a well trained approval seeker. Like a blank canvas available to be painted upon..."
{{"bits": ["bits:Relational-Explorers:+3", "bits:Contemplative-Practitioners:+2"], "domains": ["domain:personal", "domain:social"], "themes": ["theme:self-transformation", "theme:embodiment"], "postures": ["posture:personal-testimony"], "simulacrum": {{"l1": 0.6, "l2": 0.1, "l3": 0.25, "l4": 0.05}}, "signal_strength": "high", "note": "Codependency as sacred research. Somatic awareness.", "new_community_signals": []}}

Tweet: "NeuralKey: Proof of Personhood using Brainwaves. In my talk @zuitzerland, I explored this possibility."
{{"bits": ["bits:Tech-Intellectuals:+2"], "domains": ["domain:technical"], "themes": ["theme:d/acc", "theme:proof-of-personhood"], "postures": ["posture:original-insight"], "simulacrum": {{"l1": 0.5, "l2": 0.3, "l3": 0.15, "l4": 0.05}}, "signal_strength": "medium", "note": "d/acc builder shipping decentralized identity.", "new_community_signals": ["new-community-signal:d/acc-Builders"]}}

Tweet: "My mom and my dad both live on in me, And they were a really bad match for each other, Which now means that I have to somehow fix their marriage, inside myself, or have their dynamic repeated in me for the rest of my life"
{{"bits": ["bits:Quiet-Creatives:+3", "bits:Relational-Explorers:+3"], "domains": ["domain:personal"], "themes": ["theme:self-transformation", "theme:embodiment"], "postures": ["posture:personal-testimony"], "simulacrum": {{"l1": 0.5, "l2": 0.05, "l3": 0.4, "l4": 0.05}}, "signal_strength": "high", "note": "Personal crisis as art — internalizing parental dynamics, inner work as life's hardest task. Paper-and-flame energy.", "new_community_signals": []}}

Tweet: "The reason to avoid lying is that the brain is not type safe. Lying to others and lying to yourself are the same motion."
{{"bits": ["bits:Contemplative-Practitioners:+3"], "domains": ["domain:philosophy"], "themes": ["theme:epistemic-practice", "theme:contemplative-practice"], "postures": ["posture:original-insight"], "simulacrum": {{"l1": 0.7, "l2": 0.05, "l3": 0.2, "l4": 0.05}}, "signal_strength": "high", "note": "CS type-safety metaphor for meditation/integrity insight. Technical vocabulary applied to contemplative truth.", "new_community_signals": []}}

Tweet: "more evidence for the mushrooms are trying to make more mushrooms theory. almost everyone i know who has a great mushrooms trip eventually starts planting mushrooms. turns out they also try to make fewer humans"
{{"bits": ["bits:highbies:+3", "bits:Contemplative-Practitioners:+1"], "domains": ["domain:science", "domain:social"], "themes": ["theme:psychedelic-phenomenology", "theme:absurdist-humor"], "postures": ["posture:playful-exploration"], "simulacrum": {{"l1": 0.3, "l2": 0.05, "l3": 0.35, "l4": 0.3}}, "signal_strength": "high", "note": "Absurdist evolutionary biology of psychedelics. Highbie humor + psychonaut signal.", "new_community_signals": ["new-community-signal:Psychonauts"]}}

Tweet: "Claude Code just saved me 2 hours on this refactor, the future is now"
{{"bits": [], "domains": ["domain:technical"], "themes": [], "postures": ["posture:signal-boost"], "simulacrum": {{"l1": 0.3, "l2": 0.4, "l3": 0.2, "l4": 0.1}}, "signal_strength": "low", "note": "Tool usage — NOT LLM-Whisperers (no model psychology, just productivity). 0 bits.", "new_community_signals": []}}

Tweet: "Just hit 100M ARR. Grateful for the team. The future of enterprise AI is here."
{{"bits": ["bits:None:+3"], "domains": ["domain:technical"], "themes": [], "postures": ["posture:signal-boost"], "simulacrum": {{"l1": 0.2, "l2": 0.6, "l3": 0.1, "l4": 0.1}}, "signal_strength": "high", "note": "Corporate AI announcement. Adjacent ecosystem — not TPOT.", "new_community_signals": []}}

TRICKY EXAMPLES (common misclassifications — learn the boundaries):

Tweet: "Building institutions that outlast founders: lessons from monasteries to startups"
{{"bits": ["bits:Tech-Intellectuals:+2"], "domains": ["domain:social"], "themes": ["theme:field-building"], "postures": ["posture:original-insight"], "simulacrum": {{"l1": 0.6, "l2": 0.2, "l3": 0.15, "l4": 0.05}}, "signal_strength": "medium", "note": "Abstract institutional riff — NOT NYC-Institution-Builders (that's literal NYC housing/schools). Tech-Intellectuals bridging history+systems.", "new_community_signals": []}}

Tweet: "10min guided meditation to crush my todo list—productivity unlocked 🧘‍♂️"
{{"bits": [], "domains": ["domain:personal"], "themes": [], "postures": ["posture:signal-boost"], "simulacrum": {{"l1": 0.2, "l2": 0.5, "l3": 0.2, "l4": 0.1}}, "signal_strength": "low", "note": "Hustle-culture wellness — NOT Contemplative-Practitioners (who treat consciousness as laboratory, not productivity tool). 0 bits.", "new_community_signals": []}}

Tweet: "Bees pulling off collective intelligence better than any DAO—nature wins again"
{{"bits": ["bits:highbies:+2"], "domains": ["domain:science"], "themes": ["theme:absurdist-humor"], "postures": ["posture:playful-exploration"], "simulacrum": {{"l1": 0.3, "l2": 0.1, "l3": 0.4, "l4": 0.2}}, "signal_strength": "medium", "note": "Bio-mimicry observation — NOT Collective-Intelligence (that's human coordination/DAOs). Highbie nature-riff.", "new_community_signals": []}}

Tweet: "every few months I mass-DM twenty people 'thinking of you' and it rewires my entire social graph. try it."
{{"bits": ["bits:Core-TPOT:+3", "bits:Relational-Explorers:+2"], "domains": ["domain:social"], "themes": ["theme:in-group-culture", "theme:social-commentary"], "postures": ["posture:original-insight", "posture:playful-exploration"], "simulacrum": {{"l1": 0.4, "l2": 0.15, "l3": 0.3, "l4": 0.15}}, "signal_strength": "high", "note": "Peak Core-TPOT: life-hack as social experiment, earnest + playful + actionable. The TPOT posting style.", "new_community_signals": []}}

OUTPUT (JSON only, no commentary):
{{
  "bits": ["bits:ShortName:+N", ...],
  "domains": ["domain:X", ...],
  "themes": ["theme:specific-descriptor", ...],
  "postures": ["posture:X", ...],
  "simulacrum": {{"l1": float, "l2": float, "l3": float, "l4": float}},
  "signal_strength": "high|medium|low",
  "note": "1-sentence interpretation of THIS tweet",
  "new_community_signals": []
}}

FIELD DEFINITIONS:
  domains: broad buckets (AI, philosophy, social, technical, politics, personal, art, science)
  themes: specific reusable tags that form community boundaries (theme:model-interiority, theme:absurdist-humor, theme:d/acc). Create new themes when you see recurring patterns.
  postures: HOW the account engages (original-insight, signal-boost, playful-exploration, provocation, pedagogy, critique, personal-testimony)
  simulacrum: L1=truth-seeking, L2=social positioning, L3=aesthetic/narrative/vibe, L4=meta/ironic/memetic. Must sum to ~1.0. Important for tracking how ideas propagate through communities.
"""

    # Build current prior string if available from account context
    # The orchestrator can pass this via other_tweets or we extract from graph_signal
    rt_flag = "\n⚠️ THIS IS A RETWEET — at most one weak bit for interest." if is_rt else ""

    user_prompt = f"""\
Account: @{username} | Bio: {bio[:200]}
Graph: {graph_signal[:150]}
{content_profile if content_profile else ""}\
{engagement_partners if engagement_partners else ""}\
{cofollowed if cofollowed else ""}\
{"Current prior: " + other_tweets if other_tweets else ""}

TWEET TO TAG:{rt_flag}
{tweet_text}

Engagement: {engagement}
{f"Engagement context: {engagement_context}" if engagement_context and engagement_context != "No engagement data from classified accounts." else ""}\
{rt_source if rt_source else ""}\
{mention_communities if mention_communities else ""}\
{reply_communities if reply_communities else ""}

Focus on bits that SURPRISE relative to the prior. Confirming evidence = low signal_strength. Contradicting or extending = high signal_strength.
Tag sub-community facets as themes when you see them (e.g., theme:mech-interp, theme:jhana-practice).
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
    max_retries: int = 3,
) -> str:
    """POST to OpenRouter and return the raw content string.

    Retries with exponential backoff on 429 (rate limit) and 5xx errors.
    Raises httpx.HTTPStatusError on persistent failures.
    """
    import time as _time

    for attempt in range(max_retries + 1):
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
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < max_retries:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "%s returned %d, retrying in %ds (attempt %d/%d)",
                    model, resp.status_code, wait, attempt + 1, max_retries,
                )
                _time.sleep(wait)
                continue
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    resp.raise_for_status()  # final attempt failed
    return ""  # unreachable


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
