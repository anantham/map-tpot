# Enrichment Metrics & Observability Proposal

## Current Gaps

**Problem:** You have logs but no structured metrics to answer:
- How many accounts fail (404, suspended, private)?
- What's the scraping success rate?
- What are the top 5 error types?
- How fast is enrichment running (accounts/hour)?
- Are we hitting rate limits?

**Current State:**
- ✅ `ScrapeRunMetrics` stored per-seed (duration, counts, coverage)
- ❌ No aggregation across runs
- ❌ No error categorization
- ❌ No pipeline health dashboard

---

## Proposed Solution: 3-Tier Metrics System

### **Tier 1: Structured Event Logging** (immediate)

Add structured JSON logging for key events:

```python
# src/shadow/metrics.py (new file)
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

METRICS_LOGGER = logging.getLogger("enrichment.metrics")

@dataclass
class EnrichmentEvent:
    event_type: str  # "seed_start", "seed_complete", "seed_error", "account_404", etc.
    timestamp: str
    seed_username: str
    duration_seconds: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    accounts_captured: Optional[int] = None
    edges_captured: Optional[int] = None

    def log(self):
        METRICS_LOGGER.info(json.dumps(asdict(self)))
```

**Usage in enricher.py:**
```python
from src.shadow.metrics import EnrichmentEvent

# At seed start
EnrichmentEvent(
    event_type="seed_start",
    timestamp=datetime.utcnow().isoformat(),
    seed_username=seed.username,
).log()

# On 404 error
EnrichmentEvent(
    event_type="account_404",
    timestamp=datetime.utcnow().isoformat(),
    seed_username=seed.username,
    error_type="NotFound",
    error_message="Profile page returned 404",
).log()
```

**Benefits:**
- Machine-parseable JSON logs
- Easy to grep: `grep '"event_type":"account_404"' logs/enrichment.log | wc -l`
- Foundation for dashboards

---

### **Tier 2: Metrics Aggregation Table** (medium priority)

Store aggregated metrics in database:

```sql
CREATE TABLE enrichment_run_summary (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    total_seeds INTEGER,
    seeds_succeeded INTEGER,
    seeds_failed INTEGER,
    seeds_skipped INTEGER,
    total_accounts_captured INTEGER,
    total_edges_captured INTEGER,
    total_duration_seconds REAL,
    error_breakdown JSON,  -- {"404": 3, "timeout": 2, "rate_limit": 1}
    performance_metrics JSON  -- {"avg_accounts_per_minute": 15.2}
);
```

**Populate from ScrapeRunMetrics:**
```python
# scripts/summarize_metrics.py (new file)
def summarize_recent_runs(days: int = 7):
    engine = create_engine(...)
    store = get_shadow_store(engine)

    # Query scrape_run_metrics from last 7 days
    runs = store.get_recent_scrape_runs(days=days)

    # Aggregate
    summary = {
        "total_seeds": len(runs),
        "succeeded": sum(1 for r in runs if not r.skipped and r.edges_upserted > 0),
        "failed": sum(1 for r in runs if r.skip_reason and "error" in r.skip_reason.lower()),
        "skipped": sum(1 for r in runs if r.skipped),
        "total_accounts": sum(r.accounts_upserted for r in runs),
        "total_edges": sum(r.edges_upserted for r in runs),
        "avg_duration": sum(r.duration_seconds for r in runs) / len(runs),
    }

    print(json.dumps(summary, indent=2))
```

---

### **Tier 3: Real-Time Dashboard** (future)

Web UI showing:
- **Live progress:** Current seed being enriched (with ETA)
- **Success rate:** 85% success, 10% skipped, 5% errors
- **Error breakdown:** Pie chart (404: 3, timeout: 2, rate_limit: 1)
- **Performance:** 12.5 accounts/minute, 3h ETA for remaining seeds
- **Historical trends:** Success rate over time (line chart)

**Tech Stack:**
- FastAPI backend serving metrics from database
- React/Streamlit frontend
- WebSocket for live updates

---

## Quick Wins (Do These First)

### **Option A: Enhance ScrapeRunMetrics with Error Tracking**

Add error categorization to existing metrics:

```python
@dataclass(frozen=True)
class ScrapeRunMetrics:
    # ... existing fields ...
    error_type: Optional[str] = None  # "404", "timeout", "rate_limit", "private"
    error_details: Optional[str] = None
```

**CLI command:**
```bash
python -m scripts.summarize_metrics --last-7-days
```

**Output:**
```
Enrichment Summary (Last 7 Days)
================================
Total Seeds: 50
Success: 42 (84%)
Skipped: 5 (10%)
Errors: 3 (6%)

Error Breakdown:
- 404 Not Found: 2
- Timeout: 1

Performance:
- Avg Duration: 45.3s per seed
- Avg Accounts Captured: 187.2
- Avg Coverage: 78.5%
```

---

### **Option B: Structured Logging Only (Minimal)**

Just add JSON event logging, parse logs later:

```bash
# Count 404s
grep '"event_type":"account_404"' logs/enrichment.log | wc -l

# Count timeouts
grep '"error_type":"timeout"' logs/enrichment.log | wc -l

# Success rate
total=$(grep '"event_type":"seed_' logs/enrichment.log | wc -l)
success=$(grep '"event_type":"seed_complete"' logs/enrichment.log | wc -l)
echo "Success: $success / $total"
```

---

## Recommendation: Start with Option A

**Why:**
1. **Leverages existing `ScrapeRunMetrics`** - no new tables
2. **Quick to implement** - add 2 fields, write aggregation script
3. **Immediate value** - answers your questions today
4. **Foundation for Tier 2/3** - can add web UI later

**Implementation Plan:**
1. Add `error_type` and `error_details` to `ScrapeRunMetrics` (5 min)
2. Update enricher to record error types (15 min)
3. Write `scripts/summarize_metrics.py` to query and aggregate (30 min)
4. Run and validate on real data (10 min)

**Total effort: ~1 hour**

---

## What to Track

### **Critical Metrics:**
- ✅ Success rate (seeds enriched without errors)
- ✅ Error types (404, timeout, rate_limit, private, suspended)
- ✅ Scraping speed (accounts/minute, edges/minute)
- ✅ Coverage % (actual vs claimed totals)
- ✅ Duration per seed (identify slow outliers)

### **Nice-to-Have:**
- Cache hit rate (seeds skipped due to freshness)
- Policy triggers (age vs delta refresh reasons)
- Selenium retries (how often do page loads fail?)
- Disk I/O errors (SQLite retry counts)

---

## Decision Point

**Do you want:**
1. **Quick win (1 hour):** Add error tracking to ScrapeRunMetrics + summary script
2. **Structured logging (2 hours):** JSON event logging + grep-based analysis
3. **Full system (1 week):** Database aggregation + web dashboard

I recommend **Option 1** to get immediate value, then iterate.

**Should I implement the quick win now?**
