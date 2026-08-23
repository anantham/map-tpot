#!/usr/bin/env python3
"""Caption bio-link page images with an ensemble of local vision models.

Runs entirely on the local ollama server, so there is no API spend and no page
belonging to a real person leaves this machine.

Two models vote independently. A model's self-reported confidence is not treated
as evidence — ``gemma4`` was observed emitting ``confidence: 1.0`` beside an
empty caption — so trust is gated on *agreement between independent models*,
the same 2-of-3 consensus rule ``label_tweets_ensemble.py`` already uses.

Disagreement is recorded, never averaged away: "the HTML says company" and "the
picture shows one person" are different claims, and a split vote is a request
for a human, not noise.

Targeting: by default only rows where text classification failed or was weak.
Captioning every fetched page would mostly reproduce "a logo" at length.

Usage
-----
    python scripts/caption_site_images.py --limit 10      # probe first
    python scripts/caption_site_images.py                 # the undecided set
    python scripts/caption_site_images.py --all           # every page with an image
    python scripts/caption_site_images.py --report
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.tweet_enrichment import download_image_base64  # noqa: E402
from src.enrichment import ENSEMBLE_MODELS, consensus, describe  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "archive_tweets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bio_link_image_verdict (
    account_id    TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    model         TEXT NOT NULL,
    image_url     TEXT,
    caption       TEXT,
    kind          TEXT,
    shows_person  INTEGER,
    visible_text  TEXT,
    suggests      TEXT,
    confidence    REAL,
    error         TEXT,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (account_id, source_url, model)
);
CREATE INDEX IF NOT EXISTS idx_img_verdict_account
    ON bio_link_image_verdict(account_id);
"""


def connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")  # the fetch run may hold the DB
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def targets(conn, limit: int | None, everything: bool) -> list[sqlite3.Row]:
    """Rows where an image could actually change or confirm the verdict."""
    scope = "" if everything else (
        " AND (site_type = 'unknown' OR confidence < 0.55)")
    return conn.execute(
        f"""SELECT account_id, source_url, username, site_type, confidence,
                   og_image, title
            FROM bio_link_profile
            WHERE error IS NULL AND og_image IS NOT NULL{scope}
              AND (account_id, source_url) NOT IN (
                  SELECT account_id, source_url FROM bio_link_image_verdict)
            ORDER BY username
            {'LIMIT ' + str(limit) if limit else ''}"""
    ).fetchall()


def store(conn, row, image_url: str, verdicts) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR REPLACE INTO bio_link_image_verdict "
        "(account_id, source_url, model, image_url, caption, kind, shows_person,"
        " visible_text, suggests, confidence, error, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(row["account_id"], row["source_url"], v.model, image_url, v.caption,
          v.kind, int(v.shows_person), v.visible_text, v.suggests,
          v.confidence, v.error, now) for v in verdicts])
    conn.commit()


def report(conn) -> None:
    rows = conn.execute("SELECT * FROM bio_link_image_verdict").fetchall()
    if not rows:
        print("✗ nothing captioned yet")
        return
    by_key: dict[tuple, list] = {}
    for r in rows:
        by_key.setdefault((r["account_id"], r["source_url"]), []).append(r)

    from src.enrichment import ImageVerdict
    agree = Counter()
    resolved: list[tuple] = []
    for (account_id, source_url), group in by_key.items():
        verdicts = [ImageVerdict(g["caption"] or "", g["kind"] or "other",
                                 bool(g["shows_person"]), g["visible_text"] or "",
                                 g["suggests"] or "unclear", g["confidence"] or 0.0,
                                 g["model"], g["error"]) for g in group]
        c = consensus(verdicts)
        agree[c.agreement] += 1
        if c.is_trustworthy:
            resolved.append((account_id, source_url, c))

    print(f"\n{'=' * 66}\nVISION ENSEMBLE REPORT\n{'=' * 66}")
    print(f"pages captioned    {len(by_key)}")
    print(f"models             {', '.join(ENSEMBLE_MODELS)}\n")
    for k in ("unanimous", "majority", "single", "split", "none"):
        if agree[k]:
            mark = "✓" if k in ("unanimous", "majority") else "·"
            print(f"  {mark} {k:<11} {agree[k]:>4}")
    print(f"\ntrustworthy verdicts: {len(resolved)} "
          f"({100 * len(resolved) / max(1, len(by_key)):.0f}%)")

    kinds = Counter(r["kind"] for r in rows if not r["error"])
    print("\nImage kinds seen:")
    for k, n in kinds.most_common(10):
        print(f"  {k or '?':<13} {n:>4}")

    people = conn.execute(
        "SELECT COUNT(DISTINCT account_id) n FROM bio_link_image_verdict "
        "WHERE shows_person = 1 AND error IS NULL").fetchone()["n"]
    print(f"\npages showing a person: {people}")

    splits = [(a, c) for a, _, c in
              [(k[0], k[1], consensus([ImageVerdict(
                  g["caption"] or "", g["kind"] or "other", bool(g["shows_person"]),
                  g["visible_text"] or "", g["suggests"] or "unclear",
                  g["confidence"] or 0.0, g["model"], g["error"]) for g in v]))
               for k, v in by_key.items()] if c.agreement == "split"][:8]
    if splits:
        print("\nModel disagreements (a human should look):")
        for account_id, c in splits:
            u = conn.execute("SELECT username FROM bio_link_profile "
                             "WHERE account_id = ? LIMIT 1", (account_id,)).fetchone()
            print(f"  @{(u['username'] if u else account_id):<20} {c.note[:70]}")
    print(f"{'=' * 66}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--all", action="store_true",
                    help="caption every page with an image, not just undecided ones")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    conn = connect(args.db)
    if args.report:
        report(conn)
        return 0

    rows = targets(conn, args.limit, args.all)
    if not rows:
        print("✓ nothing pending")
        report(conn)
        return 0

    print(f"Captioning {len(rows)} pages with {len(ENSEMBLE_MODELS)} models "
          f"(~{len(rows) * 9.5 / 60:.0f} min)...\n")
    for i, row in enumerate(rows, 1):
        t0 = time.time()
        b64 = download_image_base64(row["og_image"])
        if not b64:
            print(f"  ✗ [{i:>4}/{len(rows)}] @{row['username']:<18} image download failed")
            continue
        verdicts = [describe(b64, model=m) for m in ENSEMBLE_MODELS]
        store(conn, row, row["og_image"], verdicts)
        c = consensus(verdicts)
        mark = "✓" if c.is_trustworthy else ("!" if c.agreement == "split" else "·")
        print(f"  {mark} [{i:>4}/{len(rows)}] @{row['username']:<18} "
              f"[{time.time() - t0:>4.1f}s] text={row['site_type']:<9} "
              f"img={c.suggests:<9} {c.agreement}")
        if c.agreement == "split":
            print(f"        {c.note[:88]}")

    report(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
