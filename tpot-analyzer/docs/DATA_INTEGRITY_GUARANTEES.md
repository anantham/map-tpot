# Data Integrity Guarantees

<!-- staleness-marker: src/data/blob_importer.py -->
<!-- staleness-marker: src/data/fetcher.py -->
<!-- staleness-marker: src/data/shadow_store.py -->
<!-- last-verified: 2026-02-27 -->

## Overview

The TPOT data layer uses SQLite (via SQLAlchemy) as its local cache. Data flows from three sources into a single `data/cache.db` file. This document describes the integrity guarantees each layer provides.

## Data Sources

```
Supabase REST API ──→ CachedDataFetcher ──→ cache.db (account, profile, followers, following)
Supabase Blob     ──→ BlobStorageImporter ──→ cache.db (archive_following, archive_followers, ...)
Selenium/X API    ──→ ShadowStore         ──→ cache.db (shadow_account, shadow_edge, ...)
```

---

## 1. Transaction Model

### CachedDataFetcher (`src/data/fetcher.py`)

| Property | Guarantee | Mechanism |
|----------|-----------|-----------|
| Atomicity | Per-table replacement | `if_exists="replace"` via pandas `to_sql` |
| Isolation | SQLAlchemy connection pool | Default pool size 5 |
| Durability | SQLite WAL mode | Not explicitly enabled (default journal mode) |
| Metadata consistency | Atomic update | `engine.begin()` for metadata writes |

**Cache replacement strategy:** Full table overwrite (not incremental). Each `_fetch_dataset()` call replaces the entire cached table with fresh data from Supabase.

**Metadata tracking:**
```sql
cache_metadata (table_name TEXT PK, fetched_at DATETIME, row_count INTEGER)
```

Old metadata is deleted before inserting new records, ensuring a single entry per table.

### BlobStorageImporter (`src/data/blob_importer.py`)

| Property | Guarantee | Mechanism |
|----------|-----------|-----------|
| Atomicity | Per-batch (500 rows) | `conn.commit()` every `BATCH_COMMIT_SIZE` rows |
| Conflict resolution | Last-write-wins | `INSERT OR REPLACE` |
| Concurrency | WAL mode | Enabled on context manager entry |
| Durability | Explicit commits | After each batch + final commit |

**Batch commit strategy:** Commits every 500 rows to reduce lock duration. A crash mid-import loses at most the current batch (≤500 rows).

**Skip logic:** Archives already in the database are skipped unless `force_reimport=True`. Checks existence via `SELECT COUNT(*) FROM archive_following WHERE account_id = ?`.

### ShadowStore (`src/data/shadow_store.py`)

| Property | Guarantee | Mechanism |
|----------|-----------|-----------|
| Atomicity | Per-operation | `engine.begin()` for writes |
| Conflict resolution | COALESCE (preserve non-NULL) | `func.coalesce(excluded[col], existing[col])` |
| Concurrency | Retry with backoff | 3 attempts, exponential backoff (1s, 2s, 4s) |
| Durability | Explicit begin/commit | SQLAlchemy `engine.begin()` context |

**COALESCE upsert strategy:** When updating an account, existing non-NULL values are preserved. New data only fills in previously NULL fields. This prevents accidental overwrites from partial scrapes.

```python
# Example: existing record has bio="ML researcher", new scrape has bio=None
# Result: bio remains "ML researcher" (COALESCE keeps existing non-NULL)
stmt = insert(table).on_conflict_do_update(
    index_elements=['account_id'],
    set_={col: func.coalesce(stmt.excluded[col], table.c[col])}
)
```

---

## 2. Retry & Error Handling

### Retryable Errors

All data modules handle transient SQLite errors with retry logic:

| Module | Max Retries | Backoff | Retryable Errors |
|--------|-------------|---------|------------------|
| BlobStorageImporter | 3 | 2^n seconds (2, 4, 8) | `"disk I/O error"` |
| ShadowStore | 3 | 2^n seconds (1, 2, 4) | `"disk i/o error"`, `"database is locked"` |
| CachedDataFetcher | 0 | N/A | None (re-raises immediately) |

### Connection Pool Reset

After retryable errors, `engine.dispose()` is called to reset the SQLAlchemy connection pool. This forces new connections on the next attempt.

### Non-Retryable Errors

| Error | Module | Behavior |
|-------|--------|----------|
| HTTP 404 | BlobStorageImporter | Archive not found, skipped |
| HTTP 400 | BlobStorageImporter | Bad request, added to permanent_failures list |
| `RuntimeError` | CachedDataFetcher | Missing Supabase config, raised immediately |
| JSON parse error | ShadowStore | Returns None for affected record |

---

## 3. Deduplication

### Edge Deduplication

**BlobStorageImporter:** Uses `INSERT OR REPLACE` with UNIQUE constraints on staging tables:
- `archive_following`: UNIQUE(account_id, following_account_id)
- `archive_followers`: UNIQUE(account_id, follower_account_id)

**ShadowStore:** Pre-checks existence before upsert:
```python
# Count existing edges with tuple-based IN clause
existing_keys = set(
    (row.source_id, row.target_id, row.direction)
    for row in conn.execute(select_stmt)
)
new_edges = [e for e in edges if (e.source_id, e.target_id, e.direction) not in existing_keys]
```

**Graph builder:** NetworkX's `add_edge()` naturally deduplicates (later calls overwrite).

### Account Deduplication

**ShadowStore:** Provides `_merge_duplicate_accounts()` for consolidating accounts with different IDs (e.g., `"shadow:alice"` → `"12345"`):
1. Reassign all edges from old_id to canonical_id
2. Reassign all discoveries from old_id to canonical_id
3. Delete the duplicate account record

### Tweet Deduplication

**BlobStorageImporter:** When importing tweets, top-20 by likes and 10 most recent are combined and deduplicated by `tweet_id`:
```python
tweets_to_import = {t["tweet_id"]: t for t in (top_liked + recent) if t["tweet_id"]}
```

---

## 4. Cache Expiry & Freshness

### REST API Cache (CachedDataFetcher)

| Parameter | Default | Source |
|-----------|---------|--------|
| `max_age_days` | 7 | `CACHE_MAX_AGE_DAYS` env var |

**Expiry check:** Compares `cache_metadata.fetched_at` against current UTC time. Data older than `max_age_days` triggers a re-fetch from Supabase.

**Timezone handling:** `fetched_at` is stored as UTC. The expiry check converts to UTC before comparison.

### Snapshot Staleness (SnapshotLoader)

Two-phase staleness detection:

**Phase 1 - Age check:**
```python
age = datetime.utcnow() - manifest.generated_at
return age.total_seconds() > max_age_seconds  # default: 86400 (24h)
```

**Phase 2 - Data change detection:**
```python
# Query current SQLite row counts
for table in ["account", "profile", "followers", "following"]:
    current_counts[table] = SELECT COUNT(*) FROM {table}

# Compare against snapshot manifest
if account_diff >= 100: return True  # 100 new accounts threshold
if profile_diff >= 100: return True  # 100 new profiles threshold
if followers_increase > 10%: return True  # 10% relative increase
if following_increase > 10%: return True  # 10% relative increase
```

**Fallback:** If row counts unavailable (old manifest format), falls back to file mtime comparison.

---

## 5. Concurrency Limits

SQLite has inherent concurrency limitations:

| Operation | Max Concurrent | Mechanism |
|-----------|---------------|-----------|
| Reads | Unlimited | WAL mode allows concurrent reads |
| Writes | 1 | SQLite write lock |
| Write + Read | Supported | WAL mode allows reads during writes |

### WAL Mode

BlobStorageImporter enables WAL mode on context entry:
```python
conn.execute(text("PRAGMA journal_mode=WAL"))
```

Other modules rely on SQLite's default journal mode. WAL provides better read concurrency but requires the `-wal` and `-shm` files to be present.

### Batch Commit Impact

BlobStorageImporter's batch commits (every 500 rows) release the write lock periodically, allowing other readers/writers to proceed. Without batching, a large import (e.g., 100k edges) would hold the write lock for the entire duration.

---

## 6. Known Limitations

### No Cross-Source Consistency

The three data sources (REST, Blob, Shadow) operate independently. There is no transaction that spans multiple sources. This means:

- A blob import and shadow scrape running simultaneously may see inconsistent intermediate states
- Cache freshness for REST data is independent of blob/shadow data freshness
- The graph builder merges all sources at query time (NetworkX deduplicates edges)

### No Rollback on Partial Import

If `import_all_archives()` crashes mid-way through 291 archives:
- Successfully imported archives are committed and retained
- The current archive's uncommitted batch (≤500 rows) is lost
- Re-running with `force_reimport=False` will skip already-imported archives

### SQLite File Lock

When multiple processes access `cache.db` simultaneously:
- Reads: Always succeed (WAL mode)
- Writes: May timeout with `"database is locked"` (retried 3x with backoff)
- Long-running writes (large blob imports): Can block other writers

### No Referential Integrity

SQLite foreign keys are not enabled. Edge references to non-existent accounts are allowed:
- `archive_following.account_id` may reference a non-existent account
- `shadow_edge.source_id` may reference a non-existent shadow_account
- The graph builder handles this by only adding edges between existing graph nodes

---

## 7. Operational Recommendations

### Before Large Imports

1. Stop the API server (releases read locks)
2. Check disk space: `df -h data/` (need ~30GB for full blob import)
3. Backup database: `cp data/cache.db data/cache.db.bak`
4. Enable WAL mode if not already: `sqlite3 data/cache.db "PRAGMA journal_mode=WAL;"`

### After Imports

1. Invalidate API caches: `POST /api/cache/invalidate` + `POST /api/metrics/cache/clear`
2. Regenerate snapshots: `python -m scripts.analyze_graph --refresh-snapshot`
3. Verify data: `python -m scripts.verify_graph_snapshot`

### Monitoring

- Check cache freshness: `GET /api/cache/stats` → `entries[].age_seconds`
- Check snapshot staleness: Read `data/graph_snapshot.meta.json` → `generated_at`
- Check import status: Review importer logs for skip/failure counts
