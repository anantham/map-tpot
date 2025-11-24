# Account Status Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add account status tracking (active/deleted/suspended/protected) with time-based retry to prevent wasted API calls on unavailable accounts.

**Architecture:** Enhance existing detection in selenium_worker.py to return structured status info. Add skip logic in enricher.py to check status age and apply retry periods (90 days protected, 365 days deleted/suspended). Store status in existing scrape_stats JSON field.

**Tech Stack:** Python 3.9, Selenium WebDriver, SQLAlchemy, dataclasses

**Design Document:** `docs/plans/2025-11-25-account-status-tracking-design.md`

---

## Task 1: Add AccountStatusInfo dataclass

**Files:**
- Modify: `src/shadow/selenium_worker.py:93-104` (after ProfileOverview dataclass)

**Step 1: Add AccountStatusInfo dataclass**

Add this dataclass after the ProfileOverview dataclass (around line 104):

```python
@dataclass
class AccountStatusInfo:
    """Result of account existence check.

    Attributes:
        status: One of "active", "deleted", "suspended", "protected"
        detected_at: Timestamp when status was detected
        message: Optional error message (e.g., "These posts are protected")
    """
    status: str
    detected_at: datetime
    message: Optional[str] = None
```

**Step 2: Add datetime import if missing**

Check the imports at top of file (around line 1-27). If `datetime` class is not imported from datetime module, add it:

```python
from datetime import datetime  # Add datetime class import
```

**Step 3: Commit**

```bash
git add src/shadow/selenium_worker.py
git commit -m "feat(selenium): Add AccountStatusInfo dataclass for structured status checking"
```

**Verification:** Run `python3 -c "from src.shadow.selenium_worker import AccountStatusInfo; print(AccountStatusInfo.__doc__)"` - should print the docstring without errors.

---

## Task 2: Enhance _check_account_exists() to return AccountStatusInfo

**Files:**
- Modify: `src/shadow/selenium_worker.py:1472-1539` (_check_account_exists method)

**Step 1: Update method signature and return type**

Change line 1472 from:
```python
def _check_account_exists(self, username: str) -> bool:
```

To:
```python
def _check_account_exists(self, username: str) -> AccountStatusInfo:
```

Update the docstring (line 1473-1479) from:
```python
    """Check if the account exists or shows a 'doesn't exist' message.

    Args:
        username: The username being checked (for logging/snapshots)

    Returns:
        True if account exists, False if deleted/suspended/doesn't exist
    """
```

To:
```python
    """Check account status and return detailed info.

    Args:
        username: The username being checked (for logging/snapshots)

    Returns:
        AccountStatusInfo with status: active/deleted/suspended/protected
    """
```

**Step 2: Add now = datetime.utcnow() at start of method**

After line 1481 `assert self._driver is not None`, add:

```python
now = datetime.utcnow()
```

**Step 3: Replace deleted account detection return (line ~1507)**

Replace:
```python
                    LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED: '%s'", text)
                    return False
```

With:
```python
                    LOGGER.warning("  ✅ DELETED ACCOUNT DETECTED: '%s'", text)
                    return AccountStatusInfo(
                        status="deleted",
                        detected_at=now,
                        message=text
                    )
```

**Step 4: Replace suspended account detection return (line ~1527)**

Replace:
```python
            LOGGER.warning("  ✅ SUSPENDED ACCOUNT DETECTED")
            self._save_page_snapshot(username, "SUSPENDED")
            return False
```

With:
```python
            LOGGER.warning("  ✅ SUSPENDED ACCOUNT DETECTED")
            self._save_page_snapshot(username, "SUSPENDED")
            return AccountStatusInfo(
                status="suspended",
                detected_at=now,
                message="Account suspended"
            )
```

**Step 5: Add protected account detection (before final return)**

After the suspended account check (around line 1530), add this NEW section:

```python
        # 3. NEW: Check for protected account
        # Text search is robust against DOM structure changes
        try:
            body = self._driver.find_element(By.TAG_NAME, 'body')
            page_text = body.text

            if "These posts are protected" in page_text:
                LOGGER.warning("  ✅ PROTECTED ACCOUNT DETECTED")
                self._save_page_snapshot(username, "PROTECTED_ACCOUNT")
                return AccountStatusInfo(
                    status="protected",
                    detected_at=now,
                    message="These posts are protected"
                )
        except Exception as e:
            LOGGER.debug("  Error checking for protected status: %s", e)
```

**Step 6: Replace final return (line ~1538)**

Replace:
```python
    LOGGER.warning("  ➜ Account appears to exist (no deletion/suspension detected)")
    return True
```

With:
```python
    LOGGER.warning("  ➜ Account appears to exist and is accessible")
    return AccountStatusInfo(
        status="active",
        detected_at=now,
        message=None
    )
```

**Step 7: Commit**

```bash
git add src/shadow/selenium_worker.py
git commit -m "feat(selenium): Enhance _check_account_exists to detect protected accounts

- Return AccountStatusInfo instead of boolean
- Add protected account detection via text search
- Preserve existing deleted/suspended detection
- Text search is robust against DOM changes"
```

**Verification:** The method should compile without errors. We'll test integration in the next task.

---

## Task 3: Update fetch_profile_overview() to use AccountStatusInfo

**Files:**
- Modify: `src/shadow/selenium_worker.py:780-890` (fetch_profile_overview method)

**Step 1: Find the account existence check (around line 806)**

Locate this code:
```python
            if not self._check_account_exists(username):
                LOGGER.error("Account @%s doesn't exist or is suspended - marking as deleted", username)
                self._save_page_snapshot(username, "DELETED_ACCOUNT")
                # Return a special ProfileOverview marking this as deleted
                deleted_profile = ProfileOverview(
                    username=username,
                    display_name="[ACCOUNT DELETED]",
                    bio="[ACCOUNT DELETED OR SUSPENDED]",
                    location=None,
                    website=None,
                    followers_total=0,
                    following_total=0,
                    joined_date=None,
                    profile_image_url=None,
                )
                self._profile_overviews[username] = deleted_profile
                return deleted_profile
```

**Step 2: Replace with new status-aware check**

Replace the entire if block with:

```python
            # Check account status
            status_info = self._check_account_exists(username)

            if status_info.status != "active":
                LOGGER.error(
                    "Account @%s status: %s - marking with status marker",
                    username,
                    status_info.status
                )
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
```

**Step 3: Commit**

```bash
git add src/shadow/selenium_worker.py
git commit -m "feat(selenium): Update fetch_profile_overview to handle AccountStatusInfo

- Use AccountStatusInfo from _check_account_exists
- Generate status markers for all status types (not just deleted)
- Preserve backward compatibility with bio markers"
```

**Verification:** Run basic import test:
```bash
.venv/bin/python3 -c "from src.shadow.selenium_worker import SeleniumWorker; print('Import successful')"
```

---

## Task 4: Add account status retry constants to enricher.py

**Files:**
- Modify: `src/shadow/enricher.py:40-42` (after LOGGER declaration)

**Step 1: Add retry period constants**

After the `LOGGER = logging.getLogger(__name__)` line (around line 40), add:

```python
# Account status retry periods (in days)
ACCOUNT_STATUS_RETRY_DAYS = {
    "protected": 90,    # Protected accounts may become public
    "deleted": 365,     # Usernames rarely recycled, but check yearly
    "suspended": 365,   # Suspended accounts may be reinstated
}
```

**Step 2: Commit**

```bash
git add src/shadow/enricher.py
git commit -m "feat(enricher): Add account status retry period constants"
```

**Verification:** Run `grep -A 5 "ACCOUNT_STATUS_RETRY_DAYS" src/shadow/enricher.py` - should show the constants.

---

## Task 5: Add time-based skip logic to enricher.py

**Files:**
- Modify: `src/shadow/enricher.py:982-1066` (skip-if-ever-scraped section in enrich method)

**Step 1: Locate the existing skip check (around line 988)**

Find this code:
```python
            # CRITICAL: Skip immediately if account was previously detected as deleted/suspended
            # This prevents wasting time trying to visit non-existent profiles
            if last_scrape and last_scrape.skipped and last_scrape.skip_reason == "account_deleted_or_suspended":
                days_since = (datetime.utcnow() - last_scrape.run_at).days
                LOGGER.info("⏭️  SKIPPED — account previously detected as deleted/suspended")
                LOGGER.info("   └─ Last detected: %d days ago", days_since)
                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": "previously_detected_as_deleted",
                }
                continue
```

**Step 2: Replace with new time-based status check**

Replace the entire if block with:

```python
            # Check account status from database with time-based retry
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
                            LOGGER.warning(
                                "Could not parse status_detected_at for @%s: %s",
                                seed.username, e
                            )
                            # Continue with scraping (treat as new check)
```

**Step 3: Commit**

```bash
git add src/shadow/enricher.py
git commit -m "feat(enricher): Add time-based skip logic for account status

- Check account status age from scrape_stats
- Apply retry periods: 90 days protected, 365 days deleted/suspended
- Log retry decisions with status details
- Record skip metrics for monitoring"
```

**Verification:** Run syntax check:
```bash
.venv/bin/python3 -m py_compile src/shadow/enricher.py
```

---

## Task 6: Update status storage to handle all status types

**Files:**
- Modify: `src/shadow/enricher.py:1213-1270` (deleted account handling in enrich method)

**Step 1: Locate existing deleted account handling (around line 1214)**

Find this code:
```python
            # Check if account is deleted/suspended (special marker from selenium_worker)
            if overview.bio == "[ACCOUNT DELETED OR SUSPENDED]":
                LOGGER.warning("⏭️  SKIPPED — account deleted or suspended")
                LOGGER.info("   └─ Saving account record with deleted marker")
                # Save the deleted account record to DB
                # Ensure display_name isn't also the marker (defensive)
                display_name = (
                    None
                    if overview.display_name == "[ACCOUNT DELETED OR SUSPENDED]"
                    else overview.display_name
                )
                deleted_account = ShadowAccount(
                    account_id=seed.account_id,
                    username=seed.username,
                    display_name=display_name,
                    bio=overview.bio,
                    location=overview.location,
                    website=overview.website,
                    profile_image_url=overview.profile_image_url,
                    followers_count=0,
                    following_count=0,
                    source_channel="selenium",
                    fetched_at=datetime.utcnow(),
                    checked_at=None,
                    scrape_stats={"deleted": True},
                )
```

**Step 2: Replace bio check to handle all status markers**

Replace the `if overview.bio == "[ACCOUNT DELETED OR SUSPENDED]":` line with:

```python
            # Check if account has status marker (deleted/suspended/protected)
            if overview.bio and overview.bio.startswith("[ACCOUNT"):
```

**Step 3: Extract and store status properly**

Replace the `scrape_stats={"deleted": True},` line with:

```python
                # Extract status from marker: "[ACCOUNT DELETED]" -> "deleted"
                status = overview.bio.replace("[ACCOUNT ", "").replace("]", "").lower()

                LOGGER.warning("⏭️  SKIPPED — account status: %s", status)
                LOGGER.info("   └─ Saving account record with status marker")

                # Save the account record to DB
                # Ensure display_name isn't also the marker (defensive)
                display_name = (
                    None
                    if overview.display_name and overview.display_name.startswith("[")
                    else overview.display_name
                )
                status_account = ShadowAccount(
                    account_id=seed.account_id,
                    username=seed.username,
                    display_name=display_name,
                    bio=overview.bio,
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
```

**Step 4: Update variable name from deleted_account to status_account**

In the `self._store.upsert_accounts([deleted_account])` line, change to:

```python
                self._store.upsert_accounts([status_account])
```

**Step 5: Update metrics skip_reason (around line 1260)**

Change:
```python
                    skip_reason="account_deleted_or_suspended",
```

To:
```python
                    skip_reason=f"account_{status}",
```

**Step 6: Update summary reason (around line 1266)**

Change:
```python
                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": "account_deleted_or_suspended",
                }
```

To:
```python
                summary[seed.account_id] = {
                    "username": seed.username,
                    "skipped": True,
                    "reason": f"account_{status}",
                    "status": status,
                }
```

**Step 7: Commit**

```bash
git add src/shadow/enricher.py
git commit -m "feat(enricher): Update status storage to handle all status types

- Extract status from bio marker (deleted/suspended/protected)
- Store account_status, status_detected_at in scrape_stats
- Preserve deleted flag for backward compatibility
- Update skip_reason to include specific status"
```

**Verification:** Run syntax check:
```bash
.venv/bin/python3 -m py_compile src/shadow/enricher.py
```

---

## Task 7: Manual Testing

**Prerequisites:**
- Working Twitter session with cookies in `data/cookies.pkl`
- Access to accounts with different statuses (protected, deleted, etc.)

**Step 1: Test protected account detection**

Find a protected Twitter account (or use a test account). Run enrichment without skip flag to force detection:

```bash
.venv/bin/python3 -m src.shadow.cli enrich \
  --cookies data/cookies.pkl \
  --seed-username <PROTECTED_USERNAME> \
  --include-following false \
  --include-followers false
```

**Expected output:**
- Log line: "🔍 CHECKING EXISTENCE for @<username>"
- Log line: "✅ PROTECTED ACCOUNT DETECTED"
- Log line: "Account @<username> status: protected - marking with status marker"
- Log line: "⏭️ SKIPPED — account status: protected"

**Verification query:**
```sql
SELECT username,
       json_extract(scrape_stats, '$.account_status') as status,
       json_extract(scrape_stats, '$.status_detected_at') as detected_at
FROM shadow_accounts
WHERE username = '<PROTECTED_USERNAME>';
```

Expected: status = "protected", detected_at = current timestamp

**Step 2: Test skip logic with time-based retry**

Run enrichment again with `--skip-if-ever-scraped` flag:

```bash
.venv/bin/python3 -m src.shadow.cli enrich \
  --cookies data/cookies.pkl \
  --seed-username <PROTECTED_USERNAME> \
  --skip-if-ever-scraped \
  --include-following false \
  --include-followers false
```

**Expected output:**
- Log line: "⏭️ SKIPPED — account status: protected (detected 0 days ago, retry after 90 days)"
- Account is skipped without visiting profile page
- No new scrape metrics recorded (or skip metrics with skip_reason containing "retry_pending")

**Step 3: Test retry after time period expires**

**Option A (fast test):** Manually update the database to simulate old status:

```sql
UPDATE shadow_accounts
SET scrape_stats = json_set(
    scrape_stats,
    '$.status_detected_at',
    datetime('now', '-100 days')
)
WHERE username = '<PROTECTED_USERNAME>';
```

**Option B (patient test):** Wait 90 days (not recommended for immediate testing)

Run enrichment again:

```bash
.venv/bin/python3 -m src.shadow.cli enrich \
  --cookies data/cookies.pkl \
  --seed-username <PROTECTED_USERNAME> \
  --skip-if-ever-scraped \
  --include-following false \
  --include-followers false
```

**Expected output:**
- Log line: "♻️ RETRY — account status: protected is 100 days old (>90 days), will re-check"
- Profile page is visited to re-check status
- New status is detected and stored with updated timestamp

**Step 4: Test deleted/suspended accounts (if available)**

Repeat Step 1-3 with deleted or suspended accounts to verify:
- Correct status detection
- 365-day retry period is applied
- Status is re-checked after expiry

**Step 5: Test backward compatibility**

Query existing accounts that were marked as deleted before this change:

```sql
SELECT username,
       json_extract(scrape_stats, '$.deleted') as old_deleted_flag,
       json_extract(scrape_stats, '$.account_status') as new_status
FROM shadow_accounts
WHERE json_extract(scrape_stats, '$.deleted') = 1;
```

Run enrichment with these accounts - they should be skipped by the new logic (if within retry period) or re-checked (if beyond retry period).

**Step 6: Test error handling**

Test with invalid/missing data:

1. Account with no scrape_stats:
   ```sql
   UPDATE shadow_accounts SET scrape_stats = NULL WHERE username = '<TEST_USER>';
   ```
   Run enrichment - should treat as new account (no skip)

2. Account with invalid date:
   ```sql
   UPDATE shadow_accounts
   SET scrape_stats = json_set(scrape_stats, '$.status_detected_at', 'invalid-date')
   WHERE username = '<TEST_USER>';
   ```
   Run enrichment - should log warning and treat as new check

**Step 7: Document test results**

Create a test report in `docs/plans/2025-11-25-account-status-tracking-test-results.md`:

```markdown
# Account Status Tracking - Test Results

**Test Date:** YYYY-MM-DD
**Tester:** Your Name

## Test Cases

### 1. Protected Account Detection
- **Account:** @<username>
- **Result:** PASS/FAIL
- **Notes:** [observations]

### 2. Skip Logic (Within Retry Period)
- **Account:** @<username>
- **Days Since Detection:** 0
- **Result:** PASS/FAIL
- **Notes:** [observations]

### 3. Retry After Expiry
- **Account:** @<username>
- **Days Since Detection:** 100
- **Result:** PASS/FAIL
- **Notes:** [observations]

### 4. Backward Compatibility
- **Existing Deleted Accounts:** X accounts tested
- **Result:** PASS/FAIL
- **Notes:** [observations]

### 5. Error Handling
- **Invalid Date:** PASS/FAIL
- **Missing scrape_stats:** PASS/FAIL
- **Notes:** [observations]

## Summary

**Overall Status:** PASS/FAIL
**Issues Found:** [list any issues]
**Recommendations:** [any improvements or follow-up work]
```

**Step 8: Final commit**

```bash
git add docs/plans/2025-11-25-account-status-tracking-test-results.md
git commit -m "test(enricher): Add manual test results for account status tracking"
```

---

## Rollback Plan

If issues are discovered during testing, rollback steps:

**Step 1: Identify the last good commit**

```bash
git log --oneline -10
```

**Step 2: Create a rollback branch**

```bash
git checkout -b rollback/account-status-tracking
```

**Step 3: Revert commits in reverse order**

```bash
git revert <commit-hash-6>
git revert <commit-hash-5>
git revert <commit-hash-4>
git revert <commit-hash-3>
git revert <commit-hash-2>
git revert <commit-hash-1>
```

**Step 4: Test rollback**

Run basic enrichment to ensure system works:

```bash
.venv/bin/python3 -m src.shadow.cli enrich --cookies data/cookies.pkl --seed-username <TEST_USER>
```

**Step 5: Push rollback if needed**

```bash
git push origin rollback/account-status-tracking
```

---

## Post-Implementation Monitoring

After deployment, monitor these metrics:

**1. Skip rate by status type:**

```sql
SELECT
    skip_reason,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM scrape_run_metrics), 2) as pct
FROM scrape_run_metrics
WHERE skipped = 1
  AND run_at >= datetime('now', '-7 days')
GROUP BY skip_reason
ORDER BY count DESC;
```

**2. Status distribution:**

```sql
SELECT
    json_extract(scrape_stats, '$.account_status') as status,
    COUNT(*) as count,
    AVG(julianday('now') - julianday(json_extract(scrape_stats, '$.status_detected_at'))) as avg_days_old
FROM shadow_accounts
WHERE scrape_stats IS NOT NULL
  AND json_extract(scrape_stats, '$.account_status') IS NOT NULL
GROUP BY status
ORDER BY count DESC;
```

**3. Retry effectiveness:**

```sql
SELECT
    json_extract(scrape_stats, '$.account_status') as prev_status,
    COUNT(*) as accounts_rechecked,
    SUM(CASE WHEN json_extract(scrape_stats, '$.account_status') = 'active' THEN 1 ELSE 0 END) as now_active
FROM shadow_accounts
WHERE json_extract(scrape_stats, '$.status_checked_at') > json_extract(scrape_stats, '$.status_detected_at')
GROUP BY prev_status;
```

**4. API time savings estimate:**

Compare average scrape duration before/after:

```sql
-- Before (baseline from old runs)
SELECT AVG(duration_seconds) as avg_duration
FROM scrape_run_metrics
WHERE run_at < datetime('now', '-30 days')
  AND skipped = 0;

-- After (with status tracking)
SELECT AVG(duration_seconds) as avg_duration
FROM scrape_run_metrics
WHERE run_at >= datetime('now', '-7 days')
  AND skipped = 0;
```

---

## Known Limitations

1. **Text search brittleness:** If Twitter changes the exact text "These posts are protected", detection will fail. Consider adding multiple text variants in the future.

2. **Status transitions:** If an account rapidly toggles between protected/public, the retry period may cause delays in capturing new data. Monitor for this pattern.

3. **Manual date manipulation:** Test Step 3 requires manual DB updates to simulate time passing. Consider adding a test flag to override current time.

4. **No UI:** Status information is only visible via SQL queries. Future enhancement: add status dashboard.

---

## Success Criteria

✅ Protected accounts are detected and flagged
✅ Accounts are skipped based on retry periods
✅ Status is re-checked after retry period expires
✅ Backward compatibility with existing deleted accounts
✅ Error handling for invalid data
✅ Logs clearly show skip decisions with status details
✅ Database queries confirm correct status storage

---

## Estimated Time

**Development:** 1-2 hours (Tasks 1-6)
**Testing:** 1 hour (Task 7)
**Documentation:** 30 minutes
**Total:** 2.5-3.5 hours

**Complexity:** Medium (mostly enhancing existing code, no schema changes)
