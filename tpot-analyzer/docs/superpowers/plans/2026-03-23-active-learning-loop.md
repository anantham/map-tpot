# Active Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an iterative pipeline that selects high-uncertainty accounts, fetches their tweets via API, labels them with a 3-model LLM ensemble, rolls up community evidence, inserts them as propagation seeds, and measures improvement — all within a $5 API budget.

**Architecture:** Three-round loop (scout → deepen → measure) orchestrated by `scripts/active_learning.py`. Twitter API fetch → enriched_tweets table → per-tweet LLM labeling via OpenRouter (Grok + DeepSeek + Gemini) → consensus bits → rollup with informativeness discount → seed insertion into community_account → re-propagation → holdout recall measurement.

**Tech Stack:** Python 3.9, httpx (Twitter API + OpenRouter), SQLite (archive_tweets.db), scikit-learn (TF-IDF), existing propagation/rollup/export pipeline.

**Spec:** `docs/superpowers/specs/2026-03-23-active-learning-loop-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/active_learning.py` | Main orchestrator — round loop, budget tracking, stopping conditions, human review output |
| `scripts/fetch_tweets_for_account.py` | Twitter API: last_tweets, advanced_search, user_info. Writes to `enriched_tweets` + `enrichment_log` |
| `scripts/label_tweets_ensemble.py` | 3-model ensemble labeling. Prompt assembly, OpenRouter calls, consensus merge, writes to tweet_tags + tweet_label_set + tweet_label_prob |
| `scripts/rollup_bits.py` | **Modify** — UNION enriched_tweets, scoped DELETE, informativeness discount for enriched accounts |
| `tests/test_fetch_tweets.py` | Unit tests for fetch module (API response parsing, dedup, holdout guard) |
| `tests/test_label_ensemble.py` | Unit tests for labeling (prompt assembly, JSON parsing, consensus, assertions) |
| `tests/test_rollup_bits_enriched.py` | Tests for modified rollup (UNION query, scoped delete, discount) |
| `tests/test_active_learning.py` | Integration tests for orchestrator (round flow, budget stop, seed insertion) |

---

### Task 1: Schema — enriched_tweets + enrichment_log tables

**Files:**
- Create: `scripts/active_learning_schema.py`
- Test: `tests/test_active_learning_schema.py`

- [ ] **Step 1: Write failing test for table creation**

```python
# tests/test_active_learning_schema.py
import sqlite3
import pytest
from scripts.active_learning_schema import create_tables

def test_creates_enriched_tweets_table(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    # Table exists
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "enriched_tweets" in tables
    assert "enrichment_log" in tables
    # Columns correct
    cols = [r[1] for r in conn.execute("PRAGMA table_info(enriched_tweets)")]
    assert "tweet_id" in cols
    assert "account_id" in cols
    assert "fetch_source" in cols
    assert "fetch_query" in cols
    conn.close()

def test_creates_indexes(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    indexes = [r[1] for r in conn.execute("PRAGMA index_list(enriched_tweets)")]
    assert "idx_enriched_tweets_account" in indexes
    conn.close()

def test_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    create_tables(conn)  # second call should not fail
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_active_learning_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.active_learning_schema'`

- [ ] **Step 3: Implement schema module**

```python
# scripts/active_learning_schema.py
"""Schema definitions for active learning pipeline tables."""
import sqlite3

ENRICHED_TWEETS_DDL = """\
CREATE TABLE IF NOT EXISTS enriched_tweets (
    tweet_id      TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL,
    username      TEXT NOT NULL,
    text          TEXT NOT NULL,
    like_count    INTEGER DEFAULT 0,
    retweet_count INTEGER DEFAULT 0,
    reply_count   INTEGER DEFAULT 0,
    view_count    INTEGER DEFAULT 0,
    created_at    TEXT,
    lang          TEXT,
    is_reply      INTEGER DEFAULT 0,
    in_reply_to_user TEXT,
    has_media     INTEGER DEFAULT 0,
    mentions_json TEXT,
    fetch_source  TEXT NOT NULL,
    fetch_query   TEXT,
    fetched_at    TEXT NOT NULL
);
"""

ENRICHED_TWEETS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_enriched_tweets_account ON enriched_tweets(account_id);",
    "CREATE INDEX IF NOT EXISTS idx_enriched_tweets_source ON enriched_tweets(fetch_source);",
]

ENRICHMENT_LOG_DDL = """\
CREATE TABLE IF NOT EXISTS enrichment_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     TEXT NOT NULL,
    username       TEXT NOT NULL,
    round          INTEGER NOT NULL,
    action         TEXT NOT NULL,
    query          TEXT,
    api_calls      INTEGER DEFAULT 1,
    tweets_fetched INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0.05,
    created_at     TEXT NOT NULL
);
"""

def create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(ENRICHED_TWEETS_DDL)
    for idx in ENRICHED_TWEETS_INDEXES:
        conn.execute(idx)
    conn.execute(ENRICHMENT_LOG_DDL)
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_active_learning_schema.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/active_learning_schema.py tests/test_active_learning_schema.py
git commit -m "feat(active-learning): schema for enriched_tweets + enrichment_log"
```

---

### Task 2: Tweet fetcher — Twitter API integration

**Files:**
- Create: `scripts/fetch_tweets_for_account.py`
- Test: `tests/test_fetch_tweets.py`
- Reference: `scripts/fetch_following_for_frontier.py` (existing API pattern), `docs/TWITTERAPI_ENDPOINTS.md`

- [ ] **Step 1: Write failing tests for fetch module**

```python
# tests/test_fetch_tweets.py
import sqlite3
import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.fetch_tweets_for_account import (
    fetch_last_tweets, fetch_advanced_search, store_tweets,
    parse_tweet, check_budget, log_api_call,
)
from scripts.active_learning_schema import create_tables

@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    create_tables(conn)
    return conn

SAMPLE_TWEET = {
    "id": "123456", "text": "test tweet", "likeCount": 10,
    "retweetCount": 2, "replyCount": 1, "viewCount": 500,
    "createdAt": "Mon Mar 20 09:00:00 +0000 2024", "lang": "en",
    "isReply": False, "inReplyToUsername": None,
    "author": {"id": "789", "userName": "testuser", "description": "bio"},
    "entities": {"user_mentions": [{"screen_name": "other"}], "urls": []},
}

def test_parse_tweet():
    result = parse_tweet(SAMPLE_TWEET, "testuser")
    assert result["tweet_id"] == "123456"
    assert result["account_id"] == "789"
    assert result["like_count"] == 10
    assert result["mentions_json"] == '["other"]'

def test_store_tweets_inserts(db):
    parsed = parse_tweet(SAMPLE_TWEET, "testuser")
    count = store_tweets(db, [parsed], fetch_source="last_tweets")
    assert count == 1
    row = db.execute("SELECT * FROM enriched_tweets WHERE tweet_id='123456'").fetchone()
    assert row is not None

def test_store_tweets_dedup(db):
    parsed = parse_tweet(SAMPLE_TWEET, "testuser")
    store_tweets(db, [parsed], fetch_source="last_tweets")
    count = store_tweets(db, [parsed], fetch_source="last_tweets")
    assert count == 0  # duplicate, not inserted

def test_check_budget_under(db):
    assert check_budget(db, limit=5.0) is True

def test_check_budget_over(db):
    db.execute(
        "INSERT INTO enrichment_log (account_id, username, round, action, estimated_cost, created_at) "
        "VALUES ('x','x',1,'test',5.01,'')"
    )
    db.commit()
    assert check_budget(db, limit=5.0) is False

def test_log_api_call(db):
    log_api_call(db, account_id="789", username="test", round_num=1,
                 action="last_tweets", tweets_fetched=20)
    row = db.execute("SELECT * FROM enrichment_log").fetchone()
    assert row is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_fetch_tweets.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement fetch module**

Reference `scripts/fetch_following_for_frontier.py` for API key resolution and httpx patterns. Key functions:
- `get_api_key()` — resolve `TWITTERAPI_IO_API_KEY` from env
- `fetch_last_tweets(api_key, username)` → list of raw tweet dicts
- `fetch_advanced_search(api_key, query)` → list of raw tweet dicts
- `fetch_user_info(api_key, username)` → author dict with bio
- `parse_tweet(raw_tweet, username)` → dict matching enriched_tweets columns
- `store_tweets(conn, parsed_tweets, fetch_source, fetch_query=None)` → int count inserted
- `check_budget(conn, limit=5.0)` → bool
- `log_api_call(conn, account_id, username, round_num, action, tweets_fetched, query=None)` → None

Use `INSERT OR IGNORE` for dedup on tweet_id PK. Rate limit with `time.sleep(0.5)` between calls.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_fetch_tweets.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_tweets_for_account.py tests/test_fetch_tweets.py
git commit -m "feat(active-learning): tweet fetcher with budget tracking + dedup"
```

---

### Task 3: LLM ensemble labeler

**Files:**
- Create: `scripts/label_tweets_ensemble.py`
- Test: `tests/test_label_ensemble.py`
- Reference: `scripts/classify_tweets.py:129-154` (existing OpenRouter pattern), `docs/LABELING_MODEL_SPEC.md`

- [ ] **Step 1: Write failing tests for label parsing + validation**

```python
# tests/test_label_ensemble.py
import pytest
from scripts.label_tweets_ensemble import (
    parse_label_json, validate_bits, build_consensus,
    VALID_SHORT_NAMES, build_prompt,
)

def test_parse_valid_json():
    raw = '{"bits": ["bits:highbies:+3"], "themes": ["theme:absurdist-humor"], "domains": ["domain:social"], "postures": ["posture:playful-exploration"], "simulacrum": {"l1": 0.4, "l2": 0.1, "l3": 0.3, "l4": 0.2}, "note": "test", "signal_strength": "high", "new_community_signals": []}'
    result = parse_label_json(raw)
    assert result is not None
    assert result["bits"] == ["bits:highbies:+3"]

def test_parse_json_with_markdown_fences():
    raw = '```json\n{"bits": ["bits:Core-TPOT:+2"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium", "new_community_signals": []}\n```'
    result = parse_label_json(raw)
    assert result is not None

def test_parse_invalid_json():
    assert parse_label_json("not json at all") is None

def test_validate_bits_valid():
    bits = ["bits:highbies:+3", "bits:Core-TPOT:+1"]
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert errors == []

def test_validate_bits_bad_format():
    bits = ["highbies:+3"]  # missing bits: prefix
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert len(errors) > 0

def test_validate_bits_bad_community():
    bits = ["bits:Feline-Poetics:+2"]  # not in DB
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert len(errors) > 0

def test_validate_bits_non_integer():
    bits = ["bits:highbies:+2.5"]  # fractional not allowed
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert len(errors) > 0

def test_consensus_median():
    """Three models agree on community, take median."""
    labels = [
        {"bits": ["bits:highbies:+2"]},
        {"bits": ["bits:highbies:+3"]},
        {"bits": ["bits:highbies:+4"]},
    ]
    result = build_consensus(labels)
    assert "bits:highbies:+3" in result["bits"]

def test_consensus_2_of_3():
    """2/3 agree, take lower value."""
    labels = [
        {"bits": ["bits:highbies:+3"]},
        {"bits": ["bits:highbies:+2"]},
        {"bits": []},  # model 3 didn't assign
    ]
    result = build_consensus(labels)
    assert "bits:highbies:+2" in result["bits"]

def test_consensus_1_of_3_discarded():
    """Only 1/3 assigned, discard."""
    labels = [
        {"bits": ["bits:highbies:+3"]},
        {"bits": []},
        {"bits": []},
    ]
    result = build_consensus(labels)
    assert result["bits"] == []

def test_build_prompt_has_communities():
    prompt = build_prompt(
        username="test", bio="a bio", graph_signal="Core TPOT: 10",
        other_tweets="tweet1; tweet2",
        tweet_text="hello world", engagement="5 likes",
        mentions="none", engagement_context="none",
        community_descriptions={"Core-TPOT": "Big tent"},
        community_short_names=["Core-TPOT"],
    )
    assert "Core-TPOT" in prompt
    assert "hello world" in prompt
    assert "bits" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_label_ensemble.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement label ensemble module**

Key functions:
- `VALID_SHORT_NAMES` — loaded from DB at startup via `SELECT short_name FROM community`
- `MODELS = ["x-ai/grok-4.1-fast", "deepseek/deepseek-v3.2", "google/gemini-3.1-flash-lite-preview"]`
- `build_prompt(username, bio, graph_signal, other_tweets, tweet_text, engagement, mentions, engagement_context, community_descriptions, community_short_names)` → str
- `call_model(api_key, model, system_prompt, user_prompt)` → raw string (reuse pattern from `classify_tweets.py:129-154`)
- `parse_label_json(raw)` → dict or None (strip markdown fences, extract JSON via regex)
- `validate_bits(bits_list, valid_names)` → list of error strings
- `validate_simulacrum(sim_dict)` → list of error strings
- `build_consensus(label_dicts)` → merged dict with median bits
- `label_tweet(conn, tweet_id, tweet_text, account_context, system_prompt, api_key)` → consensus dict (calls all 3 models, stores per-model + consensus in tweet_label_set)
- `store_labels(conn, tweet_id, label_dict, reviewer)` → None (writes to tweet_tags, tweet_label_set, tweet_label_prob)

System prompt: use the validated prompt from the spec experiments (community descriptions, bits scale, tag format, MUST assign at least 2 bits).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_label_ensemble.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/label_tweets_ensemble.py tests/test_label_ensemble.py
git commit -m "feat(active-learning): 3-model LLM ensemble labeler with consensus"
```

---

### Task 4: Modify rollup_bits.py — UNION enriched_tweets + scoped DELETE + discount

**Files:**
- Modify: `scripts/rollup_bits.py` (lines 230-243 load query, line 297 DELETE)
- Test: `tests/test_rollup_bits_enriched.py`

- [ ] **Step 1: Write failing tests for enriched tweet integration**

```python
# tests/test_rollup_bits_enriched.py
import sqlite3
import pytest
from scripts.active_learning_schema import create_tables

def _setup_db(tmp_path):
    """Create a test DB with both tweets and enriched_tweets tables."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    # Create archive tweets table
    conn.execute("""CREATE TABLE tweets (
        tweet_id TEXT PRIMARY KEY, account_id TEXT, username TEXT,
        full_text TEXT, created_at TEXT, reply_to_tweet_id TEXT,
        reply_to_username TEXT, favorite_count INTEGER DEFAULT 0,
        retweet_count INTEGER DEFAULT 0, lang TEXT,
        is_note_tweet INTEGER DEFAULT 0, fetched_at TEXT
    )""")
    # Create community table
    conn.execute("""CREATE TABLE community (
        id TEXT PRIMARY KEY, name TEXT, short_name TEXT, description TEXT
    )""")
    conn.execute("INSERT INTO community VALUES ('c1','Test Community','Test-Comm','')")
    # Create tweet_tags table
    conn.execute("""CREATE TABLE tweet_tags (
        tweet_id TEXT, tag TEXT, category TEXT,
        added_by TEXT DEFAULT 'human', created_at TEXT,
        PRIMARY KEY (tweet_id, tag)
    )""")
    # Create account_community_bits table
    conn.execute("""CREATE TABLE account_community_bits (
        account_id TEXT, community_id TEXT, total_bits INTEGER,
        tweet_count INTEGER, pct REAL, updated_at TEXT,
        PRIMARY KEY (account_id, community_id)
    )""")
    create_tables(conn)  # adds enriched_tweets + enrichment_log
    conn.commit()
    return conn

def test_rollup_includes_enriched_tweets(tmp_path):
    from scripts.rollup_bits import load_bits_tags
    conn = _setup_db(tmp_path)
    # Archive tweet
    conn.execute("INSERT INTO tweets VALUES ('t1','acc1','u1','text','','',''  ,0,0,'en',0,'')")
    conn.execute("INSERT INTO tweet_tags VALUES ('t1','bits:Test-Comm:+2','bits','human','')")
    # Enriched tweet (different account)
    conn.execute("INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) VALUES ('t2','acc2','u2','text','last_tweets','')")
    conn.execute("INSERT INTO tweet_tags VALUES ('t2','bits:Test-Comm:+3','bits','llm_ensemble_consensus','')")
    conn.commit()
    rows = load_bits_tags(conn)
    account_ids = {r[0] for r in rows}
    assert "acc1" in account_ids  # archive
    assert "acc2" in account_ids  # enriched

def test_scoped_delete_preserves_other_accounts(tmp_path):
    from scripts.rollup_bits import scoped_delete_bits
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('keep','c1',5,2,100.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('delete','c1',3,1,100.0,'')")
    conn.commit()
    scoped_delete_bits(conn, account_ids=["delete"])
    remaining = conn.execute("SELECT account_id FROM account_community_bits").fetchall()
    assert [r[0] for r in remaining] == ["keep"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_rollup_bits_enriched.py -v`
Expected: FAIL — `load_bits_tags` doesn't include enriched_tweets, `scoped_delete_bits` doesn't exist

- [ ] **Step 3: Modify rollup_bits.py**

Changes:
1. `load_bits_tags()` — add UNION ALL with enriched_tweets join
2. New function `scoped_delete_bits(conn, account_ids)` — DELETE WHERE account_id IN (?)
3. Modify main rollup flow to use scoped delete instead of global DELETE
4. Add `compute_discount(account_id, conn)` — returns `min(1.0, sqrt(N/50))` for enriched accounts, 1.0 for archive accounts
5. Apply discount to `total_bits` before writing to `account_community_bits`

- [ ] **Step 4: Run ALL rollup tests (existing + new)**

Run: `.venv/bin/python3 -m pytest tests/test_rollup_bits_enriched.py tests/test_rollup_bits.py -v` (if test_rollup_bits.py exists)
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add scripts/rollup_bits.py tests/test_rollup_bits_enriched.py
git commit -m "fix(rollup): UNION enriched_tweets, scoped DELETE, informativeness discount"
```

---

### Task 5: Seed insertion module

**Files:**
- Create: `scripts/insert_seeds.py`
- Test: `tests/test_insert_seeds.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_insert_seeds.py
import sqlite3
import pytest
from scripts.insert_seeds import insert_llm_seeds

def _setup_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("""CREATE TABLE community_account (
        community_id TEXT, account_id TEXT, weight REAL,
        source TEXT, updated_at TEXT,
        PRIMARY KEY (community_id, account_id)
    )""")
    conn.execute("""CREATE TABLE account_community_bits (
        account_id TEXT, community_id TEXT, total_bits INTEGER,
        tweet_count INTEGER, pct REAL, updated_at TEXT,
        PRIMARY KEY (account_id, community_id)
    )""")
    conn.commit()
    return conn

def test_inserts_new_seeds(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,80.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c2',3,2,20.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 2
    rows = conn.execute(
        "SELECT community_id, weight, source FROM community_account WHERE account_id='acc1' ORDER BY weight DESC"
    ).fetchall()
    assert rows[0][2] == "llm_ensemble"
    assert abs(rows[0][1] - 0.8) < 0.01  # pct/100

def test_does_not_overwrite_nmf_seeds(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO community_account VALUES ('c1','acc1',0.9,'nmf','')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,100.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 0  # skipped — already nmf seed
    row = conn.execute("SELECT source FROM community_account WHERE account_id='acc1'").fetchone()
    assert row[0] == "nmf"  # unchanged

def test_weight_in_valid_range(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',5,3,50.0,'')")
    conn.commit()
    insert_llm_seeds(conn, account_ids=["acc1"])
    weight = conn.execute("SELECT weight FROM community_account WHERE account_id='acc1'").fetchone()[0]
    assert 0.0 <= weight <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_insert_seeds.py -v`
Expected: FAIL

- [ ] **Step 3: Implement seed insertion**

```python
# scripts/insert_seeds.py
"""Insert LLM-labeled accounts as propagation seeds."""
import sqlite3
from datetime import datetime, timezone

def insert_llm_seeds(conn: sqlite3.Connection, account_ids: list[str]) -> int:
    """Insert rollup results into community_account for propagation.

    Skips accounts already present with source='nmf' (don't overwrite human seeds).
    Returns count of rows inserted.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for account_id in account_ids:
        # Check if already an NMF seed
        existing = conn.execute(
            "SELECT source FROM community_account WHERE account_id = ? AND source = 'nmf' LIMIT 1",
            (account_id,)
        ).fetchone()
        if existing:
            continue  # don't overwrite NMF seeds

        # Load bits rollup for this account
        bits_rows = conn.execute(
            "SELECT community_id, pct FROM account_community_bits WHERE account_id = ? AND pct > 5.0",
            (account_id,)
        ).fetchall()

        for community_id, pct in bits_rows:
            weight = pct / 100.0
            assert 0.0 <= weight <= 1.0, f"Invalid weight {weight} for {account_id}/{community_id}"
            conn.execute(
                "INSERT OR REPLACE INTO community_account "
                "(community_id, account_id, weight, source, updated_at) "
                "VALUES (?, ?, ?, 'llm_ensemble', ?)",
                (community_id, account_id, weight, now),
            )
            inserted += 1

    conn.commit()
    return inserted
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_insert_seeds.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/insert_seeds.py tests/test_insert_seeds.py
git commit -m "feat(active-learning): seed insertion from LLM rollup → community_account"
```

---

### Task 6: Main orchestrator

**Files:**
- Create: `scripts/active_learning.py`
- Test: `tests/test_active_learning.py`
- Reference: `scripts/rank_frontier.py` (account selection), `scripts/propagate_community_labels.py` (re-propagation)

- [ ] **Step 1: Write failing tests for orchestrator logic**

```python
# tests/test_active_learning.py
import sqlite3
import pytest
from scripts.active_learning import (
    select_accounts, triage_results, compute_metrics,
)

def test_select_accounts_excludes_holdout(tmp_path):
    # Setup with frontier_ranking + holdout tables
    # Verify holdout accounts are excluded
    pass  # full implementation in step 3

def test_select_accounts_respects_enriched_dedup(tmp_path):
    # Account with >=20 enriched_tweets should be skipped
    pass

def test_triage_high_confidence():
    bits = {"highbies": 60.0, "Core-TPOT": 25.0, "LLM-Whisperers": 15.0}
    result = triage_results(bits)
    assert result == "high"  # top >60%

def test_triage_ambiguous():
    bits = {"highbies": 30.0, "Core-TPOT": 25.0, "LLM-Whisperers": 25.0, "Qualia-Research": 20.0}
    result = triage_results(bits)
    assert result == "ambiguous"  # no community >40%

def test_triage_no_signal():
    bits = {}
    result = triage_results(bits)
    assert result == "no_signal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_active_learning.py -v`

- [ ] **Step 3: Implement orchestrator**

The orchestrator ties everything together with a CLI interface:

```
.venv/bin/python3 -m scripts.active_learning --round 1 --top 50 --budget 5.0
.venv/bin/python3 -m scripts.active_learning --round 2 --budget 5.0
.venv/bin/python3 -m scripts.active_learning --measure
```

Key functions:
- `select_accounts(conn, top_n, round_num)` — query frontier_ranking, exclude holdout + enriched
- `run_round_1(conn, api_key, openrouter_key, accounts, budget)` — fetch → label → triage
- `run_round_2(conn, api_key, openrouter_key, ambiguous_accounts, budget)` — strategic search → re-label
- `run_measure(conn)` — rollup → seed insert → re-propagate → compute metrics
- `triage_results(bits_dict)` → "high" | "ambiguous" | "no_signal"
- `compute_metrics(conn)` → dict with recall, uncertainty, abstain_rate
- `print_report(metrics, budget_spent)` — human-readable summary

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_active_learning.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add scripts/active_learning.py tests/test_active_learning.py
git commit -m "feat(active-learning): main orchestrator with round management + triage"
```

---

### Task 7: End-to-end dry run on 3 accounts

**Files:**
- No new files — integration test using real DB

- [ ] **Step 1: Run Round 1 in dry-run mode on 3 accounts**

```bash
.venv/bin/python3 -m scripts.active_learning --round 1 --top 3 --dry-run
```

Verify: prints selected accounts, shows what would be fetched, no API calls made, budget = $0.

- [ ] **Step 2: Run Round 1 on 3 real accounts**

```bash
.venv/bin/python3 -m scripts.active_learning --round 1 --top 3 --budget 1.0
```

Verify:
- 3 accounts fetched (tweets in enriched_tweets)
- Tweets labeled by 3 models (entries in tweet_tags, tweet_label_set)
- Triage output printed (high/ambiguous/no_signal per account)
- Budget tracking in enrichment_log

- [ ] **Step 3: Run measure step**

```bash
.venv/bin/python3 -m scripts.active_learning --measure
```

Verify:
- Rollup computed for new accounts
- Seeds inserted into community_account with source='llm_ensemble'
- Propagation runs successfully
- Metrics printed (recall, uncertainty, abstain rate)

- [ ] **Step 4: Spot-check labels manually**

Review the labeled tweets:
```sql
SELECT tt.tweet_id, et.text, tt.tag, tt.added_by
FROM tweet_tags tt
JOIN enriched_tweets et ON tt.tweet_id = et.tweet_id
WHERE tt.category = 'bits'
ORDER BY et.account_id, tt.tweet_id;
```

Do the bits assignments make sense? Flag any issues.

- [ ] **Step 5: Commit results + any fixes**

```bash
git add -A
git commit -m "feat(active-learning): validated end-to-end on 3 accounts"
```

---

### Task 8: Full Round 1 (50 accounts)

**Files:**
- No new code — production run

- [ ] **Step 1: Run full Round 1**

```bash
.venv/bin/python3 -m scripts.active_learning --round 1 --top 50 --budget 2.50
```

- [ ] **Step 2: Review triage output**

How many high / ambiguous / no_signal? Expected: ~20 high, ~20 ambiguous, ~10 no_signal.

- [ ] **Step 3: Run measure**

```bash
.venv/bin/python3 -m scripts.active_learning --measure
```

Record baseline metrics before Round 2.

- [ ] **Step 4: Human review gate**

Spot-check 10-15 labeled tweets. Review any new-community signals. Decide whether to proceed to Round 2.

- [ ] **Step 5: Commit metrics snapshot**

```bash
git commit -m "data(active-learning): round 1 complete — N accounts classified, recall X%"
```

---

### Task 9: Round 2 (deepen ambiguous accounts)

Only proceed if human approved after Task 8.

- [ ] **Step 1: Run Round 2**

```bash
.venv/bin/python3 -m scripts.active_learning --round 2 --budget 5.0
```

Uses advanced_search for hypothesis-driven probes on ambiguous accounts.

- [ ] **Step 2: Run measure**

```bash
.venv/bin/python3 -m scripts.active_learning --measure
```

- [ ] **Step 3: Compare metrics to Round 1 baseline**

| Metric | Baseline | After R1 | After R2 |
|--------|----------|----------|----------|
| Holdout recall | 1.6% | ? | ? |
| Abstain rate | 94.8% | ? | ? |
| Mean uncertainty | 0.391 | ? | ? |

- [ ] **Step 4: Human review + decide**

Stop or continue with remaining budget?

- [ ] **Step 5: Re-export public site if results are good**

```bash
.venv/bin/python3 -m scripts.classify_bands
.venv/bin/python3 -m scripts.export_public_site
cd public-site && vercel --prod
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat(active-learning): round 2 complete — final metrics"
```
