"""Prediction and queue methods for golden curation."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .constants import (
    QUEUE_DISAGREEMENT_WEIGHT,
    QUEUE_ENTROPY_WEIGHT,
    QUEUE_STATUSES,
    SIMULACRUM_LABELS,
    SPLIT_NAMES,
)
from .schema import normalized_entropy, now_iso, total_variation_distance, validate_distribution


class PredictionMixin:
    def _compute_disagreement(
        self,
        conn: sqlite3.Connection,
        *,
        tweet_id: str,
        axis: str,
        model_name: str,
        distribution: Dict[str, float],
    ) -> float:
        rows = conn.execute(
            """
            SELECT model_name, MAX(id) AS prediction_set_id
            FROM model_prediction_set
            WHERE tweet_id = ? AND axis = ?
            GROUP BY model_name
            """,
            (tweet_id, axis),
        ).fetchall()
        distances: List[float] = []
        for row in rows:
            if str(row["model_name"]) == model_name:
                continue
            peer = self._load_prob_map(conn, "model_prediction_prob", "prediction_set_id", int(row["prediction_set_id"]))
            if set(peer.keys()) == set(SIMULACRUM_LABELS):
                distances.append(total_variation_distance(distribution, peer))
        return (sum(distances) / len(distances)) if distances else 0.0

    def insert_predictions(
        self,
        *,
        axis: str,
        model_name: str,
        model_version: Optional[str],
        prompt_version: str,
        run_id: str,
        reviewer: str,
        predictions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self._assert_axis(axis)
        if not predictions:
            raise ValueError("predictions must contain at least one item")

        now = now_iso()
        inserted = 0
        entropies: List[float] = []
        disagreements: List[float] = []

        with self._open() as conn:
            for item in predictions:
                tweet_id = str(item.get("tweet_id") or "").strip()
                if not tweet_id:
                    raise ValueError("each prediction item requires tweet_id")
                dist = validate_distribution(item.get("distribution") or item.get("probabilities") or {})
                entropy = normalized_entropy(dist)
                disagreement = self._compute_disagreement(
                    conn,
                    tweet_id=tweet_id,
                    axis=axis,
                    model_name=model_name,
                    distribution=dist,
                )
                queue_score = QUEUE_ENTROPY_WEIGHT * entropy + QUEUE_DISAGREEMENT_WEIGHT * disagreement
                cursor = conn.execute(
                    """
                    INSERT INTO model_prediction_set
                    (tweet_id, axis, model_name, model_version, prompt_version, run_id, context_hash,
                     entropy, disagreement, queue_score, parse_status, raw_response_json, predicted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tweet_id,
                        axis,
                        model_name,
                        model_version,
                        prompt_version,
                        run_id,
                        item.get("context_hash"),
                        entropy,
                        disagreement,
                        queue_score,
                        str(item.get("parse_status") or "ok"),
                        json.dumps(item.get("raw_response_json")) if item.get("raw_response_json") is not None else None,
                        now,
                    ),
                )
                pred_set_id = int(cursor.lastrowid)
                conn.executemany(
                    "INSERT INTO model_prediction_prob (prediction_set_id, label, probability) VALUES (?, ?, ?)",
                    [(pred_set_id, label, dist[label]) for label in SIMULACRUM_LABELS],
                )

                status = "resolved" if self._has_active_label(conn, tweet_id=tweet_id, axis=axis, reviewer=reviewer) else "pending"
                conn.execute(
                    """
                    INSERT INTO uncertainty_queue
                    (tweet_id, axis, latest_prediction_set_id, entropy, disagreement, queue_score, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tweet_id, axis) DO UPDATE SET
                        latest_prediction_set_id = excluded.latest_prediction_set_id,
                        entropy = excluded.entropy,
                        disagreement = excluded.disagreement,
                        queue_score = excluded.queue_score,
                        status = CASE WHEN excluded.status = 'resolved' THEN 'resolved'
                                      WHEN uncertainty_queue.status = 'skipped' THEN 'skipped'
                                      ELSE excluded.status END,
                        updated_at = excluded.updated_at
                    """,
                    (tweet_id, axis, pred_set_id, entropy, disagreement, queue_score, status, now),
                )
                inserted += 1
                entropies.append(entropy)
                disagreements.append(disagreement)

            conn.commit()
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM uncertainty_queue WHERE axis = ? GROUP BY status",
                (axis,),
            ).fetchall()
            queue_counts = {status: 0 for status in QUEUE_STATUSES}
            for row in rows:
                queue_counts[str(row["status"])] = int(row["n"])

        return {
            "inserted": inserted,
            "meanEntropy": (sum(entropies) / len(entropies)) if entropies else 0.0,
            "meanDisagreement": (sum(disagreements) / len(disagreements)) if disagreements else 0.0,
            "queueCounts": queue_counts,
        }

    def list_queue(
        self,
        axis: str,
        *,
        status: str,
        split: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        self._assert_axis(axis)
        if status not in {"all", *QUEUE_STATUSES}:
            raise ValueError("status must be one of: all, pending, in_review, resolved, skipped")
        if split not in {None, *SPLIT_NAMES}:
            raise ValueError("split must be one of: train, dev, test")

        conditions = ["q.axis = ?"]
        params: List[Any] = [axis]
        if status != "all":
            conditions.append("q.status = ?")
            params.append(status)
        if split is not None:
            conditions.append("s.split = ?")
            params.append(split)

        query = f"""
            SELECT q.tweet_id, q.entropy, q.disagreement, q.queue_score, q.status, q.updated_at,
                   t.username, t.full_text, t.reply_to_tweet_id, s.split
            FROM uncertainty_queue q
            JOIN tweets t ON t.tweet_id = q.tweet_id
            JOIN curation_split s ON s.tweet_id = q.tweet_id AND s.axis = q.axis
            WHERE {' AND '.join(conditions)}
            ORDER BY q.queue_score DESC, q.updated_at DESC
            LIMIT ?
        """
        params.append(int(limit))

        with self._open() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                {
                    "tweetId": str(row["tweet_id"]),
                    "username": str(row["username"]),
                    "text": str(row["full_text"]),
                    "split": str(row["split"]),
                    "status": str(row["status"]),
                    "entropy": float(row["entropy"]),
                    "disagreement": float(row["disagreement"]),
                    "queueScore": float(row["queue_score"]),
                    "updatedAt": row["updated_at"],
                    **self._load_context(conn, str(row["tweet_id"]), row["reply_to_tweet_id"]),
                }
                for row in rows
            ]
