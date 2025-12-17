# Database Schema Documentation

## Overview

The TPOT analyzer uses SQLite for persistent storage in `data/cache.db`. The database tracks Twitter/X social graph data including accounts, edges (following/follower relationships), scrape metrics, and discovered connections.

## Core Tables

### `shadow_account`

Stores profile metadata for all discovered Twitter accounts.

**Schema:**
```sql
account_id          VARCHAR   PRIMARY KEY  -- Twitter user ID or "shadow:username" for unresolved IDs
username            VARCHAR                -- Twitter handle (without @)
display_name        VARCHAR                -- Display name from profile
bio                 TEXT                   -- Profile bio/description
location            VARCHAR                -- Location string from profile
website             VARCHAR                -- Website URL from profile
profile_image_url   VARCHAR                -- Profile image URL
followers_count     INTEGER                -- Total followers (from profile overview)
following_count     INTEGER                -- Total following (from profile overview)
source_channel      VARCHAR                -- How account was discovered (e.g., "hybrid_selenium")
fetched_at          DATETIME               -- When account data was fetched
checked_at          DATETIME               -- Last time account was checked/validated
```

**Key Concepts:**
- `account_id` can be numeric Twitter ID (`"1234567890"`) or shadow ID (`"shadow:username"`) when real ID is unknown
- `followers_count` and `following_count` are the "claimed totals" from Twitter's UI (may not match actual edges due to rate limits)

---

### `shadow_edge`

Stores directed edges in the social graph (following/follower relationships).

**Schema:**
```sql
source_id       VARCHAR   PRIMARY KEY (1/3)  -- Account ID that was scraped
target_id       VARCHAR   PRIMARY KEY (2/3)  -- Account ID discovered on source's page
direction       VARCHAR   PRIMARY KEY (3/3)  -- "outbound" or "inbound"
source_channel  VARCHAR                      -- Scraping method (e.g., "hybrid_selenium")
fetched_at      DATETIME                     -- When this edge was captured
checked_at      DATETIME                     -- Last validation timestamp
weight          INTEGER                      -- Edge weight (currently unused)
metadata        JSON                         -- Additional edge metadata (optional)
```

**Key Concepts:**

#### Edge Directionality

The schema uses a **source-centric** model where edges are stored from the perspective of the account being scraped:

- **`direction = "outbound"`**: `source_id` follows `target_id`
  - Captured from scraping `https://x.com/{source_username}/following`
  - Edge means: "source follows target"

- **`direction = "inbound"`**: `target_id` follows `source_id`
  - Captured from scraping `https://x.com/{source_username}/followers`
  - Edge means: "target follows source"

#### Two Perspectives for Every Account

For any given account (e.g., `@astridwilde1`), edges exist in two forms:

**1. Direct Scrape (as SOURCE):**
- Edges where `source_id = 'shadow:astridwilde1'`
- These come from visiting astrid's own pages:
  - `/following` → creates outbound edges
  - `/followers` → creates inbound edges

**2. Discovered on Others' Pages (as TARGET):**
- Edges where `target_id = 'shadow:astridwilde1'`
- These come from finding astrid while scraping OTHER people's pages:
  - Found on Alice's `/following` → creates `(Alice → astrid, "outbound")` = astrid is followed by Alice
  - Found on Bob's `/followers` → creates `(Bob → astrid, "inbound")` = astrid follows Bob

#### Example: Complete Edge Picture

For `@astridwilde1` with 6,103 following and 11,777 followers:

```sql
-- Edges FROM scraping astrid's pages (source_id = 'shadow:astridwilde1')
SELECT COUNT(*) FROM shadow_edge WHERE source_id = 'shadow:astridwilde1' AND direction = 'outbound';
-- Result: 53 (astrid follows these 53 people)

SELECT COUNT(*) FROM shadow_edge WHERE source_id = 'shadow:astridwilde1' AND direction = 'inbound';
-- Result: 9 (these 9 people follow astrid, discovered on astrid's followers page)

-- Edges FROM discovering astrid on other people's pages (target_id = 'shadow:astridwilde1')
SELECT COUNT(*) FROM shadow_edge WHERE target_id = 'shadow:astridwilde1' AND direction = 'inbound';
-- Result: 256 (these 256 people follow astrid, discovered when scraping their /following pages)
```

**Total followers for astrid:** 9 + 256 = 265 edges (vs. 11,777 claimed → 2.2% coverage)

#### Querying the Full Network

To get ALL people who follow a given account:
```sql
SELECT DISTINCT source_id as follower
FROM shadow_edge
WHERE target_id = 'shadow:astridwilde1' AND direction = 'inbound'
UNION
SELECT DISTINCT target_id as follower
FROM shadow_edge
WHERE source_id = 'shadow:astridwilde1' AND direction = 'inbound';
```

To get ALL people an account follows:
```sql
SELECT DISTINCT target_id as following
FROM shadow_edge
WHERE source_id = 'shadow:astridwilde1' AND direction = 'outbound'
UNION
SELECT DISTINCT source_id as following
FROM shadow_edge
WHERE target_id = 'shadow:astridwilde1' AND direction = 'outbound';
```

---

### `shadow_discovery`

Tracks new accounts discovered during scraping (for growth metrics and discovery tracking).

**Schema:**
```sql
discovered_account_id   VARCHAR   PRIMARY KEY (1/2)  -- Account that was discovered
discovered_via          VARCHAR   PRIMARY KEY (2/2)  -- Seed account that led to discovery
discovered_at           DATETIME                     -- When discovered
source_channel          VARCHAR                      -- Discovery method
```

**Purpose:**
- Track which seed accounts are most productive for network expansion
- Avoid re-processing already known accounts
- Measure discovery efficiency

---

### `scrape_run_metrics`

Records detailed metrics for every scrape attempt (successful or skipped).

**Schema:**
```sql
id                                  INTEGER   PRIMARY KEY AUTOINCREMENT
seed_account_id                     VARCHAR   -- Account being scraped
seed_username                       VARCHAR   -- Username of seed account
run_at                              DATETIME  -- Scrape start time
duration_seconds                    REAL      -- Time taken to scrape
following_captured                  INTEGER   -- # accounts captured from /following
followers_captured                  INTEGER   -- # accounts captured from /followers
followers_you_follow_captured       INTEGER   -- # accounts from /followers_you_follow
following_claimed_total             INTEGER   -- Total claimed in UI (from overview)
followers_claimed_total             INTEGER   -- Total claimed in UI (from overview)
followers_you_follow_claimed_total  INTEGER   -- Total claimed in UI
following_coverage                  REAL      -- % coverage (captured/claimed * 100)
followers_coverage                  REAL      -- % coverage
followers_you_follow_coverage       REAL      -- % coverage
accounts_upserted                   INTEGER   -- # account records written to DB
edges_upserted                      INTEGER   -- # edge records written to DB
discoveries_upserted                INTEGER   -- # discovery records written to DB
skipped                             BOOLEAN   -- Whether scrape was skipped
skip_reason                         VARCHAR   -- Reason for skip (if skipped=1)
error_type                          VARCHAR   -- Error type (if failed)
error_details                       TEXT      -- Error details (if failed)
```

**Key Metrics:**

- **Coverage:** Ratio of captured to claimed totals
  - Low coverage (<10%) typically indicates rate limiting or scroll limits
  - Coverage can be NULL if claimed_total is unknown

- **Skipped vs. Executed:**
  - `skipped=0`: Actual scrape attempted
  - `skipped=1`: Scrape skipped by policy (e.g., data fresh, user declined)

- **Skip Reasons:**
  - `"policy_fresh_data"`: Data age within refresh threshold
  - `"already_scraped_sufficient_coverage"`: Prior scrape has >10% coverage
  - `"profile_overview_missing"`: Could not load profile page
  - `"user_declined"`: User chose not to scrape when prompted

---

## Coverage and Data Completeness

### Understanding Coverage Metrics

**Coverage** = `(captured / claimed_total) * 100`

Due to Twitter/X rate limits and UI constraints:
- **Median coverage: ~1.5%** for both following and followers
- **Best observed coverage: ~35%** (rare)
- **Zero accounts have >50% coverage**

### Why Coverage is Low

1. **Rate Limiting:** Twitter throttles scraping after ~200-500 accounts
2. **Scroll Limits:** UI won't load infinite lists even with scrolling
3. **Session Limits:** Long scrapes get interrupted
4. **Large Networks:** Accounts with 10k+ following/followers are hard to fully capture

### Coverage-Based Skip Logic

The `--skip-if-ever-scraped` flag now uses coverage thresholds:

```python
MIN_COVERAGE_PCT = 10.0

# Only skip if BOTH conditions met:
# 1. Complete metadata (followers_count AND following_count)
# 2. Coverage >= 10% for BOTH following and followers
```

This ensures accounts with <10% coverage get re-scraped to improve edge density.

---

## Community Archive Tables

The analyzer supports **three data sources** that are merged when building the graph:

1. **REST API** (`account`, `following`, `followers`, `profile`) - Fresh but paginated (1000 row limit)
2. **Blob Storage** (`archive_*` tables) - Complete but stale (user upload date)
3. **Shadow Enrichment** (`shadow_*` tables) - Expanded network via scraping

### `archive_following`

**NEW** - Stores complete following relationships from Community Archive blob storage imports.

**Schema:**
```sql
account_id           TEXT   PRIMARY KEY (1/2)  -- Account who uploaded archive
following_account_id TEXT   PRIMARY KEY (2/2)  -- Account they follow
uploaded_at          TEXT                      -- When archive was uploaded to blob storage
imported_at          TEXT                      -- When we imported from blob storage
```

**Purpose:**
- Bypass REST API pagination limits (1000 rows)
- Access complete following lists from user archives
- Preserve upload timestamp for data freshness tracking

**Data Source:** `https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/archives/{username}/archive.json`

---

### `archive_followers`

**NEW** - Stores complete follower relationships from Community Archive blob storage imports.

**Schema:**
```sql
account_id          TEXT   PRIMARY KEY (1/2)  -- Account who uploaded archive
follower_account_id TEXT   PRIMARY KEY (2/2)  -- Account following them
uploaded_at         TEXT                      -- When archive was uploaded to blob storage
imported_at         TEXT                      -- When we imported from blob storage
```

**Purpose:**
- Complete follower data (REST API limited to 1000)
- Bidirectional validation with `archive_following`

---

### `archive_profiles` *(Planned)*

Profile metadata from Community Archive blob imports.

**Status:** Implementation exists in `src/data/blob_importer.py` but not yet deployed.

**Planned Schema:**
```sql
account_id        TEXT   PRIMARY KEY  -- Account ID
bio               TEXT                -- Profile bio/description
website           TEXT                -- Website URL
location          TEXT                -- Location string
avatar_media_url  TEXT                -- Profile image URL
header_media_url  TEXT                -- Header banner URL
uploaded_at       TEXT                -- Archive upload timestamp
imported_at       TEXT                -- Import timestamp
```

**Purpose:**
- Richer profile data than REST API provides
- Bio text for semantic matching in recommendations

---

### `archive_tweets` *(Planned)*

Top liked + recent tweets from archive imports.

**Status:** Implementation exists in `src/data/blob_importer.py` but not yet deployed.

**Planned Schema:**
```sql
account_id      TEXT    PRIMARY KEY (1/2)  -- Tweet author
tweet_id        TEXT    PRIMARY KEY (2/2)  -- Tweet ID
full_text       TEXT                       -- Complete tweet text
created_at      TEXT                       -- Tweet timestamp
favorite_count  INTEGER                    -- Like count
retweet_count   INTEGER                    -- Retweet count
lang            TEXT                       -- Language code
uploaded_at     TEXT                       -- Archive upload timestamp
imported_at     TEXT                       -- Import timestamp
```

**Planned Import Strategy:**
- Top 20 most liked tweets (for understanding user preferences)
- 10 most recent tweets (for current interests)
- Deduplicates automatically (UNIQUE constraint on account_id, tweet_id)

---

### `archive_likes` *(Planned)*

Liked tweets from archive imports.

**Status:** Implementation exists in `src/data/blob_importer.py` but not yet deployed.

**Planned Schema:**
```sql
account_id   TEXT   PRIMARY KEY (1/2)  -- Account who liked
tweet_id     TEXT   PRIMARY KEY (2/2)  -- Tweet that was liked
full_text    TEXT                      -- Full tweet text
expanded_url TEXT                      -- Tweet URL
uploaded_at  TEXT                      -- Archive upload timestamp
imported_at  TEXT                      -- Import timestamp
```

**Purpose:**
- Interest mapping for recommendations
- Content preference analysis

---

### Data Merge Strategy

When building the graph (`src/graph/builder.py`):

1. **Load REST API data** (fresh, limited to 1000 rows each)
2. **Load archive blob data** (`fetch_archive_following()`, `fetch_archive_followers()`)
3. **Concatenate DataFrames** (pandas handles deduplication naturally)
4. **Inject shadow enrichment** (if `include_shadow=True`)

**Result:** Complete graph with maximum coverage from all sources.

**Tradeoffs:**
- Archive data may be stale (months old)
- REST data is fresh but incomplete
- Shadow data expands network but is scraped (may have gaps)

---

## Legacy/REST API Tables

### `account`
Core account metadata from Community Archive REST API.

**Schema:**
```sql
account_id           TEXT   PRIMARY KEY
username             TEXT
account_display_name TEXT
created_at           TEXT
created_via          TEXT
num_followers        BIGINT
num_following        BIGINT
num_tweets           BIGINT
num_likes            BIGINT
```

### `following`
Following edges from REST API (limited to ~1000 rows due to Supabase pagination).

### `followers`
Follower edges from REST API (limited to ~1000 rows).

### `profile`
Profile metadata from REST API.

**Schema:**
```sql
account_id        TEXT   PRIMARY KEY
bio               TEXT
website           TEXT
location          TEXT
avatar_media_url  TEXT
header_media_url  TEXT
archive_upload_id FLOAT
```

### `tweets`, `likes`
Tweet and like data from REST API.

### `cache_metadata`
Tracks cache freshness for API responses and web scrapes.

**Schema:**
```sql
table_name  VARCHAR   PRIMARY KEY
fetched_at  DATETIME
row_count   INTEGER
```

---

## Data Integrity Notes

### De-duplication
- Edges are naturally de-duplicated by `(source_id, target_id, direction)` primary key
- Multiple scrapes of the same relationship create idempotent upserts

### Cross-Validation
- The dual-perspective edge model allows validation:
  - If Alice's `/following` lists Bob, expect `(Alice → Bob, "outbound")`
  - If Bob's `/followers` lists Alice, expect `(Bob → Alice, "inbound")`
  - Both should exist for verified relationships

### Missing Data
- `NULL` in `followers_count`/`following_count` indicates metadata was never captured
- `0` captured with non-zero claimed total indicates scrape hit limits early
- Check `scrape_run_metrics.error_type` for failures

---

## Querying Examples

### Get coverage statistics for all accounts
```sql
SELECT
  sa.username,
  srm.following_captured,
  sa.following_count as following_claimed,
  ROUND(CAST(srm.following_captured AS FLOAT) / sa.following_count * 100, 2) as following_cov_pct,
  srm.followers_captured,
  sa.followers_count as followers_claimed,
  ROUND(CAST(srm.followers_captured AS FLOAT) / sa.followers_count * 100, 2) as followers_cov_pct
FROM scrape_run_metrics srm
JOIN shadow_account sa ON srm.seed_account_id = sa.account_id
WHERE srm.skipped = 0
  AND sa.following_count > 0
  AND sa.followers_count > 0
ORDER BY followers_cov_pct DESC;
```

### Find accounts needing re-scrape (low coverage)
```sql
WITH latest_scrapes AS (
  SELECT
    seed_account_id,
    MAX(run_at) as last_run
  FROM scrape_run_metrics
  WHERE skipped = 0
  GROUP BY seed_account_id
)
SELECT
  sa.username,
  srm.following_coverage,
  srm.followers_coverage,
  srm.run_at
FROM scrape_run_metrics srm
JOIN latest_scrapes ls ON srm.seed_account_id = ls.seed_account_id AND srm.run_at = ls.last_run
JOIN shadow_account sa ON srm.seed_account_id = sa.account_id
WHERE (srm.following_coverage < 10.0 OR srm.followers_coverage < 10.0)
ORDER BY srm.followers_coverage ASC;
```

### Get total edges for an account (both perspectives)
```sql
SELECT
  'Following' as relation_type,
  COUNT(DISTINCT target_id) as count
FROM shadow_edge
WHERE source_id = 'shadow:astridwilde1' AND direction = 'outbound'
UNION ALL
SELECT
  'Followers (inbound on own page)',
  COUNT(DISTINCT target_id)
FROM shadow_edge
WHERE source_id = 'shadow:astridwilde1' AND direction = 'inbound'
UNION ALL
SELECT
  'Followers (discovered on others)',
  COUNT(DISTINCT source_id)
FROM shadow_edge
WHERE target_id = 'shadow:astridwilde1' AND direction = 'inbound';
```

### Check scrape history for an account
```sql
SELECT
  run_at,
  duration_seconds,
  following_captured,
  followers_captured,
  following_coverage,
  followers_coverage,
  skipped,
  skip_reason,
  error_type
FROM scrape_run_metrics
WHERE seed_account_id = 'shadow:astridwilde1'
ORDER BY run_at DESC
LIMIT 10;
```

---

## Logging and Traceability

Every DB write operation is logged with before/after counts:

```
Writing to DB for @username: 1350 accounts, 1300 edges, 25 discoveries...
✓ DB write complete for @username: 1350 accounts upserted, 1300 edges upserted, 25 discoveries upserted
✓ @username COMPLETE: DB writes: 1350 accounts, 1300 edges, 25 discoveries | Captured: following 500/2703 (18.5%), followers 800/6827 (11.7%), followers_you_follow 50/100
```

See logs for complete audit trail of all data changes.
