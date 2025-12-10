# Operations Runbook

Procedures for operating, monitoring, and troubleshooting map-tpot.

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Monitoring](#monitoring)
3. [Common Issues](#common-issues)
4. [Recovery Procedures](#recovery-procedures)
5. [Maintenance Tasks](#maintenance-tasks)

---

## Daily Operations

### Starting the Graph Explorer

**Standard startup:**

```bash
# Terminal 1: Backend
cd tpot-analyzer
source .venv/bin/activate
python -m scripts.start_api_server

# Terminal 2: Frontend
cd tpot-analyzer/graph-explorer
npm run dev

# Verify: http://localhost:5173 shows graph
```

**macOS shortcut:**
```bash
chmod +x StartGraphExplorer.command
./StartGraphExplorer.command
```

### Running Enrichment

**Standard enrichment run:**

```bash
cd tpot-analyzer
source .venv/bin/activate

# Basic run (safe defaults)
python -m scripts.enrich_shadow_graph \
  --center your_username \
  --skip-if-ever-scraped \
  --auto-confirm-first \
  --quiet

# Long-running (use caffeinate on macOS)
caffeinate -disu python -m scripts.enrich_shadow_graph \
  --center your_username \
  --max-scrolls 20
```

**Monitor progress:**
```bash
# In another terminal
tail -f logs/enrichment.log
```

### Refreshing Graph Snapshot

After enrichment, regenerate the snapshot:

```bash
python -m scripts.refresh_graph_snapshot --include-shadow

# Verify
python -m scripts.verify_graph_snapshot
```

---

## Monitoring

### Health Checks

**Backend API:**
```bash
curl http://localhost:5001/health
# Expected: {"status": "ok"}
```

**Database status:**
```bash
python scripts/verify_setup.py
# Shows: account counts, cache freshness
```

**Shadow data status:**
```bash
python -m scripts.verify_shadow_graph
# Shows: shadow account/edge counts, coverage
```

### Key Metrics to Watch

| Metric | Check | Concern if... |
|--------|-------|---------------|
| Shadow accounts | `SELECT COUNT(*) FROM shadow_account` | Stops growing |
| Shadow edges | `SELECT COUNT(*) FROM shadow_edge` | Much lower than expected |
| Scrape success rate | See query below | <80% |
| Coverage | See query below | Median <5% |

**Scrape success rate (last 7 days):**
```sql
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN skipped = 0 AND error_type IS NULL THEN 1 ELSE 0 END) as success,
  SUM(CASE WHEN error_type IS NOT NULL THEN 1 ELSE 0 END) as errors
FROM scrape_run_metrics
WHERE run_at > datetime('now', '-7 days');
```

**Coverage distribution:**
```sql
SELECT
  CASE
    WHEN following_coverage IS NULL THEN 'null'
    WHEN following_coverage < 5 THEN '<5%'
    WHEN following_coverage < 10 THEN '5-10%'
    WHEN following_coverage < 20 THEN '10-20%'
    ELSE '>20%'
  END as coverage_bucket,
  COUNT(*) as count
FROM scrape_run_metrics
WHERE skipped = 0
GROUP BY coverage_bucket;
```

### Log Analysis

**Find errors:**
```bash
grep -i error logs/enrichment.log | tail -20
```

**Find rate limits:**
```bash
grep -i "rate.limit\|429\|blocked" logs/enrichment.log
```

**Find deleted accounts:**
```bash
grep "DELETED ACCOUNT" logs/enrichment.log
```

---

## Common Issues

### Issue: "Backend API not available"

**Symptoms:**
- Red banner in browser
- Frontend can't load graph

**Diagnosis:**
```bash
# Is Flask running?
lsof -i :5001

# Can you reach it?
curl http://localhost:5001/health
```

**Resolution:**
1. Start Flask server: `python -m scripts.start_api_server`
2. Check for port conflicts: `lsof -i :5001 | grep LISTEN`
3. Kill conflicting process if needed

---

### Issue: "Enrichment stops early"

**Symptoms:**
- Only captures 100-300 accounts from 1000+ list
- "stagnant_scrolls" appears in logs

**Diagnosis:**
```bash
# Check scroll behavior
grep "stagnant\|scroll" logs/enrichment.log | tail -50
```

**Resolution:**
1. Increase `--max-scrolls 20` (or higher)
2. Increase delays: `--delay-min 10 --delay-max 40`
3. Try visible browser (remove `--headless`)
4. Check if manually scrolling works in browser

---

### Issue: "Profile data incomplete" retries

**Symptoms:**
- Logs show "Retrying in 5s... 15s... 60s..."
- 95 seconds wasted per account

**Diagnosis:**
```bash
# Check HTML snapshots
ls -la logs/snapshot_*_INCOMPLETE_DATA_*.html

# Verify counter extraction
python scripts/verify_profile_counters.py logs/snapshot_*.html
```

**Resolution:**
1. Check if account is deleted (should detect automatically)
2. Verify CSS selectors still work (Twitter may have changed DOM)
3. Increase wait times before parsing

---

### Issue: "SQLite disk I/O error"

**Symptoms:**
- API returns 500
- Logs show "disk I/O error"

**Diagnosis:**
```bash
# Check disk space
df -h data/

# Check file permissions
ls -la data/cache.db

# Try opening directly
sqlite3 data/cache.db "SELECT 1;"
```

**Resolution:**
1. Check disk space (need ~200MB free)
2. Ensure file isn't locked by another process
3. If corrupted, see [Database Recovery](#database-recovery)

---

### Issue: "Twitter blocking/rate limiting"

**Symptoms:**
- Pages fail to load
- "Something went wrong" in browser
- Increasing errors in logs

**Diagnosis:**
```bash
# Check recent error types
sqlite3 data/cache.db "
  SELECT error_type, COUNT(*)
  FROM scrape_run_metrics
  WHERE run_at > datetime('now', '-1 day')
  GROUP BY error_type;"
```

**Resolution:**
1. **Stop immediately** — Don't retry
2. **Wait 1-24 hours** — Blocks usually temporary
3. **Switch cookies** — Use different account session
4. **Reduce activity:**
   ```bash
   # Much slower, safer settings
   --delay-min 30 --delay-max 120 --max-scrolls 5
   ```

---

## Recovery Procedures

### Database Recovery

If `cache.db` is corrupted:

**Option 1: Repair (if possible)**
```bash
cd tpot-analyzer/data
sqlite3 cache.db ".recover" | sqlite3 cache_recovered.db
mv cache.db cache_corrupted.bak
mv cache_recovered.db cache.db
```

**Option 2: Rebuild from scratch**
```bash
# Delete and recreate
rm data/cache.db

# Re-fetch from Supabase
python -m scripts.sync_supabase_cache --force

# Shadow data is lost - must re-enrich
```

**Option 3: Restore from backup**
```bash
# If you have backups
cp backups/cache_2024-12-01.db data/cache.db
```

### Cookie Session Recovery

If cookies expire or are blocked:

```bash
# Capture new cookies
python -m scripts.setup_cookies --output secrets/twitter_cookies_fresh.pkl

# Use new cookies for enrichment
python -m scripts.enrich_shadow_graph \
  --cookies secrets/twitter_cookies_fresh.pkl \
  ...
```

### Graph Snapshot Recovery

If `analysis_output.json` is corrupted:

```bash
# Regenerate from database
python -m scripts.refresh_graph_snapshot --include-shadow

# Verify
python -m scripts.verify_graph_snapshot
```

---

## Maintenance Tasks

### Weekly

1. **Check enrichment progress:**
   ```bash
   sqlite3 data/cache.db "
     SELECT COUNT(*) as total,
            SUM(CASE WHEN fetched_at > datetime('now', '-7 days') THEN 1 ELSE 0 END) as recent
     FROM shadow_account;"
   ```

2. **Review error rates:**
   ```bash
   python -m scripts.summarize_metrics --last-7-days
   ```

3. **Clean old logs:**
   ```bash
   find logs/ -name "*.html" -mtime +30 -delete
   ```

### Monthly

1. **Refresh Supabase cache:**
   ```bash
   python -m scripts.sync_supabase_cache --force
   ```

2. **Rotate cookie sessions:**
   ```bash
   python -m scripts.setup_cookies --output secrets/twitter_cookies_$(date +%Y%m).pkl
   ```

3. **Backup database:**
   ```bash
   mkdir -p backups
   cp data/cache.db backups/cache_$(date +%Y-%m-%d).db
   ```

4. **Update dependencies:**
   ```bash
   pip install --upgrade -r requirements.txt
   cd graph-explorer && npm update
   ```

### As Needed

1. **Re-enrich stale accounts:**
   ```bash
   # Find accounts not scraped in 6+ months
   sqlite3 data/cache.db "
     SELECT username FROM shadow_account sa
     WHERE NOT EXISTS (
       SELECT 1 FROM scrape_run_metrics srm
       WHERE srm.seed_account_id = sa.account_id
       AND srm.run_at > datetime('now', '-180 days')
     )
     LIMIT 50;"
   ```

2. **Clean up deleted accounts:**
   ```bash
   # View deleted accounts
   sqlite3 data/cache.db "
     SELECT username, fetched_at
     FROM shadow_account
     WHERE bio = '[ACCOUNT DELETED OR SUSPENDED]';"
   ```

---

## Performance Tuning

### Slow API Response

If `/api/metrics/compute` is slow (>3 seconds):

1. **Check graph size:**
   ```sql
   SELECT COUNT(*) FROM shadow_account;  -- Target: <10k
   SELECT COUNT(*) FROM shadow_edge;     -- Target: <50k
   ```

2. **Enable caching** (future Option C)

3. **Limit graph scope:**
   - Use `min_followers` filter
   - Use `mutual_only` filter

### Slow Enrichment

If enrichment is slower than expected:

1. **Check delays:**
   - Current: `--delay-min X --delay-max Y`
   - Minimum safe: `--delay-min 5 --delay-max 10`

2. **Check scrolls:**
   - Reduce `--max-scrolls` for faster (less complete) runs

3. **Skip already-scraped:**
   - Use `--skip-if-ever-scraped` to avoid redundant work

---

## Emergency Contacts

For urgent issues:
- GitHub Issues: https://github.com/anantham/map-tpot/issues
- See SECURITY.md for security-specific concerns

---

*Keep this runbook updated as you discover new issues and solutions.*
