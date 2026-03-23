# Handover: 2026-03-23 (Session 8 — Signal Fusion & Ontology Rebuild)

## Session Summary

Rebuilt the entire community detection pipeline from scratch. Integrated 17.5M likes into NMF (24K resolved like-author edges at 0.4x weight). Re-clustered at k=16 (up from k=14), producing 15 named communities with aliases, descriptions, and tarot iconography. Built 7 new signal layers (signed replies, co-followed matrix, content vectors, mention graph, quote graph, time-decay, simulacrum-weighted bits). Fixed propagation to use the correct 182K-node archive follow graph (was running on stale 95K spectral snapshot). Validated ontology with three-signal convergence: 15/15 communities confirmed by content vectors (CT3). Classified all 182K accounts into four bands. Validated seed eligibility (26/317 demoted). Wrote comprehensive 70-item ideas inventory.

**32 commits** since session 7 handover (`88f6590..HEAD`). NOT PUSHED.

## Commits This Session

```
b2b9f45 feat(propagation): weight seed boundary conditions by concentration
45ba44a docs: session 8 comprehensive ideas inventory (70+ items)
3c48da3 feat(signals): quote graph from Supabase quote_tweets
45358a7 feat(signals): mention graph from Supabase user_mentions
0d94046 docs(about): own the perspective — this is one map, not THE map
97b75e8 feat(seeds): validate seed eligibility — not all archive = TPOT
ab858bb feat(bands): frontier ranking by information value for API enrichment
b975d0d feat(bands): four-band classification (exemplar/specialist/bridge/frontier/unknown)
bd19a79 feat(community-page): show iconography on community detail pages
3b3698e docs(about): update About page for session 8 pipeline
e28ec1e fix(propagation): use archive follow graph instead of stale spectral snapshot
5e27608 feat(cards): wire community iconography into card generation
57acba9 feat(cards): version history — cycle through all generated versions of a card
880554f fix(public-site): guard against null username in accountMap
c394fa1 feat(gallery): fullscreen carousel with arrow navigation
023c0f7 docs: community map + tarot iconography system v2
2f0f5a5 feat(tier-c): holdout recall verification script
d4bbb39 feat(public-site): fullscreen card lightbox + auto-export pipeline
7d48104 feat(bits): P1 simulacrum-weighted bits rollup
06759c7 feat(signals): R1-R2 signed reply heuristics
1d34af0 feat(nmf): P6a time-decay for retweets with configurable halflife
40ad33f feat(signals): CF1 co-followed similarity matrix
97d354c feat(content): CT1 topic modeling on 17.5M liked tweets
3911ac9 docs(spec): promote feed data to opt-in consented tier
c757722 docs(spec): add signal framework — taxonomy, coverage, fusion policy
e0f116c feat(ontology): community aliases + orphaned bits re-mapping
bd234ff feat(ontology): seed k=16 likes ontology, 15 named communities
a128384 docs(roadmap): prior improvement spec + Tier A plan, k=16 selected
7bb34a6 feat(nmf): factor-aligned NMF comparison script
ce31a4b fix(nmf): use fixed-precision floats in run_id hash
f1371c7 feat(nmf): add resolved like-author edges to NMF feature matrix
553a13b feat(bits): automate bits rollup with verification
```

## Database State (archive_tweets.db)

### Core Data
| Table | Rows | Description |
|-------|------|-------------|
| `tweets` | 5,553,430 | All archive tweets |
| `likes` | 17,501,243 | All archive likes |
| `retweets` | 774,266 | All archive retweets |
| `profiles` | 328 | Archive account profiles |
| `curation_split` | 5,553,228 | Deterministic train/dev/test splits |

### Community Detection (k=16 NMF)
| Table | Rows | Description |
|-------|------|-------------|
| `community` | 15 | Named communities with descriptions, colors, short_names |
| `community_account` | 732 | NMF memberships (317 exemplar accounts, soft weights) |
| `community_membership` | 3,714 | Legacy membership records |
| `community_alias` | 75 | Memetic names and taglines per community |
| `community_run` | 4 | NMF run history |

### Signal Layers (NEW this session)
| Table | Rows | Description |
|-------|------|-------------|
| `content_topic` | 25 | CT1 topic model from 17.5M liked tweets |
| `account_content_profile` | 4,071 | 257 accounts x 25 topic weights |
| `cofollowed_similarity` | 16,701 | CF1 co-followed Jaccard pairs |
| `signed_reply` | 17,362 | R1-R2 author-liked + mutual-follow reply valence |
| `mention_graph` | 16,477 | Mention pairs from Supabase (100K of 10.6M) |
| `quote_graph` | 1,984 | Quote pairs from Supabase (100K of 1.4M) |

### Classification & Ranking
| Table | Rows | Description |
|-------|------|-------------|
| `account_band` | 181,831 | Four-band classification of all graph accounts |
| `frontier_ranking` | 8,705 | Frontier accounts ranked by information value |
| `seed_eligibility` | 317 | 291 eligible, 26 demoted (entropy-based) |

### Graph Backbone
| Table | Rows | Description |
|-------|------|-------------|
| `account_followers` | 1,647,325 | Inbound follow edges |
| `account_following` | 392,492 | Outbound follow edges |
| `account_engagement_agg` | 408,446 | Engagement edges (RT + like + reply) |
| `resolved_accounts` | 1,051 | Handle-to-ID resolution |

### Labeling (from session 7, unchanged)
| Table | Rows | Description |
|-------|------|-------------|
| `tweet_label_set` | 446 | 20 accounts labeled |
| `tweet_label_prob` | 1,784 | Posterior community probabilities |
| `tweet_tags` | 1,740 | Tweet-level tags |
| `account_community_bits` | 152 | Bits rollup per account |
| `account_community_gold_label_set` | 167 | Gold labels |
| `tpot_directory_holdout` | 389 | Holdout set for recall testing |

## What's Wired vs What's Not

### Wired (end-to-end working)
- NMF community detection with likes, RTs, follows (k=16, 15 communities)
- Community names, descriptions, colors, short_names, aliases, iconography
- About page with signal framework and "one map, not THE map" framing
- Public site with cards, gallery, fullscreen lightbox, carousel
- Card generation with community iconography in prompts
- Tweet labeling with bits rollup (20 accounts, 446 tweets)
- Holdout recall verification
- Four-band classification of 182K accounts
- Content-graph correlation report (CT3, 15/15 validated)
- Seed eligibility validation with entropy-based concentration

### Not Wired (in DB but not exposed)
- **Export uses old binary logic** — `export_public_site.py` shows 331 accounts; should use `account_band` table (20,552 non-unknown accounts). THIS IS THE SHIPPING BLOCKER.
- Mention graph (16,477 pairs) — not in NMF feature matrix
- Quote graph (1,984 pairs) — not in NMF feature matrix
- Co-followed similarity — computed, not in NMF
- Content vectors — used for validation only, not as NMF features
- Frontier ranking — computed, no API enrichment loop yet
- Seed eligibility concentration — not yet used as propagation weight (designed, commit `b2b9f45`)

## Propagation State

- **Temperature:** T=1.0 (down from T=2.0 which flattened distributions)
- **Graph:** 182K nodes from archive follow graph (fixed from stale 95K spectral snapshot)
- **Edges:** follow + RT + like + reply engagement-weighted
- **Discovered accounts:** ~20,552 (exemplar + specialist + bridge + frontier bands)
- **Propagated in `community_account`:** 0 (only 732 NMF-sourced rows currently)
- **Seed eligibility gate:** 291/317 seeds eligible (26 demoted by entropy concentration)

## Four-Band Distribution

| Band | Count | Description |
|------|-------|-------------|
| exemplar | 317 | Archive accounts with NMF membership |
| specialist | 11,530 | Strong single-community signal |
| bridge | 1,171 | Significant membership in 2+ communities |
| frontier | 7,534 | Some signal but below threshold — highest-ROI enrichment targets |
| unknown | 161,279 | Insufficient signal |
| **Total** | **181,831** | |

## Export Blocker

The public site currently shows **331 accounts** (old export logic). The DB contains **20,552 classified accounts** across the four non-unknown bands. The fix is item #29 in the ideas inventory: update `export_public_site.py` to read from `account_band` instead of the old binary classified/propagated distinction. Estimated ~60 LOC change.

## Seed Eligibility

`scripts/validate_seeds.py` checks each archive account's NMF distribution entropy. Accounts with weight spread too evenly across communities (low concentration) are demoted:
- **291 eligible** — concentrated enough to be meaningful seeds
- **26 demoted** — too diffuse (e.g., pan-TPOT bridge accounts like @vgr)
- Concentration scores stored in `seed_eligibility.concentration` column
- Designed but not yet wired: propagation should weight by concentration (commit `b2b9f45`)

## Next Priorities (in order)

1. **Fix export to use four-band classification** — this unblocks the public site from 331 to 20K+ accounts
2. **Wire seed eligibility into propagation** — concentration-weighted boundary conditions (~5 LOC)
3. **Re-propagate with fixed seeds** — run propagation, measure holdout recall
4. **Re-export + redeploy public site** — `auto_export.py` + Vercel deploy
5. **API enrichment: fetch following lists for top 50 frontier accounts** (~$2.50) — adds ~25K outbound edges, multiplicative effect on graph quality
6. **Re-propagate with enriched graph** — measure holdout recall improvement
7. **Fetch remaining mention/quote data from Supabase** — currently 100K of 10.6M mentions, 100K of 1.4M quotes
8. **Send CA team message** — request bookmarks (dead), lists parsing, feed JSONL access
9. **Within-community sub-clustering** — run NMF on each community's liked texts to detect splits
10. **Active learning loop** — propagate, rank frontier, fetch API, label, validate, re-propagate

## What's Running / Blocked

### Ready to run immediately
- Export fix (#29) — code change only, no external dependencies
- Seed eligibility wiring — 5 LOC in propagation script
- Re-propagation — all data in place
- CT3 correlation script — `scripts/verify_content_graph_correlation.py` (shipped this session)

### Blocked on external
- **Bookmarks** — Twitter removed from archive export. Dead end.
- **X Lists member data** — CA team needs to parse `lists-created.js` from archives
- **Feed co-occurrence** — need JSONL access from CA team
- **Full mention/quote data** — Supabase pagination (10.6M mentions, 1.4M quotes)

### Blocked on decision
- **Community birth (AI Mystics)** — 7 signals from 3 accounts. User said: keep vibes-based, don't formalize until more data.
- **k=16 vs k=14** — k=16 selected and deployed. If sub-clustering reveals merges, revisit.

## API Budget

- **Spent:** $1.45 (session 7 twitterapi.io)
- **Remaining:** $18.55 of $20.00
- **Highest-ROI spend:** Following lists for top 50 frontier accounts (~$2.50)
- **Next:** Bios for top 200 shadow accounts (~$2.00)

## Key Files Created This Session

### Scripts
| File | Purpose |
|------|---------|
| `scripts/build_content_vectors.py` | CT1 topic modeling on liked tweets |
| `scripts/build_cofollowed_matrix.py` | CF1 co-followed Jaccard similarity |
| `scripts/build_signed_replies.py` | R1-R2 signed reply heuristics |
| `scripts/build_mention_graph.py` | Mention graph from Supabase |
| `scripts/build_quote_graph.py` | Quote graph from Supabase |
| `scripts/classify_bands.py` | Four-band classification |
| `scripts/rank_frontier.py` | Frontier ranking by information value |
| `scripts/validate_seeds.py` | Seed eligibility validation |
| `scripts/verify_content_graph_correlation.py` | CT3 content-graph correlation report |
| `scripts/verify_holdout_recall.py` | Holdout recall measurement |
| `scripts/verify_likes_nmf.py` | Factor-aligned NMF comparison |
| `scripts/rollup_bits.py` | Automated bits rollup with verification |

### Docs
| File | Purpose |
|------|---------|
| `docs/SESSION8_IDEAS_INVENTORY.md` | 70+ item comprehensive inventory |
| `docs/community_map_k16.txt` | 15-community map with descriptions |
| `docs/TPOT_TAROT_ICONOGRAPHY_v2.md` | Tarot-inspired community iconography |
| `docs/HANDOVER_SESSION8.md` | This document |

### Config
| File | Purpose |
|------|---------|
| `config/community_iconography.json` | Mascot, sigil, palette, motif per community |

## Key Architectural Insights

1. **"17.5M likes" was misleading** — actual signal is ~24K resolved like-author edges. Always interrogate headline numbers.
2. **Propagation was running on the WRONG GRAPH** — stale 95K-node spectral snapshot vs 182K-node archive follow graph. Found and fixed.
3. **Not all archive accounts are TPOT** — uploading data does not equal membership. Seed eligibility filtering demoted 26/317 (8%).
4. **Bridge accounts are real, not failures** — @vgr at 7% across everything IS pan-TPOT. Preserve full distributions.
5. **Three-signal convergence validates ontology** — graph + content + co-followed. 15/15 communities confirmed.
6. **The map is always from a perspective** — "Find MY Ingroup" not "THE objective map."
7. **Temperature flattens distributions** — T=2.0 made everything look the same. T=1.0 doubled discovered accounts (9.5K to 20K).
8. **Following lists are the highest-ROI API spend** — adds outbound edges that transform dead-end leaves into connected nodes.
9. **Content vectors are orthogonal to graph** — liked-text topics provide independent validation.
10. **The export script is the shipping bottleneck** — everything is in the DB but the public site still shows old data.
