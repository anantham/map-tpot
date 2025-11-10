# Blob Import Failure Analysis

**Date:** 2025-11-08
**Import Run:** `scripts/import_blob_archives.py --all`
**Result:** 126/291 successful imports (43.3% success rate)

## Executive Summary

The bulk blob import failed for 165 out of 291 archives due to two distinct failure modes:

1. **6 archives**: HTTP 400 Bad Request (archives don't exist in blob storage)
2. **159 archives**: SQLite disk I/O errors (database write failures)

**Key Finding:** There is **NO retry mechanism or exponential backoff** implemented. The script uses a simple try/catch loop that logs errors and continues to the next archive.

## Your Questions Answered

### 1. Why only 126 out of 291?

**Breakdown:**
- **126 successful imports** (43.3%)
- **6 HTTP 400 errors** (2.1%) - Archives don't exist in blob storage
  - `robotnima`, `lemondotpng`, `doctorkondraki`, `camino_delsol_`, `peer_rich`, `kompendiaproj`
- **159 disk I/O errors** (54.6%) - SQLite write failures

**Root Cause of Disk I/O Errors:**

The disk I/O errors are **NOT** due to:
- ❌ Lack of disk space (218GB free)
- ❌ Database corruption (integrity check passed)
- ❌ File system issues

They are most likely caused by:
- ✅ **Concurrent database access** - The API server and import script were both writing to `data/cache.db` simultaneously
- ✅ **SQLite locking contention** - SQLite has limited concurrency for writes
- ✅ **Long-running transactions** - Each import commits thousands of rows, holding write locks

**Evidence from logs:**
```
Failed to import 'eshear': (sqlite3.OperationalError) disk I/O error
[SQL: INSERT OR REPLACE INTO archive_followers ...]

Failed to import 'demiurgently': (sqlite3.OperationalError) disk I/O error
[SQL: INSERT OR REPLACE INTO archive_following ...]
```

All failures occur during `INSERT OR REPLACE` operations in `_import_edges()` at blob_importer.py:256.

### 2. Was there no exponential backoff? No retry mechanism?

**Answer: NO retry mechanism exists.**

**Current implementation** (blob_importer.py:304-317):
```python
for i, username in enumerate(usernames, 1):
    logger.info(f"[{i}/{len(usernames)}] Importing '{username}'...")

    try:
        metadata = self.import_archive(
            username,
            merge_strategy=merge_strategy,
            dry_run=dry_run
        )
        if metadata:
            results.append(metadata)
    except Exception as e:
        logger.error(f"Failed to import '{username}': {e}", exc_info=True)
        continue  # ← Simply continues to next archive, no retry
```

**What's missing:**
- No retry attempts for transient failures
- No exponential backoff for rate limiting
- No distinction between permanent failures (400s) and transient failures (I/O errors)
- No checkpoint/resume mechanism to skip already-imported archives

### 3. Now if we rerun it will it fetch the tweets too?

**Answer: YES, IF the import succeeds.**

**Evidence from blob_importer.py:182-189:**
```python
# Import profile data (bio, website, location)
self._import_profile_data(account_id, archive, merge_strategy)

# Import tweets (high priority: top liked + recent)
self._import_tweets(account_id, archive, merge_strategy)

# Import likes data (medium priority)
self._import_likes(account_id, archive, merge_strategy)

# Import following edges with timestamp-based merge
self._import_edges(...)
```

The code DOES call `_import_profile_data()`, `_import_tweets()`, and `_import_likes()` for every archive. However:

**Current status:**
- ❌ `archive_profiles` table: **NOT CREATED** (code exists, not deployed)
- ❌ `archive_tweets` table: **NOT CREATED** (code exists, not deployed)
- ❌ `archive_likes` table: **NOT CREATED** (code exists, not deployed)

**Why these tables don't exist:**

The bulk import **hit disk I/O errors** before completing any full import cycle that reached the profile/tweets/likes import steps. The edge imports (`_import_edges`) happen AFTER profile/tweets/likes, and most imports failed during edge insertion.

Looking at the traceback order:
1. `_import_profile_data()` (line 183) ← Called first
2. `_import_tweets()` (line 186)
3. `_import_likes()` (line 189)
4. `_import_edges()` (line 192) ← **Failed here with disk I/O errors**

This means:
- If profile/tweets/likes imports succeeded, the tables should exist
- The fact that tables don't exist suggests failures happened earlier in the process
- OR the table creation SQL was never executed

**On re-run:**
- ✅ Will attempt profile/tweets/likes imports
- ❌ Will likely hit same disk I/O errors if API server is running concurrently
- ❌ Will re-attempt 126 already-imported archives (no skip logic)
- ✅ Tables will be created IF at least one full import succeeds

## Failure Patterns

### HTTP 400 Errors (6 archives)
```
robotnima, lemondotpng, doctorkondraki, camino_delsol_, peer_rich, kompendiaproj
```
These archives exist in the `account` table but have no corresponding blob in storage.

**Fix:** These are permanent failures - skip them in future imports.

### Disk I/O Errors (159 archives)

**Pattern:** All failures occur during `INSERT OR REPLACE` in `_import_edges()`.

**Example failure:**
```python
# Import following edges
self._import_edges(
    source_account_id=account_id,
    target_account_ids=following_ids,
    edge_type="following",
    merge_strategy=merge_strategy
)
```

**Root cause:** The loop at blob_importer.py:254-276 commits thousands of rows:
```python
with self.engine.connect() as conn:
    for target_id in target_account_ids:  # ← Can be 5000+ iterations
        conn.execute(text(f"""
            INSERT OR REPLACE INTO {table_name}
            ({account_col}, {target_col}, uploaded_at, imported_at)
            VALUES (:account_id, :related_id, :uploaded_at, :imported_at)
        """), {...})
    conn.commit()  # ← Single commit after ALL inserts
```

This holds a write lock for the entire duration of the loop. If the API server tries to read/write during this time, contention occurs.

## Recommendations

### Immediate Fixes

1. **Stop the API server** before running bulk imports
   - Eliminates concurrent access issues
   - Should resolve most disk I/O errors

2. **Add skip logic for already-imported archives**
   ```python
   # Check if archive already imported
   existing_edges = conn.execute(text("""
       SELECT COUNT(*) FROM archive_following
       WHERE account_id = :account_id
   """), {"account_id": account_id}).scalar()

   if existing_edges > 0 and not force_reimport:
       logger.info(f"Skipping '{username}' - already imported")
       continue
   ```

3. **Batch commits** in `_import_edges()` to reduce lock duration
   ```python
   BATCH_SIZE = 500
   for i, target_id in enumerate(target_account_ids):
       # ... insert logic ...
       if i % BATCH_SIZE == 0:
           conn.commit()  # Commit every 500 rows
   ```

### Long-term Improvements

1. **Implement retry logic with exponential backoff**
   ```python
   MAX_RETRIES = 3
   BACKOFF_BASE = 2  # seconds

   for attempt in range(MAX_RETRIES):
       try:
           metadata = self.import_archive(...)
           break  # Success
       except sqlite3.OperationalError as e:
           if "disk I/O error" in str(e) and attempt < MAX_RETRIES - 1:
               sleep_time = BACKOFF_BASE ** attempt
               logger.warning(f"Retry {attempt+1}/{MAX_RETRIES} after {sleep_time}s")
               time.sleep(sleep_time)
           else:
               raise
   ```

2. **Add checkpoint/resume support**
   - Track import progress in a separate table
   - Resume from last successful import on re-run

3. **Use SQLite WAL mode** for better concurrency
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   ```

4. **Distinguish permanent vs transient failures**
   - 400 errors → skip permanently
   - I/O errors → retry with backoff

## Database Impact

### Current State

**Archive tables created:**
```sql
archive_following:  158,423 rows (from 126 successful imports)
archive_followers:  323,185 rows (from 126 successful imports)
```

**Planned tables NOT created:**
```sql
archive_profiles:   0 rows (table doesn't exist)
archive_tweets:     0 rows (table doesn't exist)
archive_likes:      0 rows (table doesn't exist)
```

### Expected State (if all 291 succeed)

Based on 126/291 = 43.3% success rate:

```
archive_following:  ~366,000 rows (2.3x current)
archive_followers:  ~747,000 rows (2.3x current)
archive_profiles:   ~291 rows (new table)
archive_tweets:     ~5,820 rows (20 per user)
archive_likes:      ~variable (depends on archive data)
```

**Database size impact:** +200-300 MB estimated

## Next Steps

1. **Immediate:** Stop API server, re-run import with skip logic
2. **Short-term:** Add batch commits, retry logic
3. **Long-term:** Implement WAL mode, checkpoint/resume system

## Open Questions

1. **Why didn't profile/tweets/likes tables get created?**
   - Need to verify if `_import_profile_data()` actually executed
   - Check if table creation SQL exists in those methods
   - Possibility: Methods were added but table schemas weren't

2. **What's the actual staleness of blob data?**
   - Need to compare `uploaded_at` timestamps
   - May want to prioritize re-importing stale archives

3. **Should we use a separate database for imports?**
   - Eliminate contention entirely
   - Merge databases after import completes
