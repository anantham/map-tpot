"""Evaluation and metrics methods for golden curation."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .constants import QUEUE_STATUSES, SIMULACRUM_LABELS, SPLIT_NAMES
from .schema import now_iso


class EvaluationMixin:
    def run_evaluation(
        self,
        *,
        axis: str,
        model_name: str,
        model_version: Optional[str],
        prompt_version: str,
        split: str,
        threshold: float,
        reviewer: str,
        run_id: str,
    ) -> Dict[str, Any]:
        self._assert_axis(axis)
        if split not in SPLIT_NAMES:
            raise ValueError("split must be one of: train, dev, test")

        with self._open() as conn:
            rows = conn.execute(
                """
                WITH latest_pred AS (
                    SELECT tweet_id, MAX(id) AS prediction_set_id
                    FROM model_prediction_set
                    WHERE axis = ? AND model_name = ? AND prompt_version = ?
                    GROUP BY tweet_id
                ),
                active_label AS (
                    SELECT tweet_id, id AS label_set_id
                    FROM tweet_label_set
                    WHERE axis = ? AND reviewer = ? AND is_active = 1
                )
                SELECT s.tweet_id, lp.prediction_set_id, al.label_set_id
                FROM curation_split s
                JOIN latest_pred lp ON lp.tweet_id = s.tweet_id
                JOIN active_label al ON al.tweet_id = s.tweet_id
                WHERE s.axis = ? AND s.split = ?
                """,
                (axis, model_name, prompt_version, axis, reviewer, axis, split),
            ).fetchall()

            if not rows:
                raise ValueError(
                    f"No label/prediction overlap for split={split}, model={model_name}, prompt_version={prompt_version}"
                )

            sample_size = 0
            brier_total = 0.0
            for row in rows:
                prediction = self._load_prob_map(conn, "model_prediction_prob", "prediction_set_id", int(row["prediction_set_id"]))
                label = self._load_prob_map(conn, "tweet_label_prob", "label_set_id", int(row["label_set_id"]))
                if set(prediction.keys()) != set(SIMULACRUM_LABELS) or set(label.keys()) != set(SIMULACRUM_LABELS):
                    continue
                sample_size += 1
                brier_total += sum((prediction[k] - label[k]) ** 2 for k in SIMULACRUM_LABELS) / len(SIMULACRUM_LABELS)

            if sample_size == 0:
                raise ValueError("No valid probability rows found for evaluation")

            brier_score = brier_total / sample_size
            passed = int(brier_score <= threshold)
            created_at = now_iso()
            conn.execute(
                """
                INSERT INTO evaluation_run
                (run_id, axis, model_name, model_version, prompt_version, split, brier_score, threshold, passed, sample_size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, axis, model_name, model_version, prompt_version, split, brier_score, threshold, passed, sample_size, created_at),
            )
            conn.commit()

        return {
            "runId": run_id,
            "axis": axis,
            "modelName": model_name,
            "modelVersion": model_version,
            "promptVersion": prompt_version,
            "split": split,
            "brierScore": brier_score,
            "threshold": threshold,
            "passed": bool(passed),
            "sampleSize": sample_size,
            "createdAt": created_at,
        }

    def metrics(self, axis: str, *, reviewer: str) -> Dict[str, Any]:
        self._assert_axis(axis)
        with self._open() as conn:
            split_counts = self._split_counts(conn, axis)
            total_tweets = int(conn.execute("SELECT COUNT(*) AS n FROM tweets").fetchone()["n"])
            labeled_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM tweet_label_set WHERE axis = ? AND reviewer = ? AND is_active = 1",
                    (axis, reviewer),
                ).fetchone()["n"]
            )
            predicted_count = int(
                conn.execute("SELECT COUNT(DISTINCT tweet_id) AS n FROM model_prediction_set WHERE axis = ?", (axis,)).fetchone()["n"]
            )
            queue_counts = {status: 0 for status in QUEUE_STATUSES}
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM uncertainty_queue WHERE axis = ? GROUP BY status", (axis,)).fetchall():
                queue_counts[str(row["status"])] = int(row["n"])

            latest_eval: Dict[str, Any] = {}
            for row in conn.execute(
                """
                SELECT split, brier_score, threshold, passed, sample_size, created_at, model_name, prompt_version
                FROM evaluation_run
                WHERE axis = ?
                ORDER BY created_at DESC, id DESC
                """,
                (axis,),
            ).fetchall():
                split_name = str(row["split"])
                if split_name in latest_eval:
                    continue
                latest_eval[split_name] = {
                    "brierScore": float(row["brier_score"]),
                    "threshold": float(row["threshold"]),
                    "passed": bool(int(row["passed"])),
                    "sampleSize": int(row["sample_size"]),
                    "modelName": str(row["model_name"]),
                    "promptVersion": str(row["prompt_version"]),
                    "createdAt": row["created_at"],
                }

            return {
                "axis": axis,
                "reviewer": reviewer,
                "totalTweets": total_tweets,
                "splitCounts": split_counts,
                "labeledCount": labeled_count,
                "predictedCount": predicted_count,
                "queueCounts": queue_counts,
                "latestEvaluation": latest_eval,
            }
