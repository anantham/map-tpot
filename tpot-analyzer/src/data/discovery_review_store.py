"""Frozen evidence projection and separate append-only personal review answers.

The manifest is read-only. This store never opens the archive, account-tag, or
gold databases. Every correction is a new event; the latest answer is a view.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

LEGACY_PURPOSE = {
    "key": "dharma", "title": "Dharma discovery",
    "description": "Take a look. Tell us what feels relevant and worth finding.",
    "relevanceQuestion": "Relevant to your Dharma search?",
}


@dataclass(frozen=True)
class DiscoveryReviewPacket:
    packet_id: str
    curator: str
    cards: list[dict[str, Any]]
    purpose: dict[str, str]

    @property
    def account_ids(self) -> set[str]:
        return {card["accountId"] for card in self.cards}


def project_discovery(evidence: dict) -> dict:
    """Expose dated work and uncertainties, never selection scores or judgments."""
    result = {}
    for source, target in {
        "contribution_hypothesis": "contributionHypothesis", "connection": "connection",
        "location_evidence": "locationEvidence",
    }.items():
        value = evidence[source]
        if not isinstance(value, str):
            raise ValueError(f"discovery {source} must be text")
        result[target] = value
    unknowns = evidence["unknowns"]
    if not isinstance(unknowns, list) or any(not isinstance(item, str) for item in unknowns):
        raise ValueError("discovery unknowns must be a list of text")
    result["unknowns"] = unknowns
    result["work"] = []
    for item in evidence["work"]:
        if any(not isinstance(item[key], str) for key in ("label", "url", "detail", "checked_at")):
            raise ValueError("public work evidence fields must be text")
        parsed = urlsplit(item["url"])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("public work evidence requires an HTTPS link without credentials")
        result["work"].append({
            "label": item["label"], "url": item["url"], "detail": item["detail"],
            "checkedAt": item["checked_at"],
        })
    return result


def load_review_packet(path: Path) -> DiscoveryReviewPacket:
    """Return only allowed evidence fields, bound to SHA256 of manifest bytes."""
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw)
        order = manifest["review_order"]
        evidence = manifest["evidence"]
        curator = manifest["freeze"]["ego"]
        purpose = dict(LEGACY_PURPOSE)
        if "purpose" in manifest:
            purpose = {target: manifest["purpose"][source] for source, target in {
                "key": "key", "title": "title", "description": "description",
                "relevance_question": "relevanceQuestion",
            }.items()}
            if any(not isinstance(value, str) or not value.strip() for value in purpose.values()):
                raise ValueError("review purpose fields must be nonempty text")
        if not isinstance(curator, str) or not curator.strip():
            raise ValueError("missing frozen curator")
        if not isinstance(order, list) or not order:
            raise ValueError("missing review order")
        if any(not isinstance(aid, str) or not aid for aid in order):
            raise ValueError("invalid account ID in review order")
        if len(order) != len(set(order)):
            raise ValueError("duplicate account IDs in review order")
        cards = []
        for account_id in order:
            card = evidence[account_id]
            if card["account_id"] != account_id:
                raise ValueError("evidence account does not match review order")
            profile = card["profile"]
            if profile is not None:
                profile = {
                    "accountId": profile["account_id"],
                    "username": profile["username"],
                    "displayName": profile["display_name"],
                    "bio": profile["bio"],
                    "location": profile["location"],
                    "fetchedAt": profile["fetched_at"],
                }
            posts = [{
                "tweetId": post["tweet_id"], "text": post["text"],
                "createdAt": post["created_at"], "fetchedAt": post["fetched_at"],
                "source": post["source"], "url": post["url"],
            } for post in card["posts"]]
            cards.append({
                "accountId": account_id, "username": card["username"],
                "profile": profile, "posts": posts,
            })
            if "discovery" in card:
                cards[-1]["discovery"] = project_discovery(card["discovery"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Discovery review manifest is invalid; check the frozen packet schema"
        ) from exc
    return DiscoveryReviewPacket(hashlib.sha256(raw).hexdigest(), curator, cards, purpose)


def validate_answer(packet: DiscoveryReviewPacket, account_id: str, data: Any) -> dict:
    """Validate complete personal judgments without manufacturing defaults."""
    if account_id not in packet.account_ids:
        raise ValueError("accountId is not in the configured discovery review packet")
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    if data.get("packetId") != packet.packet_id:
        raise ValueError("packetId does not match the configured discovery review packet; reload before saving")
    for field, options in {
        "relevance": ("IN", "OUT", "ABSTAIN"),
        "known": ("YES", "NO", "UNSURE"),
        "glad": ("YES", "NO", "UNSURE"),
    }.items():
        if data.get(field) not in options:
            raise ValueError(f"{field} is required and must be one of {', '.join(options)}")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise ValueError("note must be a string")
    return {"relevance": data["relevance"], "known": data["known"], "glad": data["glad"], "note": note}


class DiscoveryReviewStore:
    """Small private database with no dependency on existing tag substrates."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.is_absolute():
            raise RuntimeError("TPOT_DISCOVERY_REVIEW_DB must be an absolute path")
        if self.db_path.exists():
            with sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True) as conn:
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
            if tables - {"discovery_review_answer_events", "sqlite_sequence"}:
                raise RuntimeError(
                    "TPOT_DISCOVERY_REVIEW_DB must be a separate discovery-answer database; unrelated tables found"
                )
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            pass
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS discovery_review_answer_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_id TEXT NOT NULL,
                    curator TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    relevance TEXT NOT NULL CHECK (relevance IN ('IN', 'OUT', 'ABSTAIN')),
                    known TEXT NOT NULL CHECK (known IN ('YES', 'NO', 'UNSURE')),
                    glad TEXT NOT NULL CHECK (glad IN ('YES', 'NO', 'UNSURE')),
                    note TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_discovery_review_subject
                ON discovery_review_answer_events (packet_id, curator, account_id, event_id);
            """)

    def answers_for(self, packet: DiscoveryReviewPacket) -> dict[str, dict]:
        """Latest event per account for this exact packet and frozen curator."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT e.* FROM discovery_review_answer_events e
                JOIN (
                    SELECT account_id, MAX(event_id) AS latest
                    FROM discovery_review_answer_events
                    WHERE packet_id = ? AND curator = ?
                    GROUP BY account_id
                ) current ON e.event_id = current.latest
            """, (packet.packet_id, packet.curator)).fetchall()
        return {
            row["account_id"]: {
                "relevance": row["relevance"], "known": row["known"],
                "glad": row["glad"], "note": row["note"],
                "updatedAt": row["updated_at"], "eventId": row["event_id"],
            }
            for row in rows if row["account_id"] in packet.account_ids
        }

    def append_answer(self, packet: DiscoveryReviewPacket, account_id: str, data: Any) -> dict:
        answer = validate_answer(packet, account_id, data)
        updated_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO discovery_review_answer_events
                (packet_id, curator, account_id, relevance, known, glad, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                packet.packet_id, packet.curator, account_id, answer["relevance"],
                answer["known"], answer["glad"], answer["note"], updated_at,
            ))
        return {**answer, "updatedAt": updated_at, "eventId": int(cursor.lastrowid)}
