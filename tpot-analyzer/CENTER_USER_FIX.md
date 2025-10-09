# Center User Prioritization & Twitter DOM Changes

**Last Updated:** October 8, 2025

## Problem Summary

When using `--center adityaarpitha`, only 11 out of 268 following accounts were being prioritized, and the scraper only captured 268 out of 1,458 total following accounts. Additionally, Twitter changed their DOM structure on October 8, breaking profile metadata extraction.

## Root Causes

### Issue 1: Incomplete Scraping (268 / 1,458)

**Why it stopped early:**
- The scraper stops after **6 consecutive scrolls** with no page height change
- Twitter's lazy loading creates "gaps" where the page pauses to fetch more data
- For accounts with 1000+ following/followers, these gaps cause premature termination

**The fix:**
- Added `--max-scrolls` flag (default: 6)
- Applies to **all list types**: following, followers, verified_followers, followers_you_follow
- For large accounts, use `--max-scrolls 20` or higher

### Issue 2: Limited Prioritization (11 / 268)

**Why only 11 were prioritized:**
- The old code only **reordered** existing seeds
- It used **set intersection** to find matches:
  ```python
  center_priority_seeds = center_following_usernames.intersection(remaining_usernames)
  ```
- This only matched accounts that existed in BOTH:
  - @adityaarpitha's following list (268 from DB)
  - The preset seed list (282 from archive)

**The fix:**
- Changed to **add ALL following accounts** as new "shadow seeds"
- Shadow seeds: `SeedAccount(account_id="shadow:username", username="username")`
- These get enriched from scratch (navigate to profile, scrape data)

## Changes Made

### 1. Added `--max-scrolls` Flag

```bash
# Default behavior (stops after 6 scrolls with no change)
.venv/bin/python -m scripts.enrich_shadow_graph --center adityaarpitha

# For accounts with 1000+ following (more patient scrolling)
.venv/bin/python -m scripts.enrich_shadow_graph --center adityaarpitha --max-scrolls 20
```

**Location:** `scripts/enrich_shadow_graph.py:87-91`

### 2. Shadow Seeds for Center Following

**Old code (line 371):**
```python
# Only reorder existing seeds (intersection)
center_priority_seeds = center_following_usernames.intersection(remaining_usernames) - priority_seeds
```

**New code (lines 372-395):**
```python
# Add ALL following as priority seeds (even if not in archive)
center_following_not_in_archive = center_following_usernames - remaining_usernames - priority_seeds
center_following_in_archive = center_following_usernames.intersection(remaining_usernames) - priority_seeds

# Build seeds: use archive data where available, create shadow seeds for the rest
archive_based_seeds = build_seed_accounts(fetcher, reordered_usernames)
shadow_seed_usernames = [u for u in reordered_usernames if u.lower() not in archive_usernames]
shadow_seeds = [
    SeedAccount(account_id=f"shadow:{username}", username=username, trust=0.8)
    for username in shadow_seed_usernames
]

seeds = [center_seed] + archive_based_seeds + shadow_seeds
```

**Location:** `scripts/enrich_shadow_graph.py:360-400`

### 3. Fixed `_should_skip_seed()` Navigation

**Problem:** Even with `--skip-if-ever-scraped`, the code was still navigating to profiles before deciding to skip.

**Fix:** Added early exit when `--skip-if-ever-scraped` is enabled.

```python
# If --skip-if-ever-scraped is enabled, skip this policy check entirely
# (it was already handled earlier in the enrich() method)
if self._policy.skip_if_ever_scraped:
    return (False, None, edge_summary, None)
```

**Location:** `src/shadow/enricher.py:146-149`

## Expected Behavior After Fix

### Before:
```
Found 268 accounts followed by @adityaarpitha in DB cache.
Reordered seeds: 18 preset, 11 from @adityaarpitha's following, 253 others. Total: 283 seeds.
```

### After (with current DB):
```
Found 268 accounts followed by @adityaarpitha in DB cache.
Reordered seeds: 18 preset, 268 from @adityaarpitha's following (11 in archive, 257 new shadow seeds), 253 others. Total: ~550 seeds.
```

### After (with full scrape using --max-scrolls 20):
```
Found 1458 accounts followed by @adityaarpitha in DB cache.
Reordered seeds: 18 preset, 1458 from @adityaarpitha's following (50 in archive, 1408 new shadow seeds), 253 others. Total: ~1730 seeds.
```

## Recommended Workflow

### Step 1: Re-scrape center user with higher scroll limit

```bash
caffeinate -dimsu .venv/bin/python -m scripts.enrich_shadow_graph \
  --center adityaarpitha \
  --max-scrolls 20 \
  --auto-confirm-first \
  --quiet
```

This will:
- Scrape all ~1,458 following accounts for @adityaarpitha
- Take longer (20 scrolls × ~5-40 seconds each = up to 13 minutes of scrolling)
- Store all 1,458 usernames in the DB

### Step 2: Run full enrichment with center prioritization

```bash
caffeinate -dimsu .venv/bin/python -m scripts.enrich_shadow_graph \
  --center adityaarpitha \
  --skip-if-ever-scraped \
  --auto-confirm-first \
  --quiet
```

This will:
- Enrich @adityaarpitha first (skip if already complete)
- Add all 1,458 following accounts as priority seeds
- Enrich them in order: preset → center's following → others

## Technical Details

### Shadow Seeds Are Safe

Shadow seeds with `account_id="shadow:username"` work because:

1. **DB lookups return None** → Treated as new accounts
2. **Profile scraping gets real ID** → Real account_id populated during enrichment
3. **Edges use correct IDs** → Once real ID is known, all edges use it
4. **No data loss** → Real account_id replaces shadow ID in the DB

### Why 6 Scrolls Was Too Low

For accounts with 1000+ following:
- Twitter loads ~50-100 users per scroll
- After ~200-300 users, the page pauses to fetch more (can take 30-240 seconds)
- 6 scrolls = ~30-240 seconds of waiting before giving up
- This is often not enough for large accounts

### Recommended `--max-scrolls` Values

| Following Count | Recommended `--max-scrolls` |
|----------------|----------------------------|
| < 500          | 6 (default)                |
| 500-1000       | 10-15                      |
| 1000-2000      | 20-25                      |
| 2000+          | 30+                        |

---

## October 8, 2025 Updates

### Issue 3: Twitter DOM Structure Changed

**Problem:** Twitter changed the followers link from `/followers` to `/verified_followers`, breaking profile metadata extraction. All scrapes were failing with "Profile data considered incomplete. Missing or failed to parse: followers_total".

**Fix:** Added `/verified_followers` as a URL variant to check when extracting follower counts.

**Location:** `src/shadow/selenium_worker.py:607-609`

```python
# Twitter now uses verified_followers instead of followers
if list_type == "followers":
    href_variants.append(f"/{username}/verified_followers")
```

### Issue 4: Missing verified_followers Page Scraping

**Problem:** Twitter now has 4 follower-related pages:
- `/following`
- `/followers` (all followers)
- `/verified_followers` (curated verified followers)
- `/followers_you_follow`

We were only scraping 3 of them.

**Fix:** Added `fetch_verified_followers()` method and integrated it into the enrichment pipeline.

**Files Modified:**
- `src/shadow/selenium_worker.py:172-173` — Added fetch method
- `src/shadow/enricher.py:480-559` — Integrated into refresh logic
- Data from all 4 lists is now combined and stored together

### Issue 5: X API Rate Limiting Slowdowns

**Problem:** X API fallback was enabled by default whenever `X_BEARER_TOKEN` env var existed, causing 15-minute rate limit sleeps for every account without a bio.

**Fix:** Added `--enable-api-fallback` flag. X API is now opt-in only.

**Location:** `scripts/enrich_shadow_graph.py:151-155, 283-290`

```bash
# Default: no API fallback (fast)
.venv/bin/python -m scripts.enrich_shadow_graph --center adityaarpitha

# With API fallback (slow but enriched)
.venv/bin/python -m scripts.enrich_shadow_graph --enable-api-fallback --bearer-token TOKEN
```

### Issue 6: Insufficient Debug Logging

**Problem:** DEBUG logs weren't written to disk by default, making troubleshooting difficult.

**Fix:** Changed logging defaults to always write DEBUG to disk, INFO to console.

**Location:** `scripts/enrich_shadow_graph.py:243-247`

Now `logs/enrichment.log` always contains full DEBUG details, regardless of `--log-level` flag.

---

## Files Modified

### October 7, 2025
1. `scripts/enrich_shadow_graph.py` (lines 87-91, 360-400)
   - Added `--max-scrolls` argument
   - Modified center prioritization to create shadow seeds

2. `src/shadow/enricher.py` (lines 146-149)
   - Fixed `--skip-if-ever-scraped` navigation issue

### October 8, 2025
3. `scripts/enrich_shadow_graph.py` (lines 151-155, 243-247, 283-290)
   - Added `--enable-api-fallback` flag
   - Changed logging defaults: DEBUG to disk, INFO to console

4. `src/shadow/selenium_worker.py` (lines 172-173, 607-609)
   - Added `fetch_verified_followers()` method
   - Added `/verified_followers` href variant for metadata extraction

5. `src/shadow/enricher.py` (lines 480-559, 728, 787-788)
   - Modified `_refresh_followers()` to return 3 captures instead of 2
   - Integrated `verified_followers` into data processing pipeline
