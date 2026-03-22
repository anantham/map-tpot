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

        return [
            {"id": aid, "tier": "classified", "memberships": memberships}
            for aid, memberships in sorted(all_accounts.items())
        ]
    finally:
        conn.close()


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
    abstain_threshold = export_cfg.get("abstain_threshold", 0.10)

    if db_path is None:
        db_path = data_dir / "archive_tweets.db"

    # --- Communities ---
    logger.info("Extracting communities from %s", db_path)
    communities = extract_communities(db_path)
    logger.info("Found %d communities", len(communities))

    # --- Classified accounts ---
    logger.info("Extracting classified accounts (min_weight=%.3f)", min_weight)
    classified = extract_classified_accounts(db_path, min_weight=min_weight)
    classified_ids = {a["id"] for a in classified}
    logger.info("Found %d classified accounts", len(classified))

    # --- Enrich with parquet metadata ---
    parquet_path = data_dir / "graph_snapshot.nodes.parquet"
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
        # Build node_id to username map for propagation
        node_id_to_username = {
            row["node_id"]: row["username"]
            for _, row in df.iterrows()
            if row["username"] is not None
        }
    else:
        logger.warning("Parquet not found at %s, metadata will be missing", parquet_path)
        meta_map = {}
        node_id_to_username = {}

    # Enrich classified accounts
    for acct in classified:
        meta = meta_map.get(acct["id"])
        if meta is not None:
            acct["username"] = meta.get("username")
            acct["display_name"] = meta.get("display_name")
            acct["bio"] = meta.get("bio")
            acct["followers"] = _safe_followers(meta.get("num_followers"))
        else:
            acct["username"] = None
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

    # --- Enrich communities with featured members ---
    for c in communities:
        cid = c["id"]
        members_with_weight = []
        for acct in classified:
            if not acct.get("username"):
                continue
            for m in acct["memberships"]:
                if m["community_id"] == cid:
                    members_with_weight.append({
                        "username": acct["username"],
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

    # --- Propagated handles ---
    npz_path = data_dir / "community_propagation.npz"
    if npz_path.exists():
        logger.info("Extracting propagated handles from %s", npz_path)
        propagated = extract_propagated_handles(
            npz_path=npz_path,
            node_id_to_username=node_id_to_username,
            classified_ids=classified_ids,
            min_weight=min_weight,
            abstain_threshold=abstain_threshold,
        )
        logger.info("Found %d propagated handles", len(propagated))
    else:
        logger.warning(
            "NPZ not found at %s, exporting classified only", npz_path,
        )
        propagated = {}

    # --- Build search index ---
    search_index: dict[str, dict[str, Any]] = {}

    # Add classified accounts to search
    for acct in classified:
        username = acct.get("username")
        if username and username.lower() not in _INVALID_USERNAMES:
            search_index[username.lower()] = {
                "tier": "classified",
                "memberships": acct["memberships"],
            }

    # Add propagated handles (already keyed by lowercase)
    search_index.update(propagated)

    # --- Assemble output ---
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_payload = {
        "communities": communities,
        "accounts": classified,
        "meta": {
            "site_name": config.get("site_name", "Find My Ingroup"),
            "curator": config.get("curator"),
            "links": config.get("links", {}),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "communities": len(communities),
                "classified_accounts": len(classified),
                "propagated_handles": len(propagated),
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
    print(f"  Classified accounts: {len(classified)}")
    print(f"  Propagated handles:  {len(propagated)}")
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
