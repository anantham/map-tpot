# Glossary

Definitions for terminology used throughout the map-tpot project.

---

## Core Concepts

### TPOT (This Part of Twitter)
A loosely-defined community on Twitter/X characterized by interest in rationality, effective altruism, technology, philosophy, and intellectual discourse. Sometimes called "weird Twitter" or "post-rat Twitter." The community has no formal membership but is recognizable through follow patterns and engagement.

### Community Archive
A public Supabase PostgreSQL database containing data voluntarily uploaded by ~275 Twitter users. Includes:
- 6.9 million tweets
- 12.3 million likes
- Complete follower/following relationships
- Profile metadata

The archive is read-only and accessible via Supabase anon key.

**URL:** `https://fabxmporizzqflnftavs.supabase.co`

### Shadow Account
An account discovered through enrichment (Selenium scraping) rather than from the Community Archive. Shadow accounts:
- Have IDs prefixed with `shadow:` until resolved (e.g., `shadow:username`)
- Are stored in `shadow_account` and `shadow_edge` tables
- Have provenance metadata tracking how they were discovered
- May have incomplete data (no bio, no follower counts)

### Shadow Edge
A follow relationship discovered through enrichment, stored in `shadow_edge` table. Includes:
- Direction (`outbound` = source follows target, `inbound` = target follows source)
- Source channel (how it was discovered)
- Timestamp metadata

---

## Graph Metrics

### PageRank
A network centrality metric originally developed by Google to rank web pages. In this context:
- Measures "importance" based on who follows whom
- Uses **personalized** PageRank with seed accounts as restart nodes
- Higher PageRank = more "status" in the network
- Configured via α (alpha) weight slider

### Betweenness Centrality
Measures how often a node lies on the shortest path between other nodes:
- High betweenness = "bridge" connecting different parts of the network
- Computed on undirected (mutual-only) graph
- Configured via β (beta) weight slider

### Louvain Communities
Community detection algorithm that groups nodes into clusters:
- Maximizes "modularity" (dense connections within groups, sparse between)
- Resolution parameter controls granularity (higher = more, smaller communities)
- Visualized via node colors in the graph explorer

### Engagement Score
Aggregate measure of activity based on:
- Number of tweets
- Number of likes received
- Interaction frequency
- Configured via γ (gamma) weight slider

### Composite Score
Weighted combination of all metrics:
```
composite = α × PageRank + β × Betweenness + γ × Engagement
```
Used for final ranking in the graph explorer.

---

## Enrichment Terms

### Enrichment
The process of expanding the graph beyond Community Archive accounts by:
1. Visiting Twitter profile pages via Selenium
2. Scraping follower/following lists
3. Extracting profile metadata
4. Storing results in shadow tables

### Seed (Enrichment)
An account targeted for enrichment. Seeds are processed in order:
1. Preset seeds (curated list)
2. Center user's following (if `--center` specified)
3. Archive accounts
4. Discovered shadow accounts

### Seed (PageRank)
Accounts used as restart nodes in personalized PageRank. Determines "whose perspective" the ranking represents. Different seeds produce different rankings.

### Center User
The primary account for enrichment, specified via `--center username`. The enrichment pipeline:
1. Scrapes the center user first
2. Prioritizes their following list for subsequent enrichment
3. Builds an ego-network view

### Coverage
Ratio of captured accounts to claimed totals:
```
coverage = (captured_count / claimed_total) × 100%
```
- Low coverage (<10%) indicates rate limiting or early scroll termination
- High coverage (>30%) is rare due to Twitter limits

### Skip Policy
Rules determining when to skip re-scraping an account:
- **Fresh data:** Last scrape within 180 days
- **Sufficient coverage:** Both lists >10% coverage
- **Already scraped:** `--skip-if-ever-scraped` flag

---

## Data Model Terms

### Edge Direction
Edges are stored from the perspective of the scraped account:

| Direction | Meaning | Source |
|-----------|---------|--------|
| `outbound` | source_id follows target_id | Scraped from `/following` page |
| `inbound` | target_id follows source_id | Scraped from `/followers` page |

### Mutual Follow
A bidirectional relationship where A follows B AND B follows A. The graph explorer's "mutual-only" filter shows only these edges.

### Account ID vs Username
- **Account ID:** Numeric Twitter identifier (e.g., `1464483769222680582`)
- **Username:** Twitter handle without @ (e.g., `nosilverv`)
- **Shadow ID:** Temporary ID before real ID is known (e.g., `shadow:nosilverv`)

---

## Infrastructure Terms

### Cache (SQLite)
Local database (`data/cache.db`) storing:
- Community Archive data (mirrored from Supabase)
- Shadow accounts and edges
- Scrape metrics and history

Default freshness: 7 days before re-fetching from Supabase.

### Flask API
Backend server providing:
- `/health` — Health check
- `/api/graph-data` — Node and edge data
- `/api/metrics/compute` — Dynamic metric computation
- `/api/metrics/presets` — Seed presets

Default port: 5001

### Graph Explorer
React + Vite frontend for interactive visualization:
- Force-directed layout via `react-force-graph-2d`
- Real-time parameter adjustment
- CSV/JSON export

Default port: 5173

---

## CLI Flags (Common)

| Flag | Purpose |
|------|---------|
| `--center USERNAME` | Prioritize this account's network |
| `--skip-if-ever-scraped` | Skip accounts with existing data |
| `--auto-confirm-first` | Skip confirmation prompts |
| `--include-shadow` | Include shadow data in analysis |
| `--mutual-only` | Filter to mutual follows only |
| `--max-scrolls N` | Max scroll attempts per list |
| `--quiet` | Minimal console output |

---

## ADR (Architecture Decision Record)
Document capturing a significant architectural decision:
- Context: Why the decision was needed
- Decision: What was chosen
- Rationale: Why this option
- Consequences: What follows from the decision

Located in `tpot-analyzer/docs/adr/`.

---

## Abbreviations

| Abbrev | Full Form |
|--------|-----------|
| ADR | Architecture Decision Record |
| API | Application Programming Interface |
| BT | Betweenness (centrality) |
| CLI | Command Line Interface |
| CSV | Comma-Separated Values |
| DB | Database |
| DOM | Document Object Model |
| ENG | Engagement (score) |
| PR | PageRank |
| SQL | Structured Query Language |
| UI | User Interface |

---

*See also: [DATABASE_SCHEMA.md](tpot-analyzer/docs/DATABASE_SCHEMA.md) for complete data model documentation.*
