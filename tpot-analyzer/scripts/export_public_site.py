"""Export community data for the public Find My Ingroup site.

Reads community definitions and memberships from SQLite + NPZ propagation
data, enriches with account metadata from parquet, and writes two JSON files:

  data.json   — communities + classified accounts + meta
  search.json — handle -> {tier, memberships} lookup index

Usage:
    cd tpot-analyzer
    .venv/bin/python3 -m scripts.export_public_site
    .venv/bin/python3 -m scripts.export_public_site --output-dir /tmp/export

This file is the ORCHESTRATOR. Pure helpers live in
`scripts/_export_helpers/`. They're re-exported below so existing
imports (`from scripts.export_public_site import extract_communities`,
etc.) keep working.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# Re-export helpers for backward compatibility (40+ test import sites)
from scripts._export_helpers._community_extractors import (
    _INVALID_USERNAMES,
    _build_username_map,
    _extract_bits_accounts,
    _load_npz_memberships,
    extract_band_accounts,
    extract_classified_accounts,
    extract_communities,
    extract_propagated_handles,
)
from scripts._export_helpers._slug_registry import (
    assign_slugs,
    load_slug_registry,
    save_slug_registry,
    slugify_name,
)
from scripts._export_helpers._tweet_evidence import (
    _safe_followers,
    compute_recommendations,
    detect_tweet_types,
    get_evidence,
    get_sample_tweets,
    select_community_tweets,
)

logger = logging.getLogger(__name__)


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

    # --- Evidence enrichment (interpretable card data) ---
    # Build community_id → short_name map
    _evidence_conn = sqlite3.connect(str(db_path))
    _comm_name_map = {}
    for _r in _evidence_conn.execute("SELECT id, short_name FROM community WHERE short_name IS NOT NULL"):
        _comm_name_map[_r[0]] = _r[1]
    _evidence_conn.close()

    # Load seed_neighbor_counts from NPZ
    _npz_snc_map: dict[str, np.ndarray] = {}
    _npz_comm_names: list[str] = []
    if npz_path.exists():
        _npz_data = np.load(str(npz_path), allow_pickle=False)
        if "seed_neighbor_counts" in _npz_data:
            _snc = _npz_data["seed_neighbor_counts"]
            _nids = _npz_data["node_ids"]
            _npz_comm_names = list(_npz_data["community_names"])
            for i in range(len(_nids)):
                _npz_snc_map[str(_nids[i])] = _snc[i]

    logger.info("Enriching %d accounts with evidence data...", len(all_accounts))
    _evidence_count = 0
    for acct in all_accounts:
        aid = acct["id"]
        snc_row = _npz_snc_map.get(aid)
        ev = get_evidence(
            db_path, aid, _comm_name_map,
            npz_snc_row=snc_row,
            npz_comm_names=_npz_comm_names,
        )
        if ev:
            acct["evidence"] = ev
            _evidence_count += 1
    logger.info("Evidence added for %d accounts", _evidence_count)

    # --- Confidence adjustment using true concentration ---
    # true_concentration = max_seed_neighbors / total_followers
    # Accounts with huge audiences have inflated graph signal — many seed
    # neighbors simply because TPOT people follow famous accounts.
    # Scale CI by concentration to reflect how TPOT-specific the signal is.
    # This doesn't change bands or exclude anyone — it lets the confidence
    # speak honestly. A 237M-follower account with 30 seed neighbors has
    # real but extremely dilute signal. Their card will be dim, which is true.
    #
    # Data: user_profile_cache from batch API fetch (scripts/fetch_user_profiles.py)
    CONCENTRATION_REFERENCE = 0.005  # typical TPOT account concentration
    FOLLOWER_FLOOR_FOR_SCALING = 10_000  # only scale accounts with 10K+ followers

    conn_filt = sqlite3.connect(str(db_path))
    profile_followers: dict[str, int] = {}
    try:
        for aid, foll in conn_filt.execute(
            "SELECT account_id, followers FROM user_profile_cache WHERE followers > 0"
        ).fetchall():
            profile_followers[aid] = foll
    except sqlite3.OperationalError:
        pass
    conn_filt.close()

    npz_snc: dict[str, int] = {}
    if npz_path.exists():
        _npz_data = np.load(str(npz_path), allow_pickle=False)
        if "seed_neighbor_counts" in _npz_data:
            _snc = _npz_data["seed_neighbor_counts"]
            _nids = _npz_data["node_ids"]
            for i in range(len(_nids)):
                npz_snc[str(_nids[i])] = int(_snc[i].max())

    ci_adjusted = 0
    for acct in all_accounts:
        if acct["tier"] == "exemplar":
            continue  # human-labeled accounts keep their CI

        aid = acct["id"]
        followers = profile_followers.get(aid) or acct.get("followers") or 0
        # Enrich follower count from profile cache
        if profile_followers.get(aid) and (not acct.get("followers") or acct["followers"] == 0):
            acct["followers"] = profile_followers[aid]

        if followers < FOLLOWER_FLOOR_FOR_SCALING:
            continue  # small accounts don't need scaling

        max_snc = npz_snc.get(aid, 0)
        if max_snc == 0:
            continue

        true_conc = max_snc / followers
        # Scale factor: how TPOT-specific is their audience?
        # concentration_ratio = true_conc / reference
        # Capped at 1.0 (accounts more concentrated than reference keep full CI)
        scale = min(1.0, true_conc / CONCENTRATION_REFERENCE)
        old_ci = acct.get("confidence", 0)
        acct["confidence"] = round(old_ci * scale, 4)
        if scale < 0.99:
            ci_adjusted += 1

    if ci_adjusted > 0:
        logger.info(
            "Concentration CI scaling: adjusted %d accounts "
            "(followers >= %d, reference concentration %.4f)",
            ci_adjusted, FOLLOWER_FLOOR_FOR_SCALING, CONCENTRATION_REFERENCE,
        )

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
        # Compute evidence summary for transparency
        total_seed_neighbors = sum(
            m.get("seed_neighbors", 0)
            for m in acct.get("memberships", [])
            if isinstance(m, dict)
        )
        entry = {
            "tier": acct["tier"],
            "memberships": acct["memberships"],
            "confidence": acct.get("confidence", 0),
            "bio": acct.get("bio"),
            "display_name": acct.get("display_name"),
            "followers": acct.get("followers"),
            "seed_neighbors": total_seed_neighbors,
            "sample_tweets": acct.get("sample_tweets", []),
        }
        if acct.get("evidence"):
            entry["evidence"] = acct["evidence"]
        search_index[handle.lower()] = entry

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
