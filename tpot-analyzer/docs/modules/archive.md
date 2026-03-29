# Archive Module — Community Archive Fetch & Storage

<!--
Last verified: 2026-03-05
Code hash: bb8bf98
Verified by: agent
-->

## Purpose

The `src/archive/` package fetches Twitter/X account archives from Community Archive
Supabase blob storage, parses them, and persists the results into `archive_tweets.db`.
It also provides a supplementary thread-context fetcher (twitterapi.io) for retrieving
reply chains outside the scraped account network.

The archive is the **primary source of tweet text and historical follow graphs** — the
shadow enrichment layer (`src/shadow/`) provides fresher follow-edge data, but the archive
has historical tweets and likes that shadow scraping does not.

## Module Map

```
src/archive/
├── __init__.py        (0 LOC)  — empty package marker
├── fetcher.py       (142 LOC)  — download archive JSON from Supabase (streaming + cache)
├── store.py         (361 LOC)  — parse archive JSON and persist to archive_tweets.db
└── thread_fetcher.py (115 LOC) — fetch reply thread context from twitterapi.io (cost-aware)
```

**Total: 618 LOC.** No internal cross-module imports — fully decoupled from the rest of `src/`.

## Design Rationale

### Why streaming downloads with atomic caching?

Community archive blobs can be large. `fetcher.py` streams in 64KB chunks to avoid
holding the full archive in RAM. The download goes to a temp file and is atomically
renamed on success, so an interrupted download never leaves a corrupt cache file.

### Why store retweets separately?

`store.py` skips retweet text from the `tweets` table ("not their words") but captures
retweet metadata in a separate `retweets` table. This preserves the amplification signal
(who they retweeted, when) without misattributing content to the account.

### Why a thread context cache?

The golden curation labeling UI shows reply context to help human annotators understand
a tweet's meaning. Thread context requires a paid API call (~$0.15/1000). Caching every
result in SQLite means each thread is fetched at most once, making the cost predictable.

---

## `fetcher.py` — Archive download

```python
from src.archive.fetcher import fetch_archive

archive = fetch_archive(
    username="example_user",
    cache_dir=Path("data/archive_cache"),   # optional; None = no disk cache
    force_refresh=False,
)
# Returns: dict (parsed archive JSON) | None (no archive for this account)
```

**Retry behaviour:** 4 attempts with exponential backoff (2s, 4s, 8s, 16s).
HTTP 400/404 are treated as "no archive exists" and not retried.

**Cache:** If `cache_dir` is provided and a cached file exists, it is returned immediately
unless `force_refresh=True`.

---

## `store.py` — Archive persistence

```python
from src.archive.store import store_archive, log_fetch_error, log_not_found

summary = store_archive(
    db_path=Path("data/archive_tweets.db"),
    archive=archive_dict,
    account_id="12345678",
    username="example_user",
)
# Returns: {"tweet_count": 342, "like_count": 1204, "following_count": 180, ...}
```

### Database schema (`archive_tweets.db`)

| Table | PK | Purpose |
|-------|----|---------|
| `tweets` | `tweet_id` | Original tweets, replies, note-tweets, community-tweets (no retweets) |
| `likes` | `(liker_account_id, tweet_id)` | Liked tweets |
| `retweets` | `tweet_id` | Retweet metadata (amplification signal only, no RT text) |
| `profiles` | `account_id` | Profile metadata (bio, location, website, created_at) |
| `account_following` | `(account_id, following_account_id)` | Who this account follows |
| `account_followers` | `(account_id, follower_account_id)` | Who follows this account |
| `thread_context_cache` | `tweet_id` | Cached thread context from twitterapi.io |
| `fetch_log` | `username` | One row per account: status, counts, errors |

All `fetched_at` columns are ISO 8601 UTC strings. All writes use `INSERT OR IGNORE`
(idempotent re-runs). Schema is self-initializing — `_open()` runs the full `CREATE TABLE IF NOT EXISTS` block on every connection.

**Thread safety:** A global `_db_lock` serializes all writes in `store.py`. The lock is
per-process; do not share the same `archive_tweets.db` across multiple processes without
external coordination.

### Public functions

| Function | Returns | Description |
|----------|---------|-------------|
| `store_archive(db_path, archive, account_id, username)` | `dict` | Parse and insert one account's archive; returns count summary |
| `log_fetch_error(db_path, username, account_id, error)` | — | Record fetch failure in `fetch_log` |
| `log_not_found(db_path, username, account_id)` | — | Record "not_found" status in `fetch_log` |

---

## `thread_fetcher.py` — Thread context (cost-aware)

Fetches the reply chain for a tweet from twitterapi.io. Used exclusively by the golden
curation labeling pipeline to provide context for reply tweets.

```python
from src.archive.thread_fetcher import get_thread_context, format_thread_for_prompt

tweets = get_thread_context(
    tweet_id="1234567890",
    db_path=Path("data/archive_tweets.db"),
    force_refresh=False,
)
# Returns: List[dict] ordered from top of thread | None on error

prompt_text = format_thread_for_prompt(tweets, target_tweet_id="1234567890")
# Returns: formatted string with "← CLASSIFY THIS" marker on target tweet
```

**Cost:** ~$0.03 per call to twitterapi.io (~3000 credits, 2M credits/$20). Results are cached in
`thread_context_cache` (same `archive_tweets.db`) — each thread is fetched at most once.

**API key resolution:** checks `TWITTERAPI_IO_API_KEY`, then `TWITTERAPI_API_KEY`, then
`API_KEY` environment variables. Returns `None` silently if no key is found.

**Failure mode:** Returns `None` on any API error and logs details. Does not raise — the
labeling UI degrades gracefully to empty thread context.

---

## Dependency Map

```
scripts/fetch_archive_data.py
  └── fetcher.fetch_archive()
  └── store.store_archive() / log_fetch_error() / log_not_found()

src/api/routes/golden.py
  └── thread_fetcher.get_thread_context()
  └── thread_fetcher.format_thread_for_prompt()

src/data/golden/base.py
  └── reads archive_tweets.db directly (tweets table, thread_context_cache)

src/data/fetcher.py
  └── reads archive_following / archive_followers tables (not a direct import)
```

The archive module has **no imports from other `src/` modules** — it only depends on
`httpx` and the standard library. All callers depend on it; it depends on nothing.

---

## Known Limitations

- **No incremental update** — `store_archive()` is a full re-import per account; there is
  no delta/patch mechanism for new tweets since last import.
- **Hardcoded Supabase URL** — `fetcher.py` has the Supabase project URL and anon key
  hardcoded. If the Community Archive migrates storage, these need updating.
- **Global lock scope** — `_db_lock` in `store.py` serializes all writers in the process.
  Fine for single-threaded scripts; a bottleneck if parallelised with threads (use
  multiprocessing + separate DB files instead).
