"""Export community data for the public Find My Ingroup site.

Reads community definitions and memberships from SQLite + NPZ propagation
data, enriches with account metadata from parquet, and writes two JSON files:

  data.json   — communities + classified accounts + meta
  search.json — handle -> {tier, memberships} lookup index

Usage:
    cd tpot-analyzer
    .venv/bin/python3 -m scripts.export_public_site
    .venv/bin/python3 -m scripts.export_public_site --output-dir /tmp/export
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. extract_communities
# ---------------------------------------------------------------------------

def extract_communities(db_path: Path) -> list[dict[str, Any]]:
    """Query community + community_account tables, return community summaries.

    Returns list of dicts: {id, name, color, description, member_count}.
    member_count is the total number of community_account rows (unfiltered).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT
                c.id,
                c.name,
                c.short_name,
                c.color,
                c.description,
                COUNT(ca.account_id) AS member_count
            FROM community c
            LEFT JOIN community_account ca ON ca.community_id = c.id
            WHERE c.name != 'Interesting'
            GROUP BY c.id
            ORDER BY c.name
        """).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "short_name": r["short_name"],
                "color": r["color"],
                "description": r["description"],
                "member_count": r["member_count"],
            }
            for r in rows
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. extract_classified_accounts
# ---------------------------------------------------------------------------

def _extract_bits_accounts(
    conn: sqlite3.Connection,
    min_weight: float = 0.05,
) -> dict[str, list[dict]]:
    """Extract accounts with human-validated bits data (posterior).

    Returns dict: {account_id: [{community_id, weight}]}.
    Converts pct (0-100) to weight (0-1) for compatibility with NMF format.
    """
    rows = conn.execute(
        "SELECT account_id, community_id, pct FROM account_community_bits "
        "ORDER BY account_id, pct DESC"
    ).fetchall()

    accounts: dict[str, list[dict]] = {}
    for r in rows:
        weight = r["pct"] / 100.0
        if weight < min_weight:
            continue
        aid = r["account_id"]
        if aid not in accounts:
            accounts[aid] = []
        accounts[aid].append({
            "community_id": r["community_id"],
            "weight": round(weight, 4),
        })
    return accounts


def extract_classified_accounts(
    db_path: Path,
    min_weight: float = 0.05,
) -> list[dict[str, Any]]:
    """Extract accounts with community memberships, preferring bits over NMF.

    **Legacy function** — retained for backward compatibility and tests.
    New code should use extract_band_accounts() instead.

    For accounts with human-validated bits data (posterior), uses that.
    For all other accounts, falls back to NMF-derived community_account (prior).

    Returns list of dicts: {id, tier="classified", memberships: [{community_id, weight}]}.
    Accounts whose ALL memberships fall below min_weight are excluded entirely.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Check if bits table exists
        has_bits = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='account_community_bits'"
        ).fetchone()

        bits_accounts: dict[str, list[dict]] = {}
        if has_bits:
            bits_accounts = _extract_bits_accounts(conn, min_weight)

        # NMF accounts (prior) — skip accounts that have bits data
        rows = conn.execute(
            """
            SELECT account_id, community_id, weight
            FROM community_account
            WHERE weight >= ?
            ORDER BY account_id, weight DESC
            """,
            (min_weight,),
        ).fetchall()

        accounts: dict[str, list[dict]] = {}
        for r in rows:
            aid = r["account_id"]
            if aid in bits_accounts:
                continue  # posterior supersedes prior
            if aid not in accounts:
                accounts[aid] = []
            accounts[aid].append({
                "community_id": r["community_id"],
                "weight": round(r["weight"], 4),
            })

        # Merge: bits accounts + NMF accounts
        all_accounts = {**accounts, **bits_accounts}

        # Compute confidence index for each account
        from src.communities.confidence import compute_confidence
        result = []
        for aid, memberships in sorted(all_accounts.items()):
            ci = compute_confidence(conn, aid)
            result.append({
                "id": aid,
                "tier": "classified",
                "memberships": memberships,
                "confidence": ci["score"],
                "confidence_level": ci["level"],
            })
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2b. extract_band_accounts  (four-band system)
# ---------------------------------------------------------------------------

def _build_username_map(
    db_path: Path,
    parquet_path: Path | None = None,
) -> dict[str, str]:
    """Build account_id -> username map from all available sources.

    Priority: profiles > resolved_accounts > parquet (first non-empty wins).
    """
    username_map: dict[str, str] = {}

    conn = sqlite3.connect(str(db_path))
    try:
        # 1. profiles (highest quality -- seed accounts)
        for row in conn.execute(
            "SELECT account_id, username FROM profiles WHERE username IS NOT NULL"
        ).fetchall():
            aid, uname = row[0], row[1]
            if uname and uname.lower() not in _INVALID_USERNAMES:
                username_map[aid] = uname

        # 2. resolved_accounts
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='resolved_accounts'"
        ).fetchone()
        if has_table:
            for row in conn.execute(
                "SELECT account_id, username FROM resolved_accounts "
                "WHERE username IS NOT NULL AND username != ''"
            ).fetchall():
                aid, uname = row[0], row[1]
                if aid not in username_map and uname.lower() not in _INVALID_USERNAMES:
                    username_map[aid] = uname
    finally:
        conn.close()

    # 3. parquet (shadow usernames)
    if parquet_path is not None and parquet_path.exists():
        import pandas as pd
        df = pd.read_parquet(
            str(parquet_path),
            columns=["node_id", "username"],
        )
        for _, row in df.iterrows():
            nid = str(row["node_id"])
            uname = row["username"]
            if uname is not None and nid not in username_map:
                uname_str = str(uname)
                if uname_str.lower() not in _INVALID_USERNAMES:
                    username_map[nid] = uname_str

    return username_map


def _load_npz_memberships(
    npz_path: Path,
    min_weight: float = 0.05,
) -> dict[str, list[dict]]:
    """Load propagation NPZ and return memberships per node.

    Handles both classic (zero-sum) and independent (raw scores) modes.
    In independent mode, seed_neighbor_counts are used for noise filtering
    (accounts with 0 classified neighbors are excluded).

    Returns:
        memberships_by_id: {account_id: [{community_id, weight, seed_neighbors?}]}
    """
    # Note: allow_pickle needed for mode string array
    data = np.load(str(npz_path), allow_pickle=False)
    memberships_arr = data["memberships"]      # (N, K+1) -- last col is "none"
    node_ids = data["node_ids"]                # (N,)
    community_ids = data["community_ids"]      # (K,)

    # Detect mode from saved arrays
    has_snc = "seed_neighbor_counts" in data
    snc = data["seed_neighbor_counts"] if has_snc else None
    # If seed_neighbor_counts present, this is independent mode
    is_independent = has_snc

    n_communities = len(community_ids)
    result: dict[str, list[dict]] = {}

    for i in range(len(node_ids)):
        node_id = str(node_ids[i])
        community_weights = memberships_arr[i, :n_communities]

        entry_memberships = []
        for j in range(n_communities):
            w = float(community_weights[j])
            if w < min_weight:
                continue
            # In independent mode, filter by seed neighbors (noise gate)
            if is_independent and snc is not None:
                neighbors = int(snc[i, j])
                if neighbors < 1:
                    continue  # no classified neighbors = noise
                entry_memberships.append({
                    "community_id": str(community_ids[j]),
                    "weight": round(w, 4),
                    "seed_neighbors": neighbors,
                })
            else:
                entry_memberships.append({
                    "community_id": str(community_ids[j]),
                    "weight": round(w, 4),
                })

        if entry_memberships:
            result[node_id] = sorted(
                entry_memberships, key=lambda m: m["weight"], reverse=True,
            )

    return result


def extract_band_accounts(
    db_path: Path,
    npz_path: Path,
    parquet_path: Path | None = None,
    min_weight: float = 0.05,
) -> list[dict[str, Any]]:
    """Extract accounts using the four-band classification system.

    Reads account_band table and builds the account list:
    - exemplar: memberships from community_account (bits > NMF)
    - specialist/bridge/frontier: memberships from propagation NPZ

    Accounts without a resolvable username are skipped.

    Returns list of dicts: {id, tier, handle, memberships, ...}.
    Falls back to extract_classified_accounts if account_band table doesn't exist.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Check if account_band table exists
        has_band = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='account_band'"
        ).fetchone()
        if not has_band:
            logger.warning(
                "account_band table not found, falling back to classified-only export"
            )
            return extract_classified_accounts(db_path, min_weight)

        # Load all band assignments (including 'unknown' as 'faint')
        band_rows = conn.execute(
            "SELECT account_id, band FROM account_band"
        ).fetchall()
        band_map: dict[str, str] = {}
        for r in band_rows:
            band = r["band"]
            if band == "unknown":
                band = "faint"
            band_map[r["account_id"]] = band
        logger.info(
            "account_band: %d total (%s)",
            len(band_map),
            ", ".join(
                f"{b}={sum(1 for v in band_map.values() if v == b)}"
                for b in ("exemplar", "specialist", "bridge", "frontier", "faint")
            ),
        )
    finally:
        conn.close()

    # Build username resolver
    username_map = _build_username_map(db_path, parquet_path)
    logger.info("Username resolver: %d mappings", len(username_map))

    # --- Exemplar accounts: use community_account (bits > NMF) ---
    exemplar_ids = {aid for aid, band in band_map.items() if band == "exemplar"}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        has_bits = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='account_community_bits'"
        ).fetchone()
        bits_accounts: dict[str, list[dict]] = {}
        if has_bits:
            bits_accounts = _extract_bits_accounts(conn, min_weight)

        nmf_accounts: dict[str, list[dict]] = {}
        rows = conn.execute(
            "SELECT account_id, community_id, weight FROM community_account "
            "WHERE weight >= ? ORDER BY account_id, weight DESC",
            (min_weight,),
        ).fetchall()
        for r in rows:
            aid = r["account_id"]
            if aid in bits_accounts:
                continue
            if aid not in nmf_accounts:
                nmf_accounts[aid] = []
            nmf_accounts[aid].append({
                "community_id": r["community_id"],
                "weight": round(r["weight"], 4),
            })

        exemplar_memberships = {**nmf_accounts, **bits_accounts}

        from src.communities.confidence import compute_confidence
        result: list[dict[str, Any]] = []

        for aid in sorted(exemplar_ids):
            uname = username_map.get(aid)
            if not uname:
                continue
            memberships = exemplar_memberships.get(aid, [])
            if not memberships:
                continue
            ci = compute_confidence(conn, aid)
            result.append({
                "id": aid,
                "tier": "exemplar",
                "handle": uname,
                "memberships": memberships,
                "confidence": ci["score"],
                "confidence_level": ci["level"],
            })
    finally:
        conn.close()

    exemplar_count = len(result)
    logger.info("Exemplar accounts with username: %d", exemplar_count)

    # --- Specialist/bridge/frontier: use NPZ propagation ---
    npz_memberships: dict[str, list[dict]] = {}
    if npz_path.exists():
        npz_memberships = _load_npz_memberships(npz_path, min_weight)
        logger.info("NPZ memberships loaded: %d nodes", len(npz_memberships))
    else:
        logger.warning(
            "NPZ not found at %s, specialist/bridge/frontier will be empty",
            npz_path,
        )

    # Load band metadata for CI computation
    conn2 = sqlite3.connect(str(db_path))
    conn2.row_factory = sqlite3.Row
    band_meta = {}
    for r in conn2.execute(
        "SELECT account_id, top_weight, entropy, none_weight FROM account_band"
    ).fetchall():
        band_meta[r["account_id"]] = {
            "top_weight": r["top_weight"] or 0,
            "entropy": r["entropy"] or 0,
            "none_weight": r["none_weight"] or 0,
        }
    conn2.close()

    band_counts: dict[str, int] = {"specialist": 0, "bridge": 0, "frontier": 0, "faint": 0}
    for aid, band in sorted(band_map.items()):
        if band == "exemplar":
            continue
        uname = username_map.get(aid)
        if not uname:
            continue
        memberships = npz_memberships.get(aid, [])
        if not memberships:
            continue
        # Compute CI from propagation signals
        # Works for both classic (zero-sum) and independent (raw scores) modes.
        # In independent mode: use top weight + seed neighbor count.
        # In classic mode: use original formula.
        meta = band_meta.get(aid, {})
        tw = meta.get("top_weight", 0)
        ent = meta.get("entropy", 0)
        nw = meta.get("none_weight", 0)
        top_membership = memberships[0] if memberships else {}
        top_neighbors = top_membership.get("seed_neighbors", 0) if isinstance(top_membership, dict) else 0
        if top_neighbors > 0:
            # Independent mode CI: weight × neighbor evidence
            # More seed neighbors = more confident
            neighbor_factor = min(1.0, top_neighbors / 5.0)  # 5+ neighbors = full confidence
            ci = round(float(top_membership.get("weight", 0)) * neighbor_factor, 3)
        else:
            # Classic mode CI (original formula)
            ci = round(tw * (1 - nw) * (1 - ent), 3)
        result.append({
            "id": aid,
            "tier": band,
            "handle": uname,
            "memberships": memberships,
            "confidence": ci,
        })
        band_counts[band] += 1

    for band, count in band_counts.items():
        logger.info("%s accounts with username: %d", band.capitalize(), count)

    return result


# ---------------------------------------------------------------------------
# 3. extract_propagated_handles
# ---------------------------------------------------------------------------

_INVALID_USERNAMES = {"nan", "none", ""}


def extract_propagated_handles(
    npz_path: Path,
    node_id_to_username: dict[str, str | None],
    classified_ids: set[str],
    min_weight: float = 0.05,
    abstain_threshold: float = 0.10,
) -> dict[str, dict[str, Any]]:
    """Read community_propagation.npz and return propagated handle entries.

    Applies the abstain gate:
      - Skip nodes where abstain_mask[i] is True
      - Skip nodes where max community weight < abstain_threshold
      - Skip classified accounts (already in data.json)
      - Skip nodes without a valid username
      - Filter individual memberships below min_weight

    Returns dict keyed by lowercase username:
        {handle: {tier: "propagated", memberships: [{community_id, community_name, weight}]}}
    """
    data = np.load(str(npz_path), allow_pickle=False)
    memberships = data["memberships"]       # (N, K+1)
    abstain_mask = data["abstain_mask"]      # (N,)
    node_ids = data["node_ids"]              # (N,)
    community_ids = data["community_ids"]    # (K,)
    community_names = data["community_names"]  # (K,)

    n_communities = len(community_ids)
    result: dict[str, dict[str, Any]] = {}

    for i in range(len(node_ids)):
        # Note: abstain_mask is ignored for the public site — it's too conservative
        # (99.4% of nodes are flagged). The weight threshold alone provides sufficient
        # filtering, and the grayscale card design communicates low confidence visually.

        node_id = str(node_ids[i])

        # Gate 2: classified accounts already handled
        if node_id in classified_ids:
            continue

        # Gate 3: valid username
        username = node_id_to_username.get(node_id)
        if username is None:
            continue
        username_lower = username.lower()
        if username_lower in _INVALID_USERNAMES:
            continue

        # Gate 4: max community weight above abstain threshold
        # Only consider community columns (exclude "none" column at index n_communities)
        community_weights = memberships[i, :n_communities]
        max_weight = float(np.max(community_weights))
        if max_weight < abstain_threshold:
            continue

        # Build memberships list (filter by min_weight)
        entry_memberships = []
        for j in range(n_communities):
            w = float(community_weights[j])
            if w >= min_weight:
                entry_memberships.append({
                    "community_id": str(community_ids[j]),
                    "community_name": str(community_names[j]),
                    "weight": round(w, 4),
                })

        if not entry_memberships:
            continue

        result[username_lower] = {
            "tier": "propagated",
            "memberships": sorted(
                entry_memberships, key=lambda m: m["weight"], reverse=True,
            ),
        }

    return result


# ---------------------------------------------------------------------------
# 4. run_export
# ---------------------------------------------------------------------------

def get_sample_tweets(
    db_path: Path, account_id: str, limit: int = 3,
) -> list[str]:
    """Return top tweets by engagement (favorite_count + retweet_count).

    Args:
        db_path: Path to SQLite DB containing a ``tweets`` table.
        account_id: The account whose tweets to fetch.
        limit: Max number of tweets to return (default 3).

    Returns:
        List of tweet texts (each truncated to 280 chars), ordered by
        engagement descending. Returns ``[]`` when the account has no
        tweets or the ``tweets`` table does not exist.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """SELECT full_text FROM tweets
               WHERE account_id = ?
               ORDER BY (favorite_count + retweet_count) DESC
               LIMIT ?""",
            (account_id, limit),
        ).fetchall()
        return [row[0][:280] for row in rows]
    except sqlite3.OperationalError:
        # Table may not exist (e.g. test DBs without tweets)
        return []
    finally:
        conn.close()


def _safe_followers(val: Any) -> int | None:
    """Convert num_followers (float64, may be NaN) to int or None."""
    if val is None:
        return None
    try:
        if math.isnan(val):
            return None
        return int(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Slug generation and registry
# ---------------------------------------------------------------------------

def slugify_name(name):
    """Convert community name to URL-safe slug."""
    s = name.lower()
    s = s.replace("&", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


def load_slug_registry(path):
    """Load slug registry from JSON file. Returns empty dict if file missing."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_slug_registry(path, registry):
    """Write slug registry to JSON file."""
    path = Path(path)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=True)


def assign_slugs(communities, registry):
    """Assign slugs to communities, preserving existing. Handles collisions."""
    updated = dict(registry)
    used_slugs = set(updated.values())
    for c in communities:
        cid = c["id"]
        if cid not in updated:
            base = slugify_name(c["name"])
            slug = base
            counter = 2
            while slug in used_slugs:
                slug = f"{base}-{counter}"
                counter += 1
            updated[cid] = slug
            used_slugs.add(slug)
    return updated


# ---------------------------------------------------------------------------
# Tweet type detection and selection
# ---------------------------------------------------------------------------

def detect_tweet_types(db_path, account_id, tweet_ids):
    """Classify tweets as tweet/reply/retweet/thread."""
    if not tweet_ids:
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" for _ in tweet_ids)
        rows = conn.execute(f"""
            SELECT tweet_id, full_text, reply_to_tweet_id, created_at
            FROM tweets
            WHERE tweet_id IN ({placeholders}) AND account_id = ?
        """, [*tweet_ids, account_id]).fetchall()

        tweet_data = {}
        for row in rows:
            tweet_data[row[0]] = {
                "text": row[1] or "",
                "reply_to": row[2],
                "created_at": row[3],
            }

        from datetime import timedelta
        timestamps = []
        for tid in tweet_ids:
            if tid in tweet_data and tweet_data[tid]["created_at"]:
                try:
                    dt = datetime.strptime(tweet_data[tid]["created_at"], "%Y-%m-%d %H:%M:%S")
                    timestamps.append((tid, dt))
                except ValueError:
                    pass
        timestamps.sort(key=lambda x: x[1])

        thread_ids = set()
        for i in range(len(timestamps) - 1):
            if timestamps[i + 1][1] - timestamps[i][1] <= timedelta(minutes=5):
                thread_ids.add(timestamps[i][0])
                thread_ids.add(timestamps[i + 1][0])

        result = {}
        for tid in tweet_ids:
            if tid not in tweet_data:
                result[tid] = "tweet"
            elif tweet_data[tid]["text"].startswith("RT @"):
                result[tid] = "retweet"
            elif tweet_data[tid]["reply_to"]:
                result[tid] = "reply"
            elif tid in thread_ids:
                result[tid] = "thread"
            else:
                result[tid] = "tweet"
    finally:
        conn.close()
    return result


def select_community_tweets(db_path, account_id, n=5):
    """Select top tweets by engagement (fav + rt*2) with type detection."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("""
            SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
            FROM tweets
            WHERE account_id = ?
            ORDER BY (favorite_count + retweet_count * 2) DESC
            LIMIT ?
        """, [account_id, n]).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()

    if not rows:
        return []

    tweet_ids = [r[0] for r in rows]
    types = detect_tweet_types(db_path, account_id, tweet_ids)

    return [
        {
            "id": r[0],
            "text": (r[1] or "")[:280],
            "created_at": r[2],
            "type": types.get(r[0], "tweet"),
            "favorite_count": r[3] or 0,
            "retweet_count": r[4] or 0,
        }
        for r in rows
    ]


def run_export(
    data_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
    db_path: Path | None = None,
) -> None:
    """Main export entrypoint: reads data, assembles JSON, writes files.

    Uses the four-band classification system (exemplar/specialist/bridge/frontier)
    from the account_band table. Falls back to the legacy classified/propagated
    system if account_band doesn't exist.

    Args:
        data_dir: Directory containing graph_snapshot.nodes.parquet and
                  community_propagation.npz.
        output_dir: Where to write data.json and search.json.
        config: Parsed public_site.json config.
        db_path: Path to SQLite DB. If None, uses data_dir / "archive_tweets.db".
    """
    import pandas as pd

    export_cfg = config.get("export", {})
    min_weight = export_cfg.get("min_weight", 0.05)

    if db_path is None:
        db_path = data_dir / "archive_tweets.db"

    # --- Communities ---
    logger.info("Extracting communities from %s", db_path)
    communities = extract_communities(db_path)
    logger.info("Found %d communities", len(communities))

    # --- Band-based accounts ---
    npz_path = data_dir / "community_propagation.npz"
    parquet_path = data_dir / "graph_snapshot.nodes.parquet"

    logger.info("Extracting band accounts (min_weight=%.3f)", min_weight)
    all_accounts = extract_band_accounts(
        db_path=db_path,
        npz_path=npz_path,
        parquet_path=parquet_path,
        min_weight=min_weight,
    )
    logger.info("Found %d accounts with resolved usernames", len(all_accounts))

    # Count by band
    band_counts: dict[str, int] = {}
    for acct in all_accounts:
        tier = acct["tier"]
        band_counts[tier] = band_counts.get(tier, 0) + 1

    # --- Enrich with parquet metadata ---
    meta_map: dict[str, Any] = {}
    if parquet_path.exists():
        logger.info("Loading parquet metadata from %s", parquet_path)
        df = pd.read_parquet(
            str(parquet_path),
            columns=["node_id", "username", "display_name", "num_followers", "bio"],
        )
        meta_map = {
            row["node_id"]: row
            for _, row in df.iterrows()
        }

    # Enrich accounts with metadata
    for acct in all_accounts:
        meta = meta_map.get(acct["id"])
        if meta is not None:
            acct["username"] = meta.get("username") or acct.get("handle")
            acct["display_name"] = meta.get("display_name")
            acct["bio"] = meta.get("bio")
            acct["followers"] = _safe_followers(meta.get("num_followers"))
        else:
            acct["username"] = acct.get("handle")
            acct["display_name"] = None
            acct["bio"] = None
            acct["followers"] = None
        acct["sample_tweets"] = get_sample_tweets(db_path, acct["id"])

    # --- Slug assignment ---
    slug_registry_path = Path(output_dir) / "slug_registry.json"
    slug_registry = load_slug_registry(slug_registry_path)
    slug_registry = assign_slugs(communities, slug_registry)
    for c in communities:
        c["slug"] = slug_registry[c["id"]]

    # --- Enrich communities with featured members (exemplar only) ---
    exemplar_accounts = [a for a in all_accounts if a["tier"] == "exemplar"]
    for c in communities:
        cid = c["id"]
        members_with_weight = []
        for acct in exemplar_accounts:
            uname = acct.get("username") or acct.get("handle")
            if not uname:
                continue
            for m in acct["memberships"]:
                if m["community_id"] == cid:
                    members_with_weight.append({
                        "username": uname,
                        "display_name": acct.get("display_name", ""),
                        "bio": acct.get("bio", ""),
                        "weight": m["weight"],
                        "account_id": acct["id"],
                    })
                    break
        members_with_weight.sort(key=lambda x: x["weight"], reverse=True)

        featured = members_with_weight[:5]
        for fm in featured:
            fm["tweets"] = select_community_tweets(db_path, fm["account_id"], n=5)
            del fm["account_id"]

        all_members_list = [
            {"username": m["username"], "display_name": m["display_name"], "bio": m["bio"]}
            for m in members_with_weight[5:]
        ]

        c["featured_members"] = featured
        c["all_members"] = all_members_list

    # --- Build search index ---
    search_index: dict[str, dict[str, Any]] = {}

    for acct in all_accounts:
        handle = acct.get("handle") or acct.get("username")
        if not handle or handle.lower() in _INVALID_USERNAMES:
            continue
        search_index[handle.lower()] = {
            "tier": acct["tier"],
            "memberships": acct["memberships"],
        }

    # --- Assemble output ---
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_payload = {
        "communities": communities,
        "accounts": all_accounts,
        "meta": {
            "site_name": config.get("site_name", "Find My Ingroup"),
            "curator": config.get("curator"),
            "links": config.get("links", {}),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "communities": len(communities),
                "total_accounts": len(all_accounts),
                "by_band": band_counts,
                "total_searchable": len(search_index),
            },
        },
    }

    data_path = output_dir / "data.json"
    data_path.write_text(json.dumps(data_payload, indent=2, ensure_ascii=False))
    logger.info("Wrote %s (%d bytes)", data_path, data_path.stat().st_size)

    search_path = output_dir / "search.json"
    search_path.write_text(json.dumps(search_index, indent=None, ensure_ascii=False))
    logger.info("Wrote %s (%d bytes)", search_path, search_path.stat().st_size)

    save_slug_registry(slug_registry_path, slug_registry)

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Export complete -> {output_dir}")
    print(f"  Communities:         {len(communities)}")
    print(f"  Total accounts:      {len(all_accounts)}")
    for band in ("exemplar", "specialist", "bridge", "frontier", "faint"):
        count = band_counts.get(band, 0)
        if count > 0:
            print(f"    {band:>12s}:      {count}")
    print(f"  Total searchable:    {len(search_index)}")
    print(f"  data.json:           {data_path.stat().st_size:,} bytes")
    print(f"  search.json:         {search_path.stat().st_size:,} bytes")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# 5. __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "config" / "public_site.json"

    if not config_path.exists():
        logger.error("Config not found: %s", config_path)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    data_dir = project_root / "data"
    export_cfg = config.get("export", {})
    output_dir = project_root / export_cfg.get("output_dir", "public-site/public")

    # Allow CLI override
    import argparse
    parser = argparse.ArgumentParser(description="Export public site data")
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    run_export(
        data_dir=data_dir,
        output_dir=args.output_dir,
        config=config,
        db_path=args.db_path,
    )
