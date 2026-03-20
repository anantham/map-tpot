# JIT Collectible Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace bar-chart community cards with AI-generated tarot-style collectible artwork via OpenRouter Gemini, with $5/day budget cap, 24h caching, and BYOK support.

**Architecture:** Vercel serverless function proxies OpenRouter calls with budget tracking via Vercel KV. Frontend renders AI image as card background with text overlay. BYOK users call OpenRouter directly from browser. Graceful fallback to bar-chart cards when budget exhausted.

**Tech Stack:** Vercel Serverless (Node.js 20.x), Vercel KV, OpenRouter API (Gemini Flash image), React 19

**Spec:** `docs/superpowers/specs/2026-03-19-jit-collectible-cards-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `public-site/api/generate-card.js` | Vercel serverless function — budget check, cache, prompt assembly, OpenRouter call |
| `public-site/src/GenerateCard.jsx` | Hook/component managing generation state (loading, generated, error, exhausted) |
| `public-site/src/Settings.jsx` | BYOK modal — API key input, localStorage, status badge |
| `public-site/src/cardPrompt.js` | Prompt template builder — pure function, no side effects |

### Modified Files

| File | Changes |
|------|---------|
| `public-site/vercel.json` | Add `/api/` exclusion to rewrite rule |
| `public-site/src/App.jsx` | Add settings icon, wire GenerateCard, pass sample_tweets |
| `public-site/src/CommunityCard.jsx` | Add AI image background layer, shimmer loading state |
| `public-site/src/CardDownload.jsx` | Composite AI image + text overlay in canvas |
| `public-site/src/styles.css` | Tarot styling, shimmer, tilt-on-hover, settings modal |
| `scripts/export_public_site.py` | Add sample_tweets to classified accounts in data.json |
| `tests/test_export_public_site.py` | Test sample_tweets extraction |

---

## Task 1: Add sample_tweets to export script

**Files:**
- Modify: `scripts/export_public_site.py`
- Modify: `tests/test_export_public_site.py`

- [ ] **Step 1: Write failing test for sample tweets extraction**

```python
# Add to tests/test_export_public_site.py

class TestSampleTweets:
    def _create_db_with_tweets(self, db_path):
        """Create test DB with community tables + tweets table."""
        _create_test_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                username TEXT NOT NULL, full_text TEXT NOT NULL,
                favorite_count INTEGER DEFAULT 0, retweet_count INTEGER DEFAULT 0
            );
            INSERT INTO tweets VALUES ('t1', 'acct1', 'alice', 'Top tweet by alice', 100, 20);
            INSERT INTO tweets VALUES ('t2', 'acct1', 'alice', 'Second best', 50, 10);
            INSERT INTO tweets VALUES ('t3', 'acct1', 'alice', 'Third tweet', 30, 5);
            INSERT INTO tweets VALUES ('t4', 'acct1', 'alice', 'Fourth tweet low engagement', 1, 0);
            INSERT INTO tweets VALUES ('t5', 'acct2', 'bob', 'Bob only tweet', 10, 2);
        """)
        conn.commit()
        conn.close()

    def test_returns_top_3_tweets_by_engagement(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        self._create_db_with_tweets(db_path)

        from scripts.export_public_site import get_sample_tweets
        tweets = get_sample_tweets(db_path, "acct1", limit=3)

        assert len(tweets) == 3
        assert tweets[0] == "Top tweet by alice"
        assert tweets[1] == "Second best"
        assert tweets[2] == "Third tweet"

    def test_returns_empty_for_unknown_account(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        self._create_db_with_tweets(db_path)

        from scripts.export_public_site import get_sample_tweets
        tweets = get_sample_tweets(db_path, "nonexistent")
        assert tweets == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py::TestSampleTweets -v`
Expected: FAIL — `cannot import name 'get_sample_tweets'`

- [ ] **Step 3: Implement get_sample_tweets**

Add to `scripts/export_public_site.py`:

```python
def get_sample_tweets(db_path: Path, account_id: str, limit: int = 3) -> list[str]:
    """Return top tweets by engagement for an account. Returns [] if no tweets found."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """SELECT full_text FROM tweets
           WHERE account_id = ?
           ORDER BY (favorite_count + retweet_count) DESC
           LIMIT ?""",
        (account_id, limit),
    ).fetchall()
    conn.close()
    return [row[0][:280] for row in rows]
```

- [ ] **Step 4: Wire into _enrich_classified_accounts**

In `_enrich_classified_accounts`, after building the enriched account dict, add:

```python
sample_tweets = get_sample_tweets(db_path, acct["id"], limit=3)
enriched.append({
    **acct,
    "username": str(username),
    "display_name": str(meta.get("display_name") or username),
    "bio": str(meta.get("bio") or ""),
    "followers": int(followers) if followers and not np.isnan(followers) else 0,
    "sample_tweets": sample_tweets,
})
```

Note: `_enrich_classified_accounts` needs to accept `db_path` as a parameter now. Update its signature and the call site in `run_export`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run real export and verify sample_tweets in output**

```bash
cd tpot-analyzer && .venv/bin/python3 -m scripts.export_public_site
python3 -c "import json; d=json.load(open('public-site/public/data.json')); a=d['accounts'][0]; print(a.get('sample_tweets', [])[:1])"
```

- [ ] **Step 7: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py
git commit -m "feat(export): add sample_tweets for classified accounts"
```

---

## Task 2: Vercel config + serverless function

**Files:**
- Modify: `public-site/vercel.json`
- Create: `public-site/api/generate-card.js`

- [ ] **Step 1: Update vercel.json rewrite rule**

```json
{
  "rewrites": [
    { "source": "/((?!api/|data\\.json|search\\.json|assets/).*)", "destination": "/index.html" }
  ],
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

- [ ] **Step 2: Create the serverless function**

```js
// public-site/api/generate-card.js
import { kv } from '@vercel/kv';

const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions';
const MODEL = 'google/gemini-2.5-flash-image-preview';
const DAILY_BUDGET = parseFloat(process.env.CARD_DAILY_BUDGET || '5.00');
const COST_PER_MILLION_TOKENS = 30; // Gemini Flash output pricing

function todayKey() {
  return `budget:${new Date().toISOString().slice(0, 10)}`;
}

function cacheKey(handle) {
  return `cache:${handle.toLowerCase()}`;
}

function buildPrompt({ handle, bio, communities, tweets }) {
  let prompt = `Create a mystical tarot-style collectible card for a Twitter personality.\n\n`;
  prompt += `CARD SUBJECT: @${handle}\n`;
  if (bio) prompt += `IDENTITY: ${bio}\n`;
  if (tweets && tweets.length > 0) {
    prompt += `VOICE (sample tweets):\n`;
    tweets.forEach(t => { prompt += `- "${t}"\n`; });
  }
  prompt += `\nCOMMUNITY ALIGNMENT:\n`;
  communities.forEach(c => {
    prompt += `- ${c.name}: ${Math.round(c.weight * 100)}% (color accent: ${c.color})\n`;
  });
  const topCommunity = communities[0]?.name || 'unknown';
  prompt += `\nCARD STYLE REQUIREMENTS:\n`;
  prompt += `- Dark background with deep navy (#0a0e27) to purple (#1a1a2e) gradient\n`;
  prompt += `- Ornate golden border frame, tarot card proportions (2:3 aspect ratio)\n`;
  prompt += `- Central symbolic imagery reflecting their intellectual identity\n`;
  prompt += `- The dominant community (${topCommunity}) determines the visual motif and color accent\n`;
  prompt += `- Mystical, esoteric aesthetic — this person carries the energy of ${topCommunity}\n`;
  prompt += `- Do NOT render any text on the card — purely visual and symbolic\n`;
  prompt += `- Rich, detailed, collectible quality — dark fantasy tarot art, metallic gold accents\n`;
  return prompt;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'method_not_allowed' });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'server_not_configured' });
  }

  const { handle, bio, communities, tweets } = req.body;
  if (!handle || !communities || !Array.isArray(communities)) {
    return res.status(400).json({ error: 'handle and communities are required' });
  }

  // 1. Check cache
  const ck = cacheKey(handle);
  try {
    const cached = await kv.get(ck);
    if (cached && cached !== 'pending') {
      return res.status(200).json({ ...cached, cached: true });
    }
  } catch (e) {
    // KV unavailable — proceed without cache
  }

  // 2. Check budget
  const bk = todayKey();
  try {
    const spent = parseFloat(await kv.get(bk) || '0');
    if (spent >= DAILY_BUDGET) {
      return res.status(429).json({
        error: 'budget_exhausted',
        resets_at: new Date(new Date().setUTCHours(24, 0, 0, 0)).toISOString(),
      });
    }
  } catch (e) {
    // KV unavailable — proceed without budget check
  }

  // 3. Optimistic lock
  try {
    const lockSet = await kv.set(ck, 'pending', { nx: true, px: 30000 });
    if (!lockSet) {
      return res.status(202).json({ error: 'generation_in_progress', retry_after: 5 });
    }
  } catch (e) {
    // Proceed without lock
  }

  // 4. Generate image
  const prompt = buildPrompt({ handle, bio, communities, tweets });

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);

    const response = await fetch(OPENROUTER_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://amiingroup.vercel.app',
      },
      body: JSON.stringify({
        model: MODEL,
        messages: [{ role: 'user', content: prompt }],
        modalities: ['image', 'text'],
        image_config: { aspect_ratio: '2:3', image_size: '1K' },
      }),
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!response.ok) {
      await kv.del(ck).catch(() => {});
      return res.status(502).json({ error: 'upstream_error' });
    }

    const result = await response.json();
    const images = result?.choices?.[0]?.message?.images;
    if (!images || images.length === 0) {
      await kv.del(ck).catch(() => {});
      return res.status(500).json({ error: 'generation_failed' });
    }

    const imageUrl = images[0].image_url.url;

    // 5. Track cost from actual usage
    const completionTokens = result?.usage?.completion_tokens || 1300;
    const cost = (completionTokens / 1_000_000) * COST_PER_MILLION_TOKENS;

    const payload = { imageUrl, model: MODEL };

    // 6. Cache result + increment budget
    try {
      await kv.set(ck, payload, { ex: 86400 }); // 24h TTL
      await kv.incrbyfloat(bk, cost);
      await kv.expire(bk, 86400); // expire budget key after 24h
    } catch (e) {
      // KV write failed — image still delivered
    }

    return res.status(200).json({ ...payload, cached: false });

  } catch (e) {
    await kv.del(ck).catch(() => {});
    if (e.name === 'AbortError') {
      return res.status(500).json({ error: 'generation_timeout' });
    }
    return res.status(500).json({ error: 'generation_failed' });
  }
}
```

- [ ] **Step 3: Install @vercel/kv dependency**

```bash
cd tpot-analyzer/public-site && npm install @vercel/kv
```

- [ ] **Step 4: Commit**

```bash
git add public-site/vercel.json public-site/api/generate-card.js public-site/package.json public-site/package-lock.json
git commit -m "feat(public-site): serverless function for JIT card generation"
```

---

## Task 3: Prompt builder + GenerateCard component

**Files:**
- Create: `public-site/src/cardPrompt.js`
- Create: `public-site/src/GenerateCard.jsx`

- [ ] **Step 1: Create cardPrompt.js**

```js
// public-site/src/cardPrompt.js

export function buildCardRequest({ handle, bio, memberships, sampleTweets, communityMap }) {
  const communities = (memberships || [])
    .map(m => {
      const c = communityMap?.get(m.community_id)
      return c ? { name: c.name, color: c.color, weight: m.weight } : null
    })
    .filter(Boolean)
    .sort((a, b) => b.weight - a.weight)

  return {
    handle,
    bio: bio || undefined,
    communities,
    tweets: sampleTweets?.length > 0 ? sampleTweets : undefined,
  }
}
```

- [ ] **Step 2: Create GenerateCard.jsx**

```jsx
// public-site/src/GenerateCard.jsx
import { useState, useEffect, useRef } from 'react'
import { buildCardRequest } from './cardPrompt'

const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
const MODEL = 'google/gemini-2.5-flash-image-preview'

function getStoredKey() {
  try { return localStorage.getItem('openrouter_key') || null } catch { return null }
}

async function generateViaBYOK(apiKey, request) {
  let prompt = `Create a mystical tarot-style collectible card for a Twitter personality.\n\n`
  prompt += `CARD SUBJECT: @${request.handle}\n`
  if (request.bio) prompt += `IDENTITY: ${request.bio}\n`
  if (request.tweets?.length) {
    prompt += `VOICE (sample tweets):\n`
    request.tweets.forEach(t => { prompt += `- "${t}"\n` })
  }
  prompt += `\nCOMMUNITY ALIGNMENT:\n`
  request.communities.forEach(c => {
    prompt += `- ${c.name}: ${Math.round(c.weight * 100)}% (color accent: ${c.color})\n`
  })
  const top = request.communities[0]?.name || 'unknown'
  prompt += `\nCARD STYLE: Dark navy-to-purple gradient, ornate golden border, tarot proportions (2:3). `
  prompt += `Central symbolic imagery. Dominant community: ${top}. `
  prompt += `Mystical/esoteric. NO text on card. Dark fantasy tarot art, gold accents.\n`

  const res = await fetch(OPENROUTER_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': window.location.origin,
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [{ role: 'user', content: prompt }],
      modalities: ['image', 'text'],
      image_config: { aspect_ratio: '2:3', image_size: '1K' },
    }),
  })
  if (!res.ok) throw new Error(`OpenRouter error: ${res.status}`)
  const data = await res.json()
  const images = data?.choices?.[0]?.message?.images
  if (!images?.length) throw new Error('No image in response')
  return images[0].image_url.url
}

export function useCardGeneration({ handle, bio, memberships, sampleTweets, communityMap, tier }) {
  const [imageUrl, setImageUrl] = useState(null)
  const [status, setStatus] = useState('idle') // idle | generating | generated | error | exhausted
  const inflightRef = useRef(null)

  useEffect(() => {
    if (!handle || tier === 'not_found' || !memberships?.length) return
    // Debounce: only one in-flight per handle
    if (inflightRef.current === handle) return
    inflightRef.current = handle

    setStatus('generating')
    setImageUrl(null)

    const request = buildCardRequest({ handle, bio, memberships, sampleTweets, communityMap })
    const byokKey = getStoredKey()

    const generate = async () => {
      try {
        if (byokKey) {
          const url = await generateViaBYOK(byokKey, request)
          setImageUrl(url)
          setStatus('generated')
        } else {
          const res = await fetch('/api/generate-card', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
          })
          if (res.status === 429) {
            setStatus('exhausted')
            return
          }
          if (res.status === 202) {
            // Generation in progress by another request, retry after delay
            await new Promise(r => setTimeout(r, 5000))
            const retry = await fetch('/api/generate-card', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(request),
            })
            if (!retry.ok) { setStatus('error'); return }
            const data = await retry.json()
            setImageUrl(data.imageUrl)
            setStatus('generated')
            return
          }
          if (!res.ok) { setStatus('error'); return }
          const data = await res.json()
          setImageUrl(data.imageUrl)
          setStatus('generated')
        }
      } catch {
        setStatus('error')
      } finally {
        inflightRef.current = null
      }
    }

    generate()
  }, [handle, tier])

  return { imageUrl, status }
}
```

- [ ] **Step 3: Commit**

```bash
git add public-site/src/cardPrompt.js public-site/src/GenerateCard.jsx
git commit -m "feat(public-site): card prompt builder and generation hook"
```

---

## Task 4: Settings (BYOK) component

**Files:**
- Create: `public-site/src/Settings.jsx`

- [ ] **Step 1: Create Settings.jsx**

```jsx
// public-site/src/Settings.jsx
import { useState } from 'react'

export default function Settings({ isOpen, onClose }) {
  const [key, setKey] = useState(() => {
    try { return localStorage.getItem('openrouter_key') || '' } catch { return '' }
  })
  const [saved, setSaved] = useState(!!key)

  const handleSave = () => {
    const trimmed = key.trim()
    if (trimmed) {
      localStorage.setItem('openrouter_key', trimmed)
      setSaved(true)
    }
  }

  const handleClear = () => {
    localStorage.removeItem('openrouter_key')
    setKey('')
    setSaved(false)
  }

  if (!isOpen) return null

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h3>Settings</h3>
          <button className="settings-close" onClick={onClose}>&times;</button>
        </div>
        <div className="settings-body">
          <label className="settings-label">OpenRouter API Key</label>
          <input
            type="password"
            className="settings-input"
            value={key}
            onChange={e => { setKey(e.target.value); setSaved(false) }}
            placeholder="sk-or-v1-..."
          />
          <p className="settings-hint">
            Use your own key for unlimited card generation.{' '}
            <a href="https://openrouter.ai/keys" target="_blank" rel="noopener">Get one at openrouter.ai</a>
          </p>
          <div className="settings-actions">
            <button className="settings-save" onClick={handleSave} disabled={!key.trim()}>Save</button>
            {saved && <button className="settings-clear" onClick={handleClear}>Clear key</button>}
          </div>
          {saved && <p className="settings-status">Using your key</p>}
        </div>
      </div>
    </div>
  )
}

export function SettingsIcon({ onClick, hasKey }) {
  return (
    <button className="settings-icon" onClick={onClick} title="Settings">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
      </svg>
      {hasKey && <span className="settings-badge" />}
    </button>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add public-site/src/Settings.jsx
git commit -m "feat(public-site): BYOK settings modal with localStorage"
```

---

## Task 5: Wire everything into App + CommunityCard

**Files:**
- Modify: `public-site/src/App.jsx`
- Modify: `public-site/src/CommunityCard.jsx`
- Modify: `public-site/src/CardDownload.jsx`

- [ ] **Step 1: Update App.jsx**

Add settings state, pass sample_tweets to result, wire GenerateCard hook:

```jsx
// Key changes to App.jsx:
import Settings, { SettingsIcon } from './Settings'
import { useCardGeneration } from './GenerateCard'

// Add state:
const [settingsOpen, setSettingsOpen] = useState(false)
const hasKey = (() => { try { return !!localStorage.getItem('openrouter_key') } catch { return false } })()

// In handleResult for classified, add:
sampleTweets: account.sample_tweets || [],

// After result is set, use the hook:
// (Move hook call to a child component or restructure — hooks can't be conditional)
// Solution: create a ResultArea component that always mounts when result exists

// Add to header area:
<SettingsIcon onClick={() => setSettingsOpen(true)} hasKey={hasKey} />
<Settings isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
```

Create a `ResultArea` wrapper component inside App.jsx that calls `useCardGeneration` and passes the imageUrl down to CommunityCard.

- [ ] **Step 2: Update CommunityCard.jsx — add AI image layer**

Add an `aiImageUrl` prop. When present, render the AI image as background with gradient overlay. When absent (generating or failed), show the bar-chart card as before.

```jsx
// Add to CommunityCard props: aiImageUrl, generationStatus
// When aiImageUrl exists:
//   - Render image as background (object-fit: cover, 2:3 aspect ratio)
//   - Dark gradient overlay at bottom 40%
//   - Text overlay (handle, communities) on top
//   - Shimmer loading animation when generationStatus === 'generating'
// When aiImageUrl is null:
//   - Render current bar-chart card (existing behavior)
```

- [ ] **Step 3: Update CardDownload.jsx — composite AI image**

When `aiImageUrl` is available:
1. Load the base64 image into an `Image()` element
2. Draw it as canvas background
3. Draw gradient overlay
4. Draw text overlay (handle, communities, percentages)
5. Draw tarot-style golden border

When `aiImageUrl` is not available: use existing bar-chart rendering.

- [ ] **Step 4: Verify in dev server**

```bash
cd tpot-analyzer/public-site && npm run dev
```

Test: search a handle. Should see bar-chart card render immediately, then (if serverless function is deployed) AI image loads over it. Without deployment, BYOK path can be tested by entering an OpenRouter key in settings.

- [ ] **Step 5: Commit**

```bash
git add public-site/src/
git commit -m "feat(public-site): wire AI card generation into UI with fallback"
```

---

## Task 6: Tarot styling + shimmer + tilt

**Files:**
- Modify: `public-site/src/styles.css`
- Modify: `public-site/src/CommunityCard.jsx` (tilt effect)

- [ ] **Step 1: Add tarot-inspired styles**

```css
/* Tarot card styling */
.card-ai-container {
  position: relative;
  aspect-ratio: 2/3;
  max-width: 400px;
  margin: 0 auto 1rem;
  border-radius: 12px;
  overflow: hidden;
  border: 2px solid rgba(212, 175, 55, 0.3);
  box-shadow: 0 0 20px rgba(147, 51, 234, 0.2);
}

.card-ai-image {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
}

.card-ai-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(10,14,39,0.95) 0%, rgba(10,14,39,0.6) 40%, transparent 70%);
}

.card-ai-text {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 1.5rem;
}

/* Shimmer loading */
@keyframes shimmer {
  0% { background-position: -600px 0; }
  100% { background-position: 600px 0; }
}

.card-shimmer {
  background: linear-gradient(90deg,
    rgba(255,255,255,0.05) 25%,
    rgba(255,255,255,0.15) 50%,
    rgba(255,255,255,0.05) 75%);
  background-size: 600px 100%;
  animation: shimmer 2s infinite;
}

/* Golden glow pulse */
@keyframes glow-pulse {
  0%, 100% { box-shadow: 0 0 20px rgba(212,175,55,0.2); }
  50% { box-shadow: 0 0 40px rgba(212,175,55,0.4); }
}

.card-ai-container.generating {
  animation: glow-pulse 2s infinite;
}
```

- [ ] **Step 2: Add tilt-on-hover to CommunityCard**

Add mouse-tracking tilt from the tarot project pattern:

```jsx
const [tilt, setTilt] = useState({ x: 0, y: 0 })
const cardRef = useRef(null)

const handleMouseMove = (e) => {
  const rect = cardRef.current.getBoundingClientRect()
  const x = ((e.clientY - rect.top) / rect.height - 0.5) * -10
  const y = ((e.clientX - rect.left) / rect.width - 0.5) * 10
  setTilt({ x, y })
}
const handleMouseLeave = () => setTilt({ x: 0, y: 0 })

// Apply to card container:
// style={{ transform: `perspective(800px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)` }}
```

- [ ] **Step 3: Commit**

```bash
git add public-site/src/
git commit -m "feat(public-site): tarot styling with shimmer, glow, and tilt effects"
```

---

## Task 7: Deploy + E2E verification

**Files:**
- No new files

- [ ] **Step 1: Set Vercel environment variables**

```bash
cd tpot-analyzer/public-site
npx vercel link --yes
npx vercel env add OPENROUTER_API_KEY production
npx vercel env add CARD_DAILY_BUDGET production
# Enter: your OpenRouter key and "5.00"
```

- [ ] **Step 2: Link Vercel KV store**

```bash
npx vercel stores create kv ingroup-cache
# Or link existing KV store if one exists
```

- [ ] **Step 3: Build and deploy**

```bash
cd tpot-analyzer/public-site
npm run build
npx vercel --prod
npx vercel alias set <deployment-url> amiingroup.vercel.app
```

- [ ] **Step 4: Test all paths**

1. Search a classified handle → bar-chart card renders → AI image loads over it → download PNG with AI art
2. Search a propagated handle → grayscale bar-chart → AI image loads → download
3. Search nonexistent handle → contribute prompt (no generation triggered)
4. Open settings → enter BYOK key → search again → verify direct OpenRouter call
5. After $5 spent: verify 429 response and graceful fallback to bar-chart card

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(public-site): deploy JIT collectible cards to production"
```
