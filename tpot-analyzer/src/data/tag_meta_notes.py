"""Append-only working-intension notes for one curator-owned tag."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.data.account_tag_schema import initialize_account_tag_schema

MAX_TAG_META_NOTE_CHARS = 10_000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_ego(ego: str) -> str:
    """Return the canonical curator key used by tag-meta-note storage."""
    if not isinstance(ego, str):
        raise ValueError("ego must be a string")
    canonical = ego.strip().removeprefix("@").strip().casefold()
    if not canonical:
        raise ValueError("ego cannot be empty")
    return canonical


def normalize_tag(tag: str) -> tuple[str, str]:
    """Return the existing account-tag key/display normalization."""
    if not isinstance(tag, str):
        raise ValueError("tag must be a string")
    display = tag.strip()
    if not display:
        raise ValueError("tag cannot be empty")
    return display.casefold(), display


def normalize_note(note: str) -> str:
    if not isinstance(note, str):
        raise ValueError("note must be a string")
    normalized = note.strip()
    if len(normalized) > MAX_TAG_META_NOTE_CHARS:
        raise ValueError(
            f"note must be at most {MAX_TAG_META_NOTE_CHARS} characters"
        )
    return normalized


@dataclass(frozen=True)
class TagMetaNote:
    note_id: int
    ego: str
    tag_key: str
    tag: str
    note: str
    source: str
    created_at: str


class TagMetaNoteStore:
    """Persistent append-only note history keyed by canonical ego/tag."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            initialize_account_tag_schema(conn)

    def append_note(
        self, *, ego: str, tag: str, note: str, source: str
    ) -> TagMetaNote:
        canonical_ego = normalize_ego(ego)
        tag_key, tag_display = normalize_tag(tag)
        normalized_note = normalize_note(note)
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source cannot be empty")
        normalized_source = source.strip()
        created_at = _utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO tag_meta_notes (
                    ego, tag_key, tag_display, note, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical_ego,
                    tag_key,
                    tag_display,
                    normalized_note,
                    normalized_source,
                    created_at,
                ),
            )
        return TagMetaNote(
            note_id=int(cursor.lastrowid),
            ego=canonical_ego,
            tag_key=tag_key,
            tag=tag_display,
            note=normalized_note,
            source=normalized_source,
            created_at=created_at,
        )

    def get_notes(
        self, *, ego: str, tag: str, limit: int = 50
    ) -> tuple[Optional[TagMetaNote], list[TagMetaNote]]:
        canonical_ego = normalize_ego(ego)
        tag_key, _ = normalize_tag(tag)
        bounded_limit = max(1, min(int(limit), 200))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT note_id, ego, tag_key, tag_display, note, source, created_at
                FROM (
                    SELECT note_id, ego, tag_key, tag_display, note, source,
                           created_at
                    FROM tag_meta_notes
                    WHERE ego = ? AND tag_key = ?
                    ORDER BY note_id DESC
                    LIMIT ?
                )
                ORDER BY note_id ASC
                """,
                (canonical_ego, tag_key, bounded_limit),
            ).fetchall()
        history = [
            TagMetaNote(
                note_id=int(row[0]),
                ego=str(row[1]),
                tag_key=str(row[2]),
                tag=str(row[3]),
                note=str(row[4]),
                source=str(row[5]),
                created_at=str(row[6]),
            )
            for row in rows
        ]
        return (history[-1] if history else None), history
