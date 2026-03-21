# Community Detail Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clickable community detail pages to the Find My Ingroup public site, showcasing each community's spirit through prototypical member spotlights and their tweets.

**Architecture:** Enrich the static `data.json` export with per-community featured members (top 5 by NMF weight) and their tweets (top 5 by engagement). Frontend detects `?community=slug` query param and renders a new `CommunityPage` component. Slugs are persisted in a registry file to survive community renames.

**Tech Stack:** Python 3 (export pipeline, SQLite, NumPy, Pandas), React 19 + Vite 8 (frontend), Vitest (frontend tests), pytest (backend tests)

**Spec:** `docs/superpowers/specs/2026-03-21-community-detail-pages-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `scripts/export_public_site.py` | Slug generation/persistence, featured members, tweet selection, enriched community export |
| Create | `public-site/public/slug_registry.json` | Persisted `{community_id: slug}` map |
| Create | `public-site/src/useRouting.js` | Extracted routing hook (3-way state, navigation) |
| Modify | `public-site/src/App.jsx` | Use routing hook, render community/result/home views, clickable showcase tags |
| Create | `public-site/src/CommunityPage.jsx` | Spotlight layout: hero, member cards, tweet cards, all-members grid, sibling nav |
| Create | `public-site/src/community-page.css` | Community page styles (separate from 1056-LOC styles.css) |
| Modify | `public-site/src/CommunityCard.jsx` | Community tags become `/?community=slug` links |
| Modify | `public-site/package.json` | Add vitest + testing-library devDependencies |
| Modify | `tests/test_export_public_site.py` | Tests for slug, tweet selection, enriched export |

---

## Task 1: Slug Generation and Persistence

**Files:**
- Modify: `scripts/export_public_site.py` (add functions after line 245)
- Create: `public-site/public/slug_registry.json`
- Modify: `tests/test_export_public_site.py` (add tests after line 665)

- [ ] **Step 1: Write failing tests for slugify_name**

Add to `tests/test_export_public_site.py`:

```python
class TestSlugGeneration:
    def test_simple_name(self):
        from scripts.export_public_site import slugify_name
        assert slugify_name("Builders") == "builders"

    def test_ampersand_removed(self):
        from scripts.export_public_site import slugify_name
        assert slugify_name("LLM Whisperers & ML Tinkerers") == "llm-whisperers-ml-tinkerers"

    def test_comma_and_ampersand(self):
        from scripts.export_public_site import slugify_name
        assert slugify_name("EA, AI Safety & Forecasting") == "ea-ai-safety-forecasting"

    def test_no_trailing_hyphens(self):
        from scripts.export_public_site import slugify_name
        assert slugify_name("  Builders & ") == "builders"

    def test_consecutive_special_chars_collapse(self):
        from scripts.export_public_site import slugify_name
        assert slugify_name("Queer TPOT & Identity Experimentalists") == "queer-tpot-identity-experimentalists"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSlugGeneration -v`
Expected: FAIL with `ImportError: cannot import name 'slugify_name'`

- [ ] **Step 3: Implement slugify_name**

Add to `scripts/export_public_site.py` after the `_safe_followers` function (after line 245):

```python
import re

def slugify_name(name):
    """Convert community name to URL-safe slug.

    Lowercase, remove '&', collapse non-alphanumeric runs to single hyphen,
    trim leading/trailing hyphens.
    """
    s = name.lower()
    s = s.replace("&", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSlugGeneration -v`
Expected: 5 PASSED

- [ ] **Step 5: Write failing tests for slug registry persistence**

Add to `tests/test_export_public_site.py`:

```python
class TestSlugRegistry:
    def test_load_empty_registry(self, tmp_path):
        from scripts.export_public_site import load_slug_registry
        path = tmp_path / "slug_registry.json"
        result = load_slug_registry(path)
        assert result == {}

    def test_load_existing_registry(self, tmp_path):
        from scripts.export_public_site import load_slug_registry
        path = tmp_path / "slug_registry.json"
        path.write_text('{"abc-123": "builders"}')
        result = load_slug_registry(path)
        assert result == {"abc-123": "builders"}

    def test_save_and_reload(self, tmp_path):
        from scripts.export_public_site import load_slug_registry, save_slug_registry
        path = tmp_path / "slug_registry.json"
        registry = {"abc-123": "builders", "def-456": "contemplative-practitioners"}
        save_slug_registry(path, registry)
        reloaded = load_slug_registry(path)
        assert reloaded == registry

    def test_assign_slugs_new_communities(self):
        from scripts.export_public_site import assign_slugs
        communities = [
            {"id": "abc", "name": "Builders"},
            {"id": "def", "name": "LLM Whisperers & ML Tinkerers"},
        ]
        registry = {}
        result = assign_slugs(communities, registry)
        assert result == {"abc": "builders", "def": "llm-whisperers-ml-tinkerers"}

    def test_assign_slugs_preserves_existing(self):
        from scripts.export_public_site import assign_slugs
        communities = [
            {"id": "abc", "name": "Renamed Community"},
        ]
        registry = {"abc": "original-slug"}
        result = assign_slugs(communities, registry)
        assert result == {"abc": "original-slug"}

    def test_assign_slugs_adds_new_keeps_old(self):
        from scripts.export_public_site import assign_slugs
        communities = [
            {"id": "abc", "name": "Builders"},
            {"id": "def", "name": "New Community"},
        ]
        registry = {"abc": "builders"}
        result = assign_slugs(communities, registry)
        assert result == {"abc": "builders", "def": "new-community"}

    def test_assign_slugs_handles_collision(self):
        from scripts.export_public_site import assign_slugs
        communities = [
            {"id": "abc", "name": "Builders"},
            {"id": "def", "name": "Builders"},  # same name, different community
        ]
        registry = {}
        result = assign_slugs(communities, registry)
        assert result["abc"] == "builders"
        assert result["def"] == "builders-2"
        assert len(set(result.values())) == 2  # all slugs unique
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSlugRegistry -v`
Expected: FAIL with ImportError

- [ ] **Step 7: Implement slug registry functions**

Add to `scripts/export_public_site.py` after `slugify_name`:

```python
def load_slug_registry(path):
    """Load slug registry from JSON file. Returns empty dict if file missing."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_slug_registry(path, registry):
    """Write slug registry to JSON file."""
    path = Path(path)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=True)


def assign_slugs(communities, registry):
    """Assign slugs to communities, preserving existing registry entries.

    Handles collisions by appending -2, -3, etc.
    Returns updated registry dict.
    """
    updated = dict(registry)
    used_slugs = set(updated.values())
    for c in communities:
        cid = c["id"]
        if cid not in updated:
            base = slugify_name(c["name"])
            slug = base
            counter = 2
            while slug in used_slugs:
                slug = f"{base}-{counter}"
                counter += 1
            updated[cid] = slug
            used_slugs.add(slug)
    return updated
```

Note: Ensure `from pathlib import Path` and `import json` are at the top of the file (json is likely already imported).

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSlugRegistry -v`
Expected: 6 PASSED

- [ ] **Step 9: Create initial empty slug_registry.json**

Create `public-site/public/slug_registry.json`:

```json
{}
```

- [ ] **Step 10: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py public-site/public/slug_registry.json
git commit -m "feat(export): add slug generation and persistence for community URLs

MOTIVATION:
- Community detail pages need stable, shareable URLs
- Slugs must survive community renames

APPROACH:
- slugify_name() converts names to URL-safe slugs
- slug_registry.json persists slug assignments across exports
- assign_slugs() preserves existing, generates for new communities

CHANGES:
- scripts/export_public_site.py: Add slugify_name, load/save_slug_registry, assign_slugs
- tests/test_export_public_site.py: 11 new tests (TestSlugGeneration + TestSlugRegistry)
- public-site/public/slug_registry.json: Empty initial registry

TESTING: 11 new tests all passing"
```

---

## Task 2: Tweet Type Detection and Selection

**Files:**
- Modify: `scripts/export_public_site.py` (add functions after slug functions)
- Modify: `tests/test_export_public_site.py`

- [ ] **Step 1: Write failing tests for detect_tweet_type**

Add to `tests/test_export_public_site.py`. First, a fixture that creates a tweets table with varied tweet types:

```python
@pytest.fixture
def tweets_db(tmp_path):
    """DB with tweets table including replies, RTs, threads, and regular tweets."""
    db_path = tmp_path / "tweets.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE tweets (
            tweet_id TEXT PRIMARY KEY,
            account_id TEXT,
            full_text TEXT,
            created_at TEXT,
            reply_to_tweet_id TEXT,
            favorite_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0
        )
    """)
    # Regular tweet
    conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t1", "acct1", "Just a normal tweet", "2025-01-15 10:00:00", None, 100, 20))
    # Reply
    conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t2", "acct1", "Great point about transformers", "2025-01-15 11:00:00", "t999", 50, 10))
    # Retweet
    conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t3", "acct1", "RT @someone: Original tweet text", "2025-01-15 12:00:00", None, 30, 5))
    # Thread: two tweets within 5 min
    conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t4", "acct1", "1/ Here is a thread about ML", "2025-01-16 10:00:00", None, 200, 50))
    conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t5", "acct1", "2/ The key insight is...", "2025-01-16 10:03:00", None, 180, 40))
    # Isolated tweet (not a thread — 2 hours later)
    conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("t6", "acct1", "Completely separate thought", "2025-01-16 12:00:00", None, 60, 15))
    conn.commit()
    return db_path


class TestTweetTypeDetection:
    def test_regular_tweet(self, tweets_db):
        from scripts.export_public_site import detect_tweet_types
        types = detect_tweet_types(tweets_db, "acct1", ["t1", "t6"])
        assert types["t1"] == "tweet"
        assert types["t6"] == "tweet"

    def test_reply(self, tweets_db):
        from scripts.export_public_site import detect_tweet_types
        types = detect_tweet_types(tweets_db, "acct1", ["t2"])
        assert types["t2"] == "reply"

    def test_retweet(self, tweets_db):
        from scripts.export_public_site import detect_tweet_types
        types = detect_tweet_types(tweets_db, "acct1", ["t3"])
        assert types["t3"] == "retweet"

    def test_thread(self, tweets_db):
        from scripts.export_public_site import detect_tweet_types
        types = detect_tweet_types(tweets_db, "acct1", ["t4", "t5"])
        assert types["t4"] == "thread"
        assert types["t5"] == "thread"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestTweetTypeDetection -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement detect_tweet_types**

Add to `scripts/export_public_site.py`:

```python
def detect_tweet_types(db_path, account_id, tweet_ids):
    """Classify tweet types for a set of tweet IDs.

    Takes db_path (not conn) to match existing per-function connection pattern.
    Returns dict {tweet_id: "tweet"|"reply"|"retweet"|"thread"}.
    Thread detection: tweets from same account within 5 min of each other.
    """
    if not tweet_ids:
        return {}

    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" for _ in tweet_ids)
        rows = conn.execute(f"""
        SELECT tweet_id, full_text, reply_to_tweet_id, created_at
        FROM tweets
        WHERE tweet_id IN ({placeholders}) AND account_id = ?
    """, [*tweet_ids, account_id]).fetchall()

    tweet_data = {}
    for row in rows:
        tweet_data[row[0]] = {
            "text": row[1] or "",
            "reply_to": row[2],
            "created_at": row[3],
        }

    # Detect thread clusters: tweets within 5 min of each other
    from datetime import datetime, timedelta
    timestamps = []
    for tid in tweet_ids:
        if tid in tweet_data and tweet_data[tid]["created_at"]:
            try:
                dt = datetime.strptime(tweet_data[tid]["created_at"], "%Y-%m-%d %H:%M:%S")
                timestamps.append((tid, dt))
            except ValueError:
                pass
    timestamps.sort(key=lambda x: x[1])

    thread_ids = set()
    for i in range(len(timestamps) - 1):
        if timestamps[i + 1][1] - timestamps[i][1] <= timedelta(minutes=5):
            thread_ids.add(timestamps[i][0])
            thread_ids.add(timestamps[i + 1][0])

    result = {}
    for tid in tweet_ids:
        if tid not in tweet_data:
            result[tid] = "tweet"
        elif tweet_data[tid]["text"].startswith("RT @"):
            result[tid] = "retweet"
        elif tweet_data[tid]["reply_to"]:
            result[tid] = "reply"
        elif tid in thread_ids:
            result[tid] = "thread"
        else:
            result[tid] = "tweet"
    finally:
        conn.close()
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestTweetTypeDetection -v`
Expected: 4 PASSED

- [ ] **Step 5: Write failing tests for select_community_tweets**

```python
class TestSelectCommunityTweets:
    def test_returns_top_n_by_engagement(self, tweets_db):
        from scripts.export_public_site import select_community_tweets
        tweets = select_community_tweets(tweets_db, "acct1", n=3)
        # t4 (200+50*2=300), t5 (180+40*2=260), t1 (100+20*2=140) by fav+rt*2
        assert len(tweets) == 3
        assert tweets[0]["id"] == "t4"

    def test_includes_type_field(self, tweets_db):
        from scripts.export_public_site import select_community_tweets
        tweets = select_community_tweets(tweets_db, "acct1", n=5)
        for t in tweets:
            assert t["type"] in ("tweet", "reply", "retweet", "thread")

    def test_includes_required_fields(self, tweets_db):
        from scripts.export_public_site import select_community_tweets
        tweets = select_community_tweets(tweets_db, "acct1", n=1)
        t = tweets[0]
        assert "id" in t
        assert "text" in t
        assert "created_at" in t
        assert "favorite_count" in t
        assert "retweet_count" in t
        assert "type" in t

    def test_unknown_account_returns_empty(self, tweets_db):
        from scripts.export_public_site import select_community_tweets
        tweets = select_community_tweets(tweets_db, "nonexistent", n=5)
        assert tweets == []

    def test_respects_n_limit(self, tweets_db):
        from scripts.export_public_site import select_community_tweets
        tweets = select_community_tweets(tweets_db, "acct1", n=2)
        assert len(tweets) == 2
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSelectCommunityTweets -v`
Expected: FAIL with ImportError

- [ ] **Step 7: Implement select_community_tweets**

Add to `scripts/export_public_site.py`:

```python
def select_community_tweets(db_path, account_id, n=5):
    """Select top tweets by engagement for an account.

    Takes db_path (not conn) to match existing per-function connection pattern.
    Returns list of dicts with id, text, created_at, type, favorite_count, retweet_count.
    Scoring: favorite_count + retweet_count * 2.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("""
            SELECT tweet_id, full_text, created_at, favorite_count, retweet_count
            FROM tweets
            WHERE account_id = ?
            ORDER BY (favorite_count + retweet_count * 2) DESC
            LIMIT ?
        """, [account_id, n]).fetchall()
    except Exception:
        conn.close()
        return []

    conn.close()

    if not rows:
        return []

    tweet_ids = [r[0] for r in rows]
    types = detect_tweet_types(db_path, account_id, tweet_ids)

    return [
        {
            "id": r[0],
            "text": (r[1] or "")[:280],
            "created_at": r[2],
            "type": types.get(r[0], "tweet"),
            "favorite_count": r[3] or 0,
            "retweet_count": r[4] or 0,
        }
        for r in rows
    ]
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSelectCommunityTweets -v`
Expected: 5 PASSED

- [ ] **Step 9: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py
git commit -m "feat(export): add tweet type detection and engagement-based selection

MOTIVATION:
- Community detail pages need categorized tweets (thread/reply/retweet/tweet)
- Need top-engagement tweets per featured member

APPROACH:
- detect_tweet_types: classifies via RT prefix, reply_to_tweet_id, and 5-min thread heuristic
- select_community_tweets: top N by favorite_count + retweet_count * 2

CHANGES:
- scripts/export_public_site.py: Add detect_tweet_types, select_community_tweets
- tests/test_export_public_site.py: 9 new tests (TestTweetTypeDetection + TestSelectCommunityTweets)

TESTING: 9 new tests all passing"
```

---

## Task 3: Enriched Community Export

**Files:**
- Modify: `scripts/export_public_site.py:248-392` (wire into `run_export`)
- Modify: `tests/test_export_public_site.py`

This task wires slug generation, featured members, and all_members into the main export pipeline so that `data.json` contains the enriched community objects.

- [ ] **Step 1: Write failing test for enriched community in data.json**

Add to `tests/test_export_public_site.py`, within or after `TestRunExport`:

```python
class TestEnrichedCommunityExport:
    """Tests for community detail page data in data.json.

    Note: run_export signature is run_export(data_dir, output_dir, config, db_path=None).
    The existing fixtures put npz/parquet files in data_dir (tmp_path).
    """

    def test_communities_have_slugs(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        data = json.loads((output_dir / "data.json").read_text())
        for c in data["communities"]:
            assert "slug" in c
            assert c["slug"]  # not empty
            assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", c["slug"])

    def test_communities_have_featured_members(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        data = json.loads((output_dir / "data.json").read_text())
        for c in data["communities"]:
            assert "featured_members" in c
            assert isinstance(c["featured_members"], list)

    def test_featured_members_sorted_by_weight(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        data = json.loads((output_dir / "data.json").read_text())
        for c in data["communities"]:
            weights = [m["weight"] for m in c["featured_members"]]
            assert weights == sorted(weights, reverse=True)

    def test_featured_member_has_tweets(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        # Add tweets table to community_db for this test
        conn = sqlite3.connect(community_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT,
                full_text TEXT,
                created_at TEXT,
                reply_to_tweet_id TEXT,
                favorite_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("tw1", "acct-1", "Test tweet", "2025-01-15 10:00:00", None, 100, 20))
        conn.commit()
        conn.close()

        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        data = json.loads((output_dir / "data.json").read_text())
        # Find community with acct-1 as member
        for c in data["communities"]:
            for m in c["featured_members"]:
                if m.get("tweets"):
                    tweet = m["tweets"][0]
                    assert "id" in tweet
                    assert "text" in tweet
                    assert "type" in tweet

    def test_communities_have_all_members(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        data = json.loads((output_dir / "data.json").read_text())
        for c in data["communities"]:
            assert "all_members" in c
            assert isinstance(c["all_members"], list)

    def test_all_members_excludes_featured(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        data = json.loads((output_dir / "data.json").read_text())
        for c in data["communities"]:
            featured_usernames = {m["username"] for m in c["featured_members"]}
            all_usernames = {m["username"] for m in c["all_members"]}
            assert featured_usernames.isdisjoint(all_usernames), \
                f"Featured and all_members overlap: {featured_usernames & all_usernames}"

    def test_slug_registry_written(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        registry_path = output_dir / "slug_registry.json"
        assert registry_path.exists()
        registry = json.loads(registry_path.read_text())
        assert len(registry) > 0

    def test_slug_registry_preserves_across_exports(self, community_db, npz_file, parquet_file, config, tmp_path):
        from scripts.export_public_site import run_export
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        # First export
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        registry1 = json.loads((output_dir / "slug_registry.json").read_text())
        # Second export
        run_export(data_dir=tmp_path, output_dir=output_dir, config=config, db_path=community_db)
        registry2 = json.loads((output_dir / "slug_registry.json").read_text())
        assert registry1 == registry2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestEnrichedCommunityExport -v`
Expected: FAIL (communities in data.json lack slug, featured_members, all_members)

- [ ] **Step 3: Wire enrichment into run_export**

Modify `scripts/export_public_site.py` `run_export()` function. The key changes:

1. After `extract_communities()` (around line 260), load slug registry and assign slugs:

```python
# After communities = extract_communities(conn)
slug_registry_path = Path(output_dir) / "slug_registry.json"
slug_registry = load_slug_registry(slug_registry_path)
slug_registry = assign_slugs(communities, slug_registry)

# Add slug to each community
for c in communities:
    c["slug"] = slug_registry[c["id"]]
```

2. After classified accounts are built and enriched with parquet metadata (around line 330), build featured members and all_members per community:

```python
# Build account lookup by account_id for enrichment
# (classified_accounts is the list of account dicts with memberships)
account_by_id = {}
for acct in classified_accounts:
    account_by_id[acct["id"]] = acct

# Enrich communities with featured_members and all_members
for c in communities:
    cid = c["id"]
    # Get all classified members of this community, sorted by weight desc
    # IMPORTANT: Skip accounts without valid usernames (parquet metadata may be missing)
    members_with_weight = []
    for acct in classified_accounts:
        if not acct.get("username"):
            continue  # No username from parquet enrichment — skip
        for m in acct["memberships"]:
            if m["community_id"] == cid:
                members_with_weight.append({
                    "username": acct["username"],
                    "display_name": acct.get("display_name", ""),
                    "bio": acct.get("bio", ""),
                    "weight": m["weight"],
                    "account_id": acct["id"],
                })
                break
    members_with_weight.sort(key=lambda x: x["weight"], reverse=True)

    # Top 5 featured with tweets
    featured = members_with_weight[:5]
    for fm in featured:
        fm["tweets"] = select_community_tweets(db_path, fm["account_id"], n=5)
        del fm["account_id"]  # Don't expose internal ID

    # Remaining members (compact: username, display_name, bio)
    featured_usernames = {fm["username"] for fm in featured}
    all_members = [
        {"username": m["username"], "display_name": m["display_name"], "bio": m["bio"]}
        for m in members_with_weight[5:]
    ]

    c["featured_members"] = featured
    c["all_members"] = all_members
```

3. After writing data.json, save slug registry:

```python
save_slug_registry(slug_registry_path, slug_registry)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py::TestEnrichedCommunityExport -v`
Expected: 8 PASSED

- [ ] **Step 5: Run ALL existing tests to verify no regressions**

Run: `.venv/bin/python3 -m pytest tests/test_export_public_site.py -v`
Expected: All tests PASS (existing 28 + new ~24)

- [ ] **Step 6: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py
git commit -m "feat(export): enrich communities with featured members, tweets, and all_members

MOTIVATION:
- Community detail pages need per-community member spotlights and tweet content
- Slug registry must be written on each export

APPROACH:
- Wire slug assignment into run_export, persist to slug_registry.json
- Build featured_members (top 5 by weight) with tweets from select_community_tweets
- Build all_members (remaining classified, compact format)

CHANGES:
- scripts/export_public_site.py: Enrich communities in run_export
- tests/test_export_public_site.py: 8 new tests (TestEnrichedCommunityExport)

TESTING: All tests passing, no regressions"
```

---

## Task 4: App.jsx Query State Model

**Files:**
- Create: `public-site/src/useRouting.js` (extracted routing hook)
- Modify: `public-site/src/App.jsx:85-269`

This task extracts routing logic into a `useRouting` hook to keep App.jsx under 300 LOC (currently 269, would exceed with inline additions). The hook manages the three-way state: `community` > `handle` > homepage.

- [ ] **Step 1: Create useRouting hook**

Create `public-site/src/useRouting.js` — this extracts all routing state and navigation from App.jsx:

```jsx
import { useState, useEffect, useMemo } from 'react'

/**
 * Manages three-way routing state: community > handle > homepage.
 * Extracted from App.jsx to keep it under 300 LOC.
 */
export default function useRouting(data, accountMap) {
  const [result, setResult] = useState(null)
  const [communityResult, setCommunityResult] = useState(null)

  // Parse URL params with precedence: community > handle > homepage
  // Preserve existing handle normalization: strip @, trim, lowercase
  const params = new URLSearchParams(window.location.search)
  const [pendingCommunity] = useState(() => params.get('community')?.trim().toLowerCase() || null)
  const [pendingHandle] = useState(() => {
    const raw = params.get('handle')
    if (!raw) return null
    return raw.replace(/^@/, '').trim().toLowerCase()
  })

  // Build slug → community lookup
  const communitySlugMap = useMemo(() => {
    if (!data) return new Map()
    const map = new Map()
    for (const c of data.communities) {
      if (c.slug) map.set(c.slug, c)
    }
    return map
  }, [data])

  // Resolve community param
  useEffect(() => {
    if (!data || !pendingCommunity) return
    const community = communitySlugMap.get(pendingCommunity)
    if (community) {
      setCommunityResult(community)
    } else {
      setCommunityResult({ notFound: true, slug: pendingCommunity })
    }
  }, [data, pendingCommunity, communitySlugMap])

  // View state (mutually exclusive)
  const showCommunity = !!communityResult
  const showResult = !showCommunity && !!result
  const showHome = !showCommunity && !showResult

  // Navigation functions
  const handleCommunityClick = (slug) => {
    window.history.replaceState({}, '', `/?community=${slug}`)
    const community = communitySlugMap.get(slug)
    setCommunityResult(community || { notFound: true, slug })
    setResult(null)
  }

  const handleBackFromCommunity = () => {
    window.history.replaceState({}, '', '/')
    setCommunityResult(null)
  }

  const handleMemberClick = (username) => {
    window.history.replaceState({}, '', `/?handle=${username}`)
    setCommunityResult(null)
    // Look up full account data from accountMap (keyed by lowercase username)
    const account = accountMap.get(username.toLowerCase())
    if (account) {
      setResult({
        handle: account.username,
        tier: 'classified',
        memberships: account.memberships,
        displayName: account.display_name,
        bio: account.bio,
        sampleTweets: account.sample_tweets,
      })
    } else {
      setResult({ handle: username, tier: 'not_found' })
    }
  }

  const handleSearchAgain = () => {
    setResult(null)
    setCommunityResult(null)
    window.history.replaceState({}, '', '/')
  }

  return {
    result, setResult,
    communityResult,
    communitySlugMap,
    pendingHandle, pendingCommunity,
    showCommunity, showResult, showHome,
    handleCommunityClick, handleBackFromCommunity,
    handleMemberClick, handleSearchAgain,
  }
}
```

Note: The existing App.jsx (line 89) normalizes handles with `.replace(/^@/, '').trim().toLowerCase()`. This is preserved in the hook's `pendingHandle` init.

- [ ] **Step 2: Refactor App.jsx to use useRouting hook**

In `App.jsx`:

1. Replace the existing state/routing code with the hook:
```jsx
import useRouting from './useRouting'

// Inside App component, replace state declarations + handleSearchAgain + handleResult:
const {
  result, setResult,
  communityResult, communitySlugMap,
  pendingHandle, pendingCommunity,
  showCommunity, showResult, showHome,
  handleCommunityClick, handleBackFromCommunity,
  handleMemberClick, handleSearchAgain,
} = useRouting(data, accountMap)
```

2. Modify the existing `handleResult` to use the hook's `setResult` (it should still work since `setResult` is returned from the hook).

3. Modify the existing handle useEffect (around line 119) to skip when community param is present:
```jsx
if (pendingCommunity) return  // community takes precedence
```

- [ ] **Step 3: Update render logic for three-way routing**

- [ ] **Step 3: Update render logic for three-way routing**

Modify the render section (around line 200-268). The `showCommunity`, `showResult`, `showHome` flags are already computed by the hook. Add community page rendering (before or alongside the result block):

```jsx
{showCommunity && !communityResult.notFound && (
  <CommunityPage
    community={communityResult}
    communities={data.communities}
    communityMap={communityMap}
    onBack={handleBackFromCommunity}
    onMemberClick={handleMemberClick}
    onCommunityClick={handleCommunityClick}
  />
)}

{showCommunity && communityResult.notFound && (
  <div className="not-found">
    <p>Community "{communityResult.slug}" not found.</p>
    <button onClick={handleBackFromCommunity}>← Back to Find My Ingroup</button>
  </div>
)}
```

- [ ] **Step 4: Make showcase tags clickable**

In the community showcase section (around lines 213-222), change `<span>` to clickable elements:

```jsx
<div className="showcase-tags">
  {communities.map(c => (
    <a
      key={c.id}
      className="showcase-tag"
      style={{ borderColor: c.color, color: c.color }}
      href={`/?community=${c.slug}`}
      onClick={(e) => {
        e.preventDefault()
        handleCommunityClick(c.slug)
      }}
    >
      {c.name}
    </a>
  ))}
</div>
```

- [ ] **Step 5: Add CommunityPage import**

At the top of App.jsx:

```jsx
import CommunityPage from './CommunityPage'
```

- [ ] **Step 6: Commit**

```bash
git add public-site/src/useRouting.js public-site/src/App.jsx
git commit -m "feat(ui): add query state model for community pages

MOTIVATION:
- Community detail pages need URL-based routing with ?community=slug
- Must coexist with existing ?handle=X routing
- App.jsx at 269 LOC would exceed 300 with inline routing logic

APPROACH:
- Extract routing to useRouting.js hook (keeps App.jsx under 300 LOC)
- Three-way state: community > handle > homepage
- communitySlugMap for O(1) slug lookup
- Preserves existing handle normalization (@-strip, lowercase)

CHANGES:
- public-site/src/useRouting.js: New hook with all routing state + navigation
- public-site/src/App.jsx: Use hook, add community rendering, clickable showcase tags

TESTING: Manual verification of routing states"
```

---

## Task 5: CommunityPage Component

**Files:**
- Create: `public-site/src/CommunityPage.jsx`

- [ ] **Step 1: Create CommunityPage component**

Create `public-site/src/CommunityPage.jsx`:

```jsx
import { useState } from 'react'

function TweetCard({ tweet, username, communityColor }) {
  const typeLabels = {
    thread: '🧵 thread',
    reply: '↩ reply',
    retweet: '🔁 RT',
    tweet: 'tweet',
  }
  const date = tweet.created_at
    ? new Date(tweet.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : ''
  const xUrl = `https://x.com/${username}/status/${tweet.id}`

  return (
    <div className="cp-tweet" style={{ borderLeftColor: tweet._isTop ? communityColor : '#333' }}>
      <div className="cp-tweet-header">
        <span className="cp-tweet-type" style={{ color: tweet._isTop ? communityColor : '#aaa' }}>
          {typeLabels[tweet.type] || 'tweet'} · {date}
        </span>
        <a href={xUrl} target="_blank" rel="noopener noreferrer" className="cp-tweet-link">
          ↗ view on X
        </a>
      </div>
      <div className="cp-tweet-text">{tweet.text}</div>
      <div className="cp-tweet-stats">
        <span>❤ {tweet.favorite_count}</span>
        <span>🔁 {tweet.retweet_count}</span>
      </div>
    </div>
  )
}

function SpotlightCard({ member, communityColor, onMemberClick }) {
  const tweetsWithTop = (member.tweets || []).map((t, i) => ({ ...t, _isTop: i === 0 }))

  return (
    <div className="cp-spotlight">
      <div className="cp-spotlight-header">
        <div className="cp-spotlight-avatar" style={{ background: '#333' }} />
        <div className="cp-spotlight-info">
          <a
            className="cp-spotlight-handle"
            style={{ color: communityColor }}
            href={`/?handle=${member.username}`}
            onClick={(e) => {
              e.preventDefault()
              onMemberClick(member.username)
            }}
          >
            @{member.username}
          </a>
          <div className="cp-spotlight-bio">{member.bio}</div>
        </div>
        <div className="cp-spotlight-weight">weight {member.weight.toFixed(2)}</div>
      </div>
      {tweetsWithTop.map(t => (
        <TweetCard
          key={t.id}
          tweet={t}
          username={member.username}
          communityColor={communityColor}
        />
      ))}
    </div>
  )
}

function MemberGridItem({ member, communityColor, onMemberClick }) {
  return (
    <a
      className="cp-member-item"
      href={`/?handle=${member.username}`}
      onClick={(e) => {
        e.preventDefault()
        onMemberClick(member.username)
      }}
    >
      <div className="cp-member-handle" style={{ color: communityColor }}>@{member.username}</div>
      <div className="cp-member-bio">{member.bio}</div>
    </a>
  )
}

export default function CommunityPage({
  community,
  communities,
  onBack,
  onMemberClick,
  onCommunityClick,
}) {
  const featured = community.featured_members || []
  const allMembers = community.all_members || []
  const browseableCount = featured.length + allMembers.length
  const color = community.color

  const handleShare = () => {
    const url = `${window.location.origin}/?community=${community.slug}`
    navigator.clipboard.writeText(url)
  }

  // Sibling communities (exclude current)
  const siblings = (communities || []).filter(c => c.id !== community.id)

  return (
    <div className="community-page">
      {/* Back nav */}
      <div className="cp-back">
        <a href="/" onClick={(e) => { e.preventDefault(); onBack() }}>
          ← Back to Find My Ingroup
        </a>
      </div>

      {/* Hero header */}
      <div className="cp-hero" style={{ borderBottomColor: color }}>
        <div className="cp-hero-dot" style={{ background: color }} />
        <h1 className="cp-hero-name">{community.name}</h1>
        <p className="cp-hero-desc">{community.description}</p>
        <div className="cp-hero-meta">
          <span>{browseableCount} members</span>
          <span>·</span>
          <span>{featured.length} featured</span>
          <span>·</span>
          <button className="cp-share-btn" onClick={handleShare} style={{ color }}>
            🔗 Share this community
          </button>
        </div>
      </div>

      {/* Spotlights */}
      {featured.length > 0 && (
        <div className="cp-spotlights">
          <div className="cp-section-label">Prototypical Members</div>
          {featured.map(m => (
            <SpotlightCard
              key={m.username}
              member={m}
              communityColor={color}
              onMemberClick={onMemberClick}
            />
          ))}
        </div>
      )}

      {/* All members grid */}
      {allMembers.length > 0 && (
        <div className="cp-all-members">
          <div className="cp-section-label cp-all-members-label">
            All Members · {browseableCount}
          </div>
          <div className="cp-member-grid">
            {allMembers.map(m => (
              <MemberGridItem
                key={m.username}
                member={m}
                communityColor={color}
                onMemberClick={onMemberClick}
              />
            ))}
          </div>
        </div>
      )}

      {/* Sibling nav */}
      <div className="cp-sibling-nav">
        <div className="cp-sibling-links">
          {siblings.map(c => (
            <a
              key={c.id}
              href={`/?community=${c.slug}`}
              style={{ color: c.color }}
              onClick={(e) => {
                e.preventDefault()
                onCommunityClick(c.slug)
                window.scrollTo(0, 0)
              }}
            >
              {c.name}
            </a>
          ))}
        </div>
        <div className="cp-footer-text">Find My Ingroup · amiingroup.vercel.app</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add public-site/src/CommunityPage.jsx
git commit -m "feat(ui): add CommunityPage component with member spotlights

MOTIVATION:
- Community detail pages need a dedicated component for the spotlight layout

APPROACH:
- CommunityPage: hero header, SpotlightCard list, all-members grid, sibling nav
- TweetCard: renders individual tweets with type badge, date, X link
- MemberGridItem: compact member link for all-members section
- All navigation via callback props (onBack, onMemberClick, onCommunityClick)

CHANGES:
- public-site/src/CommunityPage.jsx: New component (3 sub-components)

TESTING: Visual verification next (CSS in Task 6)"
```

---

## Task 6: Community Page CSS

**Files:**
- Create: `public-site/src/community-page.css` (new file — styles.css is already 1056 LOC)
- Modify: `public-site/src/CommunityPage.jsx` (import the CSS)

Community page styles go in their own file to avoid pushing `styles.css` to ~1250 LOC. The community page is a self-contained view with its own component, so its styles belong alongside it.

- [ ] **Step 1: Create community-page.css**

Create `public-site/src/community-page.css`:

```css
/* ── Community Detail Page ── */

.community-page {
  max-width: 640px;
  margin: 0 auto;
  padding: 0 16px;
}

.cp-back {
  padding: 12px 0;
  border-bottom: 1px solid #222;
}
.cp-back a {
  color: #888;
  text-decoration: none;
  font-size: 13px;
}
.cp-back a:hover {
  color: #e0e0e0;
}

/* Hero */
.cp-hero {
  text-align: center;
  padding: 32px 0 24px;
  border-bottom: 2px solid #555;
}
.cp-hero-dot {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  margin: 0 auto 12px;
}
.cp-hero-name {
  font-size: 22px;
  font-weight: bold;
  color: #fff;
  margin: 0;
}
.cp-hero-desc {
  font-size: 14px;
  color: #aaa;
  margin: 10px auto 0;
  line-height: 1.6;
  max-width: 560px;
}
.cp-hero-meta {
  display: flex;
  gap: 8px;
  justify-content: center;
  align-items: center;
  margin-top: 14px;
  font-size: 12px;
  color: #666;
}
.cp-share-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}
.cp-share-btn:hover {
  opacity: 0.8;
}

/* Section labels */
.cp-section-label {
  font-size: 11px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  margin-bottom: 16px;
}

/* Spotlights */
.cp-spotlights {
  padding: 24px 0;
}
.cp-spotlight {
  background: #1a1a1a;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid #252525;
}
.cp-spotlight-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.cp-spotlight-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cp-spotlight-info {
  flex: 1;
  min-width: 0;
}
.cp-spotlight-handle {
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}
.cp-spotlight-handle:hover {
  text-decoration: underline;
}
.cp-spotlight-bio {
  font-size: 11px;
  color: #999;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-spotlight-weight {
  font-size: 10px;
  color: #555;
  background: #252525;
  padding: 3px 8px;
  border-radius: 12px;
  white-space: nowrap;
}

/* Tweet cards */
.cp-tweet {
  background: #111;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  border-left: 3px solid #333;
}
.cp-tweet:last-child {
  margin-bottom: 0;
}
.cp-tweet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.cp-tweet-type {
  font-size: 11px;
}
.cp-tweet-link {
  font-size: 10px;
  color: #555;
  text-decoration: none;
}
.cp-tweet-link:hover {
  color: #888;
}
.cp-tweet-text {
  font-size: 13px;
  color: #ddd;
  line-height: 1.5;
}
.cp-tweet-stats {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 11px;
  color: #666;
}

/* All members grid */
.cp-all-members {
  padding-bottom: 24px;
}
.cp-all-members-label {
  padding-top: 16px;
  border-top: 1px solid #222;
}
.cp-member-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.cp-member-item {
  background: #1a1a1a;
  border-radius: 6px;
  padding: 10px;
  cursor: pointer;
  text-decoration: none;
  display: block;
  transition: background 0.15s;
}
.cp-member-item:hover {
  background: #252525;
}
.cp-member-handle {
  font-size: 12px;
  font-weight: 500;
}
.cp-member-bio {
  font-size: 10px;
  color: #777;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Sibling nav */
.cp-sibling-nav {
  padding: 16px 0 32px;
  border-top: 1px solid #222;
  text-align: center;
}
.cp-sibling-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  justify-content: center;
  font-size: 12px;
}
.cp-sibling-links a {
  text-decoration: none;
}
.cp-sibling-links a:hover {
  text-decoration: underline;
}
.cp-footer-text {
  font-size: 11px;
  color: #555;
  margin-top: 12px;
}

/* Not found */
.not-found {
  text-align: center;
  padding: 64px 16px;
  color: #888;
}
.not-found button {
  margin-top: 16px;
  background: none;
  border: 1px solid #333;
  color: #e0e0e0;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}
```

- [ ] **Step 2: Add mobile responsive rules at the end of community-page.css**

```css
/* Responsive — append to end of community-page.css */
@media (max-width: 480px) {
.cp-member-grid {
  grid-template-columns: 1fr;
}
.cp-hero-name {
  font-size: 18px;
}
.cp-hero-desc {
  font-size: 13px;
}
.cp-spotlight-weight {
  display: none;
}
}
```

Then add the CSS import to `CommunityPage.jsx` at the top:

```jsx
import './community-page.css'
```

- [ ] **Step 3: Commit**

```bash
git add public-site/src/community-page.css public-site/src/CommunityPage.jsx
git commit -m "feat(ui): add CSS for community detail pages

MOTIVATION:
- CommunityPage component needs styling matching the dark theme

APPROACH:
- Separate community-page.css file (styles.css is already 1056 LOC)
- cp- prefixed classes to avoid conflicts with existing styles
- Matches existing color palette (#1a1a1a, #111, #222, #e0e0e0, etc.)
- Mobile responsive: single-column grid, smaller type on 480px

CHANGES:
- public-site/src/community-page.css: ~200 lines of community page styles + responsive rules
- public-site/src/CommunityPage.jsx: Import community-page.css

TESTING: Visual verification in browser"
```

---

## Task 7: Cross-Linking from Account Cards

**Files:**
- Modify: `public-site/src/CommunityCard.jsx:89-134` (bar chart variant)

Community membership labels on account cards should link back to community pages.

- [ ] **Step 1: Add onCommunityClick prop and slug data**

Modify `CommunityCard.jsx`. The component receives `communityMap` which now has `slug` on each community. Add `onCommunityClick` prop:

```jsx
// In the component signature, add onCommunityClick:
export default function CommunityCard({
  handle, displayName, bio, tier, memberships, communityMap,
  aiImageUrl, generationStatus, onCommunityClick
}) {
```

- [ ] **Step 2: Add communityId to bar objects**

The bar calculation (around line 18-28) currently maps memberships to `{name, color, weight, pct}` but does NOT include `communityId`. Add it so we can look up the slug:

```jsx
// In the bars calculation (around line 18-28), change the map to include communityId:
const bars = memberships
  .map(m => {
    const c = communityMap.get(m.community_id)
    return {
      communityId: m.community_id,  // ← ADD THIS
      name: c?.name || m.community_name || '?',
      color: c?.color || '#555',
      weight: m.weight,
      pct: Math.round(m.weight * 100),
    }
  })
  .sort((a, b) => b.weight - a.weight)
```

- [ ] **Step 3: Make community name labels clickable**

In the bar chart variant (around line 100-110), where community names are rendered, wrap them in clickable elements:

For the bar chart `label` span (currently just text):
```jsx
<span
  className="bar-label"
  style={{ cursor: onCommunityClick ? 'pointer' : 'default' }}
  onClick={() => {
    const comm = communityMap.get(bar.communityId)
    if (onCommunityClick && comm?.slug) onCommunityClick(comm.slug)
  }}
>
  {bar.name}
</span>
```

For the AI card community dots overlay (around line 70-80), make the community names clickable similarly using the same `communityId` → `communityMap` → `slug` lookup.

- [ ] **Step 4: Thread onCommunityClick through App.jsx**

In `App.jsx`, where `CommunityCard` is rendered inside `ResultArea`, pass the handler:

```jsx
<CommunityCard
  {...existingProps}
  onCommunityClick={handleCommunityClick}
/>
```

Note: `handleCommunityClick` is already defined in Task 4. It needs to be passed from App through to ResultArea and then to CommunityCard. Check how ResultArea receives props and thread it through.

- [ ] **Step 5: Commit**

```bash
git add public-site/src/CommunityCard.jsx public-site/src/App.jsx
git commit -m "feat(ui): cross-link account card community labels to community pages

MOTIVATION:
- Bidirectional navigation: community page → member card → community page

APPROACH:
- Community bar labels and AI overlay dots become clickable
- onCommunityClick prop threaded from App through ResultArea to CommunityCard

CHANGES:
- public-site/src/CommunityCard.jsx: Add onCommunityClick, clickable labels
- public-site/src/App.jsx: Thread handler to CommunityCard

TESTING: Manual click-through verification"
```

---

## Task 8: Re-Export Data and Verify

**Files:**
- Modify: `public-site/public/data.json` (regenerated)
- Modify: `public-site/public/slug_registry.json` (populated)

- [ ] **Step 1: Run the export**

```bash
cd tpot-analyzer
.venv/bin/python3 scripts/export_public_site.py
```

Expected: Export completes, prints summary including community slug assignments and featured member counts.

- [ ] **Step 2: Verify data.json has enriched communities**

```bash
.venv/bin/python3 -c "
import json
data = json.load(open('public-site/public/data.json'))
for c in data['communities']:
    fm = len(c.get('featured_members', []))
    am = len(c.get('all_members', []))
    print(f\"{c['slug']:40s} featured={fm} all={am}\")
"
```

Expected: 14 communities, each with a slug, 0-5 featured members, remaining as all_members.

- [ ] **Step 3: Verify slug_registry.json populated**

```bash
cat public-site/public/slug_registry.json | .venv/bin/python3 -m json.tool
```

Expected: 14 entries mapping community UUIDs to slugs.

- [ ] **Step 4: Start dev server and test manually**

```bash
cd public-site && npm run dev
```

Test these flows in browser:
1. Homepage → click community tag → community page loads
2. Community page → click member handle → account card loads
3. Account card → click community label → community page loads
4. Community page → click sibling nav → different community page
5. Direct URL: `http://localhost:5173/?community=builders` → correct page
6. Invalid slug: `http://localhost:5173/?community=nonexistent` → not-found message
7. Both params: `http://localhost:5173/?community=builders&handle=someone` → community page (community wins)

- [ ] **Step 5: Commit data files**

```bash
git add public-site/public/data.json public-site/public/slug_registry.json
git commit -m "data: re-export with enriched community data and slug registry

CHANGES:
- public-site/public/data.json: Communities now include slug, featured_members, all_members
- public-site/public/slug_registry.json: Initial slug assignments for 14 communities

TESTING: Manual browser verification of all navigation flows"
```

---

## Task 9: Frontend Tests

**Files:**
- Modify: `public-site/package.json` (add test dependencies + script)
- Create: `public-site/src/CommunityPage.test.jsx`

- [ ] **Step 0: Install test infrastructure**

The public-site has NO test runner or testing libraries. Install them and add a test script:

```bash
cd public-site
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom jsdom
```

Then add to `package.json` scripts:

```json
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest"
}
```

And add Vitest config to `vite.config.js` (or create `vitest.config.js`):

```js
// In vite.config.js, add:
export default defineConfig({
  // ... existing config
  test: {
    environment: 'jsdom',
  },
})
```

Verify setup:

```bash
npx vitest run --passWithNoTests
```

Expected: 0 tests, passes cleanly.

Commit:

```bash
git add public-site/package.json public-site/package-lock.json public-site/vite.config.js
git commit -m "chore(public-site): add vitest + testing-library test infrastructure

MOTIVATION: Public site had no test runner; needed for CommunityPage component tests

CHANGES:
- package.json: Add vitest, @testing-library/react, jsdom as devDependencies
- vite.config.js: Add test.environment = 'jsdom'"
```

- [ ] **Step 1: Write CommunityPage component tests**

Create `public-site/src/CommunityPage.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CommunityPage from './CommunityPage'

const mockCommunity = {
  id: 'comm-1',
  name: 'Test Builders',
  slug: 'test-builders',
  color: '#9b59b6',
  description: 'A test community of builders.',
  featured_members: [
    {
      username: 'builder1',
      display_name: 'Builder One',
      bio: 'Building things',
      weight: 0.93,
      tweets: [
        {
          id: 'tw1',
          text: 'Just launched something cool',
          created_at: '2025-01-15T10:00:00Z',
          type: 'tweet',
          favorite_count: 100,
          retweet_count: 20,
        },
        {
          id: 'tw2',
          text: 'Thread about building 1/',
          created_at: '2025-01-16T10:00:00Z',
          type: 'thread',
          favorite_count: 200,
          retweet_count: 50,
        },
      ],
    },
    {
      username: 'builder2',
      display_name: 'Builder Two',
      bio: 'Also building',
      weight: 0.87,
      tweets: [],
    },
  ],
  all_members: [
    { username: 'member3', display_name: 'Member Three', bio: 'A member' },
    { username: 'member4', display_name: 'Member Four', bio: 'Another member' },
  ],
}

const mockCommunities = [
  mockCommunity,
  { id: 'comm-2', name: 'Other Community', slug: 'other-community', color: '#e74c3c' },
]

describe('CommunityPage', () => {
  it('renders community name and description', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    expect(screen.getByText('Test Builders')).toBeTruthy()
    expect(screen.getByText('A test community of builders.')).toBeTruthy()
  })

  it('renders featured member spotlights', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    expect(screen.getByText('@builder1')).toBeTruthy()
    expect(screen.getByText('@builder2')).toBeTruthy()
  })

  it('renders tweets with type badges', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    expect(screen.getByText('Just launched something cool')).toBeTruthy()
    expect(screen.getByText('Thread about building 1/')).toBeTruthy()
  })

  it('renders view-on-X links with correct URLs', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    const xLinks = screen.getAllByText('↗ view on X')
    expect(xLinks.length).toBe(2)
    expect(xLinks[0].closest('a').href).toContain('x.com/builder1/status/tw1')
  })

  it('renders all members grid', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    expect(screen.getByText('@member3')).toBeTruthy()
    expect(screen.getByText('@member4')).toBeTruthy()
  })

  it('shows correct browseable count', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    // 2 featured + 2 all_members = 4
    expect(screen.getByText('4 members')).toBeTruthy()
  })

  it('calls onMemberClick when handle clicked', () => {
    const onMemberClick = vi.fn()
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={onMemberClick}
        onCommunityClick={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('@builder1'))
    expect(onMemberClick).toHaveBeenCalledWith('builder1')
  })

  it('calls onBack when back link clicked', () => {
    const onBack = vi.fn()
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={onBack}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('← Back to Find My Ingroup'))
    expect(onBack).toHaveBeenCalled()
  })

  it('renders sibling community nav', () => {
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )
    expect(screen.getByText('Other Community')).toBeTruthy()
  })

  it('calls onCommunityClick for sibling nav', () => {
    const onCommunityClick = vi.fn()
    render(
      <CommunityPage
        community={mockCommunity}
        communities={mockCommunities}
        onBack={vi.fn()}
        onMemberClick={vi.fn()}
        onCommunityClick={onCommunityClick}
      />
    )
    fireEvent.click(screen.getByText('Other Community'))
    expect(onCommunityClick).toHaveBeenCalledWith('other-community')
  })
})
```

- [ ] **Step 2: Run tests**

Run: `cd public-site && npx vitest run src/CommunityPage.test.jsx`
Expected: All tests PASS

Note: If `@testing-library/react` is not installed, run `npm install --save-dev @testing-library/react @testing-library/jest-dom` first.

- [ ] **Step 3: Commit**

```bash
git add public-site/src/CommunityPage.test.jsx
git commit -m "test(ui): add CommunityPage component tests

CHANGES:
- public-site/src/CommunityPage.test.jsx: 10 tests covering rendering, navigation, cross-linking

TESTING: 10 tests all passing"
```

---

## Task 10: Final Verification and Cleanup

- [ ] **Step 1: Run all backend tests**

```bash
.venv/bin/python3 -m pytest tests/test_export_public_site.py -v
```

Expected: All tests pass (existing + ~24 new)

- [ ] **Step 2: Run all frontend tests**

```bash
cd public-site && npx vitest run
```

Expected: All tests pass

- [ ] **Step 3: Build production bundle**

```bash
cd public-site && npm run build
```

Expected: Build succeeds, `dist/` populated

- [ ] **Step 4: Update ROADMAP.md**

Add under completed items or current features:
```
- Community detail pages: clickable community names → spotlight pages with prototypical members and their tweets
```

- [ ] **Step 5: Final commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: update roadmap with community detail pages feature

CHANGES:
- docs/ROADMAP.md: Note community detail pages as completed"
```
