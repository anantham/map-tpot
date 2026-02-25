# Data Inventory

*Last updated: 2026-02-25. All numbers from local DBs.*

A honest map of every data source available, what signals it provides,
and what's missing. Use this to make strategic decisions about what to
build and what to buy.

---

## Data Sources

### Source A — Community Archive (archive_tweets.db)

Raw Twitter export JSONs for seed accounts, downloaded from the Community Archive
Supabase instance. 277 accounts attempted; 269 successfully parsed (8 still re-fetching
due to corrupted cache files).

| Table | Rows | Notes |
|-------|------|-------|
| `tweets` | 4,000,539 | Self-authored only (RTs stripped) |
| `likes` | 13,606,378 | 98% have full text — nearly lossless |
| `profiles` | 269 | 265 with non-empty bio |
| `account_following` | 321,277 | Who each seed account follows |
| `account_followers` | 1,092,789 | Who follows each seed account |
| `retweets` | 615,437 | RT metadata: who they amplify (no RT text) |

**Signal richness: HIGH**
- Tweet content: full self-authored text going back years
- Likes: 13.6M passive preference signals, nearly all have text
- Following graph: full outbound follow list per seed account
- Retweet pattern: 615K records of who they chose to amplify
- Bio text: 265 out of 269 have it

**Hard limits:**
- Only 269 accounts have full data
- Following targets are mostly non-seed accounts with no further data
- Likes have tweet text but NOT the liked tweet's author (can't attribute)
- Tweets date range uneven — some accounts have years of history, others months

---

### Source B — Shadow Graph (cache.db)

Produced by the Selenium-based shadow scraper: crawled following/follower lists
of seed accounts, scraped account metadata. Edges use `shadow:username` IDs.

| Table | Rows | Notes |
|-------|------|-------|
| `shadow_account` | 95,086 | 72,840 with bio; sourced via `hybrid_selenium` |
| `shadow_edge` | 318,971 | `outbound` = A follows B; `inbound` = A is followed by B |
| `shadow_discovery` | 308,655 | Which seed account led to discovering each shadow account |
| `account` (seeds) | 316 | Original seed list |
| `archive_following` | 161,590 | Following from Community Archive Supabase uploads |
| `archive_followers` | 330,423 | Followers from Community Archive Supabase uploads |

**Signal richness: MEDIUM (graph + bio, no content)**
- 95K accounts in the extended graph — this is the "TPOT-adjacent universe"
- 72K of them have bio text — self-labeling ("EA researcher", "rationalist", etc.)
- Graph topology: who seed accounts follow/are followed by, 2-3 hops out
- Shadow edges sourced from actual Twitter scraping (Selenium), not archive exports

**The painful gap:**
- Only 42 shadow accounts have any tweet content in cache.db
- The other 95,044 shadow accounts are bio + graph position only
- No tweet text means no simulacrum classification, no LLM analysis
- Can do: graph-based community detection, bio embedding, degree/centrality
- Cannot do: tweet-level content analysis, temporal trajectory

---

### Source C — twitterapi.io (available, not yet used for enrichment)

REST API for live Twitter data. Key: `new1_*` in `.env`. Budget: ~1,988,000 credits.

**Pricing (confirmed from dashboard):**
| Endpoint | Credits | Per |
|----------|---------|-----|
| `/twitter/tweets` (batched) | 15 | per returned tweet |
| `/twitter/user/info` | 18 | per profile |
| `/twitter/tweet/replies/v2` | 75 | per call |
| `/twitter/tweet/advanced_search` | 75 | per call |

**What this could unlock:**
- Tweet content for shadow accounts (15 credits/tweet × ~3000 tweets/account)
- Thread context for reply tweets we're about to label (~15 credits each, on demand)
- Current follower/following counts for any account
- Tweets for TPOT-adjacent accounts NOT in community archive

**Cost reality check:**
| Task | Volume | Cost |
|------|--------|------|
| Thread context per labeled tweet (on demand) | 1 tweet | 15 credits |
| Tweets for 20 key shadow accounts | 20 × 3K tweets | 900K credits |
| Tweets for 100 key shadow accounts | 100 × 3K tweets | 4.5M credits — over budget |
| Re-fetch current profiles for 300 accounts | 300 × 18 | 5,400 credits |

---

### Source D — OpenRouter LLM (available)

`OPENROUTER_API_KEY` in `.env`. Used for `/api/golden/interpret` endpoint.
Model: `moonshotai/kimi-k2`.

- Classifies tweets into simulacrum distribution + lucidity + interpretation
- ~$0.00063 per tweet at current model pricing
- Full golden classification of 4M tweets ≈ $2,520 — not feasible
- Full classification of 269 accounts × 1000 sampled tweets ≈ $170 — feasible
- On-demand labeling assist: essentially free

---

## Signal Map

What signals we can extract from data we already have:

| Signal | Source | Coverage | Quality |
|--------|--------|----------|---------|
| Tweet content | Source A | 269 accounts, 4M tweets | High |
| Passive preferences (liked text) | Source A | 269 accounts, 13.6M likes | High (no author) |
| Following graph | Source A + B | 269 full + 95K partial | High |
| Retweet targets | Source A | 269 accounts, 615K records | High |
| Reply targets | Source A | 269 accounts, 3M replies | High |
| Bio text (seed) | Source A | 265/269 accounts | High |
| Bio text (shadow) | Source B | 72,840 accounts | Medium (1 data point each) |
| Follower graph | Source A + B | 269 full + 95K partial | Medium |
| Tweet content (shadow) | — | **42 accounts** | **MISSING** |
| Thread context | Source C (on-demand) | Per labeled tweet | Medium |

---

## The Core Problem

**Two tiers of accounts with a cliff between them:**

```
Tier 1 — SEED (269 accounts)          Tier 2 — SHADOW (95K accounts)
─────────────────────────────────      ─────────────────────────────
✓ Full tweet history                   ✗ No tweets (42 exceptions)
✓ Full like history                    ✗ No likes
✓ Following graph                      ✓ Graph position only
✓ Retweet targets                      ✗ No retweet data
✓ Bio text                             ✓ Bio text (72K/95K)
✓ Temporal trajectory                  ✗ No temporal data
```

For the goal of **community membership classification**, this means:
- Content-based classifiers (simulacrum, community from tweets) only work on Tier 1
- Shadow accounts can only be placed via graph position + bio text
- Extending the classifier to new accounts requires either their tweet content
  (expensive) or a good graph-based approximation (cheap, lower precision)

---

## Strategic Options

### Option 1: Tier 1 only — Build on what's solid
Use only the 269 seed accounts for everything. Community detection, classification,
labeling, fingerprinting — all on the full-signal accounts.

- **Pro:** Every signal available; high-quality ground truth
- **Pro:** 269 accounts × community detection is enough to see your expected clusters
- **Con:** Shadow accounts are invisible; graph doesn't extend beyond the seed set
- **Best for:** Getting community structure right before worrying about coverage

### Option 2: Bipartite graph — Use shadow topology, seed content
Keep Tier 1 for content-based signals. Use shadow accounts as structural anchors
in the following graph (they exist as nodes but aren't classified by content).
Community detection runs on the full bipartite graph (seeds + shadow topology).

- **Pro:** Richer graph structure; community anchors (e.g. @LessWrong, @ESYudkowsky)
  emerge from topology without needing their tweets
- **Pro:** Zero additional cost
- **Con:** Shadow account community labels inferred only from position, not content
- **Best for:** Phase 4-5 community detection experiment

### Option 3: Bio-augmented shadow — Embed bios for shadow accounts
Run bio text embeddings on the 72K shadow accounts with bios. Use these as a
low-fidelity content signal. Community keywords ("EA", "rationalist", "alignment")
often appear verbatim in bios — free self-labeling.

- **Pro:** Cheap, fast, zero API calls
- **Pro:** Bios are often more honest about community than tweets (explicit self-identification)
- **Con:** 1 data point per account; poetic/ironic bios give noise
- **Best for:** Bootstrapping community labels for shadow accounts; validating graph-based clusters

### Option 4: Targeted tweet fetch — Buy tweets for key shadow accounts
Identify the 20-50 highest-degree shadow nodes (the community anchor accounts
that many seed accounts follow). Fetch their recent tweets via twitterapi.io.

- **Pro:** Turns the most important shadow accounts into Tier 1
- **Pro:** Anchors get full signal; the rest follow via graph proximity
- **Con:** 20 accounts × 3K tweets × 15 credits = 900K credits ($9)
- **Con:** You'd be picking which accounts to buy — introduces selection bias
- **Best for:** Phase 6+ once you know which anchors are structurally important

### Option 5: Extend community archive — Find missing TPOT accounts
Some accounts you care about may not be in the Community Archive at all.
For those, twitterapi.io can fetch their recent tweets independently of the archive.

- **Pro:** Expands Tier 1 for accounts you specifically want
- **Con:** Manual curation required; no systematic coverage
- **Best for:** Filling specific gaps once you've done initial labeling

---

## Recommendation for Phase 4

**Start with Option 2** (bipartite graph + seed content):
- Community detection on seed accounts using following + retweet + reply
- Shadow accounts as structural reference nodes (topology only)
- Bio text for both seed and shadow to validate/label discovered clusters
- Aditya manually labels 30-50 accounts to known communities → ground truth

**Defer Options 3-5** until the seed-only clustering shows you:
- Which communities are clearly separable (don't need more data)
- Which are confounded (might need shadow account content to resolve)
- Which shadow accounts are the most important structural bridges

The 269 seed accounts are probably enough to see all your expected communities.
The question is whether the signal weights need the shadow graph to sharpen the
boundaries — and that's an empirical question we can answer cheaply before spending API credits.

---

## Open Questions

1. **Are 269 seed accounts enough?** You expect ~8-12 communities. With 269 accounts
   that's 20-30 accounts per community on average — statistically meaningful.

2. **Which community will be hardest to separate?** Rationalist / EA / alignment are
   heavily overlapping. These will need the most labeled examples to distinguish.

3. **What do we do about the likes' missing authors?** We have 13.6M liked tweet texts
   but can't attribute them to accounts. We could text-classify them into communities
   anyway — a liked tweet's community is a signal regardless of who wrote it.

4. **Is the shadow graph's 2-hop reach actually capturing TPOT?** The 95K shadow
   accounts were discovered via seed following lists. Are there TPOT-adjacent accounts
   that none of the seeds follow but that matter? Probably yes for newer accounts.

5. **Temporal coverage:** When do the seed accounts' archives start? If some only go
   back 1-2 years, we're missing their earlier community trajectory.
