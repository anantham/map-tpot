# Archive Module — Community Archive Fetch & Storage

<!--
Last verified: 2026-07-26
Verified by: agent
-->

## Purpose

The `src/archive/` package fetches Twitter/X account archives from Community Archive
Supabase blob storage, parses them, and persists the results into `archive_tweets.db`.
It also acquires validated, versioned snapshots of the mutable Community Archive
enriched-tweet Parquet export and provides a supplementary thread-context fetcher
(twitterapi.io) for retrieving reply chains outside the scraped account network.

The archive is the **primary source of tweet text and historical follow graphs** — the
shadow enrichment layer (`src/shadow/`) provides fresher follow-edge data, but the archive
has historical tweets and likes that shadow scraping does not.

## Module Map

```
src/archive/
├── __init__.py          — package marker
├── fetcher.py           — per-account archive JSON download and cache
├── snapshot.py          — remote probe and validated atomic bulk download
├── snapshot_contract.py — snapshot constants and human-facing check records
├── snapshot_dataset_validation.py — dataset count/schema/sample invariants
├── snapshot_manifest.py — Parquet inspection and no-clobber manifest creation
├── snapshot_validation.py — structural, identity, hash, and metric validation
├── snapshot_workflow.py — download/reuse orchestration and commit-marker rules
├── store.py             — parse archive JSON and persist to archive_tweets.db
└── thread_fetcher.py    — fetch reply thread context from twitterapi.io (cost-aware)
```

The snapshot modules depend only on each other plus `httpx` and `pyarrow`. The
package otherwise remains decoupled from application modules outside
`src/archive/`.

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

**Retry behaviour:** Up to four attempts, with 2s, 4s, and 8s waits before
the three retries. HTTP 400/404 are treated as "no archive exists" and not
retried.

**Cache:** If `cache_dir` is provided and a cached file exists, it is returned immediately
unless `force_refresh=True`.

---

## `snapshot.py` and `snapshot_manifest.py` — Versioned bulk snapshots

The official enriched-tweet export is a mutable object:

`https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/enriched_tweets/enriched_tweets.parquet`

The snapshot layer records each observed version under
`data/community_archive/snapshots/<snapshot_id>/` instead of replacing the
project's frozen baseline. The ID is derived from the source URL and available
`ETag`, `Last-Modified`, and `Content-Length` validators.

Acquisition probes metadata first and enforces a hard byte cap before a GET.
The response streams into a unique temporary file while computing SHA-256. An
`ETag`, `Last-Modified`, or length change, an incomplete byte count, an exceeded
streaming cap, or an HTTP failure aborts the operation and removes the partial
file. A successful file is flushed, `fsync`ed, and atomically published without
overwriting an existing snapshot.

`snapshot_manifest.py` then checks the expected Parquet columns and records:

- row and distinct-account counts;
- full column inventory;
- minimum and maximum tweet `created_at`;
- rows linked to an archive upload versus rows with no upload ID;
- source validators, local byte size, and SHA-256; and
- acquisition Git SHA and dirty state.

`manifest.json` is written atomically **after** the data is complete and
inspected, and neither data nor manifest publication overwrites an existing
file. Its presence is the commit marker: consumers must treat a directory with
no valid manifest as incomplete. See
[ADR 019](../adr/019-versioned-research-data-and-artifact-manifests.md).

This bulk snapshot currently covers enriched tweets, not following/follower
topology. Per-account archive refresh remains a separate workflow.

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

All `fetched_at` columns are ISO 8601 UTC strings. Tweets, likes, retweets,
following, and follower rows use `INSERT OR IGNORE`, so a duplicate primary key
keeps the earlier stored values. Profiles and `fetch_log` use
`INSERT OR REPLACE`, so the latest import replaces those rows. The returned count
summary describes parsed input rows, not necessarily newly inserted rows.
Schema is self-initializing — `_open()` runs the full
`CREATE TABLE IF NOT EXISTS` block on every connection.

**Writer coordination:** `store.py` declares `_db_lock`, but current write paths
do not acquire it. SQLite is opened in WAL mode with a 60-second connection
timeout; there is no application-level serialization of concurrent writers.
Callers must coordinate parallel imports and must not rely on `_db_lock`.

Relationship imports are non-destructive. A following/follower row missing from
a later archive is not deleted, because absence is not evidence of an explicit
relationship end. These tables therefore represent accumulated observed edges,
not a guaranteed current-state graph.

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

The archive package has **no dependencies on application modules outside
`src/archive/`**. Its acquisition path uses `httpx` and `pyarrow`; persistence and
per-account parsing use SQLite and the standard library.

---

## Known Limitations

- **Append/replace rather than current-state sync** — `store_archive()` is a full
  parse per account, but duplicate content/relationship keys are ignored,
  profiles and fetch status are replaced, and absent relationships are retained.
- **Hardcoded Supabase URL** — `fetcher.py` has the Supabase project URL and anon key
  hardcoded. If the Community Archive migrates storage, these need updating.
- **Per-account cache freshness** — cached JSON is reused indefinitely unless
  `force_refresh=True`; it does not record `ETag`, `Last-Modified`, content
  length, or SHA-256.
- **No application writer lock** — `_db_lock` is currently unused. Parallel
  callers require explicit coordination.
- **Bulk snapshot is tweet-only** — the versioned Parquet path does not refresh
  following/follower topology or make relationship tables point-in-time exact.
