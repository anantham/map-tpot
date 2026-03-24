#!/usr/bin/env python3
"""Compare NMF runs: factor-aligned side-by-side on known accounts.

Aligns factors between two Layer 1 runs by H-matrix feature overlap
(using feature_type:target keys to avoid cross-modality inflation).

Usage:
    .venv/bin/python3 -m scripts.verify_likes_nmf --old-run nmf-k14-20260225-a15a41 --new-run <run_id>
    .venv/bin/python3 -m scripts.verify_likes_nmf --old-run nmf-k14-20260225-a15a41 --new-run auto
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

ARCHIVE_DB = DEFAULT_ARCHIVE_DB

# Accounts whose community profiles we track across runs
KNOWN_ACCOUNTS = [
    "RomeoStevens76",
    "nickcammarata",
    "repligate",
    "visakanv",
    "dschorno",
    "QiaochuYuan",
    "adityaarpitha",
    "pee_zombie",
    "eshear",
    "xuenay",
]

MATCH_THRESHOLD = 0.1  # Below this overlap, treat factor pair as unmatched


# ── Data loading ─────────────────────────────────────────────────────────────


def load_run_info(conn: sqlite3.Connection, run_id: str) -> dict:
    """Load metadata for a single run."""
    row = conn.execute(
        "SELECT run_id, k, signal, threshold, account_count, notes, created_at"
        " FROM community_run WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        return {}
    return {
        "run_id": row[0],
        "k": row[1],
        "signal": row[2],
        "threshold": row[3],
        "account_count": row[4],
        "notes": row[5],
        "created_at": row[6],
    }


def load_definitions(
    conn: sqlite3.Connection, run_id: str
) -> dict[int, set[str]]:
    """Load H-matrix features per factor as {factor_idx: {"follow:12345", "rt:username", ...}}.

    Keys are feature_type:target to avoid cross-modality inflation
    (same account can appear under follow, rt, and like modalities).
    """
    rows = conn.execute(
        "SELECT community_idx, feature_type, target"
        " FROM community_definition WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    defs: dict[int, set[str]] = {}
    for cidx, ftype, target in rows:
        defs.setdefault(cidx, set()).add(f"{ftype}:{target}")
    return defs


def load_definitions_by_type(
    conn: sqlite3.Connection, run_id: str
) -> dict[int, dict[str, list[tuple[str, float]]]]:
    """Load H-matrix features grouped by type for display.

    Returns {factor_idx: {"follow": [(target, score), ...], "rt": [...], "like": [...]}}.
    """
    rows = conn.execute(
        "SELECT community_idx, feature_type, target, score"
        " FROM community_definition WHERE run_id = ?"
        " ORDER BY community_idx, feature_type, score DESC",
        (run_id,),
    ).fetchall()
    defs: dict[int, dict[str, list[tuple[str, float]]]] = {}
    for cidx, ftype, target, score in rows:
        defs.setdefault(cidx, {}).setdefault(ftype, []).append((target, score))
    return defs


def load_memberships(
    conn: sqlite3.Connection, run_id: str
) -> dict[str, dict[int, float]]:
    """Load W-matrix: {account_id: {factor_idx: weight}}."""
    rows = conn.execute(
        "SELECT account_id, community_idx, weight"
        " FROM community_membership WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    memberships: dict[str, dict[int, float]] = {}
    for aid, cidx, weight in rows:
        memberships.setdefault(aid, {})[cidx] = weight
    return memberships


def resolve_usernames(conn: sqlite3.Connection) -> dict[str, str]:
    """Map username (case-insensitive) -> account_id for known accounts."""
    result: dict[str, str] = {}
    for name in KNOWN_ACCOUNTS:
        row = conn.execute(
            "SELECT account_id FROM tweets WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (name,),
        ).fetchone()
        if row:
            result[name] = row[0]
        else:
            # Fallback: profiles table
            row = conn.execute(
                "SELECT account_id FROM profiles WHERE LOWER(username) = LOWER(?) LIMIT 1",
                (name,),
            ).fetchone()
            if row:
                result[name] = row[0]
    return result


def resolve_target_ids(conn: sqlite3.Connection, target_ids: list[str]) -> dict[str, str]:
    """Map account_id -> username for display. Uses resolved_accounts, profiles, tweets."""
    if not target_ids:
        return {}
    result: dict[str, str] = {}

    # resolved_accounts (primary)
    placeholders = ",".join("?" * len(target_ids))
    try:
        for aid, username, status in conn.execute(
            f"SELECT account_id, username, status FROM resolved_accounts"
            f" WHERE account_id IN ({placeholders})",
            target_ids,
        ).fetchall():
            if status == "active" and username:
                result[aid] = username
    except Exception:
        pass

    # profiles (fallback)
    missing = [t for t in target_ids if t not in result]
    if missing:
        placeholders = ",".join("?" * len(missing))
        try:
            for aid, username in conn.execute(
                f"SELECT account_id, username FROM profiles"
                f" WHERE account_id IN ({placeholders})",
                missing,
            ).fetchall():
                if username:
                    result[aid] = username
        except Exception:
            pass

    return result


# ── Factor alignment ────────────────────────────────────────────────────────


def overlap_score(set_a: set[str], set_b: set[str]) -> float:
    """Overlap = |intersection| / max(|A|, |B|). Returns 0 if both empty."""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / max(len(set_a), len(set_b))


def align_factors(
    old_defs: dict[int, set[str]],
    new_defs: dict[int, set[str]],
) -> tuple[dict[int, int], dict[int, float]]:
    """Greedy alignment of new factors to old factors by feature overlap.

    Returns:
        mapping: {new_idx: old_idx} for factors with overlap >= MATCH_THRESHOLD
        quality: {new_idx: overlap_score} for ALL new factors (including unmatched)
    """
    quality: dict[int, float] = {}

    # Build full overlap matrix
    old_idxs = sorted(old_defs.keys())
    new_idxs = sorted(new_defs.keys())

    # Score every pair
    scores: list[tuple[float, int, int]] = []
    for ni in new_idxs:
        for oi in old_idxs:
            s = overlap_score(new_defs[ni], old_defs[oi])
            scores.append((s, ni, oi))

    # Greedy: pick best-scoring pairs first
    scores.sort(reverse=True)
    mapping: dict[int, int] = {}
    used_old: set[int] = set()
    used_new: set[int] = set()

    for score, ni, oi in scores:
        if ni in used_new or oi in used_old:
            continue
        if score < MATCH_THRESHOLD:
            break  # All remaining pairs are below threshold
        mapping[ni] = oi
        quality[ni] = score
        used_new.add(ni)
        used_old.add(oi)

    # Record zero-quality for unmatched new factors
    for ni in new_idxs:
        if ni not in quality:
            # Find best overlap even if below threshold (for reporting)
            best = 0.0
            for oi in old_idxs:
                if oi not in used_old:
                    best = max(best, overlap_score(new_defs[ni], old_defs[oi]))
            quality[ni] = best

    return mapping, quality


def resolve_auto_run(conn: sqlite3.Connection, old_k: int) -> Optional[str]:
    """Find latest likes-enriched run matching the old run's k."""
    row = conn.execute(
        "SELECT run_id FROM community_run"
        " WHERE signal LIKE '%like%' AND k = ?"
        " ORDER BY created_at DESC LIMIT 1",
        (old_k,),
    ).fetchone()
    return row[0] if row else None


# ── Display helpers ──────────────────────────────────────────────────────────


def format_run_info(info: dict) -> str:
    """Format a run's metadata for display."""
    lines = [
        f"  Run ID:   {info['run_id']}",
        f"  k:        {info['k']}",
        f"  Signal:   {info['signal']}",
        f"  Accounts: {info['account_count']}",
        f"  Notes:    {info.get('notes') or '(none)'}",
        f"  Created:  {info['created_at'][:19]}",
    ]
    return "\n".join(lines)


def print_section(title: str, width: int = 76) -> None:
    """Print a section header."""
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_subsection(title: str, width: int = 76) -> None:
    """Print a subsection header."""
    print()
    print(f"-- {title} " + "-" * max(0, width - len(title) - 4))


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two NMF runs with factor-aligned analysis"
    )
    parser.add_argument(
        "--old-run",
        required=True,
        help="Baseline run_id (e.g. nmf-k14-20260225-a15a41)",
    )
    parser.add_argument(
        "--new-run",
        required=True,
        help="New run_id to compare, or 'auto' to find latest likes run matching k",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(ARCHIVE_DB),
        help="Path to archive_tweets.db",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)

    # ── Load old run ──────────────────────────────────────────────────────
    old_info = load_run_info(conn, args.old_run)
    if not old_info:
        print(f"ERROR: Old run '{args.old_run}' not found in community_run table.")
        all_runs = conn.execute(
            "SELECT run_id, signal, k FROM community_run ORDER BY created_at DESC"
        ).fetchall()
        if all_runs:
            print("Available runs:")
            for r in all_runs:
                print(f"  {r[0]}  (signal={r[1]}, k={r[2]})")
        conn.close()
        sys.exit(1)

    # ── Resolve new run ───────────────────────────────────────────────────
    new_run_id = args.new_run
    if new_run_id == "auto":
        new_run_id = resolve_auto_run(conn, old_info["k"])
        if not new_run_id:
            print(
                f"ERROR: No likes-enriched run found with k={old_info['k']}."
                " Run cluster_soft.py with --likes --save first."
            )
            conn.close()
            sys.exit(1)
        print(f"Auto-resolved new run: {new_run_id}")

    new_info = load_run_info(conn, new_run_id)
    if not new_info:
        print(f"ERROR: New run '{new_run_id}' not found in community_run table.")
        conn.close()
        sys.exit(1)

    # ── Section 1: Run info ───────────────────────────────────────────────
    print_section("NMF RUN COMPARISON")
    print()
    print("OLD (baseline):")
    print(format_run_info(old_info))
    print()
    print("NEW (experiment):")
    print(format_run_info(new_info))

    # ── Load data ─────────────────────────────────────────────────────────
    old_defs = load_definitions(conn, args.old_run)
    new_defs = load_definitions(conn, new_run_id)
    old_defs_by_type = load_definitions_by_type(conn, args.old_run)
    new_defs_by_type = load_definitions_by_type(conn, new_run_id)
    old_memberships = load_memberships(conn, args.old_run)
    new_memberships = load_memberships(conn, new_run_id)

    # Collect all target IDs for username resolution
    all_target_ids = set()
    for factor_defs in [old_defs, new_defs]:
        for features in factor_defs.values():
            for key in features:
                ftype, target = key.split(":", 1)
                if ftype == "follow" or ftype == "like":
                    all_target_ids.add(target)
    id_to_username = resolve_target_ids(conn, list(all_target_ids))

    def display_target(ftype: str, target: str) -> str:
        """Format a target for display (resolve IDs to usernames)."""
        if ftype in ("follow", "like"):
            username = id_to_username.get(target)
            if username:
                return f"@{username}"
            return f"#{target[:8]}"  # Truncated ID for unresolved
        return f"@{target}"  # RT targets are already usernames

    # ── Section 2: Factor alignment ───────────────────────────────────────
    mapping, quality = align_factors(old_defs, new_defs)

    print_section("FACTOR ALIGNMENT")
    print()
    print(
        f"  Matched: {len(mapping)} factors with overlap >= {MATCH_THRESHOLD:.0%}"
    )

    # Identify disappeared old factors (not matched by any new factor)
    matched_old = set(mapping.values())
    disappeared = sorted(set(old_defs.keys()) - matched_old)
    # Identify new-born factors (not matched to any old factor)
    newborn = sorted(set(new_defs.keys()) - set(mapping.keys()))

    if disappeared:
        print(f"  Disappeared: {len(disappeared)} old factors not matched")
    if newborn:
        print(f"  New births:  {len(newborn)} new factors not matched")

    # Print alignment table
    print()
    print(f"  {'New':>4}  {'Old':>4}  {'Overlap':>8}  {'Status':<12}  Top features (new run)")
    print(f"  {'----':>4}  {'----':>4}  {'--------':>8}  {'------':<12}  ---------------------")

    for ni in sorted(new_defs.keys()):
        oi = mapping.get(ni)
        ov = quality[ni]
        if oi is not None:
            if ov >= 0.3:
                status = "MATCHED"
                marker = "+"
            else:
                status = "WEAK"
                marker = "~"
        else:
            status = "NEW BIRTH"
            marker = "*"

        # Top 5 features from new factor for context
        top_features = []
        for ftype in ("follow", "rt", "like"):
            entries = new_defs_by_type.get(ni, {}).get(ftype, [])
            for target, score in entries[:3]:
                top_features.append(display_target(ftype, target))

        features_str = ", ".join(top_features[:6])
        oi_str = str(oi) if oi is not None else "---"
        print(
            f"  {marker} {ni:>3}  {oi_str:>4}  {ov:>7.1%}  {status:<12}  {features_str}"
        )

    # Show disappeared old factors
    if disappeared:
        print()
        print("  Disappeared old factors (no match in new run):")
        for oi in disappeared:
            top_features = []
            for ftype in ("follow", "rt"):
                entries = old_defs_by_type.get(oi, {}).get(ftype, [])
                for target, score in entries[:3]:
                    top_features.append(display_target(ftype, target))
            features_str = ", ".join(top_features[:6])
            print(f"    Old {oi}: {features_str}")

    # ── Section 3: Per-factor detail (matched factors) ────────────────────
    print_section("MATCHED FACTOR DETAILS")

    for ni in sorted(mapping.keys()):
        oi = mapping[ni]
        ov = quality[ni]
        print_subsection(f"New {ni} <-> Old {oi}  (overlap: {ov:.1%})")

        # Show side-by-side features
        for ftype in ("follow", "rt", "like"):
            old_entries = old_defs_by_type.get(oi, {}).get(ftype, [])
            new_entries = new_defs_by_type.get(ni, {}).get(ftype, [])
            if not old_entries and not new_entries:
                continue

            print(f"  {ftype.upper()} features:")
            max_show = max(len(old_entries), len(new_entries))
            max_show = min(max_show, 8)
            for i in range(max_show):
                old_col = ""
                new_col = ""
                if i < len(old_entries):
                    t, s = old_entries[i]
                    old_col = f"{display_target(ftype, t):<20} {s:.4f}"
                if i < len(new_entries):
                    t, s = new_entries[i]
                    new_col = f"{display_target(ftype, t):<20} {s:.4f}"
                print(f"    {old_col:<32}  |  {new_col}")

    # ── Section 4: Known account comparison ───────────────────────────────
    print_section("KNOWN ACCOUNT COMPARISON")

    username_to_id = resolve_usernames(conn)

    for name in KNOWN_ACCOUNTS:
        aid = username_to_id.get(name)
        if not aid:
            print(f"\n  @{name}: NOT FOUND in database")
            continue

        old_weights = old_memberships.get(aid, {})
        new_weights = new_memberships.get(aid, {})

        print(f"\n  @{name} (account_id: {aid})")

        if not old_weights and not new_weights:
            print("    No memberships in either run (below persistence threshold)")
            continue

        # Build aligned display: for each new factor, show old equivalent
        print(f"    {'Factor':>8}  {'Old wt':>8}  {'New wt':>8}  {'Delta':>8}  Note")
        print(f"    {'------':>8}  {'------':>8}  {'------':>8}  {'-----':>8}  ----")

        # Show matched factors where account has weight in either run
        shown_old_idxs: set[int] = set()
        for ni in sorted(new_defs.keys()):
            oi = mapping.get(ni)
            new_w = new_weights.get(ni, 0.0)
            old_w = old_weights.get(oi, 0.0) if oi is not None else 0.0

            if new_w < 0.01 and old_w < 0.01:
                continue  # Skip negligible weights

            delta = new_w - old_w
            delta_str = f"{delta:+.2f}" if delta != 0 else "  ---"

            note = ""
            if oi is not None:
                shown_old_idxs.add(oi)
                note = f"(aligned: new {ni} = old {oi})"
            else:
                note = "(new-born factor)"

            arrow = ""
            if abs(delta) >= 0.05:
                arrow = " >>>" if delta > 0 else " <<<"

            print(
                f"    N{ni:>5}  {old_w:>8.3f}  {new_w:>8.3f}  {delta_str:>8}{arrow}  {note}"
            )

        # Show old factors that had weight but weren't matched
        for oi in sorted(old_weights.keys()):
            if oi in shown_old_idxs:
                continue
            old_w = old_weights[oi]
            if old_w < 0.01:
                continue
            print(
                f"    O{oi:>5}  {old_w:>8.3f}  {'---':>8}  {-old_w:>+8.2f} <<<  (disappeared factor)"
            )

    # ── Section 5: Summary metrics ────────────────────────────────────────
    print_section("SUMMARY METRICS")

    # Overall alignment quality
    matched_overlaps = [quality[ni] for ni in mapping]
    avg_overlap = sum(matched_overlaps) / len(matched_overlaps) if matched_overlaps else 0.0

    print(f"""
  Factor alignment:
    Matched factors:     {len(mapping)} / {len(new_defs)} new factors
    Average overlap:     {avg_overlap:.1%}
    New births:          {len(newborn)}
    Disappeared:         {len(disappeared)}

  Run comparison:
    Old k={old_info['k']}, signal={old_info['signal']}, {old_info['account_count']} accounts
    New k={new_info['k']}, signal={new_info['signal']}, {new_info['account_count']} accounts
""")

    # Feature type breakdown for new run
    new_feature_types: dict[str, int] = {}
    for ni, feats in new_defs.items():
        for key in feats:
            ftype = key.split(":", 1)[0]
            new_feature_types[ftype] = new_feature_types.get(ftype, 0) + 1

    print("  Feature types in new run:")
    for ftype, count in sorted(new_feature_types.items()):
        print(f"    {ftype}: {count} features across all factors")

    # Membership change summary
    old_account_set = set(old_memberships.keys())
    new_account_set = set(new_memberships.keys())
    print(f"""
  Membership changes:
    Accounts in old run:  {len(old_account_set)}
    Accounts in new run:  {len(new_account_set)}
    Only in old:          {len(old_account_set - new_account_set)}
    Only in new:          {len(new_account_set - old_account_set)}
    In both:              {len(old_account_set & new_account_set)}
""")

    # Large weight shifts across all accounts
    print("  Largest weight shifts (top 10 accounts by max absolute delta):")
    shifts: list[tuple[str, float, str]] = []
    for aid in old_account_set | new_account_set:
        old_w = old_memberships.get(aid, {})
        new_w = new_memberships.get(aid, {})
        max_delta = 0.0
        detail = ""
        for ni in new_defs:
            oi = mapping.get(ni)
            nw = new_w.get(ni, 0.0)
            ow = old_w.get(oi, 0.0) if oi is not None else 0.0
            d = abs(nw - ow)
            if d > max_delta:
                max_delta = d
                detail = f"N{ni}(={oi}): {ow:.2f}->{nw:.2f}"

        # Also check disappeared factors
        for oi_check in old_w:
            if oi_check not in matched_old:
                d = old_w[oi_check]
                if d > max_delta:
                    max_delta = d
                    detail = f"O{oi_check}(gone): {d:.2f}->0.00"

        if max_delta >= 0.05:
            # Resolve username
            uname = conn.execute(
                "SELECT username FROM tweets WHERE account_id = ? LIMIT 1",
                (aid,),
            ).fetchone()
            uname = uname[0] if uname else aid[:12]
            shifts.append((uname, max_delta, detail))

    shifts.sort(key=lambda x: -x[1])
    for uname, delta, detail in shifts[:10]:
        print(f"    @{uname:<26} delta={delta:.3f}  {detail}")

    print()
    print("=" * 76)
    print("  COMPARISON COMPLETE")
    print("=" * 76)

    conn.close()


if __name__ == "__main__":
    main()
