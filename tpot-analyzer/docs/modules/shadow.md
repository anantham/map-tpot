# Shadow Enrichment — Hybrid Scraping & Active Learning

<!--
Last verified: 2026-03-05
Code hash: bb8bf98
Verified by: agent
-->

## Purpose

Grows the shadow graph by scraping follower/following lists for seed accounts, then ranks
unscraped candidates by information gain so labeling budget goes where it matters most.
The subsystem has two independent concerns: **data collection** (Selenium + X API) and
**candidate selection** (active-learning acquisition scorer).

## Design Rationale

### Why hybrid Selenium + X API?

Twitter's web app requires JavaScript execution and authentication cookies to render follower
lists — a bare HTTP client gets rate-limited or blocked. Selenium drives a real Chromium
instance that can authenticate and scroll like a human. The X API v2 is used as a fallback
for profile-only lookups when Selenium is rate-limited or only profile metadata is needed
(not full follower lists).

### Why an acquisition scorer?

Scraping is slow (minutes per account). With hundreds of unscraped candidates, naive
round-robin wastes budget on accounts that add little new information. The acquisition
scorer ranks by expected information gain per unit scrape time, using five signals derived
from NMF community membership and graph structure.

### Key decisions

| Decision | Chosen | Alternatives considered | Why |
|----------|--------|------------------------|-----|
| Browser automation | Selenium + Chromium | Playwright, requests-html | Existing cookie infrastructure; Selenium WebDriver control more stable for long scrolls |
| Login flow | Manual (default) | Automated credential injection | Avoids hardcoding credentials; human confirms first scrape |
| Pause mechanism | Signal handler on first Ctrl+C | Keyboard interrupt immediate | Graceful: finishes current seed, saves progress, offers resume menu |
| Acquisition weighting | Multi-signal weighted composite | Entropy only, random | Balances uncertainty (entropy/boundary), reach (influence), novelty, community gaps |
| Diversity | MMR greedy O(top_k × n) | Deterministic top-k | Prevents near-duplicate batches from wasting scrape budget |
| Rate limits | Local in-memory window + persistent reset timestamp | Rely on API 429 response | Avoids wasted requests; survives restarts |

### ADR references

- [ADR-009: Golden Curation Schema and Active-Learning Loop](../adr/009-golden-curation-schema-and-active-learning-loop.md)

## Module Map

```
src/shadow/
├── __init__.py          (17 LOC)  — Public exports
├── enricher.py        (2449 LOC)  — Orchestrator: policy, pause/resume, hybrid dispatch
├── selenium_worker.py (2173 LOC)  — Headless browser: scroll, extract handles, detect status
├── x_api_client.py     (167 LOC)  — X API v2 thin wrapper with rate-limit tracking
└── acquisition.py      (659 LOC)  — Active-learning candidate scorer (5 signals + MMR)
```

**Total: 5,465 LOC**

> **Note:** `enricher.py` (2449 LOC) and `selenium_worker.py` (2173 LOC) both exceed the ~300 LOC
> convention threshold. Both pass the single-domain test (enricher = orchestration/policy,
> worker = browser automation), so splitting is not urgent — but they are candidates for
> concern-level decomposition if context window pressure becomes a problem.

## Public API

### Entry point: `HybridShadowEnricher`

```python
from src.shadow import HybridShadowEnricher, ShadowEnrichmentConfig, EnrichmentPolicy, SeedAccount
```

#### `HybridShadowEnricher(store, config, policy=None)`

| Param | Type | Description |
|-------|------|-------------|
| `store` | `ShadowStore` | Persistence layer for accounts, edges, scrape metrics |
| `config` | `ShadowEnrichmentConfig` | Selenium + X API configuration |
| `policy` | `EnrichmentPolicy` | Optional cache-aware refresh policy (default: `EnrichmentPolicy.default()`) |

#### `enrich(seeds: list[SeedAccount]) → dict`

Main workflow. For each seed:
1. Checks policy (`_should_skip_seed`) — skips if recently scraped and under delta threshold
2. Dispatches to `SeleniumWorker.capture_followers()`
3. Persists edges and profile overview to `ShadowStore`
4. Handles Ctrl+C pause → resume/skip/shutdown menu

**Returns:** `{account_id: {skipped, reason, edge_count, elapsed_s}, ...}`

### Config dataclasses

#### `ShadowEnrichmentConfig`

```python
@dataclass
class ShadowEnrichmentConfig:
    selenium_cookies_path: Path     # Exported browser cookies (JSON)
    x_api_bearer_token: str         # X API v2 bearer token
    rate_state_path: Path           # Persisted API rate-limit state
    headless: bool = False          # Run Chrome headless
    scroll_delay_s: float = 1.5     # Delay between scroll steps
    confirm_first_scrape: bool = True  # Pause for manual login confirmation
```

#### `EnrichmentPolicy`

```python
@dataclass
class EnrichmentPolicy:
    list_refresh_days: int = 180      # Re-scrape follower list after N days
    profile_refresh_days: int = 30    # Re-fetch profile metadata after N days
    edge_delta_threshold: float = 0.05  # Skip if edge count change < 5%
    auto_confirm: bool = False        # Skip login confirmation prompt
```

Load from file: `EnrichmentPolicy.from_file(path)` — reads JSON.

#### `SeedAccount`

```python
@dataclass
class SeedAccount:
    account_id: str
    username: str
    trust: float = 1.0   # Edge weight multiplier
```

### Acquisition scorer: `score_candidates()`

```python
from src.shadow.acquisition import score_candidates, AcquisitionWeights

ranked = score_candidates(
    candidates,          # list[SeedAccount] — unscraped accounts to rank
    shadow_store,        # ShadowStore
    community_conn,      # sqlite3.Connection to community membership DB
    run_id,              # str — for logging
    weights,             # AcquisitionWeights (optional, uses defaults)
    top_k=50,            # How many to return
    lambda_mmr=0.7,      # MMR diversity weight (0=max diversity, 1=max relevance)
)
```

**Returns:** `list[SeedAccount]` ordered by acquisition score (highest first), length ≤ `top_k`.

## Acquisition Scoring Algorithm

### Five signals (all normalized to [0, 1])

| Signal | Weight | Formula | Interpretation |
|--------|--------|---------|---------------|
| **Entropy** | 35% | H(membership) / log(K) | How uncertain is community assignment? 1.0 = unknown |
| **Boundary** | 25% | 1 − (p_max1 − p_max2) | How close are the top 2 communities? 1.0 = equivocal |
| **Influence** | 20% | log(1 + followers) / max | How many people will this account's edges connect? |
| **Novelty** | 15% | 1 − max cosine_sim(scraped_set) | How different is this account from what we already have? |
| **Coverage boost** | 5% | 1 / (1 + min_community_size) | Is this account in an under-represented community? |

### Composite formula

```
raw_score = 0.35·entropy + 0.25·boundary + 0.20·influence + 0.15·novelty + 0.05·coverage
final_score = raw_score / expected_scrape_time_s
```

**Expected scrape time:** `followers/500 + 30` seconds (proxy for cold-start); median of last 3 runs for previously-scraped accounts. Clamped to [30, 3600].

### MMR diversity pass

After scoring, a greedy Maximal Marginal Relevance pass selects `top_k` candidates:

```
select_i = argmax_i [ λ · final_score_i − (1 − λ) · max_j∈selected sim(i, j) ]
```

Default `λ = 0.7` (relevance-weighted). Similarity is cosine similarity of NMF membership vectors. Complexity: O(top_k × n).

### Missing data handling

- Account with no community membership: entropy = 1.0, boundary = 1.0 (maximum uncertainty = highest priority)
- No previous scrape runs: uses proxy scrape time formula
- No follower count in shadow store: falls back to `account_followers` table

## Selenium Worker internals

### Anti-detection measures

`SeleniumWorker` applies three countermeasures to avoid Twitter throttling:

1. **WebDriver flag removal** — removes `enable-automation` switch and injects `navigator.webdriver = undefined` via CDP
2. **Visibility spoofing** — injects JS to mock `document.hidden = false` and `document.visibilityState = "visible"`, preventing Twitter from pausing content when the tab is unfocused
3. **Focus restoration** — simulates mouse movements and right-click to wake the browser when throttling is detected mid-scroll

### Account status detection

`detect_account_status(account_id, username)` scrapes the profile page and classifies the account as:
- `active` — normal profile loads
- `deleted` — "account doesn't exist" message
- `suspended` — Twitter suspension notice
- `protected` — padlock / private account

### Signal handling during driver init

`SeleniumWorker.__init__` temporarily ignores `SIGINT` during ChromeDriver startup to prevent the subprocess from receiving Ctrl+C before the driver is fully initialized.

## Dependencies

| Depends on | Why | Notes |
|------------|-----|-------|
| `ShadowStore` | Persist accounts, edges, scrape metrics | `src/data/shadow_store.py` |
| `EnrichmentPolicy` JSON file | Control refresh cadence | Default: `config/enrichment_policy.json` |
| Browser cookies | Selenium authentication | `secrets/cookies.json` (gitignored) |
| X API bearer token | Profile-only fallback | Env var or config |
| NMF community DB | Acquisition scorer novelty/coverage signals | `data/outputs/communities.db` |

## CLI

Enrichment is driven from `scripts/enrich_shadow_graph.py`:

```bash
cd tpot-analyzer
.venv/bin/python3 -m scripts.enrich_shadow_graph \
    --seeds data/golden/seed_accounts.json \
    --policy config/enrichment_policy.json \
    --top-k 50
```

Dry-run acquisition scoring (no commits):
```bash
.venv/bin/python3 -m scripts.dry_run_acquisition --top-k 20
```

## Known Limitations

- **`enricher.py` is 2449 LOC** — mixes policy logic, orchestration, and UI (pause menu). If splitting, natural seams are: `policy.py` (refresh decisions), `orchestrator.py` (workflow loop), `pause_ui.py` (interactive menu)
- **`selenium_worker.py` is 2173 LOC** — mixes driver setup, page navigation, scroll logic, and handle extraction. Natural seams: `driver_setup.py`, `page_navigation.py`, `handle_extraction.py`
- **No async** — enrichment is single-threaded; concurrent scraping would require worker pool + locking on `ShadowStore`
- **Acquisition scorer requires community DB** — if NMF hasn't been run, novelty and coverage signals degrade to 1.0 (unknown), which still produces a valid ranking
