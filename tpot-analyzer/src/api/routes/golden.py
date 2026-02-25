"""Routes for golden dataset curation and active-learning queue."""
from __future__ import annotations

import json
import logging
import os
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

logger = logging.getLogger(__name__)

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


@golden_bp.route("/candidates", methods=["GET"])
def get_candidates():
    try:
        axis = _parse_axis(request.args.get("axis"))
        split = _parse_split(request.args.get("split"))
        status = (request.args.get("status") or "unlabeled").strip().lower()
        reviewer = (request.args.get("reviewer") or "human").strip() or "human"
        limit = _parse_limit(request.args.get("limit"), default=20, maximum=1000)

        store = _get_store()
        split_counts = store.ensure_fixed_splits(axis, assigned_by="system")
        candidates = store.list_candidates(
            axis,
            split=split,
            status=status,
            reviewer=reviewer,
            limit=limit,
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
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Golden candidates failed: %s", exc)
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500


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
        store.ensure_fixed_splits(axis, assigned_by="system")
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
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500


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
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500


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
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500


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
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500


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
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500


def _build_interpret_prompt(tweet_text: str, thread_context: list, taxonomy: dict) -> str:
    """Build the few-shot interpretation prompt from taxonomy.yaml golden examples."""
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
  "confidence": 0.0
}
Rules: distribution values sum to 1.0. lucidity is 0.0-1.0. confidence is 0.0-1.0.""")

    return "\n".join(lines)


@golden_bp.route("/interpret", methods=["POST"])
def interpret_tweet():
    """Call LLM to classify and interpret a tweet. Returns distribution + narrative."""
    data = request.get_json(silent=True) or {}
    try:
        tweet_text = str(data.get("text") or data.get("tweet_text") or "").strip()
        if not tweet_text:
            raise ValueError("text is required")
        thread_context = data.get("threadContext") or data.get("thread_context") or []
        model = str(data.get("model") or _INTERPRET_MODEL)

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        taxonomy = {}
        if _TAXONOMY_PATH.exists():
            with open(_TAXONOMY_PATH) as f:
                taxonomy = yaml.safe_load(f) or {}

        prompt = _build_interpret_prompt(tweet_text, thread_context, taxonomy)

        response = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=30,
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

        result = json.loads(content)

        # Validate distribution
        dist = result.get("distribution", {})
        total = sum(float(v) for v in dist.values())
        if abs(total - 1.0) > 0.05:
            logger.warning("Interpretation distribution sums to %.3f, normalizing", total)
            if total > 0:
                result["distribution"] = {k: round(v / total, 4) for k, v in dist.items()}

        return jsonify({"status": "ok", "model": model, **result})

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON: %s", exc)
        return jsonify({"error": "parse_error", "detail": "LLM returned non-JSON response"}), 502
    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter error %s: %s", exc.response.status_code, exc.response.text[:200])
        return jsonify({"error": "llm_error", "detail": str(exc)}), 502
    except Exception as exc:  # pragma: no cover
        logger.exception("Interpret failed: %s", exc)
        return jsonify({"error": "internal_error", "detail": str(exc)}), 500
