# Community Detail Pages — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Context:** Public site (amiingroup.vercel.app) — extend with clickable community pages

---

## Summary

Add community detail pages to the Find My Ingroup public site. Clicking a community name on the homepage navigates to a page showcasing the community's spirit through its prototypical members and their tweets. Shareable via `/?community=<slug>`.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Content source | Existing DB descriptions (evolves with labeling) | Show, don't tell — tweets demonstrate the community |
| Tweet selection | Hybrid: engagement-weighted now, label-driven later | Ships immediately, improves as golden dataset grows |
| Privacy model | Classified-only (298 accounts already in data.json) | Data already public in data.json; community pages increase discoverability (see Privacy section); opt-out mechanism as future gate |
| URL scheme | `/?community=slug` query param with persisted slugs | Consistent with `/?handle=X`, no router needed; slugs stable across renames |
| Layout | Member Spotlights (option C) | People ARE the content — their tweets are the portrait |
| Featured count | Top 5 by NMF weight + expandable "all members" list | Editorial feel with completeness available |
| Data approach | Enrich static data.json export (approach 1) | Zero infrastructure change, works on Vercel as-is |
| Cross-linking | Member handles → `/?handle=X`, member cards show community → `/?community=slug` | Natural bidirectional navigation |

## Query State Model

The app has three mutually exclusive view states, resolved from URL params with strict precedence:

1. **Community page** — `?community=<slug>` is present → render CommunityPage (ignore `handle` if also present)
2. **Account card** — `?handle=<username>` is present (no `community`) → render ResultArea
3. **Homepage** — neither param → render hero + search

**State transitions:**
- "Search again" / back link: `window.history.replaceState` removes both params → homepage
- Click member handle on community page: replaces URL with `?handle=X` (removes `community`)
- Click community tag on account card: replaces URL with `?community=slug` (removes `handle`)
- Browser back button: works naturally via `replaceState` history

**Invalid states:** `?community=nonexistent-slug` → show "Community not found" message with link back to homepage. Same pattern as current not-found handle behavior.

## Member Count Semantics

The page displays **browseable member count** — the number of classified members that actually appear on this page (featured + all_members list). This equals `featured_members.length + all_members.length` from `data.json`, NOT the raw `member_count` from the DB (which includes sub-threshold members not exported).

The header reads: `{browseable_count} members · {featured_count} featured`.

## Privacy & Discoverability

Community pages increase discoverability of account data that is already public in `data.json`. Currently, a visitor must search for a specific handle to see their community membership. Community pages flip this: they proactively surface members grouped by community, making browsing possible.

**Why this is acceptable:**
- All data comes from the Community Archive (open-source public Twitter data)
- Only the 298 classified accounts appear (already exported and searchable)
- No new data is exposed — the same usernames, bios, and tweets are already in `data.json`

**What's honestly different:**
- Discovery shifts from pull (search) to push (browse)
- Community grouping reveals social structure that individual cards don't
- Featured spotlights create a hierarchy of visibility

**Mitigations:**
- Opt-out mechanism planned as future extension
- Only classified accounts (human-reviewed membership) appear, not propagated
- No private data (DMs, protected tweets) is involved

## Page Structure

```
/?community=llm-whisperers-ml-tinkerers

┌─────────────────────────────────────┐
│ ← Back to Find My Ingroup           │
├─────────────────────────────────────┤
│         [color dot]                 │
│    Community Name                   │
│    Description text (from DB)       │
│    66 browseable · 5 featured · 🔗  │
├─────────────────────────────────────┤
│ PROTOTYPICAL MEMBERS                │
│                                     │
│ ┌─ Spotlight Card ───────────────┐  │
│ │ [avatar] @handle  (weight 0.93)│  │
│ │ Bio text...                    │  │
│ │ ┌─ Tweet ──────────────────┐   │  │
│ │ │ 🧵 thread · Jan 15  ↗ X │   │  │
│ │ │ Tweet text...            │   │  │
│ │ │ ❤ 342 · 🔁 89           │   │  │
│ │ └──────────────────────────┘   │  │
│ │ ┌─ Tweet ──────────────────┐   │  │
│ │ │ ↩ reply · Feb 3     ↗ X │   │  │
│ │ │ Tweet text...            │   │  │
│ │ └──────────────────────────┘   │  │
│ └────────────────────────────────┘  │
│                                     │
│ (× 5 spotlight cards)               │
├─────────────────────────────────────┤
│ ALL MEMBERS · 66                    │
│ ┌──────────┐ ┌──────────┐          │
│ │ @handle   │ │ @handle   │         │
│ │ Bio...    │ │ Bio...    │         │
│ └──────────┘ └──────────┘          │
│ (2-column grid, each → /?handle=X) │
├─────────────────────────────────────┤
│ ← Builders · EA, AI Safety · ...   │
│ Find My Ingroup · amiingroup.app   │
└─────────────────────────────────────┘
```

## Data Schema Changes

### Enriched community object in `data.json`

```json
{
  "id": "bbfe5387-...",
  "name": "Builders",
  "slug": "builders",
  "color": "#9b59b6",
  "description": "Tech entrepreneurship, indie hacking...",
  "member_count": 66,
  "featured_members": [
    {
      "username": "builder1",
      "display_name": "Builder One",
      "bio": "Shipping daily...",
      "weight": 0.93,
      "tweets": [
        {
          "id": "17839201...",
          "text": "Just launched my third product...",
          "created_at": "2025-01-15T14:32:00Z",
          "type": "thread",
          "favorite_count": 342,
          "retweet_count": 89
        }
      ]
    }
  ],
  "all_members": [
    { "username": "member5", "display_name": "Name", "bio": "Short bio..." }
  ]
}
```

### Slug generation and persistence

Slugs are **persisted, not regenerated**. On first export, a slug is derived from the community name. On subsequent exports, the previous slug is reused from a `slug_registry.json` file in the export output directory. This ensures URLs survive community renames.

**Generation rule (first time only):** lowercase, replace `&` with empty, collapse runs of non-alphanumeric characters to a single hyphen, trim leading/trailing hyphens.

**Persistence:** `export_public_site.py` reads `slug_registry.json` (a `{community_id: slug}` map) before export. New communities get auto-generated slugs; existing communities keep their registered slug. The registry is written back after export.

**Manual override:** A curator can edit `slug_registry.json` to change a slug (e.g., after a rename where the old slug is confusing). Old slugs are not automatically redirected — this is a future extension.

Examples (initial generation):
- "Builders" → `builders`
- "LLM Whisperers & ML Tinkerers" → `llm-whisperers-ml-tinkerers`
- "Queer TPOT & Identity Experimentalists" → `queer-tpot-identity-experimentalists`
- "EA, AI Safety & Forecasting" → `ea-ai-safety-forecasting`

### Tweet type detection

1. `text` starts with `RT @` → `"retweet"`
2. Tweet has `reply_to_tweet_id` set (DB column in `tweets` table) → `"reply"`
3. Same account has tweet posted within 5 minutes before/after → `"thread"` (heuristic; query bounded to featured members' tweet IDs only, not full 5.5M table)
4. Otherwise → `"tweet"`

### Tweet selection (hybrid strategy)

**Phase 1 (day one):** Top 5 tweets by `favorite_count + retweet_count * 2` from each featured member. Prefer diversity: at most 2 threads, include at least 1 reply if available.

**Phase 2 (as labels grow):** When golden dataset has labeled tweets with topic tags for a community, prefer labeled tweets with high-confidence community-relevant tags. Fall back to engagement-weighted for gaps.

Selection logic lives in `export_public_site.py` — a single function `select_community_tweets(account_id, community_id, n=5)` that checks for labels first, falls back to engagement.

### Tweet linking

Each tweet links to `https://x.com/{username}/status/{tweet_id}`. The `tweet_id` comes from the `tweet_id` column in the `tweets` table (primary key). In the exported JSON, this is stored as the `id` field within each tweet object.

## Files to Modify

### Export pipeline
- **`scripts/export_public_site.py`** — Add slug generation/persistence, `featured_members` selection (top 5 by weight), tweet selection with type detection, `all_members` compact list. Add `select_community_tweets()` function. Read/write `slug_registry.json`.
- **`public-site/public/slug_registry.json`** (new) — Persisted `{community_id: slug}` map, committed to repo.

### Frontend
- **`public-site/src/App.jsx`** — Detect `?community=slug` param, look up community by slug, render `CommunityPage` component. Add slug-based `communitySlugMap`.
- **`public-site/src/CommunityPage.jsx`** (new) — The spotlight layout: hero header, spotlight cards, all-members grid, sibling nav, share button.
- **`public-site/src/styles.css`** — Community page styles (spotlight cards, tweet cards, member grid, sibling nav).

### Homepage changes
- **`public-site/src/App.jsx`** — Showcase tags become clickable links: `<span>` → `<a href="/?community=slug">`.

### Data size impact

Current `data.json`: ~400-500KB.
Added data: 14 communities × (5 featured × ~1KB each + ~60 compact members × ~100B each) ≈ **~150KB**.
New total: ~550-650KB. Negligible impact on load time.

## Navigation Flow

```
Homepage                    Community Page              Account Card
┌──────────┐               ┌──────────────┐            ┌──────────┐
│ 14 tags  │──click tag──→│ Spotlights   │            │ Card     │
│ (links)  │               │ @handle ─────│──click──→  │ memberships│
│          │←── ← Back ───│              │            │ [tag] ────│──click──→ Community
│ search   │               │ All Members  │            │          │
│ ?handle= │               │ @member ─────│──click──→  │          │
└──────────┘               │              │            └──────────┘
                           │ Sibling nav  │
                           │ [Community] ─│──click──→ Another community page
                           └──────────────┘
```

**Bidirectional cross-linking:**
- Community page → member card: `/?handle=username`
- Member card → community page: `/?community=slug` (community tags on card become links)
- Community page → sibling community: `/?community=other-slug`
- Homepage → community page: `/?community=slug`
- Community page → homepage: back link

## Testing Plan

### Export tests (extend existing tests/test_export_public_site.py)
- Slug generation: all 14 community names produce valid URL-safe slugs
- Slug persistence: re-export preserves slugs from slug_registry.json
- Slug stability: renaming a community in DB does not change its slug
- Featured members: top 5 by weight, correct sort order
- Tweet selection: respects n=5 limit, diversity constraint, type detection
- All members: includes all classified minus featured, has username + display_name + bio
- Browseable count: `featured_members.length + all_members.length` is consistent
- Data.json schema: enriched communities validate against expected structure

### Frontend tests (Vitest)
- CommunityPage renders with mock community data
- Spotlight cards show correct member count and tweets
- Tweet type badges render correctly (thread/reply/tweet)
- "View on X" links construct correct URLs
- Back button navigates to homepage
- Share button copies correct `/?community=slug` URL
- Sibling nav shows other communities
- Member handle clicks navigate to `/?handle=X`
- Query state precedence: `?community=X&handle=Y` renders community page, not account card
- Unknown slug: shows "community not found" message

### Integration (Playwright)
- Homepage tag click → community page loads with correct data
- Community page → member card → community tag → back to community page (full loop)
- Direct URL `/?community=builders` loads correctly
- Unknown slug shows graceful fallback
- Both params present: community wins over handle

## Future Extensions

- **Label-driven tweet selection** (Phase 2): As golden dataset grows, `select_community_tweets` prioritizes labeled/tagged tweets
- **Opt-out mechanism**: Allow accounts to request removal from community pages
- **Community evolution timeline**: Show how member composition changes over time
- **Cross-community bridges**: Highlight members who belong to multiple communities
- **JIT community portraits**: LLM-generated narrative synthesizing member activity (when card generation infra is ready)
