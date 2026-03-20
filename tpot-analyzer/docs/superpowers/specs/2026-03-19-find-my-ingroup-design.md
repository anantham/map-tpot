# Find My Ingroup — Static Public Site Design

**Date:** 2026-03-19
**Status:** Approved
**Curator:** Aditya

## Purpose

A lightweight static site where anyone can type their Twitter handle and see their soft community membership across a power user's curated TPOT ontology. The site incentivizes data contribution through a visual mechanic: classified accounts get colorful cards, propagated accounts get grayscale cards. Zero backend, free hosting on Vercel.

## User Types

**Casual user:** visits the site, types their handle, sees their community breakdown. May download and share their card.

**Power user:** runs the full research pipeline locally (labeling, classification, clustering), then exports results as static JSON and deploys. The published site is a read-only snapshot of their analysis.

## Architecture

```
Power User's Machine                          Vercel (free tier)
+-----------------------+                     +------------------+
| SQLite + Parquet      |                     | public-site/     |
| (communities, graph,  |  export script      |   dist/          |
|  account metadata,    | ------------------> |     index.html   |
|  propagation data)    |  produces JSON      |     data.json    |
|                       |  bundle             |     search.json  |
| scripts/              |                     |     assets/      |
|   export_public_site  |                     |                  |
+-----------------------+                     +------------------+
```

Two JSON artifacts, no API, no database in production.

## Export Pipeline

**Script:** `scripts/export_public_site.py`

**Inputs:**
- `archive_tweets.db` — community table (names, colors, descriptions), community_account table (298 accounts, soft membership weights)
- `community_propagation.npz` — propagated community scores for ~95K shadow nodes (from `scripts/propagate_community_labels.py`)
- `graph_snapshot.nodes.parquet` — account metadata (username, display_name, bio, num_followers, profile_image_url)

**Outputs** (written to `public-site/public/`):
- `data.json` (~50KB) — communities + classified accounts with full membership scores
- `search.json` (~15MB on disk, ~3-5MB gzip transfer via Vercel CDN) — handle lookup index with propagated scores inline. Excluded from Git — generated at deploy time.

**Classified account query:** All distinct `account_id` values from `community_account` inner-joined with `community` (excludes orphans). The 0.05 weight threshold applies only to individual membership entries within each account's `memberships` array, not to account inclusion. The exact count depends on current data (approximately 298 as of 2026-03-19).

**Searchable account count:** The 95K figure is the total propagated node count before username filtering. The actual `search.json` entry count will be lower — shadow nodes without resolved usernames in the parquet are excluded. The export script logs the miss rate.

**Behavior:**
- If `community_propagation.npz` doesn't exist, warns and exports only classified accounts
- Membership weights below 0.05 are filtered out (noise reduction)
- **Abstain gate for propagated accounts:** if a propagated account's max membership weight is below 0.10 (the abstain threshold per ADR-012), or if all memberships are filtered out by the 0.05 floor, the account is excluded from `search.json` entirely. These accounts have insufficient signal to present as community placements — they would mislead users. The export script logs the count of abstained handles.
- Accounts without a username are excluded from the search index
- Bio intentionally excluded from propagated entries — shadow node bios are frequently null and would bloat `search.json` without adding meaningful signal
- `followers` in the public JSON corresponds to `num_followers` in internal SQLite/parquet — renamed for API cleanliness
- Script is idempotent — safe to re-run after adding more labels

## JSON Schema

### data.json

```json
{
  "meta": {
    "exported_at": "2026-03-19T14:30:00Z",
    "curator": "aditya",
    "total_classified": 298,
    "total_searchable": 42000
  },
  "communities": [
    {
      "id": "bbfe5387-...",
      "name": "LLM Whisperers & ML Tinkerers",
      "color": "#8bc34a",
      "description": "Builders and tinkerers working with large language models...",
      "member_count": 73
    }
  ],
  "accounts": [
    {
      "id": "4683326078",
      "username": "rslantonie",
      "display_name": "R. Slantonie",
      "bio": "Building things with words and code",
      "followers": 1200,
      "tier": "classified",
      "memberships": [
        { "community_id": "bbfe5387-...", "weight": 0.85 },
        { "community_id": "a1b2c3d4-...", "weight": 0.12 }
      ]
    }
  ]
}
```

### search.json

```json
{
  "handles": {
    "rslantonie": { "id": "4683326078", "tier": "classified" },
    "shadowuser": {
      "id": "9876543210",
      "tier": "propagated",
      "display_name": "Shadow User",
      "followers": 340,
      "memberships": [
        { "community_id": "bbfe5387-...", "weight": 0.45 },
        { "community_id": "c3d4e5f6-...", "weight": 0.30 }
      ]
    }
  }
}
```

**Design decisions:**
- Propagated accounts carry memberships inline in `search.json` to avoid a second lookup
- Classified accounts: after `search.json` returns `{ "id": "...", "tier": "classified" }`, the frontend looks up the full profile in `data.json`. On load, `App.jsx` builds a `Map<id, account>` from `data.json.accounts` for O(1) lookup by account ID.
- All handles stored lowercase for case-insensitive matching
- Community IDs are UUIDs (matching the SQLite schema)
- `meta.total_searchable` is the post-filter exported handle count (after username resolution + abstain gate), not the raw propagated node count

## Frontend

### Tech Stack

Vite + React. No router (single page), no state management library (just useState). Minimal dependencies.

### File Structure

```
tpot-analyzer/public-site/
  package.json
  vite.config.js
  vercel.json
  index.html
  public/
    data.json              <- generated by export script
    search.json            <- generated by export script
  src/
    main.jsx
    App.jsx                <- search bar + result routing
    SearchBar.jsx          <- autocomplete against search.json
    CommunityCard.jsx      <- the result card (color or grayscale)
    CardDownload.jsx       <- canvas-to-PNG logic
    ContributePrompt.jsx   <- "not found" / contribution paths
    styles.css
```

### User Flow

1. **Landing page:** search bar centered, site name, tagline ("Find where you belong in TPOT")
2. **Type handle:** strip leading `@`, trim whitespace, lowercase-normalize, then autocomplete against `search.json` (lazy-loaded on first keystroke, cached in memory). Handles are ASCII-only so no Unicode normalization beyond this is needed.
3. **Result:** one of three outcomes based on account tier

### Three Card Tiers

| Tier | Visual | Data Source | Message |
|------|--------|-------------|---------|
| **Classified** (298) | Full color — community bars in hex colors, vibrant design | `data.json` accounts | "Your ingroup profile" |
| **Propagated** (~95K) | Grayscale — identical layout, monochrome bars and muted palette | `search.json` inline memberships | "Based on your network position. Contribute your data to see yourself in color." |
| **Not found** | No card | N/A | "We don't have you in our database yet." |

### Card Content

- **Header:** username, display name
- **Bio** (classified tier only — propagated accounts may not have bios)
- **Community bars:** sorted by weight descending, labeled with community name + percentage
- **Visual:** bars use community hex colors (classified) or grayscale gradient (propagated)
- **Footer:** "Download your card" button

### PNG Download

Client-side implementation:
1. Render card content to a hidden `<canvas>` element
2. Draw community bars, text, username — matching the on-screen card
3. `canvas.toDataURL('image/png')` → trigger download
4. Downloaded image is the same visual (colorful or grayscale) the user sees on screen

No server-side rendering needed.

### Contribution Paths

Shown for propagated and not-found accounts:

1. **DM the curator** — link to Twitter DM
2. **Upload to Community Archive** — link to community-archive GitHub with brief explanation
3. **Clone the repo** — link to this project's GitHub, "become a power user"

**Config contract:** Curator-specific URLs are sourced from `data.json.meta.links`, populated by the export script from a config section. This keeps deploys reproducible — no hardcoded URLs in the frontend.

```json
"meta": {
  "links": {
    "curator_dm": "https://twitter.com/messages/compose?recipient_id=NUMERIC_ID",
    "community_archive": "https://github.com/community-archive/community-archive",
    "repo": "https://github.com/youruser/tpot-analyzer"
  }
}
```

The export script reads these from a `[public_site]` section in a config file (e.g., `config/public_site.yaml`) or falls back to sensible defaults. The frontend reads `data.json.meta.links` — never hardcodes URLs.

## Data Flow Summary

```
Power user runs analysis locally
    |
    v
scripts/export_public_site.py
    |
    +-- reads archive_tweets.db (communities, memberships)
    +-- reads community_propagation.npz (95K propagated scores)
    +-- reads graph_snapshot.nodes.parquet (account metadata)
    |
    v
Writes: public-site/public/data.json + search.json
    |
    v
cd public-site && npm run build
    |
    v
vercel deploy (or any static host)
```

## Deployment

```bash
# Full publish workflow:
cd tpot-analyzer
python -m scripts.export_public_site
cd public-site
npm install && npm run build
vercel deploy

# To update after adding more labels:
python -m scripts.export_public_site   # re-export
cd public-site && vercel deploy        # re-deploy
```

### Vercel Configuration

```json
{
  "rewrites": [{ "source": "/((?!data\\.json|search\\.json|assets/).*)", "destination": "/index.html" }],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" }
      ]
    }
  ]
}
```

## What's NOT in v1

- **Map/explorer view** — spectral layout visualization (v2, the 2D scatter plot with community colors). Omit entirely from v1 UI — no greyed-out placeholder.
- **OpenGraph preview images** — server-rendered social cards for link sharing (v2)
- **Multiple curator support** — different power users' ontologies side by side (future)
- **Framework/data separation** — separating the tool from the analysis (future, if demand)
- **Real-time updates** — site is a static snapshot, updated manually by power user

## Success Criteria

- Someone can type a handle and get a result within 1 second
- Classified accounts see a colorful community card with accurate percentages
- Propagated accounts see a grayscale card that incentivizes data contribution
- The downloaded PNG is shareable on Twitter
- Total site bundle < 5MB (excluding search.json lazy load)
- Deployable to Vercel free tier with zero configuration beyond `vercel deploy`
