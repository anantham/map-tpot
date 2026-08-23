"""Community + account extraction queries for the public site export.

Pure-ish: each function takes file paths and returns plain dicts/lists.
No shared module-level state except the _INVALID_USERNAMES set used by
the username resolver and the propagated-handle gate.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from src.propagation.bands import (
    propagation_artifact_mode,
    reject_unbound_account_band_table,
    require_supported_band_artifact,
)

logger = logging.getLogger(__name__)

_INVALID_USERNAMES = {"nan", "none", ""}


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


def _extract_bits_accounts(
    conn: sqlite3.Connection,
    min_weight: float = 0.05,
) -> dict[str, list[dict]]:
    """Extract accounts with human-validated bits data (posterior).

    Returns dict: {account_id: [{community_id, weight}]}.
    Converts pct (0-100) to weight (0-1) for compatibility with NMF format.
    """
    # Build short_name → UUID lookup (account_community_bits may store short_names)
    short_to_uuid = {}
    for row in conn.execute("SELECT id, short_name FROM community WHERE short_name IS NOT NULL").fetchall():
        short_to_uuid[row["short_name"]] = row["id"]

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
        # Resolve short_name to UUID if needed
        cid = r["community_id"]
        cid = short_to_uuid.get(cid, cid)
        if aid not in accounts:
            accounts[aid] = []
        accounts[aid].append({
            "community_id": cid,
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

    mode = propagation_artifact_mode(data)
    has_snc = "seed_neighbor_counts" in data
    snc = data["seed_neighbor_counts"] if has_snc else None

    # Optional bootstrap stats
    has_stability = "stability" in data
    stability_arr = data["stability"] if has_stability else None
    has_ci = "confidence_intervals" in data
    ci_arr = data["confidence_intervals"] if has_ci else None

    is_independent = mode == "independent"

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

            m_entry = {
                "community_id": str(community_ids[j]),
                "weight": round(w, 4),
            }

            # Add bootstrap stats if available
            if has_stability and stability_arr is not None:
                m_entry["stability"] = round(float(stability_arr[i, j]), 3)
            if has_ci and ci_arr is not None:
                # Store as [low, high]
                m_entry["ci"] = [round(float(ci_arr[i, j, 0]), 4), round(float(ci_arr[i, j, 1]), 4)]

            # In independent mode, filter by seed neighbors (noise gate)
            if is_independent and snc is not None:
                neighbors = int(snc[i, j])
                if neighbors < 1:
                    continue  # no classified neighbors = noise
                m_entry["seed_neighbors"] = neighbors

            entry_memberships.append(m_entry)

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
    """Reject unbound legacy bands; retain the old extractor behind the gate.

    The historical implementation reads account_band and builds:
    - exemplar: memberships from community_account (bits > NMF)
    - specialist/bridge/frontier: memberships from propagation NPZ

    No existing table records the exact NPZ digest, taxonomy, thresholds, or
    method version that produced each row, so any present table is currently
    quarantined. If the table is absent, classified-only rows remain available.
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

        reject_unbound_account_band_table("public band export")
        if not npz_path.exists():
            raise RuntimeError(
                f"account_band propagation artifact is missing: {npz_path}"
            )
        with np.load(str(npz_path), allow_pickle=False) as propagation:
            require_supported_band_artifact(propagation)

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
        # Compute CI from seed-neighbor count (veil CV: AUC 0.999).
        # Raw propagation scores are worse than random (AUC 0.225).
        # seed_neighbors = how many classified accounts follow you in your
        # top community. 20+ = high confidence, 5-20 = moderate, 1-5 = emerging.
        top_membership = memberships[0] if memberships else {}
        top_neighbors = top_membership.get("seed_neighbors", 0) if isinstance(top_membership, dict) else 0
        if top_neighbors > 0:
            ci = round(min(1.0, top_neighbors / 20.0), 3)
        else:
            # Fallback for classic mode or missing neighbor data
            meta = band_meta.get(aid, {})
            tw = meta.get("top_weight", 0)
            ent = meta.get("entropy", 0)
            nw = meta.get("none_weight", 0)
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
