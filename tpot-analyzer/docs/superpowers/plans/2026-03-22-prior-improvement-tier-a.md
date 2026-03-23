# Prior Improvement — Tier A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 17.5M likes signal to NMF community detection and produce a new Layer 1 run for comparison against the existing follow+rt run.

**Architecture:** Four independent deliverables: push commits (hygiene), automate bits rollup (reproducibility), integrate likes into NMF feature matrix (signal improvement), re-run NMF with factor-aligned comparison script (evaluation).

**Tech Stack:** Python 3, SQLite, scipy.sparse, sklearn NMF/TF-IDF, numpy

**Spec:** `docs/superpowers/specs/2026-03-22-prior-improvement-roadmap-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `scripts/rollup_bits.py` | Parse tweet_tags → aggregate to account_community_bits |
| Create | `scripts/verify_bits_rollup.py` | Verify rollup reproduces current 20-account state |
| Create | `tests/test_rollup_bits.py` | Unit tests for bits parsing and aggregation |
| Modify | `scripts/cluster_soft.py:128-189,299-350` | Add `build_likes_matrix()`, fix run_id, save like features |
| Create | `tests/test_cluster_soft_likes.py` | Unit tests for likes matrix building |
| Create | `scripts/verify_likes_nmf.py` | Factor-aligned comparison of old vs new NMF runs |

---

### Task 1: Push commits

**Files:**
- None (git operation only)

- [ ] **Step 1: Check current status**

```bash
cd tpot-analyzer && git status && git log --oneline -5
```
Expected: 10+ commits ahead of origin/main, clean working tree.

- [ ] **Step 2: Push to origin**

```bash
git push origin main
```
Expected: success, 10+ objects pushed.

- [ ] **Step 3: Verify**

```bash
git log --oneline origin/main -3
```
Expected: latest commits visible on remote.

---

### Task 2: Automate bits rollup (E1)

**Files:**
- Create: `scripts/rollup_bits.py`
- Create: `scripts/verify_bits_rollup.py`
- Create: `tests/test_rollup_bits.py`

**Context:** Bits tags live in `tweet_tags` with format `bits:SHORT_NAME:+N` (or `-N`). The `SHORT_NAME` maps to `community.short_name`. The `account_community_bits` table already has 147 rows across 20 accounts.

**Migration note:** The existing 147 rows all have `tweet_count = 0` (the field was never populated). This script REPAIRS that field — `tweet_count` will now correctly track how many tweets contributed bits to each (account, community) pair. This is a semantic fix, not a reproduction bug. The verification script compares `total_bits` and `pct` (with tolerance) against the existing baseline, and reports `tweet_count` changes as expected migration, not failures.

- [ ] **Step 1: Write unit tests for bits tag parsing**

```python
# tests/test_rollup_bits.py
"""Tests for bits rollup — tag parsing and aggregation logic."""
import pytest
from scripts.rollup_bits import parse_bits_tag, aggregate_bits


class TestParseBitsTag:
    def test_positive_tag(self):
        assert parse_bits_tag("bits:LLM-Whisperers:+3") == ("LLM-Whisperers", 3)

    def test_negative_tag(self):
        assert parse_bits_tag("bits:Qualia-Research:-2") == ("Qualia-Research", -2)

    def test_zero_bits(self):
        assert parse_bits_tag("bits:highbies:+0") == ("highbies", 0)

    def test_malformed_no_prefix(self):
        assert parse_bits_tag("LLM-Whisperers:+3") is None

    def test_malformed_missing_value(self):
        assert parse_bits_tag("bits:LLM-Whisperers") is None

    def test_malformed_non_numeric(self):
        assert parse_bits_tag("bits:LLM-Whisperers:abc") is None

    def test_extra_colons(self):
        # Edge case: community name with colons shouldn't happen but be safe
        assert parse_bits_tag("bits:AI-Safety:+1:extra") is None


class TestAggregateBits:
    def test_basic_aggregation(self):
        """Two tags for same community on same account → sum bits."""
        tags = [
            ("account1", "bits:LLM-Whisperers:+3"),
            ("account1", "bits:LLM-Whisperers:+2"),
            ("account1", "bits:Qualia-Research:+1"),
        ]
        short_to_id = {"LLM-Whisperers": "comm-llm", "Qualia-Research": "comm-qr"}
        result = aggregate_bits(tags, short_to_id)
        assert result[("account1", "comm-llm")]["total_bits"] == 5
        assert result[("account1", "comm-llm")]["tweet_count"] == 2
        assert result[("account1", "comm-qr")]["total_bits"] == 1
        assert result[("account1", "comm-qr")]["tweet_count"] == 1

    def test_negative_bits_subtract(self):
        tags = [
            ("account1", "bits:highbies:+5"),
            ("account1", "bits:highbies:-2"),
        ]
        short_to_id = {"highbies": "comm-h"}
        result = aggregate_bits(tags, short_to_id)
        assert result[("account1", "comm-h")]["total_bits"] == 3

    def test_unknown_community_skipped(self):
        tags = [("account1", "bits:NonExistent:+3")]
        short_to_id = {"LLM-Whisperers": "comm-llm"}
        result = aggregate_bits(tags, short_to_id)
        assert len(result) == 0

    def test_pct_calculation(self):
        """pct = total_bits / sum_all_bits_for_account * 100."""
        tags = [
            ("account1", "bits:LLM-Whisperers:+3"),
            ("account1", "bits:Qualia-Research:+7"),
        ]
        short_to_id = {"LLM-Whisperers": "comm-llm", "Qualia-Research": "comm-qr"}
        result = aggregate_bits(tags, short_to_id)
        assert result[("account1", "comm-llm")]["pct"] == pytest.approx(30.0)
        assert result[("account1", "comm-qr")]["pct"] == pytest.approx(70.0)

    def test_multiple_accounts(self):
        tags = [
            ("account1", "bits:LLM-Whisperers:+3"),
            ("account2", "bits:LLM-Whisperers:+5"),
        ]
        short_to_id = {"LLM-Whisperers": "comm-llm"}
        result = aggregate_bits(tags, short_to_id)
        assert result[("account1", "comm-llm")]["total_bits"] == 3
        assert result[("account2", "comm-llm")]["total_bits"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_rollup_bits.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.rollup_bits'`

- [ ] **Step 3: Write rollup_bits.py**

```python
# scripts/rollup_bits.py
"""Automate bits rollup: tweet_tags → account_community_bits.

Reads bits-tagged tweets, parses tag format 'bits:SHORT_NAME:±N',
aggregates per (account_id, community_id), writes to account_community_bits.

Usage:
    .venv/bin/python3 -m scripts.rollup_bits
    .venv/bin/python3 -m scripts.rollup_bits --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"


def parse_bits_tag(tag: str) -> tuple[str, int] | None:
    """Parse 'bits:SHORT_NAME:±N' → (short_name, bits_value) or None."""
    parts = tag.split(":")
    if len(parts) != 3 or parts[0] != "bits":
        return None
    try:
        return (parts[1], int(parts[2]))
    except ValueError:
        return None


def aggregate_bits(
    tags: list[tuple[str, str]],
    short_to_id: dict[str, str],
) -> dict[tuple[str, str], dict]:
    """Aggregate (account_id, tag_str) pairs → {(account_id, community_id): {total_bits, tweet_count}}.

    pct is computed as total_bits / sum_all_bits_for_account * 100.
    """
    # Pass 1: accumulate per (account, community)
    accum: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"total_bits": 0, "tweet_count": 0}
    )
    for account_id, tag_str in tags:
        parsed = parse_bits_tag(tag_str)
        if parsed is None:
            continue
        short_name, bits_value = parsed
        comm_id = short_to_id.get(short_name)
        if comm_id is None:
            continue
        key = (account_id, comm_id)
        accum[key]["total_bits"] += bits_value
        accum[key]["tweet_count"] += 1

    # Pass 2: compute pct per account
    account_totals: dict[str, int] = defaultdict(int)
    for (acct, _), v in accum.items():
        account_totals[acct] += abs(v["total_bits"])

    result = {}
    for (acct, comm_id), v in accum.items():
        total = account_totals[acct]
        pct = (abs(v["total_bits"]) / total * 100) if total > 0 else 0.0
        result[(acct, comm_id)] = {
            "total_bits": v["total_bits"],
            "tweet_count": v["tweet_count"],
            "pct": pct,
        }
    return result


def load_short_to_id(conn: sqlite3.Connection) -> dict[str, str]:
    """Map community.short_name → community.id."""
    rows = conn.execute("SELECT id, short_name FROM community WHERE short_name IS NOT NULL").fetchall()
    return {short: cid for cid, short in rows}


def load_bits_tags(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Load all (account_id, tag) pairs with category='bits'."""
    return conn.execute("""
        SELECT t.account_id, tt.tag
        FROM tweet_tags tt
        JOIN tweets t ON tt.tweet_id = t.tweet_id
        WHERE tt.category = 'bits'
    """).fetchall()


def write_rollup(
    conn: sqlite3.Connection,
    rollup: dict[tuple[str, str], dict],
    dry_run: bool = False,
) -> int:
    """Write aggregated bits to account_community_bits. Returns row count."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (acct, comm_id, v["total_bits"], v["tweet_count"], v["pct"], now)
        for (acct, comm_id), v in sorted(rollup.items())
    ]
    if dry_run:
        return len(rows)
    conn.execute("DELETE FROM account_community_bits")
    conn.executemany(
        "INSERT INTO account_community_bits "
        "(account_id, community_id, total_bits, tweet_count, pct, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Rollup bits tags to account_community_bits")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db_path))
    short_to_id = load_short_to_id(conn)
    print(f"Communities with short_name: {len(short_to_id)}")

    tags = load_bits_tags(conn)
    print(f"Bits tags loaded: {len(tags)}")

    rollup = aggregate_bits(tags, short_to_id)
    accounts = len({acct for acct, _ in rollup})
    print(f"Aggregated: {len(rollup)} rows across {accounts} accounts")

    if args.dry_run:
        for (acct, comm_id), v in sorted(rollup.items()):
            comm_name = conn.execute(
                "SELECT short_name FROM community WHERE id = ?", (comm_id,)
            ).fetchone()[0]
            username = conn.execute(
                "SELECT username FROM profiles WHERE account_id = ?", (acct,)
            ).fetchone()
            uname = username[0] if username else acct[:8]
            print(f"  @{uname:<24} {comm_name:<30} bits={v['total_bits']:>3} tweets={v['tweet_count']:>2} pct={v['pct']:.1f}%")
        print(f"\nDRY RUN — {len(rollup)} rows would be written")
    else:
        count = write_rollup(conn, rollup)
        print(f"Written {count} rows to account_community_bits")

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests**

```bash
cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_rollup_bits.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Write verification script**

```python
# scripts/verify_bits_rollup.py
"""Verify bits rollup reproduces current account_community_bits state.

Compares the script's computed rollup against the existing DB state.
All 20 accounts must match exactly.

Usage:
    .venv/bin/python3 -m scripts.verify_bits_rollup
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.rollup_bits import aggregate_bits, load_bits_tags, load_short_to_id

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"


def main():
    conn = sqlite3.connect(str(DB_PATH))

    # Load existing state
    existing = {}
    for acct, comm_id, total_bits, tweet_count, pct in conn.execute(
        "SELECT account_id, community_id, total_bits, tweet_count, pct FROM account_community_bits"
    ).fetchall():
        existing[(acct, comm_id)] = {
            "total_bits": total_bits,
            "tweet_count": tweet_count,
            "pct": pct,
        }

    # Compute fresh rollup
    short_to_id = load_short_to_id(conn)
    tags = load_bits_tags(conn)
    computed = aggregate_bits(tags, short_to_id)

    # Compare
    existing_keys = set(existing.keys())
    computed_keys = set(computed.keys())

    missing = existing_keys - computed_keys
    extra = computed_keys - existing_keys
    common = existing_keys & computed_keys

    ok = True

    if missing:
        print(f"✗ {len(missing)} rows in DB but not in computed rollup:")
        for k in sorted(missing):
            print(f"    {k}")
        ok = False

    if extra:
        print(f"✗ {len(extra)} rows in computed rollup but not in DB:")
        for k in sorted(extra):
            print(f"    {k}")
        ok = False

    bits_mismatches = []
    pct_mismatches = []
    tweet_count_migrations = 0
    PCT_TOLERANCE = 0.5  # allow small floating-point drift

    for key in sorted(common):
        e = existing[key]
        c = computed[key]
        if e["total_bits"] != c["total_bits"]:
            bits_mismatches.append((key, e, c))
        if abs(e["pct"] - c["pct"]) > PCT_TOLERANCE:
            pct_mismatches.append((key, e, c))
        # tweet_count: existing baseline has 0 everywhere (legacy).
        # The script now computes real counts. This is an expected migration.
        if e["tweet_count"] != c["tweet_count"]:
            tweet_count_migrations += 1

    if bits_mismatches:
        print(f"✗ {len(bits_mismatches)} rows with different total_bits:")
        for key, e, c in bits_mismatches[:10]:
            print(f"    {key}: DB={e['total_bits']} vs computed={c['total_bits']}")
        ok = False

    if pct_mismatches:
        print(f"✗ {len(pct_mismatches)} rows with pct drift > {PCT_TOLERANCE}%:")
        for key, e, c in pct_mismatches[:10]:
            print(f"    {key}: DB={e['pct']:.1f}% vs computed={c['pct']:.1f}%")
        ok = False

    # Summary
    existing_accounts = len({k[0] for k in existing_keys})
    computed_accounts = len({k[0] for k in computed_keys})

    print(f"\n{'✓' if ok else '✗'} Bits rollup verification")
    print(f"  Existing: {len(existing)} rows across {existing_accounts} accounts")
    print(f"  Computed: {len(computed)} rows across {computed_accounts} accounts")
    print(f"  Common keys: {len(common)}")
    print(f"  total_bits mismatches: {len(bits_mismatches)}")
    print(f"  pct mismatches (>{PCT_TOLERANCE}%): {len(pct_mismatches)}")
    print(f"  tweet_count migrations (0→real): {tweet_count_migrations} (expected)")

    if ok:
        print("\n✓ Rollup matches current state (total_bits + pct)")
        if tweet_count_migrations:
            print(f"  ℹ {tweet_count_migrations} tweet_count fields will be repaired from 0 → actual count")
    else:
        print("\n✗ MISMATCH — investigate before overwriting")

    conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run verification against live DB**

```bash
cd tpot-analyzer && .venv/bin/python3 -m scripts.verify_bits_rollup
```
Expected: `✓ Rollup matches current state (total_bits + pct)` — all 147 rows across 20 accounts match on total_bits and pct (within 0.5% tolerance). The script will report N tweet_count migrations (0→actual) as expected.

If total_bits or pct mismatches: investigate before proceeding. Do NOT overwrite until they match.

- [ ] **Step 7: Commit**

```bash
git add scripts/rollup_bits.py scripts/verify_bits_rollup.py tests/test_rollup_bits.py
git commit -m "feat(bits): automate bits rollup with verification

Parses tweet_tags (bits:SHORT_NAME:±N), aggregates per (account, community),
writes to account_community_bits. Verification script confirms computed
rollup matches existing 20-account state exactly.

Scripts: rollup_bits.py, verify_bits_rollup.py
Tests: test_rollup_bits.py (8 tests)
"
```

---

### Task 3: Add likes to NMF feature matrix (D2+D5)

**Files:**
- Modify: `scripts/cluster_soft.py:20-36,128-189,299-350`
- Create: `tests/test_cluster_soft_likes.py`

**Context:** The `account_engagement_agg` table has pre-aggregated like counts per account pair (24,501 pairs with likes > 0, covering ~79% of NMF accounts). We add a third signal block to the NMF input matrix. The run_id must encode signal mix and weights to prevent same-day collisions.

- [ ] **Step 1: Write unit tests for likes matrix building**

```python
# tests/test_cluster_soft_likes.py
"""Tests for likes matrix integration in NMF clustering."""
import sqlite3
import pytest
import numpy as np
from scipy.sparse import issparse


def _make_test_db():
    """Create an in-memory DB with minimal engagement data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE account_engagement_agg (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            like_count INTEGER DEFAULT 0,
            PRIMARY KEY (source_id, target_id)
        )
    """)
    conn.executemany(
        "INSERT INTO account_engagement_agg (source_id, target_id, like_count) VALUES (?, ?, ?)",
        [
            ("acct1", "target_a", 10),
            ("acct1", "target_b", 5),
            ("acct2", "target_a", 3),
            ("acct2", "target_c", 8),
            ("acct3", "target_b", 1),  # below min_count=2 if we add that filter
        ],
    )
    conn.commit()
    return conn


class TestBuildLikesMatrix:
    def test_basic_shape(self):
        from scripts.cluster_soft import build_likes_matrix
        conn = _make_test_db()
        accounts = [("acct1", "user1"), ("acct2", "user2"), ("acct3", "user3")]
        mat, targets = build_likes_matrix(conn, accounts)
        assert mat.shape[0] == 3  # 3 accounts
        assert mat.shape[1] == len(targets)  # distinct targets
        assert issparse(mat)

    def test_values_correct(self):
        from scripts.cluster_soft import build_likes_matrix
        conn = _make_test_db()
        accounts = [("acct1", "user1"), ("acct2", "user2"), ("acct3", "user3")]
        mat, targets = build_likes_matrix(conn, accounts)
        target_idx = {t: j for j, t in enumerate(targets)}
        # acct1 liked target_a 10 times
        assert mat[0, target_idx["target_a"]] == 10.0
        # acct2 liked target_c 8 times
        assert mat[1, target_idx["target_c"]] == 8.0

    def test_unknown_account_ignored(self):
        from scripts.cluster_soft import build_likes_matrix
        conn = _make_test_db()
        # Only include acct1, not acct2/acct3
        accounts = [("acct1", "user1")]
        mat, targets = build_likes_matrix(conn, accounts)
        assert mat.shape[0] == 1

    def test_empty_engagement(self):
        from scripts.cluster_soft import build_likes_matrix
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE account_engagement_agg (
                source_id TEXT, target_id TEXT, like_count INTEGER DEFAULT 0,
                PRIMARY KEY (source_id, target_id)
            )
        """)
        accounts = [("acct1", "user1")]
        mat, targets = build_likes_matrix(conn, accounts)
        assert mat.shape == (1, 0)
        assert targets == []


class TestRunIdIdentity:
    def test_different_signals_different_ids(self):
        from scripts.cluster_soft import make_run_id
        accounts = [("acct1", "u1"), ("acct2", "u2")]
        id_a = make_run_id(14, "follow+rt", 0.6, 0.0, accounts)
        id_b = make_run_id(14, "follow+rt+like", 0.6, 0.4, accounts)
        assert id_a != id_b

    def test_different_weights_different_ids(self):
        from scripts.cluster_soft import make_run_id
        accounts = [("acct1", "u1")]
        id_a = make_run_id(14, "follow+rt+like", 0.6, 0.4, accounts)
        id_b = make_run_id(14, "follow+rt+like", 0.6, 0.8, accounts)
        assert id_a != id_b

    def test_same_params_same_id(self):
        from scripts.cluster_soft import make_run_id
        accounts = [("acct1", "u1")]
        id_a = make_run_id(14, "follow+rt+like", 0.6, 0.4, accounts)
        id_b = make_run_id(14, "follow+rt+like", 0.6, 0.4, accounts)
        assert id_a == id_b
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_cluster_soft_likes.py -v
```
Expected: FAIL — `ImportError: cannot import name 'build_likes_matrix' from 'scripts.cluster_soft'`

- [ ] **Step 3: Add `build_likes_matrix()` to cluster_soft.py**

Add after `build_retweet_matrix()` (after line 145):

```python
def build_likes_matrix(con, accounts, min_count=1):
    """Build account × liked-author matrix from pre-aggregated engagement data.

    Uses account_engagement_agg.like_count (NOT raw 17.5M-row likes table).
    Returns sparse CSR matrix and list of target account_ids.
    """
    account_idx = {aid: i for i, (aid, _) in enumerate(accounts)}

    try:
        rows = con.execute("""
            SELECT source_id, target_id, like_count
            FROM account_engagement_agg
            WHERE like_count >= ?
        """, (min_count,)).fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist — return empty matrix
        from scipy.sparse import csr_matrix
        return csr_matrix((len(accounts), 0), dtype=np.float32), []

    targets = sorted({r[1] for r in rows})
    target_idx = {t: j for j, t in enumerate(targets)}
    n, m = len(accounts), len(targets)

    if m == 0:
        from scipy.sparse import csr_matrix
        return csr_matrix((n, 0), dtype=np.float32), []

    from scipy.sparse import lil_matrix, csr_matrix
    mat = lil_matrix((n, m), dtype=np.float32)
    for src, tgt, cnt in rows:
        i = account_idx.get(src)
        j = target_idx.get(tgt)
        if i is not None and j is not None:
            mat[i, j] = float(cnt)
    return csr_matrix(mat), targets
```

- [ ] **Step 4: Add `make_run_id()` function to cluster_soft.py**

Add after `load_bios()` (after line 154):

```python
def make_run_id(k: int, signal: str, rt_w: float, like_w: float, accounts: list) -> str:
    """Construct a unique run_id encoding all run-shaping parameters."""
    aid_str = "".join(aid for aid, _ in sorted(accounts))
    h = hashlib.sha1(f"{k}{signal}{rt_w}{like_w}{aid_str}".encode()).hexdigest()[:6]
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    if like_w > 0:
        return f"nmf-k{k}-{signal}-lw{like_w}-{date}-{h}"
    return f"nmf-k{k}-{signal}-{date}-{h}"
```

- [ ] **Step 5: Run tests to verify likes matrix and run_id pass**

```bash
cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_cluster_soft_likes.py -v
```
Expected: all tests PASS.

- [ ] **Step 6: Add CLI args for likes weight and signal**

In `main()`, add to argparser (after line 167):

```python
    parser.add_argument("--likes",        action="store_true",      help="Include likes signal from account_engagement_agg")
    parser.add_argument("--likes-weight", type=float, default=0.4,  help="Weight for likes signal (default 0.4)")
    parser.add_argument("--rt-weight",    type=float, default=0.6,  help="Weight for retweet signal (default 0.6)")
```

- [ ] **Step 7: Modify `main()` to build and concatenate likes matrix**

Replace the combined matrix section (lines 185-189) with:

```python
    # Combine: following (weight 1.0) + retweet (weight rt_w) + optional likes (weight likes_w)
    blocks = [normalize(mat_f_tfidf), normalize(mat_r_tfidf) * args.rt_weight]
    signal = "follow+rt"
    targets_l = []

    if args.likes:
        print("Building likes matrix...", end=" ", flush=True)
        mat_l, targets_l = build_likes_matrix(con, accounts)
        if mat_l.shape[1] > 0:
            mat_l_tfidf = tfidf(mat_l)
            blocks.append(normalize(mat_l_tfidf) * args.likes_weight)
            signal = "follow+rt+like"
            like_coverage = (mat_l.getnnz(axis=1) > 0).sum()
            print(f"{mat_l.shape[1]:,} targets, {like_coverage}/{len(accounts)} accounts with data")
        else:
            print("no likes data found — skipping")

    combined = hstack(blocks)
```

- [ ] **Step 8: Modify `_save_run()` to use new run_id and save like features**

Replace `_save_run` signature and body (lines 299-350):

```python
def _save_run(con, args, accounts, W_norm, H, targets_f, targets_r, targets_l, nf, nr, signal):
    """Persist NMF results to archive_tweets.db (Layer 1)."""
    from communities.store import init_db, save_run, save_memberships, save_definitions

    run_id = make_run_id(args.k, signal, args.rt_weight, args.likes_weight if args.likes else 0.0, accounts)

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

    # H matrix: top features per community, split by modality
    H_follow = H[:, :nf]
    H_rt = H[:, nf:nf + nr]
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

    # Like features (only present when --likes is used)
    if targets_l:
        H_like = H[:, nf + nr:]
        for c in range(args.k):
            for rank, idx in enumerate(np.argsort(H_like[c])[::-1][:10]):
                score = float(H_like[c, idx])
                if score > 0:
                    definition_rows.append((c, "like", targets_l[idx], score, rank))

    save_definitions(arc, run_id, definition_rows)

    arc.close()
    print(f"done  ({len(membership_rows):,} membership rows, {len(definition_rows)} definition rows)")
    print(f"  → seed Layer 2 with: python scripts/seed_communities.py --run-id {run_id}")
```

- [ ] **Step 9: Update the call site in `main()` to pass new args**

In `main()`, update the `_save_run` call (around line 293-294) and the H-matrix split:

```python
    # Split H back into feature spaces (for display)
    nf = mat_f_tfidf.shape[1]
    nr = mat_r_tfidf.shape[1]
    H_follow = H[:, :nf]
    H_rt     = H[:, nf:nf + nr]
```

And update the save call:

```python
    if args.save:
        _save_run(con, args, accounts, W_norm, H, targets_f, targets_r, targets_l, nf, nr, signal)
```

- [ ] **Step 10: Update console rendering to show like-defining features**

In `main()`, after the `top_rts` line (around line 248), add like features display:

```python
        # Top like targets for this community (only when likes are in the matrix)
        top_likes = []
        if args.likes and targets_l:
            H_like_display = H[:, nf + nr:]
            top_l_idx = np.argsort(H_like_display[c])[::-1][:6]
            like_id_map = resolve_account_ids([targets_l[i] for i in top_l_idx if H_like_display[c, i] > 0])
            for i in top_l_idx:
                if H_like_display[c, i] > 0:
                    uid = like_id_map.get(targets_l[i], targets_l[i])
                    if uid and not (isinstance(uid, str) and uid.isdigit()):
                        top_likes.append(f"@{uid}")
```

And in the display section (after the RT print), add:

```python
        if top_likes:
            print(f"   Likes:   {', '.join(top_likes[:6])}")
```

- [ ] **Step 11: Test the full pipeline dry-run (no --save)**

```bash
cd tpot-analyzer && .venv/bin/python3 -m scripts.cluster_soft --k 14 --likes --topn 5
```
Expected: output shows "Building likes matrix... N targets, M/298 accounts with data" and community listings show Follows, RTs, AND Likes defining features.

- [ ] **Step 11: Run all tests**

```bash
cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_cluster_soft_likes.py tests/test_rollup_bits.py -v
```
Expected: all tests PASS.

- [ ] **Step 12: Commit**

```bash
git add scripts/cluster_soft.py tests/test_cluster_soft_likes.py
git commit -m "feat(nmf): add likes signal to NMF feature matrix

Adds build_likes_matrix() using pre-aggregated account_engagement_agg.
New CLI flags: --likes, --likes-weight, --rt-weight.
Run identity now encodes signal mix + weights to prevent collisions.
Layer 1 persistence saves like features (feature_type='like').
Coverage: ~79% of NMF accounts have likes data.
"
```

---

### Task 4: NMF re-run + factor-aligned comparison script (O4)

**Files:**
- Create: `scripts/verify_likes_nmf.py`

**Context:** We run NMF at k=12,14,16 with likes signal and compare against the existing run `nmf-k14-20260225-a15a41` (signal='follow+rt'). Factor alignment uses H-matrix `feature_type:target` overlap. Comparison focuses on known accounts: @RomeoStevens76, @nickcammarata, @repligate, @visakanv, @dschorno, @QiaochuYuan.

- [ ] **Step 1: Write the comparison/verification script**

```python
# scripts/verify_likes_nmf.py
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
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"

KNOWN_ACCOUNTS = [
    "RomeoStevens76", "nickcammarata", "repligate", "visakanv",
    "dschorno", "QiaochuYuan", "adityaarpitha", "pee_zombie",
    "eshear", "xuenay",
]


def load_definitions(conn, run_id: str) -> dict[int, set[str]]:
    """Load H-matrix features per factor as {factor_idx: {type:target, ...}}."""
    rows = conn.execute(
        "SELECT community_idx, feature_type, target FROM community_definition WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    result: dict[int, set[str]] = defaultdict(set)
    for idx, ftype, target in rows:
        result[idx].add(f"{ftype}:{target}")
    return dict(result)


def load_memberships(conn, run_id: str) -> dict[str, dict[int, float]]:
    """Load W-matrix: {account_id: {factor_idx: weight}}."""
    rows = conn.execute(
        "SELECT account_id, community_idx, weight FROM community_membership WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    result: dict[str, dict[int, float]] = defaultdict(dict)
    for aid, cidx, w in rows:
        result[aid][cidx] = w
    return dict(result)


MATCH_THRESHOLD = 0.1  # Below this overlap, treat as unmatched (birth/death)


def align_factors(
    old_defs: dict[int, set[str]],
    new_defs: dict[int, set[str]],
) -> tuple[dict[int, int], dict[int, float]]:
    """Align new factors to old by feature_type:target overlap.

    Factors with overlap below MATCH_THRESHOLD are left unmatched,
    surfacing potential births (new unmatched) and deaths (old unmatched).

    Returns:
        mapping: {new_idx: old_idx} — only for matched factors
        quality: {new_idx: overlap_score} — for all new factors (0.0 if unmatched)
    """
    mapping = {}
    quality = {}
    used_old = set()

    # Score all pairs
    scores = []
    for new_idx, new_feats in new_defs.items():
        for old_idx, old_feats in old_defs.items():
            denom = max(len(new_feats), len(old_feats), 1)
            overlap = len(new_feats & old_feats) / denom
            scores.append((overlap, new_idx, old_idx))

    # Greedy best-match (highest overlap first), skip below threshold
    scores.sort(reverse=True)
    for overlap, new_idx, old_idx in scores:
        if new_idx in mapping or old_idx in used_old:
            continue
        if overlap < MATCH_THRESHOLD:
            break  # All remaining pairs are below threshold
        mapping[new_idx] = old_idx
        quality[new_idx] = overlap
        used_old.add(old_idx)

    # Unmatched new factors — these are potential births
    for new_idx in new_defs:
        if new_idx not in mapping:
            quality[new_idx] = 0.0

    return mapping, quality


def resolve_usernames(conn) -> dict[str, str]:
    """Map username → account_id for known accounts."""
    placeholders = ",".join("?" * len(KNOWN_ACCOUNTS))
    rows = conn.execute(
        f"SELECT account_id, username FROM profiles WHERE username IN ({placeholders})",
        KNOWN_ACCOUNTS,
    ).fetchall()
    return {uname: aid for aid, uname in rows}


def main():
    parser = argparse.ArgumentParser(description="Factor-aligned NMF run comparison")
    parser.add_argument("--old-run", required=True, help="Run ID of baseline (e.g., nmf-k14-20260225-a15a41)")
    parser.add_argument("--new-run", required=True, help="Run ID of new run, or 'auto' for latest follow+rt+like run matching old run's k")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db_path))

    # Resolve 'auto' to latest likes run matching old run's k
    new_run = args.new_run
    if new_run == "auto":
        old_k = conn.execute("SELECT k FROM community_run WHERE run_id = ?", (args.old_run,)).fetchone()
        if not old_k:
            print(f"✗ Old run {args.old_run} not found")
            sys.exit(1)
        row = conn.execute(
            "SELECT run_id FROM community_run WHERE signal LIKE '%like%' AND k = ? ORDER BY created_at DESC LIMIT 1",
            (old_k[0],),
        ).fetchone()
        if not row:
            print(f"✗ No likes-enriched run with k={old_k[0]} found. Run cluster_soft.py --likes --save first.")
            sys.exit(1)
        new_run = row[0]

    # Verify both runs exist
    for rid, label in [(args.old_run, "old"), (new_run, "new")]:
        row = conn.execute("SELECT k, signal, account_count FROM community_run WHERE run_id = ?", (rid,)).fetchone()
        if not row:
            print(f"✗ Run {rid} not found in community_run")
            sys.exit(1)
        print(f"{label}: {rid} (k={row[0]}, signal={row[1]}, accounts={row[2]})")

    print()

    # Load data
    old_defs = load_definitions(conn, args.old_run)
    new_defs = load_definitions(conn, new_run)
    old_memb = load_memberships(conn, args.old_run)
    new_memb = load_memberships(conn, new_run)

    # Align factors
    mapping, quality = align_factors(old_defs, new_defs)

    # Coverage metrics
    old_k = max(old_defs.keys()) + 1 if old_defs else 0
    new_k = max(new_defs.keys()) + 1 if new_defs else 0
    old_accounts = len(old_memb)
    new_accounts = len(new_memb)
    print(f"Old run: k={old_k}, {old_accounts} accounts with memberships")
    print(f"New run: k={new_k}, {new_accounts} accounts with memberships")

    # Factor alignment report
    print(f"\n{'=' * 72}")
    print("  FACTOR ALIGNMENT")
    print(f"{'=' * 72}")

    matched = {ni: oi for ni, oi in mapping.items() if quality.get(ni, 0) >= 0.3}
    weak = {ni: oi for ni, oi in mapping.items() if 0 < quality.get(ni, 0) < 0.3}
    unmatched_new = [ni for ni in new_defs if ni not in mapping]
    unmatched_old = [oi for oi in old_defs if oi not in set(mapping.values())]

    for new_idx in sorted(new_defs.keys()):
        q = quality.get(new_idx, 0)
        if new_idx in mapping:
            old_idx = mapping[new_idx]
            status = "✓ matched" if q >= 0.3 else "~ weak match"
            # Show top features for context
            old_top = sorted(old_defs.get(old_idx, set()))[:3]
            new_top = sorted(new_defs.get(new_idx, set()))[:3]
            print(f"  new[{new_idx:>2}] → old[{old_idx:>2}]  overlap={q:.2f}  {status}")
        else:
            print(f"  new[{new_idx:>2}] → ???         overlap=0.00  ★ NEW FACTOR")

    if unmatched_old:
        print(f"\n  Disappeared old factors: {unmatched_old}")

    print(f"\n  Matched (≥0.3): {len(matched)}")
    print(f"  Weak (<0.3):    {len(weak)}")
    print(f"  New factors:    {len(unmatched_new)}")
    print(f"  Disappeared:    {len(unmatched_old)}")

    # Known account comparison
    print(f"\n{'=' * 72}")
    print("  KNOWN ACCOUNT COMPARISON (aligned factors)")
    print(f"{'=' * 72}")

    username_to_aid = resolve_usernames(conn)

    for uname in KNOWN_ACCOUNTS:
        aid = username_to_aid.get(uname)
        if not aid:
            print(f"\n  @{uname}: not found in profiles")
            continue

        old_w = old_memb.get(aid, {})
        new_w = new_memb.get(aid, {})

        print(f"\n  @{uname}:")

        # Show aligned comparison
        all_factors = sorted(set(list(old_w.keys()) + [mapping.get(ni, -1) for ni in new_w.keys()]))
        for old_idx in sorted(old_defs.keys()):
            ow = old_w.get(old_idx, 0)
            # Find new_idx that maps to this old_idx
            new_idx = None
            for ni, oi in mapping.items():
                if oi == old_idx:
                    new_idx = ni
                    break
            nw = new_w.get(new_idx, 0) if new_idx is not None else 0
            delta = nw - ow
            if ow > 0.03 or nw > 0.03:
                arrow = "→" if abs(delta) < 0.03 else ("▲" if delta > 0 else "▼")
                print(f"    factor[{old_idx:>2}]: {ow:.2f} {arrow} {nw:.2f}  ({delta:+.2f})")

        # Show new factors not aligned to any old factor
        for new_idx in sorted(new_defs.keys()):
            if new_idx not in mapping:
                nw = new_w.get(new_idx, 0)
                if nw > 0.03:
                    print(f"    factor[★{new_idx}]: 0.00 → {nw:.2f}  (NEW)")

    # Summary metrics
    print(f"\n{'=' * 72}")
    print("  SUMMARY")
    print(f"{'=' * 72}")
    print(f"  Old run: {args.old_run}")
    print(f"  New run: {new_run}")
    print(f"  Factor alignment: {len(matched)}/{new_k} matched (≥0.3 overlap)")
    print(f"  New factors: {len(unmatched_new)}, Disappeared: {len(unmatched_old)}")
    print(f"  Account coverage: old={old_accounts}, new={new_accounts}")

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run NMF with likes at k=14 and save**

```bash
cd tpot-analyzer && .venv/bin/python3 -m scripts.cluster_soft --k 14 --likes --likes-weight 0.4 --save --notes "likes-experiment-k14-lw0.4"
```
Expected: "Building likes matrix... N targets, M/298 accounts with data", then "Saving run nmf-k14-follow+rt+like-lw0.4-..." success.

- [ ] **Step 3: Run NMF with likes at k=12 and k=16**

```bash
cd tpot-analyzer && .venv/bin/python3 -m scripts.cluster_soft --k 12 --likes --likes-weight 0.4 --save --notes "likes-experiment-k12-lw0.4"
cd tpot-analyzer && .venv/bin/python3 -m scripts.cluster_soft --k 16 --likes --likes-weight 0.4 --save --notes "likes-experiment-k16-lw0.4"
```
Expected: two more runs saved with distinct run_ids.

- [ ] **Step 4: Run factor-aligned comparison for k=14**

Note: `--new-run auto` now filters by k, matching the old run's k=14. It will select the latest likes-enriched k=14 run, not k=12 or k=16.

```bash
cd tpot-analyzer && .venv/bin/python3 -m scripts.verify_likes_nmf --old-run nmf-k14-20260225-a15a41 --new-run auto
```
Expected: factor alignment table, known account comparison showing deltas. Unmatched factors (overlap < 0.1) are flagged as potential births/deaths, not weak matches. Review output with user.

- [ ] **Step 5: Commit comparison script**

```bash
git add scripts/verify_likes_nmf.py
git commit -m "feat(nmf): factor-aligned NMF comparison script

Compares two Layer 1 runs with H-matrix feature_type:target alignment.
Shows factor matches/births/deaths and per-account weight deltas.
Designed for old (follow+rt) vs new (follow+rt+like) comparison.
"
```

- [ ] **Step 6: DECISION GATE — review with user**

Present the comparison output to the user. Key questions:
1. Do the likes-enriched communities look more meaningful?
2. Does "Emergence & Self-Transformation" still appear as a catch-all?
3. Did Romeo Stevens and Nick Cammarata separate better?
4. Are there new unmatched factors that look like real community births?
5. Which k (12, 14, 16) produces the best ontology?

**If likes helped:** proceed to Tier B (ontology review).
**If likes didn't help:** try higher weights (0.6, 0.8) or consider ontology-first approach.

---

## Post-Plan Verification Checklist

After all tasks complete, verify:

```bash
# All tests pass
.venv/bin/python3 -m pytest tests/test_rollup_bits.py tests/test_cluster_soft_likes.py -v

# Bits rollup matches existing state
.venv/bin/python3 -m scripts.verify_bits_rollup

# Multiple NMF runs coexist in community_run
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('data/archive_tweets.db')
for r in conn.execute('SELECT run_id, k, signal, notes FROM community_run ORDER BY created_at').fetchall():
    print(f'  {r[0]}: k={r[1]} signal={r[2]} notes={r[3]}')
conn.close()
"

# Factor-aligned comparison works
.venv/bin/python3 -m scripts.verify_likes_nmf --old-run nmf-k14-20260225-a15a41 --new-run auto
```
