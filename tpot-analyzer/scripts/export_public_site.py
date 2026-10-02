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

from src.propagation.bands import UnboundAccountBandError
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

from scripts._export_helpers._account_enrichment import enrich_account_evidence
from scripts._export_helpers._publication import write_public_candidate

logger = logging.getLogger(__name__)


def run_export(
    data_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
    db_path: Path | None = None,
) -> None:
    """Main export entrypoint: reads data, assembles JSON, writes files.

    Exports classified rows directly. A legacy account_band table is used only
    after exact artifact binding exists; until then it is quarantined and this
    entrypoint falls back to classified-only rows.

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
    try:
        all_accounts = extract_band_accounts(
            db_path=db_path,
            npz_path=npz_path,
            parquet_path=parquet_path,
            min_weight=min_weight,
        )
    except UnboundAccountBandError as exc:
        logger.warning(
            "%s; suppressing unbound bands and exporting classified-only rows",
            exc,
        )
        all_accounts = extract_classified_accounts(db_path, min_weight)
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

    enrich_account_evidence(db_path, npz_path, all_accounts)

    # --- Slug assignment ---
    slug_registry_path = Path(output_dir) / "slug_registry.json"
    slug_registry = load_slug_registry(slug_registry_path)
    slug_registry = assign_slugs(communities, slug_registry)
    for c in communities:
        c["slug"] = slug_registry[c["id"]]

    # --- Enrich communities with direct seed/classified members only ---
    # ``classified`` is the safe fallback tier when unbound band rows are
    # suppressed. Propagated specialist/bridge/frontier rows stay excluded.
    seed_accounts = [
        account
        for account in all_accounts
        if account["tier"] in {"exemplar", "classified"}
    ]
    for c in communities:
        cid = c["id"]
        members_with_weight = []
        for acct in seed_accounts:
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

    manifest = write_public_candidate(output_dir, data_payload, search_index)
    data_path = output_dir / "data.json"
    search_path = output_dir / "search.json"
    logger.info("Local candidate requires exact-digest publication approval: %s", manifest["export_digest"])

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
    output_dir = project_root / export_cfg.get("output_dir", "data/publication_candidates")

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
