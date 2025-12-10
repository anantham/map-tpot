# Architecture Overview

This document provides a system-level view of the map-tpot project, showing how components interact and data flows through the system.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 EXTERNAL DATA SOURCES                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────┐        ┌─────────────────────────────┐            │
│  │    Community Archive        │        │       Twitter/X Web         │            │
│  │    (Supabase PostgreSQL)    │        │    (via Selenium/cookies)   │            │
│  │                             │        │                             │            │
│  │  • 275 archived accounts    │        │  • Live profile pages       │            │
│  │  • 6.9M tweets              │        │  • Follower/following lists │            │
│  │  • 12.3M likes              │        │  • Profile metadata         │            │
│  │  • Follow relationships     │        │                             │            │
│  └─────────────┬───────────────┘        └─────────────┬───────────────┘            │
│                │                                      │                             │
│                │ REST API                             │ Selenium WebDriver          │
│                │ (read-only)                          │ (authenticated)             │
│                │                                      │                             │
└────────────────┼──────────────────────────────────────┼─────────────────────────────┘
                 │                                      │
                 ▼                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    tpot-analyzer                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                           DATA LAYER (src/data/)                              │   │
│  │                                                                               │   │
│  │  ┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────────┐  │   │
│  │  │  CachedDataFetcher  │    │    ShadowStore      │    │   SQLite Cache   │  │   │
│  │  │                     │    │                     │    │   (cache.db)     │  │   │
│  │  │  • fetch_profiles() │    │  • upsert_accounts()│    │                  │  │   │
│  │  │  • fetch_accounts() │    │  • upsert_edges()   │    │  ┌────────────┐  │  │   │
│  │  │  • fetch_followers()│    │  • get_edges()      │    │  │  account   │  │  │   │
│  │  │  • fetch_following()│    │  • edge_summary()   │    │  │  profile   │  │  │   │
│  │  │                     │    │  • scrape_metrics() │    │  │  followers │  │  │   │
│  │  │  Caches to SQLite   │    │                     │    │  │  following │  │  │   │
│  │  │  (7-day freshness)  │    │  Shadow-specific    │    │  ├────────────┤  │  │   │
│  │  └─────────┬───────────┘    │  tables for         │    │  │shadow_acct │  │  │   │
│  │            │                │  enriched data      │    │  │shadow_edge │  │  │   │
│  │            │                └──────────┬──────────┘    │  │scrape_metr │  │  │   │
│  │            │                           │               │  └────────────┘  │  │   │
│  │            └───────────────────────────┼───────────────┼──────────────────┘  │   │
│  │                                        │               │                      │   │
│  └────────────────────────────────────────┼───────────────┼──────────────────────┘   │
│                                           │               │                          │
│                                           │               │                          │
│  ┌────────────────────────────────────────┼───────────────┼─────────────────────┐   │
│  │                    ENRICHMENT LAYER (src/shadow/)      │                      │   │
│  │                                        │               │                      │   │
│  │  ┌─────────────────────┐  ┌───────────┴───────┐  ┌────┴────────────────┐    │   │
│  │  │  SeleniumWorker     │  │ HybridShadow     │  │   X API Client      │    │   │
│  │  │                     │  │ Enricher         │  │   (optional)        │    │   │
│  │  │  • fetch_profile()  │  │                  │  │                     │    │   │
│  │  │  • fetch_following()│←─│  • enrich()      │─→│  • lookup_users()   │    │   │
│  │  │  • fetch_followers()│  │  • skip_policy() │  │  • get_list_members │    │   │
│  │  │  • scroll_and_parse │  │  • refresh_list()│  │                     │    │   │
│  │  │                     │  │                  │  │  Bearer token auth  │    │   │
│  │  │  Cookie auth        │  │  Orchestrates    │  │  Rate-limit aware   │    │   │
│  │  │  Chrome WebDriver   │  │  data collection │  └─────────────────────┘    │   │
│  │  └─────────────────────┘  └──────────────────┘                             │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│                                           │                                          │
│                                           ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         GRAPH LAYER (src/graph/)                              │   │
│  │                                                                               │   │
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐   │   │
│  │  │    GraphBuilder     │  │      Metrics        │  │       Seeds         │   │   │
│  │  │                     │  │                     │  │                     │   │   │
│  │  │  • build_graph()    │  │  • pagerank()       │  │  • parse_list()     │   │   │
│  │  │  • inject_shadow()  │  │  • betweenness()    │  │  • resolve_seeds()  │   │   │
│  │  │  • filter_mutual()  │  │  • louvain()        │  │  • preset_seeds()   │   │   │
│  │  │                     │  │  • engagement()     │  │                     │   │   │
│  │  │  NetworkX DiGraph   │  │  • composite()      │  │  Username ↔ ID      │   │   │
│  │  │                     │  │                     │  │  resolution         │   │   │
│  │  └──────────┬──────────┘  └──────────┬──────────┘  └─────────────────────┘   │   │
│  │             │                        │                                        │   │
│  └─────────────┼────────────────────────┼────────────────────────────────────────┘   │
│                │                        │                                            │
│                └────────────┬───────────┘                                            │
│                             │                                                        │
│                             ▼                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                           API LAYER (src/api/)                                │   │
│  │                                                                               │   │
│  │  ┌──────────────────────────────────────────────────────────────────────┐    │   │
│  │  │                     Flask Server (port 5001)                          │    │   │
│  │  │                                                                       │    │   │
│  │  │   GET /health              → {"status": "ok"}                        │    │   │
│  │  │   GET /api/graph-data      → {nodes, edges, counts}                  │    │   │
│  │  │   POST /api/metrics/compute → {pagerank, betweenness, composite}     │    │   │
│  │  │   GET /api/metrics/presets → {preset_name: [seeds]}                  │    │   │
│  │  │                                                                       │    │   │
│  │  └──────────────────────────────────────────────────────────────────────┘    │   │
│  │                                                                               │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└──────────────────────────────────────────────┬──────────────────────────────────────┘
                                               │
                                               │ HTTP/JSON
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (graph-explorer/)                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    React + Vite (port 5173)                                   │   │
│  │                                                                               │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐   │   │
│  │  │  GraphExplorer  │  │     data.js     │  │  react-force-graph-2d       │   │   │
│  │  │                 │  │                 │  │                             │   │   │
│  │  │  • Seed input   │  │  • fetchGraph() │  │  • Force simulation         │   │   │
│  │  │  • Weight sliderds  │  • computeMetrics()  │  • Interactive canvas    │   │   │
│  │  │  • Filters      │  │  • checkHealth()│  │  • Zoom/pan/drag            │   │   │
│  │  │  • Export       │  │                 │  │  • Node tooltips            │   │   │
│  │  │                 │  │  API client     │  │                             │   │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘   │   │
│  │                                                                               │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                               │
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │   Browser    │
                                        │              │
                                        │  User views  │
                                        │  interactive │
                                        │  graph       │
                                        └──────────────┘
```

---

## Component Descriptions

### External Data Sources

| Source | Purpose | Access Method |
|--------|---------|---------------|
| Community Archive | Base dataset of opted-in accounts | Supabase REST API |
| Twitter/X Web | Live profile and relationship data | Selenium with cookies |
| X API (optional) | Metadata enrichment | Bearer token auth |

### Data Layer (`src/data/`)

**CachedDataFetcher**
- Fetches data from Supabase
- Caches to local SQLite (7-day freshness)
- Provides pandas DataFrames

**ShadowStore**
- Manages shadow account/edge tables
- Handles upserts with retry logic
- Tracks scrape metrics

### Enrichment Layer (`src/shadow/`)

**SeleniumWorker**
- Browser automation for Twitter
- Profile and list scraping
- HTML snapshot capture for debugging

**HybridShadowEnricher**
- Orchestrates enrichment pipeline
- Policy-based skip/refresh logic
- Coordinates Selenium and API clients

### Graph Layer (`src/graph/`)

**GraphBuilder**
- Constructs NetworkX DiGraph
- Merges archive and shadow data
- Supports mutual-only filtering

**Metrics**
- PageRank (personalized)
- Betweenness centrality
- Louvain communities
- Composite scoring

### API Layer (`src/api/`)

**Flask Server**
- REST endpoints for frontend
- Dynamic metric computation
- CORS-enabled for local development

### Frontend (`graph-explorer/`)

**React + Vite Application**
- Force-directed visualization
- Real-time parameter adjustment
- CSV/JSON export

---

## Data Flow

### 1. Initial Data Load

```
Supabase → CachedDataFetcher → SQLite cache → GraphBuilder → NetworkX graph
```

### 2. Enrichment Flow

```
Seed list → HybridShadowEnricher → SeleniumWorker → Twitter pages
                                        ↓
                                   Parse HTML
                                        ↓
                                   ShadowStore → SQLite (shadow tables)
```

### 3. Visualization Flow

```
Browser → React app → data.js → Flask API → GraphBuilder + Metrics → JSON response
                                                                           ↓
                                                              react-force-graph-2d
```

---

## Key Design Decisions

| Decision | Rationale | Reference |
|----------|-----------|-----------|
| SQLite cache | Offline support, fast iteration | [ADR 001](tpot-analyzer/docs/adr/001-data-pipeline-architecture.md) |
| Client-side metrics (original) | Sub-200ms response for exploration | [ADR 002](tpot-analyzer/docs/adr/002-graph-analysis-foundation.md) |
| Flask backend | Dynamic seeds, fresh data | [ADR 003](tpot-analyzer/docs/adr/003-backend-api-integration.md) |
| Shadow tables | Explicit provenance for scraped data | [DATABASE_SCHEMA.md](tpot-analyzer/docs/DATABASE_SCHEMA.md) |

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Database | SQLite | Local cache, portable |
| Backend | Python 3.9+, Flask | API, analysis |
| Graph | NetworkX | Algorithms |
| Scraping | Selenium, Chrome | Browser automation |
| Frontend | React, Vite | UI framework |
| Visualization | react-force-graph-2d | Graph rendering |
| Styling | CSS | UI styling |

---

## Deployment Modes

### Development (Local)
- Flask server on port 5001
- Vite dev server on port 5173
- SQLite file in `data/cache.db`

### Production (Planned)
- Not yet implemented
- Would require: static frontend build, production WSGI server, database hosting

---

## Related Projects

### grok-probe

Separate subproject for LLM memorization testing:
- Express server + browser UI
- OpenRouter API integration
- No shared code with tpot-analyzer

---

*See individual component documentation for detailed API references and implementation notes.*
