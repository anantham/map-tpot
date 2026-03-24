"""Membership confidence index — continuous 0→1 score per account.

Combines multiple evidence signals into a single confidence score
that replaces the binary classified/propagated distinction.

Factors (weights sum to 1.0):
  1. Data richness     (0.25) — archive depth, likes availability
  2. Labeling depth    (0.30) — tweets labeled, total bits
  3. Concentration     (0.20) — how peaked the community distribution is
  4. Network context   (0.15) — classified neighbors in follow graph
  5. Source agreement  (0.10) — do NMF, bits, follows agree?

Usage:
    from src.communities.confidence import compute_confidence, compute_all_confidences
    ci = compute_confidence(conn, account_id)

    # Returns: {"score": 0.72, "factors": {...}, "level": "bits_stable"}
"""
from __future__ import annotations

import logging
import math
import sqlite3
from collections import defaultdict

logger = logging.getLogger(__name__)


def _data_richness(conn: sqlite3.Connection, account_id: str) -> float:
    """Factor 1: How much raw data do we have? (0-0.25)"""
    score = 0.0

    # Has tweets in archive? (0-0.10)
    tweet_count = conn.execute(
        "SELECT COUNT(*) FROM tweets WHERE account_id = ?", (account_id,),
    ).fetchone()[0]
    if tweet_count > 1000:
        score += 0.10
    elif tweet_count > 100:
        score += 0.07
    elif tweet_count > 10:
        score += 0.04
    elif tweet_count > 0:
        score += 0.02

    # Has likes data? (0-0.08) — strongest engagement signal
    likes_given = conn.execute(
        "SELECT COUNT(*) FROM likes WHERE liker_account_id = ?", (account_id,),
    ).fetchone()[0]
    if likes_given > 100:
        score += 0.08
    elif likes_given > 10:
        score += 0.05
    elif likes_given > 0:
        score += 0.02

    # Has follow data in DB? (0-0.04)
    following = conn.execute(
        "SELECT COUNT(*) FROM account_following WHERE account_id = ?", (account_id,),
    ).fetchone()[0]
    if following > 100:
        score += 0.04
    elif following > 0:
        score += 0.02

    # Has engagement aggregation? (0-0.03)
    try:
        engagement_edges = conn.execute(
            "SELECT COUNT(*) FROM account_engagement_agg WHERE source_id = ? OR target_id = ?",
            (account_id, account_id),
        ).fetchone()[0]
        if engagement_edges > 50:
            score += 0.03
        elif engagement_edges > 0:
            score += 0.01
    except sqlite3.OperationalError as exc:
        logger.warning("engagement table missing for confidence calc (account %s): %s", account_id, exc)

    return min(0.25, score)


def _labeling_depth(conn: sqlite3.Connection, account_id: str) -> float:
    """Factor 2: How much human/AI labeling has been done? (0-0.30)"""
    score = 0.0

    # Tweets labeled (0-0.15)
    labeled = conn.execute(
        "SELECT COUNT(DISTINCT tweet_id) FROM tweet_label_set "
        "WHERE tweet_id IN (SELECT tweet_id FROM tweets WHERE account_id = ?)",
        (account_id,),
    ).fetchone()[0]
    if labeled >= 50:
        score += 0.15
    elif labeled >= 20:
        score += 0.12
    elif labeled >= 10:
        score += 0.08
    elif labeled > 0:
        score += 0.04

    # Total bits accumulated (0-0.10)
    rows = conn.execute("""
        SELECT tt.tag FROM tweet_tags tt
        JOIN tweets t ON t.tweet_id = tt.tweet_id
        WHERE tt.category = 'bits' AND t.account_id = ?
    """, (account_id,)).fetchall()
    total_bits = 0
    for (tag,) in rows:
        parts = tag.split(":")
        if len(parts) == 3:
            try:
                total_bits += abs(int(parts[2]))
            except ValueError:
                pass
    if total_bits >= 100:
        score += 0.10
    elif total_bits >= 50:
        score += 0.07
    elif total_bits >= 20:
        score += 0.05
    elif total_bits > 0:
        score += 0.02

    # Has bits rollup? (0-0.05)
    has_rollup = conn.execute(
        "SELECT COUNT(*) FROM account_community_bits WHERE account_id = ?",
        (account_id,),
    ).fetchone()[0]
    if has_rollup > 0:
        score += 0.05

    return min(0.30, score)


def _concentration(conn: sqlite3.Connection, account_id: str) -> float:
    """Factor 3: How concentrated is the community distribution? (0-0.20)

    Low entropy = confident assignment (peaked distribution).
    High entropy = ambiguous (spread across many communities).
    """
    # Get community weights from bits or NMF
    rows = conn.execute("""
        SELECT pct FROM account_community_bits WHERE account_id = ?
    """, (account_id,)).fetchall()

    if not rows:
        rows = conn.execute("""
            SELECT weight * 100 FROM community_account WHERE account_id = ? AND weight >= 0.05
        """, (account_id,)).fetchall()

    if not rows:
        return 0.0

    weights = [r[0] for r in rows]
    total = sum(weights)
    if total <= 0:
        return 0.0

    # Normalize to probabilities
    probs = [w / total for w in weights if w > 0]

    # Shannon entropy
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    # Max entropy for N communities
    max_entropy = math.log2(max(len(probs), 1)) if len(probs) > 1 else 1.0

    # Invert: low entropy = high confidence
    concentration = 1.0 - (entropy / max_entropy) if max_entropy > 0 else 1.0
    return 0.20 * concentration


def _network_context(conn: sqlite3.Connection, account_id: str) -> float:
    """Factor 4: What fraction of neighbors are classified? (0-0.15)"""
    # Following: how many are classified?
    following_total = conn.execute(
        "SELECT COUNT(*) FROM account_following WHERE account_id = ?", (account_id,),
    ).fetchone()[0]

    if following_total == 0:
        return 0.0

    following_classified = conn.execute("""
        SELECT COUNT(DISTINCT af.following_account_id)
        FROM account_following af
        JOIN community_account ca ON ca.account_id = af.following_account_id
        WHERE af.account_id = ? AND ca.weight >= 0.2
    """, (account_id,)).fetchone()[0]

    ratio = following_classified / following_total if following_total > 0 else 0
    # 10%+ classified following = max score
    return 0.15 * min(1.0, ratio * 10)


def _source_agreement(conn: sqlite3.Connection, account_id: str) -> float:
    """Factor 5: Do NMF and bits agree on top communities? (0-0.10)"""
    # Get NMF top community
    nmf_top = conn.execute("""
        SELECT c.short_name FROM community_account ca
        JOIN community c ON c.id = ca.community_id
        WHERE ca.account_id = ? ORDER BY ca.weight DESC LIMIT 1
    """, (account_id,)).fetchone()

    # Get bits top community
    bits_top = conn.execute("""
        SELECT c.short_name FROM account_community_bits acb
        JOIN community c ON c.id = acb.community_id
        WHERE acb.account_id = ? ORDER BY acb.total_bits DESC LIMIT 1
    """, (account_id,)).fetchone()

    if not nmf_top or not bits_top:
        return 0.0  # Can't compare if one source missing

    if nmf_top[0] == bits_top[0]:
        return 0.10  # Full agreement
    else:
        # Check if bits top is in NMF top 3
        nmf_top3 = [r[0] for r in conn.execute("""
            SELECT c.short_name FROM community_account ca
            JOIN community c ON c.id = ca.community_id
            WHERE ca.account_id = ? ORDER BY ca.weight DESC LIMIT 3
        """, (account_id,)).fetchall()]
        if bits_top[0] in nmf_top3:
            return 0.05  # Partial agreement
        return 0.0  # Disagreement


def compute_confidence(conn: sqlite3.Connection, account_id: str) -> dict:
    """Compute membership confidence index for a single account.

    Returns:
        {
            "score": 0.72,
            "level": "bits_stable",
            "factors": {
                "data_richness": 0.22,
                "labeling_depth": 0.25,
                "concentration": 0.15,
                "network_context": 0.05,
                "source_agreement": 0.05,
            },
        }
    """
    factors = {
        "data_richness": _data_richness(conn, account_id),
        "labeling_depth": _labeling_depth(conn, account_id),
        "concentration": _concentration(conn, account_id),
        "network_context": _network_context(conn, account_id),
        "source_agreement": _source_agreement(conn, account_id),
    }

    score = sum(factors.values())

    # Assign level based on score
    if score >= 0.80:
        level = "human_validated"
    elif score >= 0.55:
        level = "bits_stable"
    elif score >= 0.35:
        level = "bits_partial"
    elif score >= 0.15:
        level = "follow_propagated"
    else:
        level = "nmf_only"

    return {"score": round(score, 3), "level": level, "factors": factors}


def compute_all_confidences(db_path: str | None = None) -> list[dict]:
    """Compute confidence for all accounts that have any community data."""
    if db_path is None:
        from src.config import DEFAULT_ARCHIVE_DB
        db_path = str(DEFAULT_ARCHIVE_DB)

    conn = sqlite3.connect(db_path)

    # All accounts with NMF or bits data
    accounts = set()
    for row in conn.execute("SELECT DISTINCT account_id FROM community_account"):
        accounts.add(row[0])
    for row in conn.execute("SELECT DISTINCT account_id FROM account_community_bits"):
        accounts.add(row[0])

    results = []
    for aid in accounts:
        username_row = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (aid,),
        ).fetchone()
        username = username_row[0] if username_row else None

        ci = compute_confidence(conn, aid)
        ci["account_id"] = aid
        ci["username"] = username
        results.append(ci)

    conn.close()
    results.sort(key=lambda x: -x["score"])
    return results
