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
import logging
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
from scipy.sparse import hstack
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

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
    except (sqlite3.OperationalError, sqlite3.DatabaseError, FileNotFoundError) as exc:
        logger.warning("resolve_account_ids: resolved_accounts lookup failed: %s", exc)

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
        except (sqlite3.OperationalError, sqlite3.DatabaseError, FileNotFoundError) as exc:
            logger.warning("resolve_account_ids: profiles lookup failed: %s", exc)

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
        except (sqlite3.OperationalError, sqlite3.DatabaseError, FileNotFoundError) as exc:
            logger.warning("resolve_account_ids: cache.db lookup failed: %s", exc)

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


def build_likes_matrix(con, accounts, min_count=1):
    """Build sparse matrix of like-author edges from account_engagement_agg.

    Values are like_count (not binary). Handles missing table gracefully.
    Returns (CSR matrix, sorted target_list).
    """
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}
    n = len(accounts)
    try:
        rows = con.execute(
            "SELECT source_id, target_id, like_count "
            "FROM account_engagement_agg WHERE like_count >= ?",
            (min_count,),
        ).fetchall()
    except Exception:
        # Table doesn't exist — return empty matrix
        from scipy.sparse import csr_matrix
        return csr_matrix((n, 0), dtype=np.float32), []

    if not rows:
        from scipy.sparse import csr_matrix
        return csr_matrix((n, 0), dtype=np.float32), []

    targets = sorted({r[1] for r in rows})
    target_idx = {t: j for j, t in enumerate(targets)}
    m = len(targets)

    from scipy.sparse import lil_matrix, csr_matrix
    mat = lil_matrix((n, m), dtype=np.float32)
    for src, tgt, cnt in rows:
        i = account_idx.get(src)
        j = target_idx.get(tgt)
        if i is not None and j is not None:
            mat[i, j] = float(cnt)
    return csr_matrix(mat), targets


def make_run_id(k, signal, rt_w, like_w, accounts, halflife_days=None):
    """Deterministic run_id encoding all run-shaping params.

    Format:
      nmf-k{k}-{signal}-lw{like_w}-{date}-{hash}   (when like_w > 0)
      nmf-k{k}-{signal}-{date}-{hash}               (when like_w == 0)

    halflife_days is included in the hash when set, so decay runs get unique IDs.
    """
    aid_str = "".join(aid for aid, _ in sorted(accounts))
    hl_str = f"hl{halflife_days}" if halflife_days is not None else ""
    h = hashlib.sha1(f"{k}{signal}{rt_w:.2f}{like_w:.2f}{hl_str}{aid_str}".encode()).hexdigest()[:6]
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    if like_w > 0:
        return f"nmf-k{k}-{signal}-lw{like_w}-{date}-{h}"
    return f"nmf-k{k}-{signal}-{date}-{h}"


def compute_decay_weight(age_days: float, halflife_days: float) -> float:
    """Compute exponential decay weight for a given age.

    weight = exp(-lambda * age_days) where lambda = ln(2) / halflife_days.
    At age_days == halflife_days, weight == 0.5.
    """
    lam = math.log(2) / halflife_days
    return math.exp(-lam * age_days)


def _parse_twitter_date(date_str: str):
    """Parse Twitter's created_at format: 'Tue Nov 25 03:54:12 +0000 2025'.

    Returns None if parsing fails.
    """
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def build_retweet_matrix(con, accounts, min_count=2, halflife_days=None, now=None):
    """Build sparse retweet matrix, optionally with time-decay weighting.

    When halflife_days is None (default), uses raw counts (original behavior).
    When set, each RT is weighted by exp(-lambda * age_days) before aggregation.
    min_count threshold applies to the aggregated (possibly decayed) sum.
    """
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}

    if halflife_days is not None:
        # Fetch individual rows for per-RT decay weighting
        rows = con.execute(
            "SELECT account_id, rt_of_username, created_at "
            "FROM retweets WHERE created_at IS NOT NULL"
        ).fetchall()

        if now is None:
            now = datetime.now(timezone.utc)

        # Aggregate with decay weights
        pair_weights = defaultdict(float)
        for aid, uname, created_at in rows:
            if not uname:
                continue
            dt = _parse_twitter_date(created_at)
            if dt is None:
                continue
            age_days = max(0, (now - dt).total_seconds() / 86400)
            weight = compute_decay_weight(age_days, halflife_days)
            pair_weights[(aid, uname)] += weight

        # Apply min_count to decayed sums
        filtered = [
            (aid, uname, w)
            for (aid, uname), w in pair_weights.items()
            if w >= min_count
        ]
    else:
        # Original behavior: aggregate with raw counts
        raw_rows = con.execute("""
            SELECT account_id, rt_of_username, COUNT(*) as cnt
            FROM retweets GROUP BY account_id, rt_of_username HAVING cnt >= ?
        """, (min_count,)).fetchall()
        filtered = [(r[0], r[1], r[2]) for r in raw_rows]

    targets = sorted({uname for _, uname, _ in filtered if uname})
    target_idx = {t: j for j, t in enumerate(targets)}
    n, m = len(accounts), len(targets)

    from scipy.sparse import lil_matrix, csr_matrix
    mat = lil_matrix((n, m), dtype=np.float32)
    for aid, uname, w in filtered:
        i = account_idx.get(aid)
        j = target_idx.get(uname)
        if i is not None and j is not None:
            mat[i, j] = float(w)
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
    parser.add_argument("--likes",         action="store_true",      help="Include likes signal")
    parser.add_argument("--likes-weight",  type=float, default=0.4,  help="Weight for likes (default 0.4)")
    parser.add_argument("--rt-weight",     type=float, default=0.6,  help="Weight for retweets (default 0.6)")
    parser.add_argument("--decay-halflife", type=int,  default=None, help="RT decay halflife in days (e.g. 365). Off by default.")
    args = parser.parse_args()

    con = sqlite3.connect(str(ARCHIVE_DB))
    accounts = load_accounts(con)
    bios = load_bios(con, accounts)
    print(f"Accounts: {len(accounts)}")

    print("Building following matrix...", end=" ", flush=True)
    mat_f, targets_f = build_following_matrix(con, accounts)
    mat_f_tfidf = tfidf(mat_f)
    print(f"{mat_f.shape[1]:,} targets")

    decay_label = ""
    if args.decay_halflife:
        print(f"Building retweet matrix (halflife={args.decay_halflife}d)...", end=" ", flush=True)
        mat_r, targets_r = build_retweet_matrix(
            con, accounts, halflife_days=args.decay_halflife,
        )
        decay_label = f"_decay{args.decay_halflife}"
    else:
        print("Building retweet matrix...", end=" ", flush=True)
        mat_r, targets_r = build_retweet_matrix(con, accounts)
    mat_r_tfidf = tfidf(mat_r)
    print(f"{mat_r.shape[1]:,} targets")

    # Optionally build likes matrix
    targets_l = []
    if args.likes:
        print("Building likes matrix...", end=" ", flush=True)
        mat_l, targets_l = build_likes_matrix(con, accounts)
        if mat_l.shape[1] > 0:
            mat_l_tfidf = tfidf(mat_l)
            like_coverage = (mat_l.getnnz(axis=1) > 0).sum()
            print(f"{mat_l.shape[1]:,} targets, {like_coverage}/{len(accounts)} accounts with data")
        else:
            mat_l_tfidf = None
            print("no data (table missing or empty)")

    # Determine signal label (e.g. "follow+rt_decay365+like")
    rt_label = f"rt{decay_label}"
    signal = f"follow+{rt_label}+like" if args.likes and targets_l else f"follow+{rt_label}"

    # Combine: following (weight 1.0) + retweet + optional likes
    blocks = [
        normalize(mat_f_tfidf),
        normalize(mat_r_tfidf) * args.rt_weight,
    ]
    if args.likes and mat_l_tfidf is not None:
        blocks.append(normalize(mat_l_tfidf) * args.likes_weight)
    combined = hstack(blocks)

    print(f"Running NMF (k={args.k})...", end=" ", flush=True)
    nmf = NMF(n_components=args.k, random_state=42, max_iter=500, init="nndsvda")
    W = nmf.fit_transform(combined)   # accounts × communities
    H = nmf.components_                # communities × features
    print("done")

    # Normalise W so each account's weights sum to 1 → interpretable as fractions
    W_norm = W / (W.sum(axis=1, keepdims=True) + 1e-10)

    # Split H back into following / RT / likes feature spaces
    nf = mat_f_tfidf.shape[1]
    nr = mat_r_tfidf.shape[1]
    H_follow = H[:, :nf]
    H_rt     = H[:, nf:nf + nr]
    H_like   = H[:, nf + nr:] if (nf + nr) < H.shape[1] else None

    # Pre-resolve target IDs → usernames for following targets
    follow_ids_needed = [targets_f[i] for c in range(args.k)
                         for i in np.argsort(H_follow[c])[::-1][:args.topn]]
    # Also resolve like target IDs if present
    like_ids_needed = []
    if H_like is not None and targets_l:
        like_ids_needed = [targets_l[i] for c in range(args.k)
                           for i in np.argsort(H_like[c])[::-1][:args.topn]]
    id_map = resolve_account_ids(list(set(follow_ids_needed + like_ids_needed)))

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

        # Top like targets for this community
        if H_like is not None and targets_l:
            top_l_idx = np.argsort(H_like[c])[::-1][:args.topn * 2]
            top_likes = []
            for idx in top_l_idx:
                if len(top_likes) >= 6:
                    break
                raw = targets_l[idx]
                username = id_map.get(raw, raw)
                if username is None or (username == raw and username.isdigit()):
                    continue
                top_likes.append(f"@{username}")
            if top_likes:
                print(f"   Likes:   {', '.join(top_likes)}")

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
        _save_run(con, args, accounts, W_norm, H,
                  targets_f, targets_r, targets_l, nf, nr, signal)

    con.close()


def _save_run(con, args, accounts, W_norm, H,
              targets_f, targets_r, targets_l, nf, nr, signal):
    """Persist NMF results to archive_tweets.db (Layer 1)."""
    from communities.store import init_db, save_run, save_memberships, save_definitions

    like_w = args.likes_weight if args.likes else 0.0
    halflife = getattr(args, 'decay_halflife', None)
    run_id = make_run_id(
        k=args.k, signal=signal,
        rt_w=args.rt_weight, like_w=like_w,
        accounts=accounts,
        halflife_days=halflife,
    )

    print(f"\nSaving run {run_id} to DB...", end=" ", flush=True)

    arc = sqlite3.connect(str(ARCHIVE_DB))
    arc.execute("PRAGMA journal_mode=WAL")
    init_db(arc)

    save_run(
        arc, run_id,
        k=args.k,
        signal=signal,
        threshold=args.threshold,
        account_count=len(accounts),
        notes=args.notes,
    )

    # W matrix: store all weights >= 0.05 (wider than display threshold)
    membership_rows = []
    for i, (aid, _) in enumerate(accounts):
        for c in range(args.k):
            w = float(W_norm[i, c])
            if w >= 0.05:
                membership_rows.append((aid, c, w))
    save_memberships(arc, run_id, membership_rows)

    # H matrix: top 20 follow + top 10 RT + top 10 like features per community
    H_follow = H[:, :nf]
    H_rt     = H[:, nf:nf + nr]
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
        # Like features (if present)
        if (nf + nr) < H.shape[1] and targets_l:
            H_like = H[:, nf + nr:]
            for rank, idx in enumerate(np.argsort(H_like[c])[::-1][:10]):
                score = float(H_like[c, idx])
                if score > 0:
                    definition_rows.append((c, "like", targets_l[idx], score, rank))
    save_definitions(arc, run_id, definition_rows)

    arc.close()
    print(f"done  ({len(membership_rows):,} membership rows, {len(definition_rows)} definition rows)")
    print(f"  → seed Layer 2 with: python scripts/seed_communities.py --run-id {run_id}")


if __name__ == "__main__":
    main()
