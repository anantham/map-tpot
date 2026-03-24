"""Verify propagation recall against TPOT directory holdout accounts.

Checks how many of the 389 holdout accounts were discovered by propagation,
which communities they were assigned to, and at what confidence.

Usage:
    .venv/bin/python3 -m scripts.verify_holdout_recall
"""
import sqlite3
import sys
import numpy as np
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

DB_PATH = DEFAULT_ARCHIVE_DB
NPZ_PATH = Path(__file__).parent.parent / "data" / "community_propagation.npz"


def main():
    db = sqlite3.connect(str(DB_PATH))

    # Load holdout accounts
    holdout = db.execute("""
        SELECT handle, source, match_type, account_id
        FROM tpot_directory_holdout
    """).fetchall()
    print(f"Holdout accounts: {len(holdout)}")

    # Load propagation results
    if not NPZ_PATH.exists():
        print(f"✗ {NPZ_PATH} not found — run propagate_community_labels.py --save first")
        sys.exit(1)

    data = np.load(str(NPZ_PATH), allow_pickle=True)
    memberships = data["memberships"]  # (n_nodes, K+1)
    account_ids = data["node_ids"] if "node_ids" in data else (data["account_ids"] if "account_ids" in data else None)
    abstain_mask = data["abstain_mask"] if "abstain_mask" in data else None
    uncertainty = data["uncertainty"] if "uncertainty" in data else None

    if account_ids is not None:
        aid_to_idx = {str(aid): i for i, aid in enumerate(account_ids)}
    else:
        print("✗ No account_ids in NPZ — cannot match holdout accounts")
        sys.exit(1)

    # Load community names
    communities = db.execute("SELECT id, name, short_name FROM community ORDER BY name").fetchall()
    comm_names = {i: name for i, (_, name, _) in enumerate(communities)}

    # Check each holdout account
    found_seed = 0
    found_propagated = 0
    found_abstained = 0
    not_in_graph = 0
    results = []

    for handle, source, match_type, account_id in holdout:
        if not account_id:
            # Try to resolve via profiles or resolved_accounts
            row = db.execute(
                "SELECT account_id FROM profiles WHERE LOWER(username) = LOWER(?)", (handle,)
            ).fetchone()
            if not row:
                row = db.execute(
                    "SELECT account_id FROM resolved_accounts WHERE LOWER(username) = LOWER(?)", (handle,)
                ).fetchone()
            if row:
                account_id = row[0]

        if not account_id:
            not_in_graph += 1
            continue

        idx = aid_to_idx.get(str(account_id))
        if idx is None:
            not_in_graph += 1
            continue

        if match_type == "seed":
            found_seed += 1
            continue

        # Check propagation result
        membership = memberships[idx]
        max_community = int(np.argmax(membership[:-1]))  # exclude "none" column
        max_weight = float(membership[max_community])
        is_abstained = bool(abstain_mask[idx]) if abstain_mask is not None else False
        unc = float(uncertainty[idx]) if uncertainty is not None else 0

        if is_abstained:
            found_abstained += 1
            status = "ABSTAINED"
        elif max_weight > 0.05:
            found_propagated += 1
            status = "FOUND"
        else:
            found_abstained += 1
            status = "BELOW_THRESHOLD"

        comm_name = comm_names.get(max_community, f"factor_{max_community}")
        results.append((handle, source, status, comm_name, max_weight, unc))

    # Summary
    print(f"\n{'='*72}")
    print(f"  HOLDOUT RECALL")
    print(f"{'='*72}")
    print(f"  Total holdout:     {len(holdout)}")
    print(f"  Seeds (skip):      {found_seed}")
    print(f"  Not in graph:      {not_in_graph}")
    print(f"  FOUND:             {found_propagated}")
    print(f"  Abstained:         {found_abstained}")
    if found_propagated + found_abstained > 0:
        recall = found_propagated / (found_propagated + found_abstained)
        print(f"  Recall:            {recall:.1%} ({found_propagated}/{found_propagated + found_abstained})")

    # Show discovered accounts
    found_results = [r for r in results if r[2] == "FOUND"]
    found_results.sort(key=lambda x: -x[4])
    if found_results:
        print(f"\n  DISCOVERED ({len(found_results)}):")
        for handle, source, status, comm, weight, unc in found_results[:30]:
            print(f"    @{handle:<24} → {comm:<35} weight={weight:.2f} unc={unc:.2f}")
        if len(found_results) > 30:
            print(f"    ... and {len(found_results) - 30} more")

    # Show abstained
    abstained_results = [r for r in results if r[2] in ("ABSTAINED", "BELOW_THRESHOLD")]
    if abstained_results:
        print(f"\n  ABSTAINED/MISSED ({len(abstained_results)}):")
        for handle, source, status, comm, weight, unc in abstained_results[:15]:
            print(f"    @{handle:<24} best={comm:<30} weight={weight:.2f} unc={unc:.2f}")

    db.close()


if __name__ == "__main__":
    main()
