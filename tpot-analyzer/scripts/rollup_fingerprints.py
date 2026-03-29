"""Roll up per-tweet tags into per-account epistemic fingerprints.

The fingerprint is the vision's primary representation — not "which community"
but "how does this person relate to ideas." It aggregates:

  1. Simulacrum distribution: L1/L2/L3/L4 averages across labeled tweets
  2. Posture distribution: how they engage (insight, exploration, critique, etc.)
  3. Theme distribution: what topics recur in their tweets
  4. Domain distribution: broad subject areas
  5. Cadence: tweet frequency, reply ratio, RT ratio

Stored in account_fingerprint table. Each account gets one row with JSON
distributions. This is computed from existing tweet_tags + tweet_label_prob
data — no new API calls needed.

Usage:
    .venv/bin/python3 -m scripts.rollup_fingerprints
    .venv/bin/python3 -m scripts.rollup_fingerprints --account repligate
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import DEFAULT_ARCHIVE_DB

logger = logging.getLogger(__name__)


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_fingerprint (
            account_id          TEXT PRIMARY KEY,
            username            TEXT,
            n_tweets_labeled    INTEGER NOT NULL DEFAULT 0,
            simulacrum_json     TEXT,   -- {"l1": 0.45, "l2": 0.15, "l3": 0.30, "l4": 0.10}
            posture_json        TEXT,   -- {"original-insight": 0.30, "playful-exploration": 0.25, ...}
            theme_json          TEXT,   -- {"absurdist-humor": 0.15, "model-interiority": 0.12, ...}
            domain_json         TEXT,   -- {"AI": 0.25, "philosophy": 0.20, ...}
            cadence_json        TEXT,   -- {"tweets_per_week": 12, "reply_ratio": 0.4, "rt_ratio": 0.15}
            evidence_ring       TEXT,   -- core, enriched, profiled, graph_only
            updated_at          TEXT
        )
    """)
    conn.commit()


def _compute_simulacrum(conn: sqlite3.Connection, account_id: str) -> Optional[dict]:
    """Average L1/L2/L3/L4 across all labeled tweets for this account."""
    rows = conn.execute("""
        SELECT tlp.label, AVG(tlp.probability)
        FROM tweet_label_prob tlp
        JOIN tweet_label_set tls ON tls.id = tlp.label_set_id
        JOIN enriched_tweets et ON et.tweet_id = tls.tweet_id
        WHERE et.account_id = ?
        AND tlp.label IN ('l1', 'l2', 'l3', 'l4')
        GROUP BY tlp.label
    """, (account_id,)).fetchall()

    if not rows:
        return None

    dist = {r[0]: round(r[1], 4) for r in rows}
    # Normalize to sum to 1
    total = sum(dist.values())
    if total > 0:
        dist = {k: round(v / total, 4) for k, v in dist.items()}
    return dist


def _compute_distribution(
    conn: sqlite3.Connection, account_id: str, category: str, top_n: int = 15,
) -> Optional[dict]:
    """Compute normalized tag distribution for a category (posture, thematic, domain)."""
    rows = conn.execute("""
        SELECT tt.tag, COUNT(*) as cnt
        FROM tweet_tags tt
        JOIN enriched_tweets et ON et.tweet_id = tt.tweet_id
        WHERE et.account_id = ?
        AND tt.category = ?
        GROUP BY tt.tag
        ORDER BY cnt DESC
        LIMIT ?
    """, (account_id, category, top_n)).fetchall()

    if not rows:
        return None

    total = sum(r[1] for r in rows)
    # Strip category prefix (e.g., "posture:original-insight" → "original-insight")
    dist = {}
    for tag, cnt in rows:
        clean = tag.split(":", 1)[1] if ":" in tag else tag
        dist[clean] = round(cnt / total, 4)
    return dist


def _compute_cadence(conn: sqlite3.Connection, account_id: str) -> Optional[dict]:
    """Compute posting cadence from enriched_tweets."""
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_reply = 1 THEN 1 ELSE 0 END) as replies,
            SUM(CASE WHEN text LIKE 'RT @%%' THEN 1 ELSE 0 END) as rts,
            MIN(created_at) as earliest,
            MAX(created_at) as latest
        FROM enriched_tweets
        WHERE account_id = ?
    """, (account_id,)).fetchone()

    if not stats or stats[0] == 0:
        return None

    total, replies, rts, earliest, latest = stats
    cadence = {
        "total_tweets": total,
        "reply_ratio": round(replies / total, 3) if total else 0,
        "rt_ratio": round(rts / total, 3) if total else 0,
        "original_ratio": round((total - replies - rts) / total, 3) if total else 0,
    }

    # Compute tweets per week if we have date range
    try:
        from dateutil import parser as dp
        if earliest and latest:
            e = dp.parse(earliest.replace("+0000", "UTC"))
            l = dp.parse(latest.replace("+0000", "UTC"))
            days = max((l - e).days, 1)
            cadence["tweets_per_week"] = round(total / (days / 7), 1)
            cadence["span_days"] = days
    except Exception:
        pass

    return cadence


def _determine_ring(conn: sqlite3.Connection, account_id: str) -> str:
    """Determine which evidence ring this account belongs to."""
    # Core: has archive tweets
    has_archive = conn.execute(
        "SELECT 1 FROM tweets WHERE account_id = ? LIMIT 1", (account_id,)
    ).fetchone()
    if has_archive:
        return "core"

    # Enriched: has API-fetched tweets + labels
    has_enriched = conn.execute(
        "SELECT 1 FROM enriched_tweets WHERE account_id = ? LIMIT 1", (account_id,)
    ).fetchone()
    if has_enriched:
        return "enriched"

    # Profiled: has bio/profile data
    has_profile = None
    try:
        has_profile = conn.execute(
            "SELECT 1 FROM user_profile_cache WHERE account_id = ? LIMIT 1", (account_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        pass
    if has_profile:
        return "profiled"

    return "graph_only"


def rollup_account(conn: sqlite3.Connection, account_id: str) -> dict:
    """Compute full fingerprint for a single account."""
    # Get username
    uname_row = conn.execute(
        "SELECT username FROM resolved_accounts WHERE account_id = ?", (account_id,)
    ).fetchone()
    if not uname_row:
        uname_row = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (account_id,)
        ).fetchone()
    username = uname_row[0] if uname_row else None

    # Count labeled tweets
    n_labeled = conn.execute("""
        SELECT COUNT(DISTINCT tt.tweet_id)
        FROM tweet_tags tt
        JOIN enriched_tweets et ON et.tweet_id = tt.tweet_id
        WHERE et.account_id = ?
    """, (account_id,)).fetchone()[0]

    simulacrum = _compute_simulacrum(conn, account_id)
    posture = _compute_distribution(conn, account_id, "posture")
    theme = _compute_distribution(conn, account_id, "thematic")
    domain = _compute_distribution(conn, account_id, "domain")
    cadence = _compute_cadence(conn, account_id)
    ring = _determine_ring(conn, account_id)

    return {
        "account_id": account_id,
        "username": username,
        "n_tweets_labeled": n_labeled,
        "simulacrum": simulacrum,
        "posture": posture,
        "theme": theme,
        "domain": domain,
        "cadence": cadence,
        "evidence_ring": ring,
    }


def store_fingerprint(conn: sqlite3.Connection, fp: dict) -> None:
    """Store a fingerprint in account_fingerprint table."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO account_fingerprint
        (account_id, username, n_tweets_labeled, simulacrum_json,
         posture_json, theme_json, domain_json, cadence_json,
         evidence_ring, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        fp["account_id"],
        fp["username"],
        fp["n_tweets_labeled"],
        json.dumps(fp["simulacrum"]) if fp["simulacrum"] else None,
        json.dumps(fp["posture"]) if fp["posture"] else None,
        json.dumps(fp["theme"]) if fp["theme"] else None,
        json.dumps(fp["domain"]) if fp["domain"] else None,
        json.dumps(fp["cadence"]) if fp["cadence"] else None,
        fp["evidence_ring"],
        now,
    ))


def rollup_all(conn: sqlite3.Connection) -> int:
    """Roll up fingerprints for all accounts with labeled tweets."""
    _ensure_table(conn)

    # Find all accounts with tweet tags
    accounts = conn.execute("""
        SELECT DISTINCT et.account_id
        FROM enriched_tweets et
        JOIN tweet_tags tt ON tt.tweet_id = et.tweet_id
    """).fetchall()

    count = 0
    for (account_id,) in accounts:
        fp = rollup_account(conn, account_id)
        store_fingerprint(conn, fp)
        count += 1

        if fp["simulacrum"]:
            sim_str = " ".join(f"{k}={v:.0%}" for k, v in sorted(fp["simulacrum"].items()))
        else:
            sim_str = "no simulacrum"

        top_posture = ""
        if fp["posture"]:
            top = max(fp["posture"].items(), key=lambda x: x[1])
            top_posture = f" posture={top[0]}({top[1]:.0%})"

        top_theme = ""
        if fp["theme"]:
            top = max(fp["theme"].items(), key=lambda x: x[1])
            top_theme = f" theme={top[0]}({top[1]:.0%})"

        logger.info(
            "  @%-25s ring=%-8s tweets=%3d %s%s%s",
            fp["username"] or "?", fp["evidence_ring"],
            fp["n_tweets_labeled"], sim_str, top_posture, top_theme,
        )

    conn.commit()
    return count


def main():
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Roll up epistemic fingerprints per account")
    parser.add_argument("--account", type=str, help="Single account username to roll up")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_ARCHIVE_DB)
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db_path))
    _ensure_table(conn)

    if args.account:
        row = conn.execute(
            "SELECT account_id FROM resolved_accounts WHERE lower(username) = lower(?)",
            (args.account,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT account_id FROM profiles WHERE lower(username) = lower(?)",
                (args.account,),
            ).fetchone()
        if not row:
            logger.error("Account not found: @%s", args.account)
            return

        fp = rollup_account(conn, row[0])
        store_fingerprint(conn, fp)
        conn.commit()

        print(f"\n@{fp['username']} ({fp['evidence_ring']} ring, {fp['n_tweets_labeled']} tweets):")
        if fp["simulacrum"]:
            print(f"  Simulacrum: {json.dumps(fp['simulacrum'])}")
        if fp["posture"]:
            print(f"  Posture:    {json.dumps(fp['posture'])}")
        if fp["theme"]:
            top_5 = dict(list(fp["theme"].items())[:5])
            print(f"  Themes:     {json.dumps(top_5)}")
        if fp["domain"]:
            print(f"  Domains:    {json.dumps(fp['domain'])}")
        if fp["cadence"]:
            print(f"  Cadence:    {json.dumps(fp['cadence'])}")
    else:
        count = rollup_all(conn)
        total = conn.execute("SELECT COUNT(*) FROM account_fingerprint").fetchone()[0]
        print(f"\nRolled up {count} fingerprints ({total} total in table)")

    conn.close()


if __name__ == "__main__":
    main()
