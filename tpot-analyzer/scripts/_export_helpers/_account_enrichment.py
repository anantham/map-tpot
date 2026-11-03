"""Local evidence and legacy confidence enrichment for export candidates."""

from src.artifacts.safe_io import load_npz_arrays
import logging
import sqlite3

import numpy as np

from scripts._export_helpers._tweet_evidence import get_evidence

logger = logging.getLogger(__name__)


def enrich_account_evidence(db_path, npz_path, all_accounts):
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
        _npz_data = load_npz_arrays(str(npz_path))
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
        _npz_data = load_npz_arrays(str(npz_path))
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
