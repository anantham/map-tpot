# Account Status Tracking with Time-Based Retry

**Date:** 2025-11-25
**Status:** Approved Design
**Author:** Claude (with user validation)

## Problem Statement

The enrichment system currently:
1. Detects and skips deleted/suspended accounts permanently
2. Does NOT detect protected accounts ("These posts are protected")
3. Wastes expensive API time trying to scrape protected account edges
4. Gets 0 results from protected accounts but doesn't flag them for future skips

This leads to repeated failed scraping attempts on the same protected accounts.

## Goals

1. Detect protected accounts during profile fetch
2. Store account status (active, deleted, suspended, protected) in database
3. Skip unavailable accounts for configured time periods:
   - Protected accounts: 90 days
   - Deleted/suspended accounts: 365 days
4. Automatically retry after time period expires (accounts may become public)
5. Maintain backward compatibility with existing deleted account handling

## Non-Goals

- Schema migration (use existing `scrape_stats` JSON field)
- Changing existing deleted account detection logic
- Adding UI for status management
- Configuring retry periods per account (global policy only)

## Architecture Overview

### Components

1. **AccountStatusInfo dataclass** (`selenium_worker.py`)
   - Structured result from account existence check
   - Fields: status, detected_at, message

2. **Enhanced detection** (`selenium_worker.py::_check_account_exists`)
   - Detects: deleted, suspended, protected
   - Returns AccountStatusInfo instead of boolean
   - Text search for "These posts are protected" (robust against DOM changes)

3. **Skip logic** (`enricher.py::enrich`)
   - Checks status age from scrape_stats
   - Applies retry period based on status type
   - Re-checks status when retry period expires

4. **Storage** (`scrape_stats` JSON field)
   ```json
   {
     "account_status": "protected",
     "status_detected_at": "2025-11-24T10:30:00Z",
     "status_checked_at": "2025-11-24T10:30:00Z"
   }
   ```

## Detailed Design

### 1. Detection Logic (`selenium_worker.py`)

#### New Data Structure

```python
@dataclass
class AccountStatusInfo:
    """Result of account existence check."""
    status: str  # "active", "deleted", "suspended", "protected"
    detected_at: datetime
    message: Optional[str] = None  # Error message if not active
```

#### Enhanced `_check_account_exists()` Method

**Location:** `selenium_worker.py`, line ~1472

**Current behavior:** Returns boolean

**New behavior:** Returns AccountStatusInfo

**Detection sequence:**
1. Check for emptyState with "doesn't exist" → status="deleted"
2. Check for "Account suspended" text → status="suspended"
3. **NEW:** Search page text for "These posts are protected" → status="protected"
4. Otherwise → status="active"

**Implementation:**

```python
def _check_account_exists(self, username: str) -> AccountStatusInfo:
    """Check account status and return detailed info.

    Returns:
        AccountStatusInfo with status: active/deleted/suspended/protected
    """
    now = datetime.utcnow()

    # 1. Check for deleted account (existing logic preserved)
    empty_state = self._driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="emptyState"]')
    if empty_state:
        header_text = empty_state[0].find_elements(By.CSS_SELECTOR, 'div[data-testid="empty_state_header_text"]')
        if header_text:
            text = header_text[0].text.strip()
            text_normalized = text.lower().replace('\u2019', "'").replace('\u2018', "'")

            if "doesn't exist" in text_normalized:
                LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED: '%s'", text)
                return AccountStatusInfo(
                    status="deleted",
                    detected_at=now,
                    message=text
                )

    # 2. Check for suspended account (existing logic preserved)
    suspended_elements = self._driver.find_elements(By.XPATH, "//*[contains(text(), 'Account suspended')]")
    if suspended_elements:
        LOGGER.warning("  ✅ SUSPENDED ACCOUNT DETECTED")
        return AccountStatusInfo(
            status="suspended",
            detected_at=now,
            message="Account suspended"
        )

    # 3. NEW: Check for protected account
    # Text search is robust against DOM structure changes
    try:
        body = self._driver.find_element(By.TAG_NAME, 'body')
        page_text = body.text

        if "These posts are protected" in page_text:
            LOGGER.warning("  ✅ PROTECTED ACCOUNT DETECTED")
            return AccountStatusInfo(
                status="protected",
                detected_at=now,
                message="These posts are protected"
            )
    except Exception as e:
        LOGGER.debug("  Error checking for protected status: %s", e)

    # 4. Account is active/accessible
    LOGGER.warning("  ➜ Account appears to exist and is accessible")
    return AccountStatusInfo(
        status="active",
        detected_at=now,
        message=None
    )
```

#### Integration with `fetch_profile_overview()`

**Location:** `selenium_worker.py`, line ~780

**Changes:**
1. Call `_check_account_exists()` to get AccountStatusInfo
2. If status != "active", return ProfileOverview with status marker
3. Marker format: `bio="[ACCOUNT {STATUS}]"` (e.g., "[ACCOUNT PROTECTED]")

**Implementation:**

```python
def fetch_profile_overview(self, username: str) -> Optional[ProfileOverview]:
    # ... existing navigation code ...

    # Check account status (replaces existing boolean check)
    status_info = self._check_account_exists(username)

    if status_info.status != "active":
        LOGGER.error("Account @%s status: %s - marking with status marker", username, status_info.status)
        self._save_page_snapshot(username, f"{status_info.status.upper()}_ACCOUNT")

        # Return ProfileOverview with status marker
        # This triggers special handling in enricher.py
        status_profile = ProfileOverview(
            username=username,
            display_name=f"[{status_info.status.upper()}]",
            bio=f"[ACCOUNT {status_info.status.upper()}]",  # Marker for enricher
            location=None,
            website=None,
            followers_total=0,
            following_total=0,
            joined_date=None,
            profile_image_url=None,
        )
        self._profile_overviews[username] = status_profile
        return status_profile

    # Continue with normal profile extraction for active accounts
    profile_overview = self._extract_profile_overview(username)
    # ...
```

### 2. Skip Logic (`enricher.py`)

#### Time-Based Skip Check

**Location:** `enricher.py::enrich()`, around line ~982-997

**Logic:**
1. Get last scrape metrics for account
2. If account was skipped, check scrape_stats for status
3. Calculate days since status was detected
4. Compare against retry period for that status type
5. Skip if within retry period, otherwise continue (re-check status)

**Retry Periods (configurable constants):**

```python
# At top of enricher.py or in EnrichmentPolicy
ACCOUNT_STATUS_RETRY_DAYS = {
    "protected": 90,    # Protected accounts may become public
    "deleted": 365,     # Usernames rarely recycled, but check yearly
    "suspended": 365,   # Suspended accounts may be reinstated
}
```

**Implementation:**

```python
# In enricher.py, within enrich() method
# Around line 982-997, enhance existing skip logic

if self._policy.skip_if_ever_scraped:
    last_scrape = self._store.get_last_scrape_metrics(seed.account_id)

    # NEW: Check account status from database
    if last_scrape and last_scrape.skipped:
        account = self._store.get_shadow_account(seed.account_id)

        if account and account.scrape_stats:
            status = account.scrape_stats.get("account_status")
            status_detected_at = account.scrape_stats.get("status_detected_at")

            if status and status != "active" and status_detected_at:
                # Calculate age of status
                try:
                    detected_date = datetime.fromisoformat(status_detected_at)
                    days_since = (datetime.utcnow() - detected_date).days
                    retry_after = ACCOUNT_STATUS_RETRY_DAYS.get(status, 0)

                    # Skip if status is still within retry period
                    if days_since < retry_after:
                        LOGGER.info(
                            "⏭️  SKIPPED — account status: %s (detected %d days ago, retry after %d days)",
                            status, days_since, retry_after
                        )
                        summary[seed.account_id] = {
                            "username": seed.username,
                            "skipped": True,
                            "reason": f"account_status_{status}_within_retry_period",
                            "status": status,
                            "days_since_detected": days_since,
                            "retry_after_days": retry_after,
                        }
                        # Record skip metrics
                        skip_metrics = ScrapeRunMetrics(
                            seed_account_id=seed.account_id,
                            seed_username=seed.username or "",
                            run_at=datetime.utcnow(),
                            duration_seconds=0.0,
                            following_captured=0,
                            followers_captured=0,
                            followers_you_follow_captured=0,
                            list_members_captured=0,
                            following_claimed_total=None,
                            followers_claimed_total=None,
                            followers_you_follow_claimed_total=None,
                            following_coverage=None,
                            followers_coverage=None,
                            followers_you_follow_coverage=None,
                            accounts_upserted=0,
                            edges_upserted=0,
                            discoveries_upserted=0,
                            phase_timings=self._phase_snapshot(),
                            skipped=True,
                            skip_reason=f"account_status_{status}_retry_pending",
                        )
                        self._store.record_scrape_metrics(skip_metrics)
                        continue  # Skip to next seed
                    else:
                        LOGGER.info(
                            "♻️  RETRY — account status: %s is %d days old (>%d days), will re-check",
                            status, days_since, retry_after
                        )
                        # Continue with scraping to re-check status

                except (ValueError, TypeError) as e:
                    LOGGER.warning("Could not parse status_detected_at for @%s: %s", seed.username, e)
                    # Continue with scraping (treat as new check)
```

#### Status Storage When Detected

**Location:** `enricher.py::enrich()`, around line ~1213-1270 (existing deleted account handling)

**Enhancement:** Generalize to handle all status types

**Implementation:**

```python
# Check if account has status marker (deleted/suspended/protected)
if overview.bio and overview.bio.startswith("[ACCOUNT"):
    # Extract status from marker: "[ACCOUNT DELETED]" -> "deleted"
    status = overview.bio.replace("[ACCOUNT ", "").replace("]", "").lower()

    LOGGER.warning("⏭️  SKIPPED — account status: %s", status)
    LOGGER.info("   └─ Saving account record with status marker")

    # Store account with status in scrape_stats
    status_account = ShadowAccount(
        account_id=seed.account_id,
        username=seed.username,
        display_name=(
            None if overview.display_name and overview.display_name.startswith("[")
            else overview.display_name
        ),
        bio=overview.bio,  # Keep marker for debugging
        location=overview.location,
        website=overview.website,
        profile_image_url=overview.profile_image_url,
        followers_count=0,
        following_count=0,
        source_channel="selenium",
        fetched_at=datetime.utcnow(),
        checked_at=None,
        scrape_stats={
            "account_status": status,
            "status_detected_at": datetime.utcnow().isoformat(),
            "status_checked_at": datetime.utcnow().isoformat(),
            # Keep existing deleted flag for backward compatibility
            "deleted": (status in ["deleted", "suspended"]),
        },
    )
    self._store.upsert_accounts([status_account])

    # Record skip metrics with status reason
    status_metrics = ScrapeRunMetrics(
        seed_account_id=seed.account_id,
        seed_username=seed.username or "",
        run_at=datetime.utcnow(),
        duration_seconds=time.perf_counter() - start,
        following_captured=0,
        followers_captured=0,
        followers_you_follow_captured=0,
        list_members_captured=0,
        following_claimed_total=0,
        followers_claimed_total=0,
        followers_you_follow_claimed_total=0,
        following_coverage=None,
        followers_coverage=None,
        followers_you_follow_coverage=None,
        accounts_upserted=1,
        edges_upserted=0,
        discoveries_upserted=0,
        phase_timings=self._phase_snapshot(),
        skipped=True,
        skip_reason=f"account_{status}",
    )
    self._store.record_scrape_metrics(status_metrics)

    summary[seed.account_id] = {
        "username": seed.username,
        "skipped": True,
        "reason": f"account_{status}",
        "status": status,
    }
    continue
```

## Data Schema

### scrape_stats JSON Structure

**Field:** `shadow_accounts.scrape_stats` (existing JSON column)

**New structure:**

```json
{
  "account_status": "protected",
  "status_detected_at": "2025-11-24T10:30:00Z",
  "status_checked_at": "2025-11-24T10:30:00Z",
  "deleted": false,
  "resolution": "selenium",
  "canonical_username": "username",
  "sources": ["seed_profile_page"],
  "seed_usernames": ["seed_user"]
}
```

**Fields:**
- `account_status`: "active" | "deleted" | "suspended" | "protected"
- `status_detected_at`: ISO timestamp when status was first detected
- `status_checked_at`: ISO timestamp of most recent status check
- `deleted`: boolean (backward compatibility flag)

## Testing Strategy

### Manual Testing

1. **Protected account detection:**
   - Find a protected account on Twitter
   - Run enrichment with `--skip-if-ever-scraped` disabled
   - Verify: "PROTECTED ACCOUNT DETECTED" in logs
   - Verify: Account stored with `account_status: "protected"` in DB

2. **Skip logic:**
   - Run enrichment twice on same protected account with `--skip-if-ever-scraped` enabled
   - First run: Should detect and store status
   - Second run: Should skip with "within retry period" message

3. **Retry after expiry:**
   - Manually edit DB: set `status_detected_at` to 100 days ago
   - Run enrichment with `--skip-if-ever-scraped` enabled
   - Verify: "RETRY — account status" message
   - Verify: Status is re-checked

4. **Backward compatibility:**
   - Verify existing deleted/suspended accounts still work
   - Verify accounts without status field are treated as new

### Edge Cases

1. **Account transitions:**
   - Protected → Public: Status will be updated on next retry
   - Deleted → Active (username recycled): Will be detected on retry after 365 days

2. **Missing data:**
   - No `status_detected_at`: Treat as new check
   - Invalid date format: Log warning, treat as new check
   - Unknown status type: Use default retry (0 days = always retry)

3. **Concurrent updates:**
   - Last scrape wins (same as existing behavior)
   - Status timestamps prevent stale data issues

## Rollout Plan

### Phase 1: Code Changes
1. Add AccountStatusInfo dataclass to selenium_worker.py
2. Enhance _check_account_exists() with protected detection
3. Update fetch_profile_overview() to return status markers
4. Add skip logic to enricher.py enrich() method
5. Update status storage logic

### Phase 2: Testing
1. Test on small seed list (10 accounts with mixed statuses)
2. Verify logs show correct status detection
3. Verify DB contains correct scrape_stats
4. Verify skip logic works correctly

### Phase 3: Deployment
1. Run on full seed list
2. Monitor logs for unexpected statuses
3. Check metrics for skip rate improvements

## Monitoring

**Key metrics to track:**

1. Skip rate by status type:
   - How many accounts are skipped due to protected/deleted/suspended?
   - What % of total seeds does this represent?

2. Retry effectiveness:
   - How many accounts transition from unavailable → active after retry period?
   - Are retry periods too short/long?

3. API time savings:
   - Compare scrape duration before/after for same seed list
   - Estimate API calls saved per status type

**Query for status breakdown:**

```sql
SELECT
  json_extract(scrape_stats, '$.account_status') as status,
  COUNT(*) as count,
  AVG(julianday('now') - julianday(json_extract(scrape_stats, '$.status_detected_at'))) as avg_days_old
FROM shadow_accounts
WHERE scrape_stats IS NOT NULL
  AND json_extract(scrape_stats, '$.account_status') IS NOT NULL
GROUP BY status;
```

## Future Enhancements

1. **Configurable retry periods:**
   - Move retry days to EnrichmentPolicy
   - Allow per-run customization via CLI flags

2. **Status history:**
   - Track status transitions over time
   - Detect patterns (e.g., accounts that toggle protected frequently)

3. **Rate limiting detection:**
   - Detect when Twitter blocks scraping
   - Back off automatically with exponential retry

4. **Status dashboard:**
   - UI showing account status distribution
   - Alerts for unusual patterns

## Backward Compatibility

**Preserved:**
- Existing `scrape_stats.deleted` boolean flag (still set for deleted/suspended)
- Existing skip logic for `skip_reason == "account_deleted_or_suspended"`
- Existing ProfileOverview marker format for deleted accounts

**Enhanced:**
- New status types don't break existing queries
- Accounts without `account_status` are treated as "active" (default behavior)
- Time-based retry is additive (doesn't remove existing skip logic)

## References

- User logs showing protected account detection: lines 1-100 of initial problem statement
- Existing deleted account handling: enricher.py:988-997, 1213-1270
- Account existence check: selenium_worker.py:1472-1539
