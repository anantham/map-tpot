"""Routes for golden dataset curation and active-learning queue."""
from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
import yaml
from flask import Blueprint, jsonify, request

from src.config import get_snapshot_dir
from src.data.golden_store import AXIS_SIMULACRUM, GoldenStore

_TAXONOMY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "golden" / "taxonomy.yaml"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_INTERPRET_MODEL = "moonshotai/kimi-k2"
_INTERPRET_ALLOWED_MODELS_ENV = "GOLDEN_INTERPRET_ALLOWED_MODELS"
_INTERPRET_ALLOW_REMOTE_ENV = "GOLDEN_INTERPRET_ALLOW_REMOTE"
# Models available by default when no env override is set.
# Set GOLDEN_INTERPRET_ALLOWED_MODELS=model1,model2 to restrict or expand.
_INTERPRET_DEFAULT_MODELS = {
    "moonshotai/kimi-k2",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-opus-4",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-pro-1.5",
}

logger = logging.getLogger(__name__)


def _get_graph_account_ids() -> set:
    """Return the set of account IDs present in the loaded graph, or empty set.

    Uses the already-loaded SNAPSHOT_GRAPH from Flask app config — zero cost
    if the graph isn't loaded yet (discovery tab not visited). Falls back
    gracefully to empty set so candidate ordering degrades to the default.
    """
    try:
        from flask import current_app
        graph_result = current_app.config.get("SNAPSHOT_GRAPH")
        if graph_result is None:
            return set()
        directed = getattr(graph_result, "directed", graph_result)
        return {str(n) for n in directed.nodes()}
    except Exception:
        return set()

golden_bp = Blueprint("golden", __name__, url_prefix="/api/golden")
_golden_store: Optional[GoldenStore] = None

def _get_store() -> GoldenStore:
    global _golden_store
    if _golden_store is not None:
        return _golden_store
    snapshot_dir = get_snapshot_dir()
    db_path = Path(snapshot_dir) / "archive_tweets.db"
    _golden_store = GoldenStore(db_path)
    return _golden_store

def _parse_axis(raw: Optional[str]) -> str:
    axis = (raw or AXIS_SIMULACRUM).strip()
    if axis != AXIS_SIMULACRUM:
        raise ValueError(f"Unsupported axis '{axis}'. Expected '{AXIS_SIMULACRUM}'.")
    return axis


def _parse_split(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip().lower()
    if not value or value == "all":
        return None
    if value not in {"train", "dev", "test"}:
        raise ValueError("split must be one of: train, dev, test, all")
    return value


def _parse_limit(raw: Optional[str], *, default: int = 20, minimum: int = 1, maximum: int = 500) -> int:
    value = raw if raw is not None else str(default)
    parsed = int(value)
    return max(minimum, min(maximum, parsed))


def _allowed_interpret_models() -> set[str]:
    raw = (os.environ.get(_INTERPRET_ALLOWED_MODELS_ENV) or "").strip()
    if not raw:
        return set(_INTERPRET_DEFAULT_MODELS)
    return {m.strip() for m in raw.split(",") if m.strip()}


def _enforce_interpret_access(*, model: str) -> None:
    allowed_models = _allowed_interpret_models()
    if model not in allowed_models:
        raise ValueError(
            f"model '{model}' is not allowed. Allowed models: {sorted(allowed_models)}"
        )
    allow_remote = (os.environ.get(_INTERPRET_ALLOW_REMOTE_ENV) or "").strip().lower() in {"1", "true", "yes"}
    if not allow_remote:
        # When remote access is disabled, require a valid TPOT_EXTENSION_TOKEN.
        # The old loopback-IP check was broken behind reverse proxies (Fly.io, nginx).
        expected_token = (os.getenv("TPOT_EXTENSION_TOKEN") or "").strip()
        received_token = (request.headers.get("X-TPOT-Extension-Token") or "").strip()
        if not expected_token:
            raise PermissionError(
                "interpret endpoint requires TPOT_EXTENSION_TOKEN to be configured, "
                "or set GOLDEN_INTERPRET_ALLOW_REMOTE=1 to allow open access."
            )
        if not received_token or not secrets.compare_digest(received_token, expected_token):
            raise PermissionError("missing or invalid extension token for interpret endpoint")


@golden_bp.route("/candidates", methods=["GET"])
def get_candidates():
    try:
        axis = _parse_axis(request.args.get("axis"))
        split = _parse_split(request.args.get("split"))
        status = (request.args.get("status") or "unlabeled").strip().lower()
        reviewer = (request.args.get("reviewer") or "human").strip() or "human"
        limit = _parse_limit(request.args.get("limit"), default=20, maximum=1000)

        store = _get_store()
        # ensure_fixed_splits is fast when splits already exist (LIMIT 1 check).
        # Full bootstrap runs only on first call or after archive fetch adds new tweets.
        split_counts = store.ensure_fixed_splits(axis, assigned_by="system")
        preferred = _get_graph_account_ids()
        candidates = store.list_candidates(
            axis,
            split=split,
            status=status,
            reviewer=reviewer,
            limit=limit,
            preferred_account_ids=preferred or None,
        )
        return jsonify(
            {
                "axis": axis,
                "split": split or "all",
                "status": status,
                "reviewer": reviewer,
                "limit": limit,
                "splitCounts": split_counts,
                "candidates": candidates,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        logger.error("Golden candidates runtime error: %s", exc)
        return jsonify({"error": "golden candidates query failed"}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden candidates failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/labels", methods=["POST"])
def upsert_label():
    data = request.get_json(silent=True) or {}
    try:
        axis = _parse_axis(data.get("axis"))
        tweet_id = str(data.get("tweet_id") or data.get("tweetId") or "").strip()
        if not tweet_id:
            raise ValueError("tweet_id is required")
        reviewer = (data.get("reviewer") or "human").strip() or "human"
        distribution = data.get("distribution") or data.get("probabilities")
        note = data.get("note")
        context_snapshot_json = data.get("context_snapshot_json")

        store = _get_store()
        label_set_id = store.upsert_label(
            tweet_id=tweet_id,
            axis=axis,
            reviewer=reviewer,
            distribution=distribution,
            note=note,
            context_snapshot_json=context_snapshot_json,
        )
        return jsonify(
            {
                "status": "ok",
                "axis": axis,
                "tweetId": tweet_id,
                "reviewer": reviewer,
                "labelSetId": label_set_id,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden label upsert failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/queue", methods=["GET"])
def get_queue():
    try:
        axis = _parse_axis(request.args.get("axis"))
        split = _parse_split(request.args.get("split"))
        status = (request.args.get("status") or "pending").strip().lower()
        limit = _parse_limit(request.args.get("limit"), default=50, maximum=1000)

        store = _get_store()
        store.ensure_fixed_splits(axis, assigned_by="system")
        queue = store.list_queue(axis, status=status, split=split, limit=limit)
        return jsonify(
            {
                "axis": axis,
                "split": split or "all",
                "status": status,
                "limit": limit,
                "queue": queue,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden queue fetch failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/predictions/run", methods=["POST"])
def ingest_predictions_run():
    data = request.get_json(silent=True) or {}
    try:
        axis = _parse_axis(data.get("axis"))
        model_name = str(data.get("model_name") or data.get("modelName") or "").strip()
        if not model_name:
            raise ValueError("model_name is required")
        model_version = data.get("model_version") or data.get("modelVersion")
        prompt_version = str(data.get("prompt_version") or data.get("promptVersion") or "v1").strip() or "v1"
        run_id = str(data.get("run_id") or data.get("runId") or f"run_{uuid4().hex[:12]}")
        reviewer = (data.get("reviewer") or "human").strip() or "human"
        predictions = data.get("predictions")
        if not isinstance(predictions, list):
            raise ValueError("predictions must be a list")

        store = _get_store()
        store.ensure_fixed_splits(axis, assigned_by="system")
        result = store.insert_predictions(
            axis=axis,
            model_name=model_name,
            model_version=str(model_version) if model_version is not None else None,
            prompt_version=prompt_version,
            run_id=run_id,
            reviewer=reviewer,
            predictions=predictions,
        )
        return jsonify({
            "status": "ok",
            "axis": axis,
            "runId": run_id,
            "modelName": model_name,
            "promptVersion": prompt_version,
            **result,
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden predictions ingest failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/eval/run", methods=["POST"])
def run_eval():
    data = request.get_json(silent=True) or {}
    try:
        axis = _parse_axis(data.get("axis"))
        model_name = str(data.get("model_name") or data.get("modelName") or "").strip()
        if not model_name:
            raise ValueError("model_name is required")
        model_version = data.get("model_version") or data.get("modelVersion")
        prompt_version = str(data.get("prompt_version") or data.get("promptVersion") or "v1").strip() or "v1"
        split = _parse_split(str(data.get("split") or "dev")) or "dev"
        threshold = float(data.get("threshold") or 0.18)
        reviewer = (data.get("reviewer") or "human").strip() or "human"
        run_id = str(data.get("run_id") or data.get("runId") or f"eval_{uuid4().hex[:12]}")

        store = _get_store()
        store.ensure_fixed_splits(axis, assigned_by="system")
        result = store.run_evaluation(
            axis=axis,
            model_name=model_name,
            model_version=str(model_version) if model_version is not None else None,
            prompt_version=prompt_version,
            split=split,
            threshold=threshold,
            reviewer=reviewer,
            run_id=run_id,
        )
        return jsonify({"status": "ok", **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden eval failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/metrics", methods=["GET"])
def get_metrics():
    try:
        axis = _parse_axis(request.args.get("axis"))
        reviewer = (request.args.get("reviewer") or "human").strip() or "human"
        store = _get_store()
        store.ensure_fixed_splits(axis, assigned_by="system")
        return jsonify(store.metrics(axis, reviewer=reviewer))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden metrics failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/tags", methods=["POST"])
def save_tags():
    """Save topic tags for a tweet."""
    data = request.get_json(silent=True) or {}
    try:
        tweet_id = str(data.get("tweet_id") or data.get("tweetId") or "").strip()
        if not tweet_id:
            raise ValueError("tweet_id is required")
        tags = data.get("tags")
        if not isinstance(tags, list):
            raise ValueError("tags must be a list of strings")
        added_by = (data.get("added_by") or data.get("addedBy") or "human").strip() or "human"
        category = data.get("category")

        store = _get_store()
        count = store.save_tags(
            tweet_id=tweet_id,
            tags=tags,
            added_by=added_by,
            category=category,
        )
        return jsonify({"status": "ok", "tweetId": tweet_id, "count": count})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden save_tags failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/tags/<tweet_id>", methods=["GET"])
def get_tweet_tags(tweet_id):
    """Return all tags for a given tweet."""
    try:
        store = _get_store()
        tags = store.get_tags_for_tweet(tweet_id)
        return jsonify({"tweetId": tweet_id, "tags": tags})
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden get_tweet_tags failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/tags/<tweet_id>/<tag>", methods=["DELETE"])
def delete_tweet_tag(tweet_id, tag):
    """Remove a single tag from a tweet."""
    try:
        store = _get_store()
        removed = store.remove_tag(tweet_id=tweet_id, tag=tag)
        return jsonify({"status": "ok", "removed": removed})
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden delete_tweet_tag failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/tags/vocabulary", methods=["GET"])
def get_tag_vocabulary():
    """Return all previously used tags with usage counts."""
    try:
        limit = _parse_limit(request.args.get("limit"), default=200, maximum=1000)
        store = _get_store()
        tags = store.get_tag_vocabulary(limit=limit)
        return jsonify({"tags": tags})
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden get_tag_vocabulary failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


def _build_interpret_prompt(tweet_text: str, thread_context: list, taxonomy: dict) -> str:
    """Build the LEGACY interpretation prompt. Use _build_rich_interpret_prompt for full labeling."""
    sim = taxonomy.get("simulacrum", {})
    levels = sim.get("levels", {})

    lines = [
        "You are a tweet epistemic classifier. Classify the tweet below on these axes:\n",
        "SIMULACRUM LEVELS:",
    ]
    for key, level in levels.items():
        name = level.get("name", key)
        defn = (level.get("definition") or "").strip().replace("\n", " ")
        test = (level.get("key_test") or "").strip()
        lines.append(f"  {key.upper()} ({name}): {defn}")
        if test:
            lines.append(f"    Key test: {test}")

    lines.append("\nGOLDEN EXAMPLES:")
    for key, level in levels.items():
        for ex in (level.get("examples") or {}).get("positive", []):
            tweet = (ex.get("tweet") or "").strip()[:200]
            note = (ex.get("note") or "").strip()[:200]
            dist = ex.get("distribution", {})
            if tweet and dist:
                lines.append(f'  Tweet: "{tweet}"')
                lines.append(f'  Classification: {json.dumps(dist)}')
                if note:
                    lines.append(f'  Note: {note}')
                lines.append("")

    if thread_context:
        lines.append("THREAD CONTEXT (parent tweets leading up to the target):")
        for t in thread_context:
            author = t.get("author", {}).get("userName", "?")
            text = (t.get("text") or "").strip()[:300]
            lines.append(f'  @{author}: "{text}"')
        lines.append("")

    lines.append(f'NOW CLASSIFY THIS TWEET:\n"{tweet_text.strip()[:500]}"\n')
    lines.append("""Return ONLY valid JSON with this exact structure:
{
  "distribution": {"l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.0},
  "lucidity": 0.0,
  "interpretation": "2-3 sentences explaining the classification",
  "cluster_hypothesis": "which TPOT subcommunity this suggests (e.g. rationalist, woo, EA, dharma, e/acc, none)",
  "ingroup_signal": "what community or tribe is being signaled to, or 'none' if l1",
  "meme_role": "one of: originating | amplifying | remixing | none",
  "confidence": 0.0,
  "suggested_tags": ["tag1", "tag2", "tag3"]
}
Rules for suggested_tags: 3-5 fine-grained topic tags describing what this tweet is ABOUT at the object level. Examples: "alignment", "jhanas", "LLM psychology", "gender", "attention mechanisms", "crypto", "meditation", "game theory", "consciousness". Be specific, not generic.
Distribution values must sum to 1.0. lucidity is 0.0-1.0. confidence is 0.0-1.0.""")

    return "\n".join(lines)


def _build_rich_interpret_prompt(
    tweet_text: str,
    thread_context: list,
    labeling_ctx: dict,
) -> str:
    """Build enriched interpretation prompt with full DB context.

    Includes: account profile, engagement, similar labeled tweets,
    community profiles, thematic glossary, full output schema.
    """
    lines = [
        "You are a TPOT community tweet labeler. You assign multi-dimensional labels to tweets",
        "to build evidence about which communities the tweeter belongs to.\n",
    ]

    # --- Account metadata ---
    username = labeling_ctx.get("username")
    created_at = labeling_ctx.get("created_at")
    account_meta = labeling_ctx.get("account_meta", {})
    if username or created_at or account_meta:
        lines.append("TWEET METADATA:")
        if username:
            lines.append(f"  Author: @{username}")
        if account_meta.get("display_name"):
            lines.append(f"  Display name: {account_meta['display_name']}")
        if account_meta.get("bio"):
            lines.append(f"  Bio: {account_meta['bio'][:200]}")
        if created_at:
            lines.append(f"  Posted: {created_at}")
        lines.append("")

    # --- Account profile ---
    profile = labeling_ctx.get("account_profile", {})
    if profile.get("communities"):
        source = profile["source"]
        lines.append(f"ACCOUNT PROFILE (source: {source}):")
        for c in profile["communities"]:
            if source == "bits":
                lines.append(f"  {c['pct']:.1f}%  {c['short_name']} ({c['bits']:+d} bits)")
            else:
                lines.append(f"  {c['weight']:.0%}  {c['short_name']}")
        lines.append("")

    # --- Engagement context ---
    engagement = labeling_ctx.get("engagement", {})
    replies = engagement.get("replies", [])
    likes = engagement.get("likes", [])
    if replies or likes:
        lines.append("ENGAGEMENT ON THIS TWEET:")
        if replies:
            lines.append("  Replies:")
            for r in replies[:8]:
                comm = f" [{r['community']}({r['weight']:.0%})]" if r.get("community") else " [unclassified]"
                lines.append(f"    @{r['username']}{comm}: \"{r['text'][:80]}\"")
        if likes:
            lines.append(f"  Classified accounts who liked ({len(likes)} total):")
            for l in likes[:8]:
                lines.append(f"    @{l['username']} [{l['community']}({l['weight']:.0%})]")
        lines.append("")

    # --- Similar labeled tweets ---
    similar = labeling_ctx.get("similar_tweets", [])
    if similar:
        lines.append("SIMILAR ALREADY-LABELED TWEETS (same thematic tags):")
        for s in similar[:4]:
            lines.append(f"  @{s['username']}: \"{s['text'][:150]}\"")
            lines.append(f"    themes: {', '.join(s['themes'])}")
            if s['bits']:
                bits_str = ", ".join(f"{k}:{v:+d}" for k, v in sorted(s['bits'].items(), key=lambda x: -abs(x[1])))
                lines.append(f"    bits: {bits_str}")
            if s.get('note'):
                lines.append(f"    note: {s['note'][:150]}")
            lines.append("")

    # --- Reply parent (if this is a reply) ---
    reply_parent = labeling_ctx.get("reply_parent")
    if reply_parent and reply_parent.get("text"):
        lines.append("THIS TWEET IS A REPLY TO:")
        lines.append(f"  @{reply_parent['username']}: \"{reply_parent['text'][:250]}\"")
        lines.append("")
    elif reply_parent and not reply_parent.get("text"):
        lines.append(f"THIS TWEET IS A REPLY (parent tweet {reply_parent['parent_tweet_id']} not in archive)")
        lines.append("")

    # --- Account's other top tweets (pattern context) ---
    top_tweets = labeling_ctx.get("account_top_tweets", [])
    if top_tweets:
        lines.append("ACCOUNT'S TOP TWEETS (to see sustained patterns, not just this one tweet):")
        for t in top_tweets[:8]:
            lines.append(f"  [{t['engagement']:>5} eng] \"{t['text'][:150]}\"")
        lines.append("")

    # --- Community profiles ---
    communities = labeling_ctx.get("communities", [])
    if communities:
        lines.append("COMMUNITY PROFILES:")
        for c in communities:
            desc = c['description'][:200] if c.get('description') else 'no description'
            lines.append(f"  {c['short_name']}: {desc}")
        lines.append("")

    # --- Thematic tag glossary ---
    glossary = labeling_ctx.get("thematic_glossary", [])
    if glossary:
        lines.append("THEMATIC TAG GLOSSARY (use these, or propose new ones):")
        for g in glossary[:30]:
            lines.append(f"  {g['count']:>3}x  {g['tag']}")
        lines.append("")

    # --- Thread context (from DB chain or frontend) ---
    thread_chain = labeling_ctx.get("thread_chain", [])
    if thread_chain and len(thread_chain) > 1:
        lines.append("THREAD CONTEXT (full reply chain, root → target):")
        for t in thread_chain:
            marker = " ← TARGET" if t.get("is_target") else ""
            lines.append(f"  @{t['username']} [{t['engagement']} eng]: \"{t['text'][:200]}\"{marker}")
        lines.append("")
    elif thread_context:
        # Fallback to frontend-provided context
        lines.append("THREAD CONTEXT (parent tweets):")
        for t in thread_context:
            author = t.get("author", {}).get("userName", "?")
            text = (t.get("text") or "").strip()[:300]
            lines.append(f'  @{author}: "{text}"')
        lines.append("")

    # --- Resolved external links ---
    resolved_links = labeling_ctx.get("resolved_links", [])
    external_links = [l for l in resolved_links if l.get("type") == "external"]
    if external_links:
        lines.append("LINKED CONTENT (external articles/pages):")
        for link in external_links[:3]:
            if link.get("title"):
                lines.append(f"  Title: {link['title']}")
            if link.get("description"):
                lines.append(f"  Description: {link['description'][:200]}")
            if link.get("body_excerpt"):
                lines.append(f"  Excerpt: {link['body_excerpt'][:300]}")
            lines.append(f"  URL: {link.get('resolved_url', link.get('tco_url', ''))}")
            lines.append("")

    # --- Simulacrum levels ---
    lines.append("""SIMULACRUM LEVELS:
  L1 (Truth-tracking): Genuine belief, observation, factual claim. Would retract if wrong.
  L2 (Persuasion): Trying to convince, sell, argue a position. Shaped for audience.
  L3 (Tribe-signaling): Marking community membership, in-group reference, belonging signal.
  L4 (Meta/game): Self-aware, ironic, intentionally channeling, playing with frames.
""")

    # --- Bits scale ---
    lines.append("""BITS SCALE (prior-independent log-likelihood ratios):
  +1 = weak (2x more likely if community member)
  +2 = moderate (4x)
  +3 = strong (8x)
  +4 = diagnostic (16x)
  -1 = weak against (only for NEARBY communities the account is expected to be in)
  -2 = moderate against
  0 = irrelevant to this community
  Assess the tweet IN ISOLATION — "if I saw only this tweet with no username..."
""")

    # --- Enrichment (media, quote tweets) ---
    enrichment = labeling_ctx.get("enrichment", {})
    media = enrichment.get("media", [])
    quote = enrichment.get("quote_tweet")

    if media:
        lines.append("ATTACHED MEDIA:")
        for m in media:
            lines.append(f"  [{m['type']}] {m['url']}")
        lines.append("  NOTE: Image URLs above can be viewed to understand visual context.")
        lines.append("")

    if quote:
        lines.append("QUOTE TWEET (this tweet is reacting to):")
        lines.append(f"  @{quote['username']}: \"{quote['text'][:300]}\"")
        lines.append("")

    # Use syndication full_text if available (may be longer than archive version)
    display_text = enrichment.get("full_text") or tweet_text
    # --- The tweet ---
    lines.append(f'NOW LABEL THIS TWEET:\n"{display_text.strip()[:500]}"\n')

    # --- Output schema ---
    lines.append("""Return ONLY valid JSON with this structure:
{
  "domains": ["domain:AI", "domain:philosophy"],
  "themes": ["theme:model-interiority", "theme:AI-consciousness"],
  "specifics": ["specific-tag-1", "specific-tag-2"],
  "postures": ["posture:original-insight", "posture:playful-exploration"],
  "bits": {"LLM-Whisperers": +2, "Qualia-Research": +1, "highbies": -1},
  "distribution": {"l1": 0.4, "l2": 0.1, "l3": 0.2, "l4": 0.3},
  "note": "2-3 sentences: what the tweet means, why these bits, notable engagement context",
  "new_community_signals": [],
  "confidence": 0.8
}

Rules:
- domains: use domain:X format. Options: AI, philosophy, social, technical, politics, personal, art, science
- themes: use theme:X format. Prefer existing tags from glossary. Create new ones sparingly.
- specifics: fine-grained breadcrumbs unique to this tweet. Niche is good.
- postures: how the account engages. Options: original-insight, signal-boost, playful-exploration, provocation, pedagogy, defense, critique, personal-testimony
- bits: ONLY for communities relevant to this tweet. Include negative bits ONLY for nearby communities the account is expected to be in. Skip distant communities entirely.
- distribution: L1+L2+L3+L4 must sum to 1.0
- new_community_signals: if tweet doesn't fit any community, propose a name
- confidence: 0.0-1.0""")

    return "\n".join(lines)


@golden_bp.route("/accounts/<username>/profile", methods=["GET"])
def get_account_profile(username):
    """Return archive profile + recent tweets for a username."""
    try:
        snapshot_dir = get_snapshot_dir()
        db_path = Path(snapshot_dir) / "archive_tweets.db"
        if not db_path.exists():
            return jsonify({"username": username, "profile": None, "recentTweets": []})

        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row

            row = conn.execute(
                "SELECT account_id, username, display_name, bio, location, website, created_at FROM profiles WHERE username = ? LIMIT 1",
                (username,),
            ).fetchone()

            if not row:
                return jsonify({"username": username, "profile": None, "recentTweets": []})

            account_id = row["account_id"]

            # Community membership
            community_row = conn.execute(
                """SELECT c.name, c.color, ca.weight
                   FROM community_account ca
                   JOIN community c ON c.id = ca.community_id
                   WHERE ca.account_id = ?
                   ORDER BY ca.weight DESC LIMIT 1""",
                (account_id,),
            ).fetchone()

            # Followers/following counts within the archive
            archive_followers = conn.execute(
                "SELECT COUNT(*) FROM account_following WHERE following_account_id = ?",
                (account_id,),
            ).fetchone()[0]
            archive_following = conn.execute(
                "SELECT COUNT(*) FROM account_following WHERE account_id = ?",
                (account_id,),
            ).fetchone()[0]

            # Total tweet/like counts from fetch log
            fetch_row = conn.execute(
                "SELECT tweet_count, like_count FROM fetch_log WHERE account_id = ? ORDER BY fetched_at DESC LIMIT 1",
                (account_id,),
            ).fetchone()

            # Resolved/suspended status
            resolved_row = conn.execute(
                "SELECT status FROM resolved_accounts WHERE account_id = ? LIMIT 1",
                (account_id,),
            ).fetchone()

            # Account note
            note_row = conn.execute(
                "SELECT note FROM account_note WHERE account_id = ? LIMIT 1",
                (account_id,),
            ).fetchone()

            profile = {
                "accountId": account_id,
                "username": row["username"],
                "displayName": row["display_name"],
                "bio": row["bio"],
                "location": row["location"],
                "website": row["website"],
                "createdAt": row["created_at"],
                "community": {
                    "name": community_row["name"],
                    "color": community_row["color"],
                    "weight": community_row["weight"],
                } if community_row else None,
                "archiveFollowers": archive_followers,
                "archiveFollowing": archive_following,
                "totalTweets": fetch_row["tweet_count"] if fetch_row else None,
                "totalLikesGiven": fetch_row["like_count"] if fetch_row else None,
                "resolvedStatus": resolved_row["status"] if resolved_row else None,
                "accountNote": note_row["note"] if note_row else None,
            }

            tweet_rows = conn.execute(
                """SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
                   FROM tweets
                   WHERE account_id = ? AND reply_to_tweet_id IS NULL
                   ORDER BY created_at DESC LIMIT 5""",
                (account_id,),
            ).fetchall()

        recent_tweets = [
            {
                "tweetId": r["tweet_id"],
                "text": r["full_text"],
                "createdAt": r["created_at"],
                "likeCount": r["favorite_count"] or 0,
                "retweetCount": r["retweet_count"] or 0,
            }
            for r in tweet_rows
        ]
        return jsonify({"username": username, "profile": profile, "recentTweets": recent_tweets})
    except Exception as exc:
        logger.exception("get_account_profile failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/tweets/<tweet_id>/replies", methods=["GET"])
def get_tweet_replies(tweet_id):
    """Return archived replies to a tweet from accounts in the community archive."""
    try:
        limit = _parse_limit(request.args.get("limit"), default=50, maximum=200)
        snapshot_dir = get_snapshot_dir()
        db_path = Path(snapshot_dir) / "archive_tweets.db"
        if not db_path.exists():
            return jsonify({"tweetId": tweet_id, "replies": [], "count": 0})

        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT tweet_id, username, full_text, created_at,
                          favorite_count, retweet_count
                   FROM tweets
                   WHERE reply_to_tweet_id = ?
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (tweet_id, limit),
            ).fetchall()

        replies = [
            {
                "tweetId": r["tweet_id"],
                "username": r["username"],
                "text": r["full_text"],
                "createdAt": r["created_at"],
                "likeCount": r["favorite_count"] or 0,
                "retweetCount": r["retweet_count"] or 0,
            }
            for r in rows
        ]
        return jsonify({"tweetId": tweet_id, "replies": replies, "count": len(replies)})
    except Exception as exc:
        logger.exception("get_tweet_replies failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/tweets/<tweet_id>/engagement", methods=["GET"])
def get_tweet_engagement(tweet_id):
    """Return archive-account likes and retweets for a tweet, with community info."""
    try:
        snapshot_dir = get_snapshot_dir()
        db_path = Path(snapshot_dir) / "archive_tweets.db"
        if not db_path.exists():
            return jsonify({"tweetId": tweet_id, "likers": [], "retweeters": []})

        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row

            # Use MAX(ca.weight) subquery to pick each account's primary community.
            liker_rows = conn.execute(
                """SELECT l.liker_username, l.liker_account_id,
                          c.name AS community_name, c.color AS community_color
                   FROM likes l
                   LEFT JOIN community_account ca ON ca.account_id = l.liker_account_id
                       AND ca.weight = (
                           SELECT MAX(ca2.weight) FROM community_account ca2
                           WHERE ca2.account_id = l.liker_account_id
                       )
                   LEFT JOIN community c ON c.id = ca.community_id
                   WHERE l.tweet_id = ?
                   GROUP BY l.liker_account_id
                   ORDER BY l.liker_username""",
                (tweet_id,),
            ).fetchall()

            rt_rows = conn.execute(
                """SELECT r.username, r.account_id,
                          c.name AS community_name, c.color AS community_color
                   FROM retweets r
                   LEFT JOIN community_account ca ON ca.account_id = r.account_id
                       AND ca.weight = (
                           SELECT MAX(ca2.weight) FROM community_account ca2
                           WHERE ca2.account_id = r.account_id
                       )
                   LEFT JOIN community c ON c.id = ca.community_id
                   WHERE r.tweet_id = ?
                   GROUP BY r.account_id
                   ORDER BY r.username""",
                (tweet_id,),
            ).fetchall()

        def _person(r, uname_col, acct_col):
            return {
                "username": r[uname_col],
                "accountId": r[acct_col],
                "community": {"name": r["community_name"], "color": r["community_color"]}
                if r["community_name"] else None,
            }

        return jsonify({
            "tweetId": tweet_id,
            "likers": [_person(r, "liker_username", "liker_account_id") for r in liker_rows],
            "retweeters": [_person(r, "username", "account_id") for r in rt_rows],
        })
    except Exception as exc:
        logger.exception("get_tweet_engagement failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500


@golden_bp.route("/interpret/models", methods=["GET"])
def list_interpret_models():
    """Return the list of models available for tweet interpretation."""
    models = sorted(_allowed_interpret_models())
    return jsonify({"models": models, "default": _INTERPRET_MODEL})


@golden_bp.route("/interpret", methods=["POST"])
def interpret_tweet():
    """Call LLM to classify and interpret a tweet. Returns distribution + narrative.

    Accepts either:
      - {text, threadContext, model} — legacy mode (simulacrum only)
      - {tweet_id, model, mode: "rich"} — enriched mode (full labeling with DB context)
    """
    data = request.get_json(silent=True) or {}
    try:
        mode = data.get("mode", "legacy")
        tweet_id = data.get("tweet_id")
        tweet_text = str(data.get("text") or data.get("tweet_text") or "").strip()
        thread_context = data.get("threadContext") or data.get("thread_context") or []
        if not isinstance(thread_context, list):
            raise ValueError("threadContext must be a list")
        model = str(data.get("model") or _INTERPRET_MODEL)
        _enforce_interpret_access(model=model)

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        if mode == "rich" and tweet_id:
            # Enriched mode: gather full DB context
            from src.api.labeling_context import gather_labeling_context
            labeling_ctx = gather_labeling_context(tweet_id=tweet_id)
            tweet_text = tweet_text or labeling_ctx.get("tweet_text") or ""
            if not tweet_text:
                raise ValueError("tweet not found in DB")
            prompt = _build_rich_interpret_prompt(tweet_text, thread_context, labeling_ctx)
            max_tokens = 1000  # richer output
        else:
            # Legacy mode
            if not tweet_text:
                raise ValueError("text is required")
            taxonomy = {}
            if _TAXONOMY_PATH.exists():
                with open(_TAXONOMY_PATH) as f:
                    taxonomy = yaml.safe_load(f) or {}
            prompt = _build_interpret_prompt(tweet_text, thread_context, taxonomy)
            max_tokens = 600

        # Build message content — multimodal if images available
        content_parts = [{"type": "text", "text": prompt}]
        if mode == "rich" and tweet_id:
            enrichment = labeling_ctx.get("enrichment", {})
            from src.api.tweet_enrichment import get_image_data_urls
            image_data_urls = get_image_data_urls(enrichment, max_images=3)
            for data_url in image_data_urls:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })

        # Use multimodal content blocks if images exist, plain text otherwise
        if len(content_parts) > 1:
            messages = [{"role": "user", "content": content_parts}]
        else:
            messages = [{"role": "user", "content": prompt}]

        response = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=45,
        )
        response.raise_for_status()
        raw = response.json()
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Strip markdown fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        # Fix +N → N in JSON (common LLM output for bits)
        import re as _re
        content = _re.sub(r':\s*\+(\d)', r': \1', content)
        result = json.loads(content)

        # Validate distribution
        dist = result.get("distribution", {})
        total = sum(float(v) for v in dist.values())
        if abs(total - 1.0) > 0.05:
            logger.warning("Interpretation distribution sums to %.3f, normalizing", total)
            if total > 0:
                result["distribution"] = {k: round(v / total, 4) for k, v in dist.items()}

        # Store interpretation run for model comparison
        if tweet_id:
            try:
                import hashlib
                from datetime import datetime, timezone
                from uuid import uuid4 as _uuid4
                prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
                run_now = datetime.now(timezone.utc).isoformat()
                snapshot_dir = get_snapshot_dir()
                _db = sqlite3.connect(str(Path(snapshot_dir) / "archive_tweets.db"))
                _db.execute(
                    "INSERT OR IGNORE INTO interpretation_prompt (prompt_hash, prompt_text, created_at) VALUES (?, ?, ?)",
                    (prompt_hash, prompt, run_now),
                )
                _db.execute(
                    "INSERT INTO interpretation_run (id, tweet_id, model_id, prompt_hash, prompt_length, response_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(_uuid4()), tweet_id, model, prompt_hash, len(prompt), json.dumps(result), run_now),
                )
                _db.commit()
                _db.close()
                logger.info("Stored interpretation run for tweet %s model %s", tweet_id, model)
            except Exception as store_exc:
                logger.warning("Failed to store interpretation run: %s", store_exc)

        return jsonify({"status": "ok", "model": model, "mode": mode, **result})

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON: %s", exc)
        return jsonify({"error": "parse_error", "detail": "LLM returned non-JSON response"}), 502
    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter error %s: %s", exc.response.status_code, exc.response.text[:200])
        return jsonify({"error": "llm_error", "detail": "upstream LLM service returned an error"}), 502
    except Exception as exc:  # pragma: no cover
        logger.exception("Interpret failed: %s", exc)
        return jsonify({"error": "internal_error"}), 500
