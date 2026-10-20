#!/usr/bin/env python3
"""Verify frozen discovery evidence and saved review behavior without live writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.serve_discovery_review import create_review_app  # noqa: E402
from src.data.discovery_review_store import load_review_packet  # noqa: E402

OWNER = "synthetic-owner@example.test"
ORIGIN = "https://synthetic-review.example.ts.net:5444"
BASE = "/api/discovery-review"


def require(name: str, passed: bool, detail: str) -> None:
    print(f"{'✓' if passed else '✗'} {name}: {detail}")
    if not passed:
        raise RuntimeError(f"{name} failed: {detail}")


def event_rows(db_path: Path) -> list:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT relevance, known, glad FROM discovery_review_answer_events ORDER BY event_id"
        ).fetchall()


def synthetic_checks() -> None:
    """All writes stay inside one automatically removed temporary directory."""
    with tempfile.TemporaryDirectory(prefix="tpot-discovery-review-verify-") as name:
        temporary = Path(name)
        packet_path = temporary / "manifest.json"
        answer_db = temporary / "answers.db"
        dist = temporary / "dist"
        dist.mkdir()
        (dist / "discovery-review.html").write_text("<h1>Synthetic review</h1>")
        packet_path.write_text(json.dumps({
            "freeze": {"ego": "synthetic-curator"}, "review_order": ["101"],
            "methods": {"hidden-method": [{"account_id": "101", "rank": 1}]},
            "evidence": {"101": {
                "account_id": "101", "username": "synthetic", "profile": None,
                "posts": [], "raw_support": "hidden-support",
            }},
        }))

        def fresh_client():
            app = create_review_app(
                packet_path=packet_path, answer_db=answer_db, dist_dir=dist,
                owner_login=OWNER, origin=ORIGIN,
            )
            app.config["TESTING"] = True
            return app.test_client()

        client = fresh_client()
        owner = {"Tailscale-User-Login": OWNER}
        response = client.get(BASE, base_url=ORIGIN, headers=owner)
        payload = response.get_json() or {}
        require("Owner GET and masked evidence", response.status_code == 200
                and payload.get("totalCount") == 1 and payload.get("answers") == {}
                and response.headers.get("Cache-Control") == "no-store"
                and "hidden" not in response.get_data(as_text=True),
                f"status={response.status_code}; synthetic cards={payload.get('totalCount')}; no-store")
        body = {
            "packetId": payload["packetId"], "relevance": "IN", "known": "NO",
            "glad": "YES", "note": "Synthetic verifier answer, not a real judgment",
        }
        url = f"{BASE}/answers/101"
        write_headers = {**owner, "Origin": ORIGIN}
        saved = client.put(url, base_url=ORIGIN, headers=write_headers, json=body)
        saved_payload = saved.get_json() or {}
        saved_rows = event_rows(answer_db)
        require("Complete answer PUT", saved.status_code == 200
                and saved_payload.get("completedCount") == 1 and len(saved_rows) == 1,
                f"status={saved.status_code}; completed={saved_payload.get('completedCount')}; events={len(saved_rows)}")

        corrected_body = {**body, "relevance": "ABSTAIN", "known": "UNSURE", "glad": "NO"}
        corrected = client.put(url, base_url=ORIGIN, headers=write_headers, json=corrected_body)
        rows = event_rows(answer_db)
        correction_payload = corrected.get_json() or {}
        require("Correction preserves the original", corrected.status_code == 200
                and rows == [("IN", "NO", "YES"), ("ABSTAIN", "UNSURE", "NO")],
                f"status={corrected.status_code}; retained events={len(rows)}; original and correction present")
        reopened = fresh_client().get(BASE, base_url=ORIGIN, headers=owner)
        resumed = reopened.get_json() or {}
        require("Fresh app resumes latest answer", reopened.status_code == 200
                and resumed.get("answers", {}).get("101") == correction_payload.get("answer")
                and resumed.get("completedCount") == 1,
                f"status={reopened.status_code}; completed={resumed.get('completedCount')}; latest=ABSTAIN")

        owner_statuses = []
        for other_headers in ({}, {"Tailscale-User-Login": "other@example.test"}):
            owner_statuses.append(client.get(BASE, base_url=ORIGIN, headers=other_headers).status_code)
            owner_statuses.append(client.put(
                url, base_url=ORIGIN, headers={**other_headers, "Origin": ORIGIN}, json=body,
            ).status_code)
        require("Missing and other owners rejected", owner_statuses == [403] * 4,
                f"GET/PUT statuses={owner_statuses}; no browser curator token used")
        origin_statuses = []
        for wrong_origin in (None, "https://other.example.test"):
            headers = dict(owner)
            if wrong_origin:
                headers["Origin"] = wrong_origin
            origin_statuses.append(client.put(url, base_url=ORIGIN, headers=headers, json=body).status_code)
        require("Missing and wrong Origin rejected", origin_statuses == [403, 403]
                and event_rows(answer_db) == rows,
                f"statuses={origin_statuses}; retained events={len(event_rows(answer_db))}; rejected writes=0")
        changed = json.loads(packet_path.read_text())
        changed["purpose"] = {
            "key": "synthetic-retreat", "title": "Synthetic retreat contributors",
            "description": "Synthetic evidence, not real judgments.",
            "relevance_question": "Worth considering for this synthetic retreat?",
        }
        packet_path.write_text(json.dumps(changed))
        retreat = fresh_client().get(BASE, base_url=ORIGIN, headers=owner).get_json()
        require("Retreat purpose stays separate", retreat["targetTag"] == "synthetic-retreat"
                and retreat["answers"] == {} and retreat["packetId"] != payload["packetId"]
                and event_rows(answer_db) == rows,
                "new purpose visible; old events retained; no labels transferred")
        stale = fresh_client().put(url, base_url=ORIGIN, headers=write_headers, json=body)
        require("Old-page save rejected after packet change", stale.status_code == 400
                and event_rows(answer_db) == rows,
                f"status={stale.status_code}; retained events={len(rows)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path,
                        default=ROOT / "data/private/discovery-review-20260922-v2/manifest.json")
    args = parser.parse_args()
    print("Private Discovery Review Verification")
    print("=" * 40)
    try:
        packet = load_review_packet(args.packet.resolve())
        profiles = sum(card["profile"] is not None for card in packet.cards)
        posts = sum(len(card["posts"]) for card in packet.cards)
        missing_handles = sum(not card["username"] for card in packet.cards)
        require("Real frozen packet read-only", True,
                f"cards={len(packet.cards)}; profiles={profiles}; posts={posts}; missing handles={missing_handles}")
        print(f"Packet SHA256: {packet.packet_id}")
        print(f"Review purpose: {packet.purpose['title']} ({packet.purpose['key']})")
        synthetic_checks()
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"✗ Verification stopped: {exc}")
        print("Next: inspect the named failure; do not activate the review until verification passes.")
        print("Live writes: 0. Any answer events were synthetic temporary data only.")
        return 1
    print("Checks: 9 passed; real packet opened read-only; synthetic answer events: 2.")
    print("Live writes: 0. Temporary packet, frontend stub and answer DB removed.")
    print("Next: open the private review on the owner's tailnet device and visually check the cards before answering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
