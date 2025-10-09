# Shadow Scrape Debugging Guide

## What We Discovered

Your `adityaarpitha` account shows **19.3% following coverage** (281/1458) and **4.7% follower coverage** (25/532).

### The metadata tells the truth!

```sql
-- All 281 outbound edges came from YOUR following page
SELECT json_extract(metadata, '$.seed_username'),
       json_extract(metadata, '$.list_type'),
       COUNT(*)
FROM shadow_edge
WHERE source_id = 'shadow:adityaarpitha' AND direction = 'outbound'
GROUP BY 1, 2;

-- Result: adityaarpitha | following | 281
```

This means:
✅ The following page WAS scraped
✅ All edges have correct `seed_username` tracking
❌ Only captured 281/1458 = 19.3% before stopping

### Why did it stop early?

**Current scroll logic** (src/shadow/selenium_worker.py:350-358):
```python
self._driver.execute_script("window.scrollBy(0, 1200);")
time.sleep(random.uniform(scroll_delay_min, scroll_delay_max))  # 5-40s
new_height = self._driver.execute_script("return document.body.scrollHeight")
if new_height == last_height:
    stagnant_scrolls += 1  # If height unchanged 6 times -> stop
```

**Hypothesis**: Twitter's lazy loading stopped responding, OR the page height stopped changing even though more content was available.

## Debug Single Account Script

Created: `scripts/debug_single_account.py`

### Features

1. **Colored terminal output**
   - 🔵 Blue = scroll activity
   - 🟢 Green = successful operations
   - 🟣 Magenta = DB writes
   - 🔴 Red = errors

2. **DB transparency**
   - Shows what data exists before scraping
   - Displays sample edges with source tracking
   - Shows final counts and coverage %

3. **Source tracking**
   - Every edge shows: `(from @username's list_type list)`
   - Distinguishes edges from YOUR page vs OTHER pages

4. **Full trace log**
   - `logs/debug_single_account.log` has everything
   - Line numbers, timestamps, all DEBUG messages

### Usage

```bash
# Run with verbose output, watch the browser
.venv/bin/python3 -m scripts.debug_single_account adityaarpitha --force --following-only

# Fast mode for debugging (lower delays)
.venv/bin/python3 -m scripts.debug_single_account adityaarpitha --force --delay-min 2 --delay-max 5

# Increase scroll attempts
.venv/bin/python3 -m scripts.debug_single_account adityaarpitha --force --max-scrolls 30
```

## What to Watch For

### 1. In the terminal

```
[following] scroll #1 (collected=15)
[following] scroll #2 (collected=32)
[following] scroll #3 (collected=48)
[following] scroll #4 no height change (1/6)  ← HEIGHT NOT CHANGING
[following] scroll #5 no height change (2/6)
[following] scroll #6 (collected=65)          ← NEW CONTENT LOADED
```

Watch for:
- How many unique users are collected per scroll
- When "no height change" appears
- If scrolling stops at exactly 281 again

### 2. In the browser window

- Does the page keep loading more users as you scroll?
- Does it hit a "You've reached the end" message?
- Does the page freeze/hang?
- Are there any error messages in the UI?

### 3. In the log file

```bash
tail -f logs/debug_single_account.log | grep -E "scroll|Collected|stagnant"
```

Look for:
- Total scroll rounds before stopping
- Pattern of `stagnant_scrolls` incrementing
- Final "Collected X following entries"

## Potential Issues & Fixes

### Issue 1: Twitter stops lazy-loading

**Symptom**: Height stops changing, but only captured 281

**Test**: Manually scroll your following page in a browser:
1. Open https://twitter.com/adityaarpitha/following
2. Keep scrolling down
3. Does it load all 1458 users?

**Fix if needed**:
- Increase wait time between scrolls (use `--delay-max 60`)
- Add explicit "wait for element" checks before scrolling
- Check for loading spinners

### Issue 2: Page height detection broken

**Symptom**: Content loads but height metric doesn't change

**Test**: In the debug run, check if `discovered` dict keeps growing even when height is stagnant

**Fix if needed**:
- Use `discovered` count instead of page height
- Add secondary detection: count visible UserCell elements

### Issue 3: Twitter rate limiting / blocking

**Symptom**: Scrolling works initially then stops

**Test**: Check for error messages in browser during scrape

**Fix if needed**:
- Longer delays between actions
- Visit fewer pages in one session
- Use different cookie sessions

## Quick Test Plan

1. **Establish baseline** (current behavior):
   ```bash
   .venv/bin/python3 -m scripts.debug_single_account adityaarpitha --force --following-only --delay-min 2 --delay-max 5
   ```
   Note: Where does it stop? 281 again? Different number?

2. **Test with longer waits**:
   ```bash
   .venv/bin/python3 -m scripts.debug_single_account adityaarpitha --force --following-only --delay-min 10 --delay-max 20
   ```
   Does longer wait help?

3. **Test with more scroll attempts**:
   ```bash
   .venv/bin/python3 -m scripts.debug_single_account adityaarpitha --force --following-only --max-scrolls 30
   ```
   Does it capture more with higher threshold?

4. **Manual verification**:
   - Open browser to https://twitter.com/adityaarpitha/following
   - Manually scroll to the bottom
   - Count roughly how many users load
   - Does it match the 1458 claimed total?

## Next Steps

Based on what you find:

### If it's a height detection issue:
- We can change the stop condition from "height unchanged" to "no new users discovered"
- Code change in `selenium_worker.py:300-358`

### If it's a loading issue:
- We can add explicit waits for loading spinners
- Increase delays between scrolls
- Add retry logic for stagnant periods

### If Twitter blocks after N users:
- We may need to accept partial scraping
- Add session rotation
- Spread scraping across multiple days

## Questions to Answer

1. **Does manual scrolling reach all 1458 users?**
   - If yes → scroll logic needs improvement
   - If no → Twitter may limit what's shown

2. **What's in the debug log when it stops?**
   ```bash
   grep "Collected.*following" logs/debug_single_account.log
   ```

3. **Are the 281 users the FIRST 281, or scattered throughout?**
   - Check usernames in DB vs your actual following list

4. **Does the number change on re-runs?**
   - Run the debug script 2-3 times
   - If it varies → random timing issue
   - If always 281 → deterministic limit

---

**TL;DR**: Run the debug script, watch the browser, check the logs, and report back:
- Where it stops (number of users)
- What the terminal shows
- What the browser shows

Then we can pinpoint the exact issue and fix it.
