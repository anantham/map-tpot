# Data Layer — Persistence, Caching & Feed Signals

<!--
Last verified: 2026-03-05
Code hash: bb8bf98
Verified by: agent
-->

## Purpose

The `src/data/` package is the persistence layer for all non-golden data. It has four
independent concerns:

| Concern | Module(s) | Backend |
|---------|-----------|---------|
| Shadow graph storage | `shadow_store.py` | SQLite via SQLAlchemy |
| Archive blob import | `blob_importer.py` | SQLite (direct) + httpx |
| Supabase REST cache | `fetcher.py` | SQLite via SQLAlchemy |
| Extension feed signals | `feed_signals.py`, `feed_scope_policy.py` | SQLite (direct) |
| Account tagging | `account_tags.py` | SQLite (direct) |
| Golden curation | `golden/` subpackage | SQLite (direct) — see [`golden.md`](golden.md) |

The golden subpackage is documented separately. `golden_store.py` is a 10-line re-export
facade that surfaces `GoldenStore` and its constants from `src.data.golden`.

## Design Rationale

### Why SQLite everywhere?

All stores are single-process, file-backed SQLite. There is no shared network DB. This
keeps the dev loop friction-free (no service to start), keeps data portable (files on disk),
and avoids connection pool complexity for a workload that is predominantly read-heavy with
infrequent writes. WAL mode is enabled on all stores to allow concurrent reads alongside
writes.

### Why separate stores rather than one big DB?

Each store owns a distinct domain with different write patterns and lifecycle. Shadow data
is written by long-running enrichment jobs. Feed signals are written by the extension
ingest endpoint (high-frequency small writes). Golden curation is written by a human
labeler. Separating them prevents schema migrations in one domain from affecting another
and makes backup/restore per-domain straightforward.

### Why a merge strategy for archive imports?

Community Archive blobs are complete snapshots (full follower/following lists) but may be
months old. Shadow enrichment data is fresher but incomplete. The `blob_importer.py` merge
strategy (timestamp / archive_only / shadow_only) lets operators choose per-import which
source wins on conflict.

---

## `ShadowStore` — `shadow_store.py` (1,252 LOC)

Canonical persistence for all shadow graph data: accounts discovered during enrichment,
directed edges between them, list memberships, and per-run scrape metrics.

> **Note:** 1,252 LOC exceeds the ~300 LOC convention threshold. The file passes the
> single-domain test (all shadow graph persistence), so it is not split — but it is a
> candidate for concern-level decomposition if needed: `account_ops.py`, `edge_ops.py`,
> `list_ops.py`, `metrics_ops.py`.

### Schema

| Table | PK | Purpose |
|-------|----|---------|
| `shadow_account` | `account_id` | Account metadata (profile, counts, is_shadow flag) |
| `shadow_edge` | `(source_id, target_id, direction)` | Directed follow edges with weight and metadata JSON |
| `shadow_discovery` | `(shadow_account_id, seed_account_id)` | Which seed account discovered which shadow account |
| `shadow_list` | `list_id` | Twitter list snapshot metadata |
| `shadow_list_member` | `(list_id, member_account_id)` | List membership |
| `scrape_run_metrics` | `id` (autoincrement) | Per-seed run metrics with phase timings JSON |

### Key Dataclasses

```python
@dataclass
class ShadowAccount:
    account_id: str
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    followers_count: Optional[int]
    following_count: Optional[int]
    source_channel: str        # "selenium" | "x_api" | "archive"
    fetched_at: str            # ISO-8601
    is_shadow: bool = True
    # ... location, website, profile_image_url, scrape_stats

@dataclass
class ShadowEdge:
    source_id: str
    target_id: str
    direction: str             # "following" | "followers"
    source_channel: str
    weight: float = 1.0
    fetched_at: str            # ISO-8601

@dataclass
class ScrapeRunMetrics:
    seed_account_id: str
    seed_username: str
    run_at: str
    duration_seconds: float
    following_captured: int
    followers_captured: int
    claimed totals + coverage percentages
    accounts_upserted: int
    edges_upserted: int
    phase_timings: dict        # JSON — per-phase elapsed seconds
```

### Public Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `upsert_accounts(accounts)` | `int` | Insert/update accounts; returns count upserted |
| `fetch_accounts(account_ids)` | `List[dict]` | Fetch account records by ID list |
| `unresolved_accounts(account_ids)` | `List[str]` | IDs not yet in DB |
| `is_seed_profile_complete(account_id)` | `bool` | Has location, website, avatar, counts, joined_date |
| `upsert_edges(edges)` | `int` | Insert new edges; returns count of **new** edges only |
| `fetch_edges(direction)` | `List[dict]` | All edges for a direction |
| `edge_summary_for_seed(account_id)` | `Dict[str, int]` | following/followers/total counts |
| `upsert_discoveries(discoveries)` | `int` | Track which seed discovered which account |
| `get_last_scrape_metrics(seed_account_id)` | `Optional[ScrapeRunMetrics]` | Most recent run for seed |
| `get_recent_scrape_runs(days)` | `List[ScrapeRunMetrics]` | All runs in last N days |
| `get_account_id_by_username(username)` | `Optional[str]` | Username → account_id lookup |
| `get_following_usernames(username)` | `List[str]` | All usernames this account follows |
| `upsert_lists(lists)` | `int` | Insert/update list metadata |
| `replace_list_members(list_id, members)` | `int` | Atomically replace all members of a list |
| `record_scrape_metrics(metrics)` | `int` | Persist a ScrapeRunMetrics record |
| `sync_archive_overlaps()` | `int` | Merge archive + shadow data by timestamp |

### Design Notes

- **Edge upsert counts new rows only** — uses a pre-check `tuple_ IN` query to determine
  which edges are genuinely new before inserting; the return value reflects actual DB changes.
- **Retry with backoff** — all write operations retry up to 3 times on `OperationalError`
  ("database is locked", "disk i/o error") with exponential backoff.
- **Schema migrations on init** — `_migrate_schema()` adds columns to existing tables
  (`list_members_captured`, `phase_timings`, etc.) using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- **Archive overlap sync** — `sync_archive_overlaps()` merges archive profile data into
  `shadow_account` rows, preferring the more recent `fetched_at` timestamp.

---

## `BlobStorageImporter` — `blob_importer.py` (663 LOC)

Imports Community Archive JSON blobs from Supabase blob storage into local SQLite tables.
Handles merge conflicts between stale archive data and fresher shadow enrichment data via
a configurable merge strategy.

### Schema (written by this module)

| Table | PK | Purpose |
|-------|----|---------|
| `archive_following` | `(account_id, following_account_id)` | Accounts this one follows |
| `archive_followers` | `(account_id, follower_account_id)` | Accounts following this one |
| `archive_profiles` | `account_id` | Profile metadata (bio, website, location, avatar) |
| `archive_tweets` | `(account_id, tweet_id)` | Top 20 liked + 10 most recent tweets per account |
| `archive_likes` | `(account_id, tweet_id)` | All liked tweets |

All tables include `uploaded_at` (from HTTP `Last-Modified` header) and `imported_at` timestamps.

### Public Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `list_archives()` | `List[str]` | All importable usernames from the account table |
| `fetch_archive(username)` | `Optional[tuple[Dict, Optional[datetime]]]` | Fetch JSON blob + upload timestamp |
| `import_archive(username, merge_strategy, dry_run)` | `Optional[ArchiveMetadata]` | Import one account |
| `import_all_archives(merge_strategy, dry_run, max_archives, force_reimport)` | `List[ArchiveMetadata]` | Batch import |

### Merge Strategies

| Strategy | Behavior |
|----------|----------|
| `"timestamp"` (default) | Prefer the record with the newer `uploaded_at` / `fetched_at` |
| `"archive_only"` | Archive blob always wins on conflict |
| `"shadow_only"` | Shadow enrichment data always wins on conflict |

### Design Notes

- **Selective tweet import** — imports top 20 liked tweets + 10 most recent per account
  (deduplicated). Full `archive_likes` table stores all liked tweets separately.
- **Batch commits** — commits every 500 rows to reduce SQLite lock duration during large imports.
- **Upload timestamp from HTTP header** — extracts `Last-Modified` from the blob HTTP response;
  used as `uploaded_at` to determine merge winner.
- **Idempotent by default** — skips already-imported accounts unless `force_reimport=True`.

---

## `CachedDataFetcher` — `fetcher.py` (347 LOC)

Read-through cache for Community Archive data from the Supabase REST API. Returns cached
DataFrames and falls back to stale cache if a Supabase refresh fails.

### Cache Schema

| Table | Purpose |
|-------|---------|
| `cache_metadata` | Tracks (table_name, fetched_at, row_count) for expiry checks |
| (one table per cached dataset) | `profiles`, `accounts`, `followers`, `following`, `tweets`, `likes` |

### Public Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `fetch_profiles(use_cache, force_refresh)` | `pd.DataFrame` | Account profile rows |
| `fetch_accounts(use_cache, force_refresh)` | `pd.DataFrame` | Account rows |
| `fetch_followers(use_cache, force_refresh)` | `pd.DataFrame` | Follower edges |
| `fetch_following(use_cache, force_refresh)` | `pd.DataFrame` | Following edges |
| `fetch_tweets(use_cache, force_refresh)` | `pd.DataFrame` | Tweet rows |
| `fetch_likes(use_cache, force_refresh)` | `pd.DataFrame` | Like rows |
| `fetch_archive_following()` | `pd.DataFrame` | Reads from local `archive_following` table (not REST) |
| `fetch_archive_followers()` | `pd.DataFrame` | Reads from local `archive_followers` table (not REST) |
| `cache_status()` | `Dict` | Per-table: fetched_at, row_count, age_days, is_expired |

### Design Notes

- **Stale-on-failure** — if Supabase refresh fails, logs a warning and returns the stale
  cached DataFrame rather than raising. This keeps the app usable when offline.
- **Configurable TTL** — `max_age_days` comes from `CacheSettings` in `src/config.py`.
- **Range requests** — fetches up to 999,999 rows per table via Supabase REST `Range` header.

---

## `FeedSignalsStore` — `feed_signals.py` (293 LOC)

Stores impressions and tweet context captured by the Chrome extension as accounts appear
in the user's Twitter feed.

### Schema

| Table | PK | Purpose |
|-------|----|---------|
| `feed_events` | `event_key` (SHA1) | Raw extension events, deduplicated |
| `feed_tweet_rollup` | `(workspace_id, ego, account_id, tweet_id)` | Aggregated per-account/tweet counts |

**Dedup key** (`event_key`): `SHA1(workspace_id | ego | account_id | tweet_id | seen_at | surface | position | tweet_text[:64])`

### Public Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `ingest_events(workspace_id, ego, events, collect_inserted_keys)` | `Dict` | Bulk ingest; returns `{inserted, duplicates, failed}` |
| `account_summary(workspace_id, ego, account_id, days, keyword_limit, sample_limit)` | `Dict` | Per-account exposure stats |
| `top_exposed_accounts(workspace_id, ego, days, limit)` | `List[Dict]` | Most-seen accounts in feed |

### Design Notes

- **Accepts both camelCase and snake_case** field names from the extension payload.
- **Rollup uses `ON CONFLICT` with `MIN`/`MAX`** — `first_seen_at`, `last_seen_at`, and
  `seen_count` are updated atomically without a read-modify-write cycle.

---

## `FeedScopePolicyStore` — `feed_scope_policy.py` (269 LOC)

Stores per-(workspace, ego) ingestion policy: what the extension is allowed to capture,
whether a firehose relay is active, and allowlist filtering rules.

### Policy Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ingestion_mode` | `"open"` \| `"guarded"` | `"open"` | Open = all feed events; guarded = allowlist only |
| `retention_mode` | `"infinite"` | `"infinite"` | Data retention policy |
| `allowlist_enabled` | `bool` | `False` | Enforce allowlist filtering |
| `allowlist_accounts` | `List[str]` | `[]` | Account IDs allowed when guarded |
| `allowlist_tags` | `List[str]` | `[]` | Tags controlling inclusion |
| `firehose_enabled` | `bool` | `True` | Relay to firehose relay subprocess |
| `firehose_path` | `Optional[str]` | `None` | Unix socket path for firehose relay |

### Public Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_policy(workspace_id, ego)` | `FeedScopePolicy` | Fetch policy; returns default if not found |
| `upsert_policy(workspace_id, ego, **fields)` | `FeedScopePolicy` | Partial upsert — only provided fields update |

---

## `AccountTagStore` — `account_tags.py` (265 LOC)

Semantic account tags scoped by ego. Tags have polarity (`+1` = in-group, `-1` = excluded)
and optional confidence, supporting anchor-conditioned TPOT membership (ADR-006).

### Schema

| Table | PK | Purpose |
|-------|----|---------|
| `account_tags` | `(ego, account_id, tag_key)` | Tag assignments; key stored casefolded |

### Public Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `list_tags(ego, account_id)` | `List[AccountTag]` | All tags for an account |
| `list_distinct_tags(ego)` | `List[str]` | All unique tags for an ego (for autocomplete) |
| `list_account_ids_for_tag(ego, tag)` | `List[str]` | Accounts positively tagged |
| `list_account_ids_for_tags(ego, tags)` | `List[str]` | Accounts tagged with any of the given tags |
| `list_tags_for_accounts(ego, account_ids)` | `List[AccountTag]` | Bulk tag fetch (batched to stay under SQLite 900-var limit) |
| `list_anchor_polarities(ego)` | `List[tuple[str, int]]` | Per-account net polarity (`sign(sum(polarity))`) |
| `upsert_tag(ego, account_id, tag, polarity, confidence)` | `AccountTag` | Insert or update tag |
| `delete_tag(ego, account_id, tag)` | `bool` | Remove tag; returns True if found |

### Design Notes

- **Casefolded keys, preserved display** — `tag_key` is lowercased for consistent lookups;
  `tag_display` preserves original capitalization for UI rendering.
- **Anchor polarity** — `list_anchor_polarities()` aggregates net polarity per account:
  `+1` if positive tags outweigh negative, `-1` if reverse, omitted if tied. Used by the
  spectral clustering pipeline to condition membership inference (ADR-006).
- **Batching** — `list_tags_for_accounts()` splits account_ids into chunks of 900 to stay
  under SQLite's variable limit.

---

## Dependencies Map

```
shadow_store.py      ← sqlalchemy, stdlib only
blob_importer.py     ← httpx, pandas, sqlalchemy, stdlib
fetcher.py           ← httpx, pandas, sqlalchemy, src.config
feed_signals.py      ← src.data.feed_signals_queries, stdlib
feed_scope_policy.py ← stdlib only
account_tags.py      ← stdlib only
golden_store.py      ← src.data.golden (re-export only)
```

---

## Common Patterns

All stores in this package follow the same conventions:

| Pattern | Implementation |
|---------|---------------|
| WAL mode | `PRAGMA journal_mode=WAL` on connection open |
| Retry on lock | `OperationalError` → up to 3 retries with exponential backoff |
| Schema migration on init | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `_migrate_schema()` |
| JSON for flexible metadata | `metadata` / `phase_timings` / `allowlist_*` stored as JSON strings |
| ISO-8601 timestamps | All `*_at` columns are UTC ISO-8601 strings |
| camelCase in API responses | Conversion happens in route handlers, not in stores |
