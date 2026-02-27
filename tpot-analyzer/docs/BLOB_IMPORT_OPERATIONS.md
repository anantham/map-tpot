# Blob Import Operations Guide

<!-- staleness-marker: src/data/blob_importer.py -->
<!-- last-verified: 2026-02-27 -->

## Overview

The blob importer downloads Community Archive data from Supabase blob storage and imports it into the local SQLite cache. This is the most complete data source (~291 archives) but requires careful operational procedures.

**Source:** `src/data/blob_importer.py`

---

## Pre-Flight Checklist

Before running a bulk import:

- [ ] **Disk space:** At least 30GB free in `data/` directory
  ```bash
  df -h data/
  ```
- [ ] **Database backup:** Copy the current cache
  ```bash
  cp data/cache.db data/cache.db.bak
  ```
- [ ] **Stop API server:** Prevents write lock contention
  ```bash
  # Kill running server process
  pkill -f "start_api_server"
  ```
- [ ] **Network:** Stable connection to Supabase (downloads ~291 JSON archives)
- [ ] **WAL mode:** Enabled for better concurrency (auto-enabled by importer)

---

## Running the Import

### Full Import (All Archives)

```bash
cd tpot-analyzer

# Dry run first (no database writes)
python -c "
from src.data.blob_importer import BlobStorageImporter
from src.config import get_cache_settings
from sqlalchemy import create_engine

settings = get_cache_settings()
engine = create_engine(f'sqlite:///{settings.path}')

with BlobStorageImporter(engine) as importer:
    results = importer.import_all_archives(dry_run=True)
    print(f'Would import: {len(results)} archives')
"

# Actual import
python -c "
from src.data.blob_importer import BlobStorageImporter
from src.config import get_cache_settings
from sqlalchemy import create_engine

settings = get_cache_settings()
engine = create_engine(f'sqlite:///{settings.path}')

with BlobStorageImporter(engine) as importer:
    results = importer.import_all_archives()
    print(f'Imported: {len(results)} archives')
"
```

### Partial Import (Testing)

```bash
python -c "
from src.data.blob_importer import BlobStorageImporter
from src.config import get_cache_settings
from sqlalchemy import create_engine

settings = get_cache_settings()
engine = create_engine(f'sqlite:///{settings.path}')

with BlobStorageImporter(engine) as importer:
    results = importer.import_all_archives(max_archives=10)
"
```

### Re-Import Specific Archive

```bash
python -c "
from src.data.blob_importer import BlobStorageImporter
from src.config import get_cache_settings
from sqlalchemy import create_engine

settings = get_cache_settings()
engine = create_engine(f'sqlite:///{settings.path}')

with BlobStorageImporter(engine) as importer:
    result = importer.import_archive('username_here')
    if result:
        print(f'Imported: {result.username} ({result.following_count} following, {result.follower_count} followers)')
    else:
        print('Archive not found')
"
```

### Force Re-Import (Overwrite Existing)

```bash
python -c "
from src.data.blob_importer import BlobStorageImporter
from src.config import get_cache_settings
from sqlalchemy import create_engine

settings = get_cache_settings()
engine = create_engine(f'sqlite:///{settings.path}')

with BlobStorageImporter(engine) as importer:
    results = importer.import_all_archives(force_reimport=True)
"
```

---

## What Gets Imported

Each archive imports five categories of data:

| Data Type | Target Table | Strategy |
|-----------|-------------|----------|
| Following edges | `archive_following` | INSERT OR REPLACE |
| Follower edges | `archive_followers` | INSERT OR REPLACE |
| Profile data | `archive_profiles` | INSERT OR REPLACE |
| Tweets (top 20 liked + 10 recent) | `archive_tweets` | INSERT OR REPLACE |
| Likes | `archive_likes` | INSERT OR REPLACE |

### Import Order per Archive

1. Profile data (bio, website, location, avatar, header)
2. Tweets (top 20 by favorite_count + 10 most recent, deduplicated)
3. Likes (all liked tweets)
4. Following edges (who the user follows)
5. Follower edges (who follows the user)

---

## Error Recovery

### Disk I/O Errors

**Symptoms:** `sqlite3.OperationalError: disk I/O error`

**Automatic recovery:** Retries 3 times with exponential backoff (2s, 4s, 8s).

**Manual recovery if retries fail:**
1. Check disk space: `df -h data/`
2. Check file permissions: `ls -la data/cache.db*`
3. Check for WAL corruption: `sqlite3 data/cache.db "PRAGMA integrity_check;"`
4. If corrupted, restore from backup: `cp data/cache.db.bak data/cache.db`

### Network Errors

**Symptoms:** `httpx.HTTPError` during archive fetch

**Behavior:** Logs error and moves to next archive. Does not retry network errors (only I/O errors are retried).

**Manual recovery:** Re-run import with `force_reimport=False` - already-imported archives will be skipped.

### 404 Errors (Archive Not Found)

**Symptoms:** `Archive not found for 'username' at URL`

**Behavior:** Normal - not all accounts in the `account` table have blob archives. Logged as warning and skipped.

**Expected rate:** ~40-50% of accounts may return 404 (no archive uploaded).

### Database Locked

**Symptoms:** `sqlite3.OperationalError: database is locked`

**Recovery:**
1. Check for other processes: `fuser data/cache.db`
2. Stop the API server if running
3. Wait for locks to clear (or restart)
4. Re-run import

---

## Performance Expectations

| Metric | Value | Notes |
|--------|-------|-------|
| Archives per minute | ~10-15 | Network-bound (Supabase download) |
| Total import time | ~20-30 minutes | For ~291 archives |
| Database growth | ~500MB-1GB | Depends on archive sizes |
| Memory usage | ~200MB peak | Single archive loaded in memory at a time |

### Batch Commit Behavior

Edges are committed every 500 rows to balance:
- **Throughput:** Fewer commits = faster bulk inserts
- **Lock duration:** More frequent commits = shorter write locks
- **Crash recovery:** At most 500 uncommitted rows lost

---

## Post-Import Steps

After a successful import:

1. **Regenerate graph snapshot:**
   ```bash
   python -m scripts.analyze_graph --include-shadow --refresh-snapshot
   ```

2. **Verify snapshot:**
   ```bash
   python -m scripts.verify_graph_snapshot
   ```

3. **Start API server:**
   ```bash
   python -m scripts.start_api_server
   ```

4. **Invalidate caches:**
   ```bash
   curl -X POST http://localhost:5001/api/cache/invalidate -H "Content-Type: application/json" -d '{}'
   curl -X POST http://localhost:5001/api/metrics/cache/clear
   ```

5. **Verify data in explorer:** Open the graph explorer and check node/edge counts.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_RETRIES` | 3 | Retry attempts for I/O errors |
| `BACKOFF_BASE` | 2 | Backoff base (seconds): 2^attempt |
| `BATCH_COMMIT_SIZE` | 500 | Rows per commit batch |
| HTTP timeout | 30s | Per-request download timeout |
| Supabase base URL | `https://fabxmporizzqflnftavs.supabase.co` | Blob storage host |

### Merge Strategies

| Strategy | Behavior |
|----------|----------|
| `"timestamp"` (default) | Import all data, uses `INSERT OR REPLACE` |
| `"archive_only"` | Import blob data, skip shadow-enriched data |
| `"shadow_only"` | Skip all blob imports (edges, profiles, tweets, likes) |

---

## Monitoring Import Progress

Import logs include progress indicators:

```
[1/291] Processing 'alice'...
Archive for 'alice' (12345): 350 following, 1200 followers
Imported 350 following edges to archive_following
Imported 1200 follower edges to archive_followers
[2/291] Processing 'bob'...
Skipping 'bob' (67890) - already imported
[3/291] Processing 'charlie'...
Archive not found for 'charlie' at https://...
```

Final summary:
```
Import complete: 126 imported, 32 skipped, 133 not found
```
