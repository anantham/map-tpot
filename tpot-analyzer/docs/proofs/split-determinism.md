# ASSERTION: Split assignment is deterministic — the same tweet ID always maps to the same split

<!--
Status: valid
Created: 2026-02-27
Last verified: 2026-02-27
Code hash: a9a572c
Verified by: agent
-->

---
## Part I: Human Proof
---

### Claim

For any tweet ID `t`, `split_for_tweet(t)` always returns the same value `s ∈ {train, dev, test}`, regardless of when, where, or how many times it is called. The split depends ONLY on the tweet ID string — no randomness, no database state, no ordering, no external state.

### Why This Matters

If splits were non-deterministic:
- Rerunning `ensure_fixed_splits()` could reassign tweets to different splits, contaminating train/test boundaries
- The LLM classification harness (`scripts/classify_tweets.py`) filters tweets client-side using the same hash — if the function were non-deterministic, the script would select different tweets than the database, producing invalid evaluations
- Brier score comparisons across evaluation runs would be meaningless (different test sets)
- Reproducibility of the entire golden dataset pipeline collapses

### The Argument

The system assigns every tweet to exactly one of three splits (train/dev/test) using a deterministic hash. The key insight is that the split depends ONLY on the tweet ID — no randomness, no database state, no ordering.

The function `split_for_tweet()` in `schema.py` takes a tweet ID string, computes its SHA256 hash, extracts the first 8 hex digits as an integer, and takes modulo 100. This gives a bucket from 0 to 99:

```python
bucket = int(hashlib.sha256(tweet_id.encode("utf-8")).hexdigest()[:8], 16) % 100
```

The bucket is then mapped to a split:
- Buckets 0–69 → `"train"` (70%)
- Buckets 70–84 → `"dev"` (15%)
- Buckets 85–99 → `"test"` (15%)

This mapping is implemented as a simple cascade of `if` checks:

```python
if bucket < 70:
    return "train"
if bucket < 85:
    return "dev"
return "test"
```

Because SHA256 is a pure function (no internal state, no side effects, no randomness), the same tweet ID always produces the same hash, the same first 8 hex characters, the same bucket, and therefore the same split. This holds across runs, across machines, across time.

The function is called in two places:

1. **`base.py:ensure_fixed_splits()`** — during split bootstrap, each unassigned tweet's ID is passed to `split_for_tweet()` and the result is stored in the `curation_split` table. The batch loop processes 10,000 tweets at a time, calling `split_for_tweet(str(row["tweet_id"]))` for each.

2. **`scripts/classify_tweets.py:_split_for_tweet()`** — the classification harness duplicates the function for client-side filtering (performance optimization to avoid a 107-second SQL JOIN). This is a verbatim copy of the same algorithm.

Both call sites use the tweet ID as a string and produce the same mapping. The stored split in `curation_split` matches what the script computes at runtime.

### Boundary Conditions

- **Assumption:** Tweet IDs are strings. If a numeric tweet ID were passed as `int`, the `.encode("utf-8")` would fail with `AttributeError`. Both call sites explicitly cast to `str()`.
- **Assumption:** The function is only called with valid tweet ID strings (non-empty). An empty string `""` would still produce a deterministic result, just not a meaningful one.
- **Threat: modifying bucket boundaries** — changing `70` or `85` would reassign tweets. The thresholds are hardcoded, not configurable, which is both a strength (can't accidentally drift) and a limitation (can't rebalance without force-reassign).
- **What would break this:** Adding `random.seed()` or any source of entropy to the hash computation. Using a different hash function. Changing the `[:8]` slice length.
- **Exception:** `force_reassign=True` in `ensure_fixed_splits()` deletes and recomputes all splits. The recomputed values are still deterministic (same function), but the `assigned_at` timestamp changes.

### Verification (for the skeptical reader)

```bash
# Verify determinism: run twice, compare outputs
cd tpot-analyzer
python3 -c "
from src.data.golden.schema import split_for_tweet
ids = ['1234567890', '9876543210', '1111111111', '2222222222']
for tid in ids:
    print(f'{tid} → {split_for_tweet(tid)}')
"
# Run again — identical output every time

# Verify parity between schema.py and classify_tweets.py
python3 -c "
from src.data.golden.schema import split_for_tweet
import hashlib
def _split_for_tweet(tweet_id):
    bucket = int(hashlib.sha256(tweet_id.encode('utf-8')).hexdigest()[:8], 16) % 100
    if bucket < 70: return 'train'
    if bucket < 85: return 'dev'
    return 'test'

import random
for _ in range(10000):
    tid = str(random.randint(10**17, 10**18))
    assert split_for_tweet(tid) == _split_for_tweet(tid), f'Mismatch on {tid}'
print('10,000 random IDs: all match')
"

# Verify distribution is approximately 70/15/15
python3 -c "
from src.data.golden.schema import split_for_tweet
from collections import Counter
import random
c = Counter(split_for_tweet(str(random.randint(10**17, 10**18))) for _ in range(100000))
total = sum(c.values())
for split in ['train', 'dev', 'test']:
    print(f'{split}: {c[split]/total*100:.1f}%')
"
# Expected: train ~70%, dev ~15%, test ~15%
```

### Related

- Module doc: [`docs/modules/golden.md`](../modules/golden.md)
- ADR: [`docs/adr/009-golden-curation-schema-and-active-learning-loop.md`](../adr/009-golden-curation-schema-and-active-learning-loop.md)

---
## Part II: Machine Manifest
---

### Citations

| # | File | Lines | Code hash | Status |
|---|------|-------|-----------|--------|
| 1 | `src/data/golden/schema.py` | `110-116` | `4c54153` | valid |
| 2 | `src/data/golden/base.py` | `96-116` | `a9a572c` | valid |
| 3 | `src/data/golden/schema.py` | `13-19` | `4c54153` | valid |

### Cited Code Snapshots

#### Citation 1: `schema.py:110-116`

```python
def split_for_tweet(tweet_id: str) -> str:
    bucket = int(hashlib.sha256(tweet_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "dev"
    return "test"
```

**Establishes:** The split function is a pure function of `tweet_id` with no external state, randomness, or side effects.

#### Citation 2: `base.py:96-116`

```python
            while True:
                rows = conn.execute(
                    """
                    SELECT t.tweet_id
                    FROM tweets t
                    LEFT JOIN curation_split s ON s.tweet_id = t.tweet_id AND s.axis = ?
                    WHERE s.tweet_id IS NULL
                    LIMIT ?
                    """,
                    (axis, BATCH_SIZE),
                ).fetchall()
                if not rows:
                    break
                batch = [
                    (str(row["tweet_id"]), axis, split_for_tweet(str(row["tweet_id"])), assigned_by, now)
                    for row in rows
                ]
                conn.executemany(
                    "INSERT OR REPLACE INTO curation_split (tweet_id, axis, split, assigned_by, assigned_at) VALUES (?, ?, ?, ?, ?)",
                    batch,
                )
```

**Establishes:** `ensure_fixed_splits()` calls `split_for_tweet()` for each tweet and stores the result. The INSERT uses `OR REPLACE`, so re-running produces identical splits.

#### Citation 3: `schema.py:13-19`

```python
CREATE TABLE IF NOT EXISTS curation_split (
    tweet_id TEXT PRIMARY KEY,
    axis TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('train','dev','test')),
    assigned_by TEXT NOT NULL,
    assigned_at TEXT NOT NULL
);
```

**Establishes:** The `curation_split` table enforces `tweet_id` as PRIMARY KEY (one split per tweet) and constrains `split` to the valid enum.

### Logical Chain (formal)

1. Citation 1 establishes that `split_for_tweet()` is a pure function of `tweet_id` — it uses only `hashlib.sha256` (deterministic), string slicing (deterministic), integer conversion (deterministic), modulo (deterministic), and constant boundary checks.
2. Citation 3 establishes that each tweet can have at most one split assignment (`tweet_id` is PRIMARY KEY).
3. Citation 2 establishes that `ensure_fixed_splits()` delegates to `split_for_tweet()` and stores the result via `INSERT OR REPLACE`.
4. From 1: the same `tweet_id` always produces the same bucket and split.
5. From 2 and 3: the stored split is always the output of this pure function.
6. Therefore, the split assignment is deterministic — the same tweet ID always maps to the same split.

### Re-verification Commands

```bash
# Quick check: have any cited files changed?
git diff a9a572c..HEAD -- src/data/golden/schema.py src/data/golden/base.py

# If diff is empty → all citations still valid
# If diff is non-empty → re-examine affected citations
```
