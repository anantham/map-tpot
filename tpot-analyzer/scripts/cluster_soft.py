#!/usr/bin/env python3
"""
Soft community detection via NMF (Non-negative Matrix Factorization).

Unlike hard clustering, NMF gives each account a fractional membership weight
per community — so @thezvi can be EA=0.7 + consciousness=0.4 simultaneously.

The H matrix tells you what DEFINES each community (top following targets).
The W matrix tells you how much each account belongs to each community.

Usage:
    python scripts/cluster_soft.py
    python scripts/cluster_soft.py --k 12
    python scripts/cluster_soft.py --k 16 --topn 10
    python scripts/cluster_soft.py --show-accounts 20   # show top-N accounts per community
    python scripts/cluster_soft.py --k 14 --save                   # persist to DB
    python scripts/cluster_soft.py --k 14 --save --notes "main-v1" # with human label
"""

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.sparse import hstack
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"
CACHE_DB   = ROOT / "data" / "cache.db"


# ── data loading ────────────────────────────────────────────────────────────

def load_accounts(con):
    rows = con.execute("SELECT DISTINCT account_id, username FROM tweets").fetchall()
    return [(r[0], r[1]) for r in rows if r[0]]


def resolve_account_ids(target_ids: list) -> dict:
    """
    Map accountId → username (or None if suspended/unknown).

    Resolution order:
      1. resolved_accounts table in archive_tweets.db (pre-built by resolve_follow_targets.py)
      2. profiles table in archive_tweets.db (seed accounts)
      3. account table in cache.db (seed list)

    Returns None for IDs that are unresolvable (empirically: suspended accounts).
    """
    if not target_ids:
        return {}

    id_to_user: dict[str, str | None] = {}

    # Primary: resolved_accounts table (covers all local sources + marks unknowns)
    try:
        arc = sqlite3.connect(str(ARCHIVE_DB))
        placeholders = ",".join("?" * len(target_ids))
        for aid, username, status in arc.execute(
            f"SELECT account_id, username, status FROM resolved_accounts"
            f" WHERE account_id IN ({placeholders})",
            target_ids,
        ).fetchall():
            id_to_user[aid] = username if status == "active" else None
        arc.close()
    except Exception:
        pass

    # Fallback: profiles table (in case resolved_accounts hasn't been built yet)
    missing = [tid for tid in target_ids if tid not in id_to_user]
    if missing:
        try:
            arc = sqlite3.connect(str(ARCHIVE_DB))
            placeholders = ",".join("?" * len(missing))
            for aid, username in arc.execute(
                f"SELECT account_id, username FROM profiles"
                f" WHERE account_id IN ({placeholders})",
                missing,
            ).fetchall():
                id_to_user[aid] = username
            arc.close()
        except Exception:
            pass

    # Fallback: cache.db account table
    still_missing = [tid for tid in target_ids if tid not in id_to_user]
    if still_missing:
        try:
            cache = sqlite3.connect(str(CACHE_DB))
            placeholders = ",".join("?" * len(still_missing))
            for aid, username in cache.execute(
                f"SELECT account_id, username FROM account"
                f" WHERE account_id IN ({placeholders})",
                still_missing,
            ).fetchall():
                id_to_user[aid] = username
            cache.close()
        except Exception:
            pass

    return id_to_user


def build_following_matrix(con, accounts):
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}
    rows = con.execute("SELECT account_id, following_account_id FROM account_following").fetchall()
    targets = sorted({r[1] for r in rows})
    target_idx = {t: j for j, t in enumerate(targets)}
    n, m = len(accounts), len(targets)

    from scipy.sparse import lil_matrix, csr_matrix
    mat = lil_matrix((n, m), dtype=np.float32)
    for aid, tid in rows:
        i = account_idx.get(aid)
        j = target_idx.get(tid)
        if i is not None and j is not None:
            mat[i, j] = 1.0
    return csr_matrix(mat), targets


def build_retweet_matrix(con, accounts, min_count=2):
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}
    rows = con.execute("""
        SELECT account_id, rt_of_username, COUNT(*) as cnt
        FROM retweets GROUP BY account_id, rt_of_username HAVING cnt >= ?
    """, (min_count,)).fetchall()
    targets = sorted({r[1] for r in rows if r[1]})
    target_idx = {t: j for j, t in enumerate(targets)}
    n, m = len(accounts), len(targets)

    from scipy.sparse import lil_matrix, csr_matrix
    mat = lil_matrix((n, m), dtype=np.float32)
    for aid, uname, cnt in rows:
        i = account_idx.get(aid)
        j = target_idx.get(uname)
        if i is not None and j is not None:
            mat[i, j] = float(cnt)
    return csr_matrix(mat), targets


def tfidf(mat):
    return TfidfTransformer(smooth_idf=True, sublinear_tf=True).fit_transform(mat)


def load_bios(con, accounts):
    rows = con.execute("SELECT account_id, bio FROM profiles").fetchall()
    return {r[0]: r[1] for r in rows if r[1]}


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k",             type=int,   default=14,   help="Number of communities")
    parser.add_argument("--topn",          type=int,   default=8,    help="Top defining targets per community")
    parser.add_argument("--show-accounts", type=int,   default=15,   help="Top accounts to show per community")
    parser.add_argument("--threshold",     type=float, default=0.1,  help="Min membership weight to count as member")
    parser.add_argument("--multi-only",    action="store_true",      help="Only show accounts in 2+ communities")
    parser.add_argument("--save",          action="store_true",      help="Persist NMF results to archive_tweets.db")
    parser.add_argument("--notes",         type=str,   default=None, help="Human label for this run (e.g. 'main-v1')")
    args = parser.parse_args()

    con = sqlite3.connect(str(ARCHIVE_DB))
    accounts = load_accounts(con)
    bios = load_bios(con, accounts)
    print(f"Accounts: {len(accounts)}")

    print("Building following matrix...", end=" ", flush=True)
    mat_f, targets_f = build_following_matrix(con, accounts)
    mat_f_tfidf = tfidf(mat_f)
    print(f"{mat_f.shape[1]:,} targets")

    print("Building retweet matrix...", end=" ", flush=True)
    mat_r, targets_r = build_retweet_matrix(con, accounts)
    mat_r_tfidf = tfidf(mat_r)
    print(f"{mat_r.shape[1]:,} targets")

    # Combine: following (weight 1.0) + retweet (weight 0.6)
    combined = hstack([
        normalize(mat_f_tfidf),
        normalize(mat_r_tfidf) * 0.6,
    ])

    print(f"Running NMF (k={args.k})...", end=" ", flush=True)
    nmf = NMF(n_components=args.k, random_state=42, max_iter=500, init="nndsvda")
    W = nmf.fit_transform(combined)   # accounts × communities
    H = nmf.components_                # communities × features
    print("done")

    # Normalise W so each account's weights sum to 1 → interpretable as fractions
    W_norm = W / (W.sum(axis=1, keepdims=True) + 1e-10)

    # Split H back into following vs RT feature spaces
    nf = mat_f_tfidf.shape[1]
    H_follow = H[:, :nf]
    H_rt     = H[:, nf:]

    # Pre-resolve target IDs → usernames for following targets
    follow_ids_needed = [targets_f[i] for c in range(args.k)
                         for i in np.argsort(H_follow[c])[::-1][:args.topn]]
    id_map = resolve_account_ids(list(set(follow_ids_needed)))

    aid_to_user = {aid: user for aid, user in accounts}

    print()
    print("=" * 72)
    print(f"  SOFT COMMUNITY MEMBERSHIPS  (k={args.k})")
    print("=" * 72)

    for c in range(args.k):
        # Accounts in this community (above threshold), sorted by weight
        weights = W_norm[:, c]
        members = [(accounts[i], weights[i]) for i in range(len(accounts))
                   if weights[i] >= args.threshold]
        members.sort(key=lambda x: -x[1])

        if not members:
            continue

        # Top defining following targets — show active accounts only; skip suspended
        top_f_idx = np.argsort(H_follow[c])[::-1][:args.topn * 2]  # oversample to fill after filtering
        top_follows = []
        suspended_count = 0
        for idx in top_f_idx:
            if len(top_follows) >= args.topn:
                break
            raw = targets_f[idx]
            username = id_map.get(raw, raw)  # raw if not in map at all
            if username is None:
                # Resolved but suspended — count and skip for display clarity
                suspended_count += 1
                continue
            if username == raw and username.isdigit():
                # Not in id_map at all — treat as unknown
                suspended_count += 1
                continue
            top_follows.append(f"@{username}")

        # Top RT targets for this community
        top_r_idx = np.argsort(H_rt[c])[::-1][:6]
        top_rts = [f"@{targets_r[i]}" for i in top_r_idx if H_rt[c, i] > 0]

        susp_note = f"  (+{suspended_count} suspended)" if suspended_count else ""
        print(f"\n── Community {c+1}  ({len(members)} members above {args.threshold:.0%}) ─────────────────")
        if top_follows:
            print(f"   Follows: {', '.join(top_follows)}{susp_note}")
        elif suspended_count:
            print(f"   Follows: (all top targets suspended{susp_note})")
        if top_rts:
            print(f"   RTs:     {', '.join(top_rts[:6])}")
        print()

        for (aid, user), w in members[:args.show_accounts]:
            bio = (bios.get(aid) or "")[:55]
            bar = "█" * int(w * 20)
            print(f"  {w:.2f} {bar:<4}  @{user:<24} {bio}")

        if len(members) > args.show_accounts:
            print(f"  ... and {len(members) - args.show_accounts} more")

    # ── Multi-community accounts ───────────────────────────────────────────
    print()
    print("=" * 72)
    print("  MULTI-COMMUNITY ACCOUNTS (top communities per account)")
    print("=" * 72)

    rows_out = []
    for i, (aid, user) in enumerate(accounts):
        top = sorted(enumerate(W_norm[i]), key=lambda x: -x[1])
        top = [(c, w) for c, w in top if w >= args.threshold]
        if len(top) >= 2:
            rows_out.append((user, top, bios.get(aid, "")[:50]))

    rows_out.sort(key=lambda x: -len(x[1]))

    for user, top, bio in rows_out[:40]:
        parts = "  ".join(f"C{c+1}={w:.2f}" for c, w in top[:4])
        print(f"  @{user:<26} {parts}   {bio}")

    print()
    print(f"Accounts in 2+ communities: {len(rows_out)} / {len(accounts)}")
    print("=" * 72)
    print(f"Tip: --k {args.k-2} to merge similar communities, --k {args.k+4} to split broad ones")

    # ── Optional persistence ───────────────────────────────────────────────
    if args.save:
        _save_run(con, args, accounts, W_norm, H, targets_f, targets_r, nf)

    con.close()


def _save_run(con, args, accounts, W_norm, H, targets_f, targets_r, nf):
    """Persist NMF results to archive_tweets.db (Layer 1)."""
    from communities.store import init_db, save_run, save_memberships, save_definitions

    # Stable run_id: hash of k + account_ids so same inputs → same id
    aid_str = "".join(aid for aid, _ in sorted(accounts))
    h = hashlib.sha1(f"{args.k}{aid_str}".encode()).hexdigest()[:6]
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    run_id = f"nmf-k{args.k}-{date}-{h}"

    print(f"\nSaving run {run_id} to DB...", end=" ", flush=True)

    arc = sqlite3.connect(str(ARCHIVE_DB))
    arc.execute("PRAGMA journal_mode=WAL")
    init_db(arc)

    save_run(
        arc, run_id,
        k=args.k,
        signal="follow+rt",
        threshold=args.threshold,
        account_count=len(accounts),
        notes=args.notes,
    )

    # W matrix: store all weights ≥ 0.05 (wider than display threshold)
    membership_rows = []
    for i, (aid, _) in enumerate(accounts):
        for c in range(args.k):
            w = float(W_norm[i, c])
            if w >= 0.05:
                membership_rows.append((aid, c, w))
    save_memberships(arc, run_id, membership_rows)

    # H matrix: top 20 follow features + top 10 RT features per community
    H_follow = H[:, :len(targets_f)]
    H_rt     = H[:, len(targets_f):]
    definition_rows = []
    for c in range(args.k):
        for rank, idx in enumerate(np.argsort(H_follow[c])[::-1][:20]):
            score = float(H_follow[c, idx])
            if score > 0:
                definition_rows.append((c, "follow", targets_f[idx], score, rank))
        for rank, idx in enumerate(np.argsort(H_rt[c])[::-1][:10]):
            score = float(H_rt[c, idx])
            if score > 0:
                definition_rows.append((c, "rt", targets_r[idx], score, rank))
    save_definitions(arc, run_id, definition_rows)

    arc.close()
    print(f"done  ({len(membership_rows):,} membership rows, {len(definition_rows)} definition rows)")
    print(f"  → seed Layer 2 with: python scripts/seed_communities.py --run-id {run_id}")


if __name__ == "__main__":
    main()
