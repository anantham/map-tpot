#!/usr/bin/env python3
"""
Community detection on seed accounts using multi-signal following/retweet/reply graph.

Builds a TF-IDF weighted feature matrix per account, runs hierarchical clustering,
prints a human-readable cluster summary showing what distinguishes each cluster.

Usage:
    python scripts/cluster_communities.py
    python scripts/cluster_communities.py --k 10          # number of clusters
    python scripts/cluster_communities.py --signal follow  # following only
    python scripts/cluster_communities.py --signal all     # following + retweet + reply
    python scripts/cluster_communities.py --min-rt 3       # RT target must appear 3+ times
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from scipy.cluster.hierarchy import linkage, fcluster, dendrogram
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"

# ── helpers ─────────────────────────────────────────────────────────────────

def load_accounts(con) -> list[tuple[str, str]]:
    """Return [(account_id, username)] for all accounts with tweets."""
    rows = con.execute(
        "SELECT DISTINCT account_id, username FROM tweets"
    ).fetchall()
    return [(r[0], r[1]) for r in rows if r[0]]


def build_following_matrix(con, accounts: list, weight: float = 1.0):
    """
    Binary matrix: accounts × following_targets.
    Each cell = 1 if account follows that target.
    """
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}
    n = len(accounts)

    # Load all following edges for seed accounts
    rows = con.execute(
        "SELECT account_id, following_account_id FROM account_following"
    ).fetchall()

    # Build target index
    targets = sorted({r[1] for r in rows})
    target_idx = {t: j for j, t in enumerate(targets)}
    m = len(targets)

    mat = lil_matrix((n, m), dtype=np.float32)
    for aid, tid in rows:
        i = account_idx.get(aid)
        j = target_idx.get(tid)
        if i is not None and j is not None:
            mat[i, j] = weight

    return csr_matrix(mat), targets


def build_retweet_matrix(con, accounts: list, min_count: int = 2, weight: float = 1.0):
    """
    Frequency matrix: accounts × retweeted_username.
    Only includes RT targets that appear min_count+ times for an account.
    """
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}
    n = len(accounts)

    rows = con.execute("""
        SELECT account_id, rt_of_username, COUNT(*) as cnt
        FROM retweets
        GROUP BY account_id, rt_of_username
        HAVING cnt >= ?
    """, (min_count,)).fetchall()

    targets = sorted({r[1] for r in rows if r[1]})
    target_idx = {t: j for j, t in enumerate(targets)}
    m = len(targets)

    mat = lil_matrix((n, m), dtype=np.float32)
    for aid, username, cnt in rows:
        i = account_idx.get(aid)
        j = target_idx.get(username)
        if i is not None and j is not None:
            mat[i, j] = float(cnt) * weight

    return csr_matrix(mat), targets


def build_reply_matrix(con, accounts: list, min_count: int = 3, weight: float = 0.5):
    """
    Frequency matrix: accounts × reply_to_username.
    Lower weight than following/RT — replies include critics.
    """
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}
    n = len(accounts)

    rows = con.execute("""
        SELECT account_id, reply_to_username, COUNT(*) as cnt
        FROM tweets
        WHERE reply_to_username IS NOT NULL
        GROUP BY account_id, reply_to_username
        HAVING cnt >= ?
    """, (min_count,)).fetchall()

    targets = sorted({r[1] for r in rows if r[1]})
    target_idx = {t: j for j, t in enumerate(targets)}
    m = len(targets)

    mat = lil_matrix((n, m), dtype=np.float32)
    for aid, username, cnt in rows:
        i = account_idx.get(aid)
        j = target_idx.get(username)
        if i is not None and j is not None:
            mat[i, j] = float(cnt) * weight

    return csr_matrix(mat), targets


def tfidf_weight(mat: csr_matrix) -> csr_matrix:
    """Apply TF-IDF: downweights targets followed by everyone (prestige follows)."""
    transformer = TfidfTransformer(smooth_idf=True, sublinear_tf=True)
    return transformer.fit_transform(mat)


def top_targets_for_cluster(
    mat_raw: csr_matrix,
    targets: list[str],
    cluster_mask: np.ndarray,
    other_mask: np.ndarray,
    topn: int = 10,
) -> list[str]:
    """
    Find targets that discriminate this cluster from others.
    Score = mean presence in cluster / (mean presence elsewhere + 0.01).
    """
    in_cluster = np.asarray(mat_raw[cluster_mask].mean(axis=0)).flatten()
    outside    = np.asarray(mat_raw[other_mask].mean(axis=0)).flatten()
    score = in_cluster / (outside + 0.01)

    # Also require at least 20% of cluster follows this target
    threshold = 0.15 * cluster_mask.sum()
    score[in_cluster < threshold / mat_raw.shape[0]] = 0

    top_idx = np.argsort(score)[::-1][:topn]
    return [targets[i] for i in top_idx if score[i] > 0]


def load_bios(con, accounts: list) -> dict[str, str]:
    aid_to_user = {aid: user for aid, user in accounts}
    rows = con.execute("SELECT account_id, username, bio FROM profiles").fetchall()
    bios = {}
    for aid, user, bio in rows:
        if aid in aid_to_user and bio:
            bios[aid] = bio
    return bios


# ── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k",        type=int,   default=12,       help="Number of clusters")
    parser.add_argument("--signal",   type=str,   default="all",    help="follow | rt | reply | all")
    parser.add_argument("--min-rt",   type=int,   default=2,        help="Min RT count to include target")
    parser.add_argument("--min-reply",type=int,   default=3,        help="Min reply count to include target")
    parser.add_argument("--topn",     type=int,   default=8,        help="Top discriminating targets to show")
    args = parser.parse_args()

    con = sqlite3.connect(str(ARCHIVE_DB))
    accounts = load_accounts(con)
    print(f"Accounts: {len(accounts)}")

    mats = []

    # ── following signal ──────────────────────────────────────────────────
    if args.signal in ("follow", "all"):
        print("Building following matrix...", end=" ", flush=True)
        mat_f, targets_f = build_following_matrix(con, accounts, weight=1.0)
        mat_f_tfidf = tfidf_weight(mat_f)
        mats.append(normalize(mat_f_tfidf))
        print(f"{mat_f.shape[1]:,} targets, {mat_f.nnz:,} edges")

    # ── retweet signal ────────────────────────────────────────────────────
    if args.signal in ("rt", "all"):
        print("Building retweet matrix...", end=" ", flush=True)
        mat_r, targets_r = build_retweet_matrix(con, accounts, min_count=args.min_rt, weight=0.8)
        mat_r_tfidf = tfidf_weight(mat_r)
        mats.append(normalize(mat_r_tfidf))
        print(f"{mat_r.shape[1]:,} targets, {mat_r.nnz:,} edges")

    # ── reply signal ──────────────────────────────────────────────────────
    if args.signal in ("reply", "all"):
        print("Building reply matrix...", end=" ", flush=True)
        mat_rep, targets_rep = build_reply_matrix(con, accounts, min_count=args.min_reply, weight=0.5)
        mat_rep_tfidf = tfidf_weight(mat_rep)
        mats.append(normalize(mat_rep_tfidf))
        print(f"{mat_rep.shape[1]:,} targets, {mat_rep.nnz:,} edges")

    if not mats:
        print("No signal matrices built. Check --signal flag.")
        sys.exit(1)

    # ── combine signals horizontally ──────────────────────────────────────
    from scipy.sparse import hstack
    combined = hstack(mats).toarray()  # dense for cosine_similarity
    print(f"Combined feature matrix: {combined.shape}")

    # ── hierarchical clustering ───────────────────────────────────────────
    print("Computing pairwise similarities...", end=" ", flush=True)
    sim = cosine_similarity(combined)
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0)
    print("done")

    # Convert to condensed distance matrix for linkage
    from scipy.spatial.distance import squareform
    condensed = squareform(dist, checks=False)
    condensed = np.clip(condensed, 0, None)  # numerical safety

    print("Running hierarchical clustering (Ward linkage)...", end=" ", flush=True)
    Z = linkage(condensed, method="ward")
    labels = fcluster(Z, args.k, criterion="maxclust")
    print("done")

    # ── load bios for context ─────────────────────────────────────────────
    bios = load_bios(con, accounts)
    aid_to_user = {aid: user for aid, user in accounts}

    # ── print cluster summary ─────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"  COMMUNITY CLUSTERS  (k={args.k}, signal={args.signal})")
    print("=" * 70)

    for c in range(1, args.k + 1):
        mask = labels == c
        cluster_accounts = [accounts[i] for i in range(len(accounts)) if mask[i]]
        if not cluster_accounts:
            continue

        print(f"\n── Cluster {c}  ({len(cluster_accounts)} accounts) ───────────────────────")

        # Show accounts with bios
        for aid, user in sorted(cluster_accounts, key=lambda x: x[1].lower()):
            bio = bios.get(aid, "")
            bio_short = (bio[:70] + "…") if len(bio) > 70 else bio
            print(f"  @{user:<25}  {bio_short}")

        # Show discriminating following targets
        if args.signal in ("follow", "all"):
            other_mask = labels != c
            top = top_targets_for_cluster(
                mat_f, targets_f, mask, other_mask, topn=args.topn
            )
            if top:
                print(f"\n  ↗ Distinctive follows: {', '.join('@' + t for t in top[:args.topn])}")

        # Show discriminating RT targets
        if args.signal in ("rt", "all") and mat_r.shape[1] > 0:
            other_mask = labels != c
            top_rt = top_targets_for_cluster(
                mat_r, targets_r, mask, other_mask, topn=args.topn
            )
            if top_rt:
                print(f"  ↻ Distinctive RTs:     {', '.join('@' + t for t in top_rt[:args.topn])}")

    print()
    print("=" * 70)
    print(f"Tip: adjust --k and --signal to explore different granularities")
    print(f"     e.g. --k 8 --signal follow  or  --k 15 --signal all")

    con.close()


if __name__ == "__main__":
    main()
