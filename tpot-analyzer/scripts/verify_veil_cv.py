#!/usr/bin/env python3
"""Veil-of-ignorance cross-validation of the production propagation.

Hides known TPOT accounts from the seeds, runs the production algorithm
(src.propagation.propagate, Directed PPR + Lift, independent mode, on the
TypedGraph adjacency), and asks whether the hidden accounts outscore random
non-TPOT accounts. The score is an account's best lift across communities.

Two tests:
  1. Archive + directory accounts, split into folds; each is hidden exactly once.
  2. Directory-only accounts, which are never seeds, scored with every seed.

Positives and negatives both need weighted degree >= min_degree, the
threshold below which production assigns nothing. Against the full-list pool,
positives also need MIN_FULL_LIST recorded follows (all hidden archive accounts
have them; about a third of directory-only accounts do). Two negative pools of
non-TPOT accounts:
  - any such account;
  - such accounts with at least MIN_FULL_LIST recorded follows. Every hidden
    archive account has a full follow list (median ~1,000), so this pool asks
    the harder question. Most accounts with follow rows have exactly one, usually a
    seed: a seed's follower list records each follower as following that seed,
    and nothing else about them. Those single-follow accounts are not "known" lists.

Each hidden account is compared only with negatives scored in the run it was
hidden from; in the other folds' runs it was a seed. --compare-reversed also
runs the walk in the opposite direction on the same folds and negatives and
reports the paired AUC gap with a bootstrap interval.

Also reports how often production's abstain rule places each group.

History: until 4 Nov 2026 this script scored the retired harmonic solve, which
is where the About page's AUC of 0.178 came from.

Usage:
    .venv/bin/python3 -m scripts.verify_veil_cv
    .venv/bin/python3 -m scripts.verify_veil_cv --compare-reversed
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DEFAULT_ARCHIVE_DB
from src.propagation import PropagationConfig, propagate
from src.propagation.engine import compute_ppr
from src.propagation.io import build_adjacency_from_archive
from src.propagation.veil import bootstrap_auc, stratified_folds

N_NEGATIVES = 500
MIN_FULL_LIST = 20


def load_categories(db_path: Path) -> tuple[dict[str, str], set[str], set[str], dict[str, int]]:
    """Return (dominant community per archive account, directory ids, archive ids,
    recorded follow count per account)."""
    with sqlite3.connect(str(db_path)) as db:
        rows = db.execute("SELECT account_id, community_id, weight FROM community_account").fetchall()
        directory = {r[0] for r in db.execute(
            "SELECT account_id FROM tpot_directory_holdout WHERE account_id IS NOT NULL")}
        follow_counts = dict(db.execute(
            "SELECT account_id, COUNT(*) FROM account_following GROUP BY account_id"))
    best: dict[str, tuple[float, str]] = {}
    for aid, cid, w in rows:
        if aid not in best or w > best[aid][0]:
            best[aid] = (w, cid)
    return {a: c for a, (_, c) in best.items()}, directory, set(best), follow_counts


def run(adj, node_ids, config, exclude, verbose) -> tuple[np.ndarray, np.ndarray, bool]:
    """Best lift per node, and whether production places it, from one propagation run."""
    sink = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
    with sink:
        result, _ = propagate(adj, node_ids, config, exclude_accounts=exclude)
    K = len(result.community_ids)
    placed = ~result.abstain_mask & ~result.labeled_mask
    return result.memberships[:, :K].max(axis=1), placed, all(result.converged)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n-folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--alpha", type=float, default=0.15)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--compare-reversed", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="show propagation logs")
    ap.add_argument("--output", type=Path, default=ROOT / "data" / "veil_cv_results.json")
    args = ap.parse_args()

    t0 = time.time()
    dominant, directory, archive, follow_counts = load_categories(DEFAULT_ARCHIVE_DB)
    with contextlib.redirect_stdout(io.StringIO()):
        adj, ids = build_adjacency_from_archive(DEFAULT_ARCHIVE_DB, weighted=True)
    node_ids = np.array(ids)
    idx = {n: i for i, n in enumerate(ids)}
    config = PropagationConfig(mode="independent", alpha=args.alpha)

    degree = np.asarray(adj.sum(axis=1)).ravel() + np.asarray(adj.sum(axis=0)).ravel()
    scorable = {n for n in ids if degree[idx[n]] >= config.min_degree_for_assignment}
    tpot = archive | directory
    eligible = sorted(scorable - tpot)
    eligible_full = [n for n in eligible if follow_counts.get(n, 0) >= MIN_FULL_LIST]
    rng = np.random.RandomState(args.seed)
    neg_pools = {
        "any": sorted(rng.choice(eligible, min(N_NEGATIVES, len(eligible)), replace=False)),
        "full_follow_list": sorted(rng.choice(eligible_full, min(N_NEGATIVES, len(eligible_full)),
                                              replace=False)),
    }

    hideable = {a: dominant[a] for a in archive & directory & scorable}
    folds = stratified_folds(hideable, args.n_folds, args.seed)
    dir_only = sorted((directory - archive) & scorable)
    dropped = {"hidden_archive": len({a for a in archive & directory if a in idx} - scorable),
               "directory_only": len({a for a in directory - archive if a in idx} - scorable)}
    directions = {"production": adj}
    if args.compare_reversed:
        directions["reversed"] = adj.T.tocsr()
    names = list(directions)
    print(f"Graph {len(ids):,} nodes · hidden {len(hideable)} in {args.n_folds} folds · "
          f"directory-only {len(dir_only)} · below min degree, not scored: {dropped} · "
          f"negatives {len(eligible):,} eligible, {len(eligible_full):,} with >= {MIN_FULL_LIST} follows · "
          f"setup {time.time() - t0:.0f}s")

    # Global PageRank (the lift denominator) doesn't depend on seeds: check it once per direction.
    global_converged = all(compute_ppr(directions[d], None, alpha=args.alpha)[2] for d in names)

    pos_rows: list[list[float]] = []
    pos_fold: list[int] = []
    pos_ids: list[str] = []
    pos_placed: list[bool] = []
    neg_placed = {p: 0 for p in neg_pools}
    neg_by_pool = {p: np.zeros((len(v), args.n_folds, len(names))) for p, v in neg_pools.items()}
    converged = True
    for f, hidden in enumerate(folds):
        fold_scores = {}
        for d in names:
            fold_scores[d], placed, ok = run(directions[d], node_ids, config, hidden, args.verbose)
            if d == "production":
                pos_placed.extend(placed[idx[a]] for a in sorted(hidden))
                for p, accounts in neg_pools.items():
                    neg_placed[p] += sum(placed[idx[a]] for a in accounts)
            converged &= ok
        for a in sorted(hidden):
            pos_rows.append([fold_scores[d][idx[a]] for d in names])
            pos_fold.append(f)
            pos_ids.append(a)
        for p, accounts in neg_pools.items():
            for j, a in enumerate(accounts):
                neg_by_pool[p][j, f] = [fold_scores[d][idx[a]] for d in names]
        print(f"  fold {f + 1}/{args.n_folds}: hid {len(hidden)} · {time.time() - t0:.0f}s")

    full = {}
    for d in names:
        full[d], placed, ok = run(directions[d], node_ids, config, None, args.verbose)
        if d == "production":
            dir_placed = float(np.mean([placed[idx[a]] for a in dir_only]))
        converged &= ok
    dir_pos = np.array([[full[d][idx[a]] for d in names] for a in dir_only])
    dir_neg = {p: np.array([[[full[d][idx[a]] for d in names]] for a in v]) for p, v in neg_pools.items()}

    def score(ids_, rows, folds, neg, pool):
        # The full-list pool compares like with like: positives need full lists too.
        keep = np.array([pool != "full_follow_list" or follow_counts.get(a, 0) >= MIN_FULL_LIST
                         for a in ids_])
        return bootstrap_auc(rows[keep], folds[keep], neg, n_boot=args.n_boot, seed=args.seed)

    pos = np.array(pos_rows)
    results = {
        "hidden_archive": {p: score(pos_ids, pos, np.array(pos_fold), neg_by_pool[p], p) for p in neg_pools},
        "directory_only": {p: score(dir_only, dir_pos, np.zeros(len(dir_pos), int), dir_neg[p], p)
                           for p in neg_pools},
    }
    for test, positives in (("hidden_archive", pos), ("directory_only", dir_pos)):
        results[test]["share_scored_zero"] = [float(np.mean(positives[:, m] == 0)) for m in range(len(names))]
        results[test]["below_min_degree_not_scored"] = dropped[test]

    results["placed_rate_production"] = {
        "hidden_archive": float(np.mean(pos_placed)), "directory_only": dir_placed,
        **{f"negatives_{p}": neg_placed[p] / (len(v) * args.n_folds) for p, v in neg_pools.items()},
    }
    print(f"\nPlaced by production (lift >= 1 and >= {config.min_seed_neighbors} seed neighbours "
          "in one community): " + ", ".join(f"{k} {v:.0%}" for k, v in results["placed_rate_production"].items()))
    print("\nAUC with 95% bootstrap interval (accounts resampled; 0.5 = chance)")
    for test, by_pool in ((t, results[t]) for t in ("hidden_archive", "directory_only")):
        for p in neg_pools:
            r = by_pool[p]
            cells = "  ".join(f"{d} {r['auc'][m]:.3f} [{r['ci'][m][0]:.3f}, {r['ci'][m][1]:.3f}]"
                              for m, d in enumerate(names))
            print(f"  {test:15s} vs {p:17s} (n={r['n_pos']}/{r['n_neg']}): {cells}")
            if len(names) == 2:
                g, (lo, hi) = r["gap_vs_first"][1], r["gap_ci"][1]
                verdict = "interval includes 0" if lo <= 0 <= hi else "interval excludes 0"
                print(f"  {'':15s}    reversed − production: {g:+.3f} [{lo:+.3f}, {hi:+.3f}] ({verdict})")

    hard = results["hidden_archive"]["full_follow_list"]
    checks = [
        ("every PageRank run converged, including global PageRank", converged and global_converged),
        ("at least 50 hidden accounts scored", hard["n_pos"] >= 50),
        ("production beats chance on the harder negatives (interval above 0.5)", hard["ci"][0][0] > 0.5),
    ]
    print()
    for label, ok in checks:
        print(f"  {'✓' if ok else '✗'} {label}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "algorithm": "directed PPR + lift, independent mode, TypedGraph adjacency",
        "config": {"n_folds": args.n_folds, "seed": args.seed, "alpha": args.alpha,
                   "n_boot": args.n_boot, "directions": names, "n_negatives": N_NEGATIVES},
        "results": results,
    }, indent=2))
    print(f"\nSaved {args.output} · {time.time() - t0:.0f}s")
    print("Next: read the two pools together. A high AUC against 'any' with a low one against "
          "'full_follow_list' means the score mostly tracks how much graph data an account has.")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
