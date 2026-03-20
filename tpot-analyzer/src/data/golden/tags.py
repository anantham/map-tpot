"""Tag storage methods for golden curation."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from .schema import now_iso

logger = logging.getLogger(__name__)


class TagMixin:
    """Mixin providing tweet tag CRUD operations."""

    def save_tags(
        self,
        *,
        tweet_id: str,
        tags: List[str],
        added_by: str = "human",
        category: Optional[str] = None,
    ) -> int:
        """Save tags for a tweet. Upserts on (tweet_id, tag) primary key.

        Returns the number of tags saved.
        """
        if not tweet_id:
            raise ValueError("tweet_id is required")
        if not isinstance(tags, list):
            raise ValueError("tags must be a list of strings")

        # Deduplicate and normalize: strip whitespace, lowercase, skip empty
        seen: set[str] = set()
        clean_tags: list[str] = []
        for raw in tags:
            if not isinstance(raw, str):
                continue
            normalized = raw.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                clean_tags.append(normalized)

        if not clean_tags:
            return 0

        now = now_iso()
        with self._open() as conn:
            conn.executemany(
                """INSERT INTO tweet_tags (tweet_id, tag, category, added_by, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(tweet_id, tag) DO UPDATE SET
                       category = COALESCE(excluded.category, tweet_tags.category),
                       added_by = excluded.added_by,
                       created_at = excluded.created_at
                """,
                [(tweet_id, tag, category, added_by, now) for tag in clean_tags],
            )
            conn.commit()
        return len(clean_tags)

    def get_tags_for_tweet(self, tweet_id: str) -> List[Dict[str, Any]]:
        """Return all tags for a given tweet."""
        with self._open() as conn:
            rows = conn.execute(
                "SELECT tag, category, added_by, created_at FROM tweet_tags WHERE tweet_id = ? ORDER BY tag",
                (tweet_id,),
            ).fetchall()
        return [
            {
                "tag": str(row["tag"]),
                "category": row["category"],
                "addedBy": str(row["added_by"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_tag_vocabulary(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        """Return all previously used tags with usage counts, ordered by frequency."""
        with self._open() as conn:
            rows = conn.execute(
                """SELECT tag, category, COUNT(*) AS cnt
                   FROM tweet_tags
                   GROUP BY tag
                   ORDER BY cnt DESC, tag ASC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {"tag": str(row["tag"]), "category": row["category"], "count": int(row["cnt"])}
            for row in rows
        ]

    def remove_tag(self, *, tweet_id: str, tag: str) -> bool:
        """Remove a single tag from a tweet. Returns True if a row was deleted."""
        normalized = tag.strip().lower()
        with self._open() as conn:
            cursor = conn.execute(
                "DELETE FROM tweet_tags WHERE tweet_id = ? AND tag = ?",
                (tweet_id, normalized),
            )
            conn.commit()
        return cursor.rowcount > 0

    def seed_community_tags(self) -> int:
        """Seed the tag vocabulary with community names from the community table.

        Inserts a sentinel row per community name (tweet_id='__vocabulary__')
        so the vocabulary endpoint returns them even before any tweet is tagged.
        Returns the number of community tags seeded.
        """
        now = now_iso()
        with self._open() as conn:
            # Check if community table exists
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='community'"
            ).fetchone()
            if not table_exists:
                logger.debug("seed_community_tags: community table not found, skipping")
                return 0

            communities = conn.execute(
                "SELECT name FROM community ORDER BY name"
            ).fetchall()
            if not communities:
                return 0

            count = 0
            for row in communities:
                name = str(row["name"]).strip().lower()
                if not name:
                    continue
                conn.execute(
                    """INSERT INTO tweet_tags (tweet_id, tag, category, added_by, created_at)
                       VALUES ('__vocabulary__', ?, 'community', 'system', ?)
                       ON CONFLICT(tweet_id, tag) DO NOTHING""",
                    (name, now),
                )
                count += 1
            conn.commit()
            logger.info("Seeded %d community tags into vocabulary", count)
        return count
