# ADR 005: Community Archive Blob Storage Import

**Status:** Implemented (Partial - edges only)
**Date:** 2025-11-08
**Deciders:** System architecture

## Context

The Community Archive Supabase REST API has pagination limits (~1000 rows per table), which means we cannot access complete following/follower lists for accounts with large networks. However, Community Archive also provides complete archive data via blob storage at `https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/archives/{username}/archive.json`.

**Problem:** Users with 1000+ following/followers only have partial data via REST API, leading to incomplete graph construction.

**Discovery:** User archives in blob storage contain complete relationship data, plus additional metadata (bio, tweets, likes) not available via REST API.

## Decision

Implement a **3-layer data architecture** that merges data from multiple sources:

1. **REST API** (`src/data/fetcher.py`) - Fresh but limited (1000 rows)
2. **Blob Storage** (`src/data/blob_importer.py`) - Complete but stale (upload date)
3. **Shadow Enrichment** (`src/data/shadow_store.py`) - Expanded network via scraping

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Graph Builder                             │
│                 (src/graph/builder.py)                       │
└──────┬────────────────┬────────────────┬────────────────────┘
       │                │                │
       ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ REST API    │  │ Blob Storage│  │ Shadow      │
│ (fetcher)   │  │ (importer)  │  │ (scraper)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ following   │  │ archive_    │  │ shadow_edge │
│ followers   │  │ following   │  │             │
│ account     │  │ archive_    │  │ shadow_     │
│ profile     │  │ followers   │  │ account     │
└─────────────┘  └─────────────┘  └─────────────┘
```

### Merge Strategy

When building the graph:
1. Load REST API data (fresh, limited)
2. Load archive blob data (complete, stale)
3. Concatenate DataFrames (pandas handles deduplication)
4. Inject shadow enrichment (if enabled)

**Deduplication:** NetworkX naturally deduplicates edges. For attributes, last write wins (shadow data preferred if fresher).

## Implementation

### Blob Importer (`src/data/blob_importer.py`)

**Core class:** `BlobStorageImporter`

**Key methods:**
- `list_archives()` - Get all usernames from account table
- `fetch_archive(username)` - Fetch JSON from blob storage
- `import_archive(username)` - Import single archive to staging tables
- `import_all_archives()` - Bulk import all available archives

**Staging Tables:**
- `archive_following` - Complete following edges with timestamps
- `archive_followers` - Complete follower edges with timestamps
- *(Planned)* `archive_profiles` - Profile metadata (bio, website, location)
- *(Planned)* `archive_tweets` - Top 20 liked + 10 recent tweets
- *(Planned)* `archive_likes` - All liked tweets

**Schema Design:**
- `UNIQUE (account_id, target_id)` constraints prevent duplicates
- `INSERT OR REPLACE` enables idempotent re-imports
- `uploaded_at` tracks archive staleness
- `imported_at` tracks when we fetched from blob

### Graph Builder Integration (`src/graph/builder.py`)

```python
# Fetch REST data (limited)
followers = fetcher.fetch_followers()
following = fetcher.fetch_following()

# Fetch archive data (complete)
if include_archive:
    archive_followers = fetcher.fetch_archive_followers()
    archive_following = fetcher.fetch_archive_following()

    # Merge
    followers = pd.concat([followers, archive_followers])
    following = pd.concat([following, archive_following])

# Build graph (NetworkX deduplicates)
graph = build_graph_from_frames(...)
```

### CLI Tool (`scripts/import_blob_archives.py`)

```bash
# Import specific user
python -m scripts.import_blob_archives --username adityaarpitha

# Import all archives
python -m scripts.import_blob_archives --all

# Dry run (preview without writing)
python -m scripts.import_blob_archives --all --dry-run --max 10
```

## Consequences

### Positive

✅ **Complete relationship data** - No longer limited by REST API pagination
✅ **Zero blast radius** - Staging tables don't affect existing REST tables
✅ **Idempotent imports** - Can re-run safely (UNIQUE constraints)
✅ **Data provenance** - `uploaded_at`/`imported_at` track freshness
✅ **Future-ready** - Can add profile/tweet/likes data later

### Negative

⚠️ **Stale data** - Archives may be months old (trade-off for completeness)
⚠️ **Network overhead** - Fetching 109MB JSON files for large archives
⚠️ **Storage growth** - Archive tables add ~200MB to cache.db
⚠️ **No auto-refresh** - Must manually trigger imports (unlike REST caching)

### Trade-offs

| Dimension | REST API | Blob Storage | Shadow Scraping |
|-----------|----------|--------------|-----------------|
| Freshness | ✅ Fresh (7-day cache) | ⚠️ Stale (upload date) | ✅ Fresh (recent scrape) |
| Completeness | ❌ Limited (1000 rows) | ✅ Complete | ⚠️ Partial (rate limits) |
| Coverage | ~275 accounts | ~279 accounts | Expandable (1000+) |
| Speed | ✅ Fast (cached) | ⚠️ Slow (fetch 100MB) | ❌ Very slow (scraping) |
| Maintenance | ✅ Auto-refresh | ❌ Manual trigger | ❌ Cookie mgmt |

## Open Questions

1. **Timestamp-based merge:** Should we prefer newer data automatically?
   - Current: Simple concatenation (NetworkX deduplicates)
   - Future: Compare `uploaded_at` vs `fetched_at` to keep fresher data

2. **Auto-refresh:** Should blob imports run automatically?
   - Current: Manual trigger via `scripts/import_blob_archives.py`
   - Future: Cron job or API server startup hook?

3. **Partial failures:** How to handle disk I/O errors during bulk imports?
   - Current: Continue with remaining archives, log failures
   - Future: Implement retry logic with exponential backoff?

4. **Profile/tweet/likes:** When to deploy these features?
   - Current: Code exists but tables not created (import failed partway)
   - Future: Re-run import after fixing I/O issues or add separate import command

## Status (2025-11-08)

**Deployed:**
- ✅ `archive_following` (158,423 edges from 126 archives)
- ✅ `archive_followers` (323,185 edges from 126 archives)
- ✅ Graph builder integration (`include_archive=True`)
- ✅ CLI import tool

**Planned:**
- ⏳ `archive_profiles` (code exists, not deployed)
- ⏳ `archive_tweets` (code exists, not deployed)
- ⏳ `archive_likes` (code exists, not deployed)
- ⏳ Complete bulk import (165 archives failed due to disk I/O)

## References

- Implementation: `src/data/blob_importer.py`
- Graph integration: `src/graph/builder.py:124-135`
- Schema documentation: `docs/reference/DATABASE_SCHEMA.md`
- Blob storage URL: `https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/archives/{username}/archive.json`
