# JIT Collectible Card Generation — Design Spec

**Date:** 2026-03-19
**Status:** Approved
**Depends on:** Find My Ingroup static site (deployed at amiingroup.vercel.app)

## Purpose

Replace the bar-chart community cards with AI-generated tarot-style collectible artwork. Each card is generated just-in-time when a user looks up a handle, using the account's community data, bio, and tweets as prompt input. Cards are cached for 24 hours. The curator funds generation with a $5/day budget cap; power users can bring their own OpenRouter key for unlimited generation.

## Architecture

```
Browser                          Vercel Serverless              OpenRouter
+----------+                    +--------------+              +----------+
| User     | POST /api/card     | /api/card.js |  Gemini      | Image    |
| searches | ------------------>| - budget cap | ------------>| Gen API  |
| handle   |                    | - prompt     |              |          |
|          | <------------------| - cache 24h  | <------------|  base64  |
| Card     |  { imageUrl, ... } |              |              |  PNG     |
| renders  |                    +--------------+              +----------+
+----------+
     | (fallback if budget exhausted or user has own key)
     |
     v
  localStorage BYOK --> direct to OpenRouter (no serverless)
```

Two paths to image generation:
1. **Default:** browser -> Vercel serverless function -> OpenRouter (curator's key, $5/day cap)
2. **BYOK:** browser -> OpenRouter directly (user's own key, no cap)

## Serverless Function

**Endpoint:** `POST /api/generate-card`

**Request body:**
```json
{
  "handle": "bhi5hmaraj",
  "bio": "Figuring out the near term trajectory of AGI",
  "communities": [
    { "name": "EA, AI Safety & Forecasting", "weight": 0.081, "color": "#ff5500" },
    { "name": "highbies", "weight": 0.070, "color": "#9c27b0" }
  ],
  "tweets": ["sample tweet 1", "sample tweet 2", "sample tweet 3"]
}
```

The `tweets` field is optional — only classified accounts (298) have tweet data. Propagated accounts send communities + bio only.

**Response:**
```json
{
  "imageUrl": "data:image/png;base64,iVBORw0KGgo...",
  "cached": false,
  "model": "google/gemini-2.5-flash-image-preview"
}
```

**Error responses:**
- `429` — `{ "error": "budget_exhausted", "resets_at": "2026-03-20T00:00:00Z" }`
- `500` — `{ "error": "generation_failed" }`

### Budget Tracking

Uses Vercel KV (free tier: 30K requests/month, 256MB storage):
- Key `budget:YYYY-MM-DD` — float, cumulative spend today in USD
- Key `cache:{handle}` — JSON string with `{ imageUrl, generatedAt }`, 24h TTL

**Flow:**
1. Check `cache:{handle}` — if exists and < 24h old, return cached result
2. Check `budget:{today}` — if >= 5.00, return 429
3. Call OpenRouter `/api/v1/chat/completions` with Gemini model + image modality
4. Estimate cost (~$0.02 per image), increment `budget:{today}`
5. Store result in `cache:{handle}` with 24h TTL
6. Return image

**Budget cap:** $5.00/day, configurable via `CARD_DAILY_BUDGET` env var.

### OpenRouter Integration

**Model:** `google/gemini-2.5-flash-image-preview` (cheapest image-capable model)

**Request to OpenRouter:**
```json
{
  "model": "google/gemini-2.5-flash-image-preview",
  "messages": [{ "role": "user", "content": "<prompt>" }],
  "modalities": ["image", "text"],
  "image_config": {
    "aspect_ratio": "2:3",
    "image_size": "1K"
  }
}
```

**Response parsing:** Extract base64 image from `choices[0].message.images[0].image_url.url`.

## Prompt Template

```
Create a mystical tarot-style collectible card for a Twitter personality.

CARD SUBJECT: @{handle}
{if bio} IDENTITY: {bio} {/if}
{if tweets} VOICE (sample tweets):
- "{tweet1}"
- "{tweet2}"
- "{tweet3}"
{/if}

COMMUNITY ALIGNMENT:
{for each membership, sorted by weight desc}
- {community_name}: {weight_pct}% (color accent: {hex})
{/for}

CARD STYLE REQUIREMENTS:
- Dark background with deep navy (#0a0e27) to purple (#1a1a2e) gradient
- Ornate golden border frame, tarot card proportions (2:3 aspect ratio)
- Central symbolic imagery reflecting their intellectual identity and community alignment
- The dominant community ({top_community_name}) determines the visual motif and color accent
- Mystical, esoteric aesthetic — this person carries the energy of {top_community_name}
- Do NOT render any text on the card — the image should be purely visual and symbolic
- Rich, detailed, collectible quality — something worth screenshotting and sharing
- Style reference: dark fantasy tarot art, metallic gold accents, deep jewel-tone colors
```

**Key design decisions:**
- "No text" instruction — Gemini's text rendering is unreliable. Text (handle, communities, percentages) is overlaid by the frontend DOM/canvas.
- Dominant community drives the visual motif — gives each card a distinct character.
- Same prompt template for all accounts — unified collectible series aesthetic.

## Frontend Integration

### Card Rendering (layered)

The card is a DOM element with layered content:

1. **AI-generated image** (bottom) — fills the card as background, 2:3 aspect ratio
2. **Gradient overlay** — dark gradient at bottom 40% for text readability
3. **Text overlay** — @handle, display name, community memberships styled in the tarot aesthetic
4. **Tarot frame border** — CSS border using the tarot project's golden ornate styling

### Visual Style (from tarot project)

**Color palette:**
- Background gradient: `#0a0e27` → `#1a1a2e` → `#16213e`
- Gold accents: `#d4af37`
- Purple glow: `#9333ea`
- Text: `#e8e8e8` primary, `rgba(232,232,232,0.8)` secondary

**Effects:**
- Tilt-on-hover: mouse position drives `rotateX/rotateY` (from `CardDetailPreview.tsx`)
- Shimmer loading state: 2s infinite gradient sweep (`rgba(255,255,255,0.05)` → `0.2`)
- Glow pulse on card border: `box-shadow: 0 0 20px rgba(147,51,234,0.5)`

### Card States

| State | Visual | Trigger |
|-------|--------|---------|
| **Searching** | Current bar-chart card renders immediately | Handle found in search.json |
| **Generating** | Shimmer overlay on card, "Generating your card..." text | POST to /api/generate-card sent |
| **Generated** | AI image fades in as background, text overlays appear | Image response received |
| **Cached** | Same as generated but instant (no shimmer) | Cache hit |
| **Budget exhausted** | Bar-chart card stays (no AI image), note: "AI cards back tomorrow" | 429 response |
| **Error** | Bar-chart card stays, subtle error note | 500 response |
| **BYOK** | Same as generating/generated but uses user's key | localStorage key present |

**Important:** The current bar-chart card renders immediately on search. The AI image generation happens in parallel — when the image arrives, it replaces the bar-chart background. If generation fails, the bar-chart card remains functional. The AI image is an enhancement, not a requirement.

### PNG Download (updated)

When the AI image is available:
1. Draw AI-generated image onto canvas as background
2. Draw gradient overlay at bottom
3. Draw text: @handle, community names + percentages, site URL footer
4. Apply tarot-style golden border
5. `canvas.toDataURL('image/png')` → download as `ingroup-{handle}.png`

When AI image is NOT available (budget exhausted / error):
- Falls back to current bar-chart PNG generation

### Settings UI

Subtle gear icon in the site header (top-right). Opens a minimal modal:

```
┌─────────────────────────────────────────┐
│  Settings                           [X] │
│                                         │
│  OpenRouter API Key                     │
│  ┌─────────────────────────────────────┐│
│  │ sk-or-v1-••••••••••••              ││
│  └─────────────────────────────────────┘│
│  Use your own key for unlimited card    │
│  generation. Get one at openrouter.ai   │
│                                         │
│  [Save]                     [Clear key] │
│                                         │
│  Status: Using your key ✓              │
└─────────────────────────────────────────┘
```

- Key stored in `localStorage` (never sent to our server)
- When key is set, requests go direct to OpenRouter from browser (CORS-allowed)
- When key is cleared, falls back to serverless function with curator's key
- Badge in header: "Using your key" or nothing (default)

## Sample Tweets for Prompt

For classified accounts (298), the export script should include a `sample_tweets` field with 3 representative tweets selected by engagement (likes + retweets). This enriches the prompt with the account's actual voice.

**Export script change:** Query `archive_tweets.db` for top 3 tweets by `favorite_count + retweet_count` for each classified account. Add to `data.json` accounts:

```json
{
  "username": "alice",
  "tier": "classified",
  "sample_tweets": [
    "The egregore doesn't care about your intentions, only your attention",
    "Every framework is a territory claim dressed up as a map",
    "The real post-irony was the sincerity we performed along the way"
  ],
  "memberships": [...]
}
```

For propagated accounts: no tweets available, prompt uses communities + bio only.

## Environment Variables (Vercel)

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Curator's OpenRouter key for serverless function |
| `CARD_DAILY_BUDGET` | Daily budget cap in USD (default: 5.00) |
| `KV_REST_API_URL` | Vercel KV connection (auto-set when KV is linked) |
| `KV_REST_API_TOKEN` | Vercel KV auth (auto-set) |

## File Structure (new/modified)

```
public-site/
  api/
    generate-card.js          <- Vercel serverless function
  src/
    App.jsx                   <- modified: add settings icon, AI card state
    CommunityCard.jsx         <- modified: layered rendering with AI image
    CardDownload.jsx          <- modified: composite AI image + text overlay
    GenerateCard.jsx          <- NEW: handles generation request + states
    Settings.jsx              <- NEW: BYOK modal
    styles.css                <- modified: tarot styling, shimmer, tilt
```

## What's NOT in v1

- **Video generation** (Veo 3.1) — v2
- **Profile pic as image input** — v2 (user upload)
- **3D flip animation / Three.js** — v2
- **Card sharing via URL with OG preview** — v2
- **Multiple card styles/themes** — v2

## Success Criteria

- Searching a handle generates a unique tarot-style card within 5 seconds
- Cards are visually distinct per account (different community = different motif)
- Cached cards load instantly on repeat visits
- Budget exhaustion degrades gracefully to bar-chart cards
- BYOK users get unlimited generation with their own key
- Downloaded PNG includes AI image with text overlay
- Total serverless function cold start < 2 seconds
