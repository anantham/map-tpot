# Account Labeling Runbook

Operational guide for labeling new accounts. Codifies the rules, cost tradeoffs, and decision points discovered through labeling 12 accounts.

## Decision Tree: New Account

```
Is account in archive (archive_tweets.db)?
├── YES → FREE. Use DB data. Label 20 top-engagement tweets. CI will be ~0.65+
└── NO → API required (~$0.04-0.10 per account)
         │
         ├── How many following?
         │   ├── <500 → Full pagination (2-3 pages, $0.06-0.09) ← DO THIS
         │   ├── 500-1000 → Full pagination (3-5 pages, $0.09-0.15) ← DO THIS
         │   └── >1000 → Cap at 5 pages ($0.15). Full only if high-priority.
         │
         ├── How many followers?
         │   ├── <500 → 1-2 pages ($0.03). Worth it.
         │   ├── 500-5000 → 1 page ($0.015). Diminishing returns.
         │   └── >5000 → SKIP. Too expensive. Not enough classified accounts.
         │
         └── Tweets: Always 3 pages ($0.009). 5 if account is high-priority.
```

## Cost Reference (twitterapi.io)

Plan: $20 = 2,000,000 credits

| Endpoint | Credits/call | $/call | When to use |
|----------|-------------|--------|-------------|
| user/info | 18 | $0.0002 | ALWAYS |
| user/last_tweets | 285/page | $0.003 | 3 pages standard, 5 deep |
| user/followings | 3000/page | $0.030 | FULL for <1000. Cap at 5 pages. |
| user/followers | 1500/page | $0.015 | 1 page for <5K followers. Skip for large. |
| tweet/replies | 240 | $0.002 | Only for tweets with 100+ engagement |
| tweet/advanced_search | 300 | $0.003 | Great for targeted topic queries |
| user/mentions | 270 | $0.003 | Often empty for small accounts |
| tweet/retweeters | 495 | $0.005 | Only for viral tweets |

**Free alternatives (no API cost):**
- Syndication API: images, quotes, full text (unlimited, no auth)
- Archive DB: tweets, likes, follows, replies (for opt-in accounts)

## Pipeline Steps

### Archive Account (FREE)

```bash
# 1. Check archive
python -c "SELECT COUNT(*) FROM tweets WHERE username='X'"

# 2. Run labeling context
python scripts/labeling_context.py <username>

# 3. Label via AI (OpenRouter — separate cost, ~$0.01/tweet)
# Use enriched pipeline with full DB context

# 4. Compute rollup
# Automated in the labeling script

# 5. Check CI
python -c "from src.communities.confidence import compute_confidence; ..."
```

### Non-Archive Account (API)

```
1. user/info → profile, stats                           18 credits
2. user/last_tweets × 3 → ~60 tweets                   855 credits
3. user/followings × N → full following list         3000×N credits
4. Insert tweets + profile into DB
5. Syndication API → images, quotes for top tweets       FREE
6. AI labeling → proposed labels                    ~$0.01/tweet
7. Compute rollup + CI
```

## Labeling Rules

### Tweet Selection
- Pick by ENGAGEMENT (likes + RTs), not recency
- Deduplicate (same text appears multiple times in API results)
- Skip pure replies (@-prefixed)
- Skip retweets (RT @-prefixed)
- 20 tweets is the standard batch. 10 for quick assessment.

### AI Labeling
- Model: google/gemini-2.5-flash via OpenRouter
- MUST list exact community names in prompt (AI ignores them otherwise)
- Provide author bio in prompt (critical for context)
- Clamp distribution values to [0.0, 1.0]
- Fix +N → N in JSON (common LLM output error)
- Valid communities: AI-Safety, LLM-Whisperers, Qualia-Research, Contemplative-Practitioners,
  Emergence-Self-Transformation, highbies, Quiet-Creatives, Builders,
  Collective-Intelligence, Relational-Explorers, NYC-Institution-Builders,
  Ethereum-Builders, Feline-Poetics, Queer-TPOT

### Known AI Limitations
- Gives empty bits when community names are buried in long prompts
- Over-attributes L2 (persuasion) — most posting is L1 or L3
- Never proposes new-community-signals
- Misses observational humor as community signal
- Can't see images without multimodal (use syndication + base64)
- Confuses practical AI use with AI research (insurance/Claude tweet)

### Human Review Triggers
- AI confidence < 0.5 on a tweet
- Tweet has images but syndication failed
- Tweet is a quote-tweet (need to understand the original)
- Bits are spread evenly (ambiguous classification)
- New-community-signal potential

## CI Thresholds

| CI Range | Level | What it means |
|----------|-------|--------------|
| 0.80+ | human_validated | Stable, reviewed, trustworthy |
| 0.55-0.80 | bits_stable | Good evidence, concentrated profile |
| 0.35-0.55 | bits_partial | Some evidence, may still shift |
| 0.15-0.35 | follow_propagated | Thin evidence, needs more labeling |
| 0-0.15 | nmf_only | NMF prior only, unvalidated |

### Improving CI
- More tweets labeled: biggest impact below 20 tweets
- Full following list: critical for network_context factor
- Archive data (likes): biggest single factor but requires opt-in
- Profile concentration: can't control — some people are genuinely spread

## After Labeling

### Mandatory (model spec: Community Description Sync)
1. Update model spec community profiles if new exemplars found
2. Sync community.description in DB
3. Recompute account_community_bits rollup
4. Check for new-community-signal accumulation (3+ = birth candidate)

### Before Deploy
1. Re-run export: `python -m scripts.export_public_site`
2. Verify repligate/dschorno/etc show correct bits profile
3. Deploy: `cd public-site && vercel --prod`

## Budget Tracking

Usage is logged in `api_endpoint_costs` table in archive_tweets.db.
Check twitterapi.io dashboard for exact credit consumption.
Budget: $20/2M credits. At standard rate ($0.08/account) = ~250 accounts.

---
*Created 2026-03-22 after labeling 12 accounts*
