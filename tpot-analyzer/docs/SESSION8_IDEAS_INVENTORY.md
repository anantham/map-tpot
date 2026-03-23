# Session 8 Ideas Inventory

> Comprehensive list of everything discussed, built, designed, deferred, or blocked.
> Last updated: 2026-03-23 (end of session). This is a living document — update as items ship.

---

## DONE (shipped this session — 37 commits)

| # | Item | Commit | Notes |
|---|------|--------|-------|
| 1 | Likes into NMF (24K resolved pairs) | `f1371c7` | `build_likes_matrix()`, 0.4x weight |
| 2 | Author-liked-reply valence (R1) | `06759c7` | 194K replies signed |
| 3 | Mutual-follow reply valence (R2) | `06759c7` | 244K replies signed |
| 4 | Simulacrum-weighted bits (L3=2x) | `7d48104` | `--simulacrum-weighted` flag |
| 5 | Time-decay for RT/replies (P6a) | `1d34af0` | `--decay-halflife` flag |
| 6 | Co-followed matrix (CF1) | `40ad33f` | 16,701 pairs, 12/15 cohesive |
| 7 | Content vectors (CT1, 17.5M likes) | `97d354c` | 25 topics, 4,071 profiles |
| 8 | Content-vs-graph correlation (CT3) | `4ab2d5d` | Reusable script, 12-15/15 validated |
| 9 | k=16 ontology, 15 named communities | `bd234ff` | Seeded from likes-enriched NMF |
| 10 | Community aliases (75 total) | `e0f116c` | Memetic names + taglines per community |
| 11 | Tarot iconography → card prompt | `5e27608` | `config/community_iconography.json` |
| 12 | Signal framework in spec | `c757722` | Taxonomy, coverage, fusion, governance tiers |
| 13 | Holdout table (389 accounts) | In DB | Strangest Loop + Orange TPOT directories |
| 14 | 107 handles resolved (Supabase) | In DB | Via `mentioned_users` table (free) |
| 15 | Fix propagation graph (182K→190K nodes) | `e28ec1e` | Was using stale 95K spectral snapshot |
| 16 | Engagement-weighted edges | `e28ec1e` | follow + RT + like + reply weights |
| 17 | Bits rollup automation | `553a13b` | `rollup_bits.py` + verification |
| 18 | Factor-aligned NMF comparison | `7bb34a6` | `verify_likes_nmf.py` |
| 19 | About page (signals, recall, bands) | `3b3698e` | Updated for session 8 pipeline |
| 20 | Community map text file | `023c0f7` | `docs/community_map_k16.txt` |
| 21 | Four-band classification | `b975d0d` | 317 exemplar, 9.2K specialist, 325 bridge, 17.5K frontier |
| 22 | Frontier ranking script | `ab858bb` | 8,705 ranked by info_value, holdout bonus works |
| 23 | Mention graph from Supabase | `45358a7` | 74,817 pairs from 100K of 10.6M rows |
| 24 | Quote graph from Supabase | `3c48da3` | 1,984 pairs from 100K of 1.4M rows |
| 25 | Seed eligibility validation | `97b75e8` | 26/317 demoted, entropy-based concentration |
| 26 | Community page iconography | `bd19a79` | Mascot, sigil, palette, motif on detail pages |
| 27 | About page "One Map Not The Map" | `0d94046` | Owns the perspective, explains iconography |
| 28 | Ideas inventory doc | `45ba44a` | This document |
| 29 | Handover doc | `15d25e1` | `docs/HANDOVER_SESSION8.md` |
| 30 | Wire seed eligibility into propagation | `b2b9f45` | `concentration` weights boundary conditions |
| 31 | Four-band export system | `8e22a0b` | `extract_band_accounts()` replaces binary export |
| 32 | Fetch following lists pipeline | `05c9dbd` | `/user/followings` endpoint, bio enrichment |
| 33 | **50 accounts enriched via API** | In DB | 27,583 new edges added ($5.00), graph 392K→436K |
| 34 | **Three re-propagation cycles** | In DB | Final: 190K nodes, 436K edges, 17s solve |
| 35 | **Final export: 16,226 accounts** | In files | 317 exemplar + 7,158 specialist + 216 bridge + 8,535 frontier |

---

## READY TO DEPLOY

The public site is ready with:
- **16,226 searchable accounts** (was 331 at start of session)
- **15 named communities** with descriptions, aliases, iconography
- **Four-band classification** (exemplar / specialist / bridge / frontier)
- **Community detail pages** with mascot, sigil, palette, motif
- **About page** with honest framing ("one map, not THE map")
- **Card generation** with community iconography wired into prompts

Deploy: `cd public-site && vercel --prod`

---

## DESIGNED BUT NOT BUILT

| # | Item | Effort | Context |
|---|------|--------|---------|
| 36 | **Within-community sub-clustering** | ~100 LOC | Run NMF on each community's liked texts to detect potential splits. All data exists. |
| 37 | **Lifecycle audit log** | ~40 LOC | Schema designed, tracks merge/split/birth/rename events |
| 38 | **Smart enrichment filter** | ~30 LOC | Score shadow accounts by RT concentration (community-specific) to prioritize API spend |
| 39 | **Active learning loop** | ~150 LOC | Full cycle: propagate → rank frontier → fetch API → label → validate → re-propagate |
| 40 | **Bio keyword → community mapping** | ~50 LOC | "jhanas, vipassana" → Contemplative. Zero ML, just string matching against descriptions. |

---

## API BUDGET STATUS

| Item | Spent | Result |
|------|-------|--------|
| Fetch following for 50 frontier accounts | **$5.00** | 27,583 new edges, 50 bios stored |
| Resolve handles (mentioned_users) | **$0.00** | 107 resolved (free via Supabase) |
| **Remaining budget** | **~$13.55** | |

### Next API spend priorities:
| # | Item | Cost | ROI |
|---|------|------|-----|
| 41 | Fetch following for next 50 frontier | ~$5.00 | ~25K more edges |
| 42 | Fetch bios for top 200 shadow accounts | ~$2.00 | Instant community validation |
| 43 | Resolve remaining 192 Substack handles | ~$2.00 | Complete holdout set |
| 44 | Fetch your 8 X Lists members | ~$0.40 | Free human ontology |

---

## BLOCKED ON EXTERNAL

| # | Item | Blocker | Action |
|---|------|---------|--------|
| 45 | **Lists (member data)** | CA team needs to parse `lists-created.js` | Message drafted |
| 46 | **Feed co-occurrence** | CA team needs JSONL access or junction table | Message drafted |
| 47 | **`personalization.js` for all archives** | CA team needs to add to pipeline (711 interest tags per account from Twitter!) | Message drafted |
| 48 | **Bookmarks** | Twitter removed from archive export entirely | Dead end |
| 49 | **Retweet text for shadow classification** | `retweets` table has no `full_text` column | API fetch needed |

**CA team message covers:** lists + feed JSONL + personalization.js. Message is drafted, not sent.

---

## SUPABASE TABLES — STATUS

| # | Table | Fetched | Total available | Status |
|---|-------|---------|----------------|--------|
| 50 | `user_mentions` | 74,817 pairs | ~10.6M | Partially fetched (need `--limit 5000000` re-run) |
| 51 | `quote_tweets` | 1,984 pairs | ~1.4M | Partially fetched (need re-run) |
| 52 | `user_directory` | Used for handle resolution | ~331 with bios | Already used |
| 53 | `conversations` | Not fetched | Millions | Thread depth heuristic |
| 54 | `tweet_urls` | Not fetched | 1.6M | URL domain → community mapping |
| 55 | `tweet_media` | Not fetched | Millions | Descriptive only |

---

## IDEAS DISCUSSED BUT DEFERRED

| # | Item | Why deferred | When to revisit |
|---|------|-------------|-----------------|
| 56 | Bluesky cross-reference (free API) | Identity resolution hard | After identity pipeline exists |
| 57 | Mastodon follows (ActivityPub) | Same | Same |
| 58 | Cheap LLM reply valence at scale (4.3M) | $10-20, after heuristics validated | After R1-R2 show value |
| 59 | Co-like matrix | Speculative | After ablation |
| 60 | Hashtag co-usage | Diminishing returns | Low priority |
| 61 | Display name / emoji patterns | Weak signal | Research curiosity |
| 62 | Account age | Descriptive | "Community timeline" feature |
| 63 | Profile location | Geographic only | "Who's in my city" feature |
| 64 | Tweet posting cadence | Lifestyle, not community | Research |
| 65 | Betweenness centrality | Expensive on 190K nodes | After more enrichment |
| 66 | Triadic closure | Nice-to-have metric | Community cohesion |
| 67 | Hierarchical communities | Future ontology evolution | After sub-clustering (#36) |
| 68 | `personalization.js` (your archive) | 711 tags found, only yours available | After CA team adds to pipeline |
| 69 | `ad-engagements.js` | Found in archive, niche | Research |

---

## CODEX FEEDBACK (execution contracts)

| # | Item | Priority |
|---|------|----------|
| 70 | Artifact schemas for outputs | Medium |
| 71 | Ontology migration protocol | Medium (hit this with k=14→k=16) |
| 72 | Signal scoreboard table | Medium |
| 73 | Data lineage / provenance | Low |
| 74 | Consent/revocation for feed data | Low until feed is live |
| 75 | Representation framework | Medium |

---

## KEY ARCHITECTURAL INSIGHTS

1. **"17.5M likes" was misleading** — actual signal is ~24K resolved like-author edges
2. **Propagation was on the WRONG GRAPH** — stale 95K snapshot vs 190K archive graph
3. **Not all archive = TPOT** — 26 seeds demoted via entropy-based eligibility
4. **Bridge accounts are real** — @vgr IS pan-TPOT, not a classification failure
5. **Three-signal convergence validates ontology** — graph + content + co-followed
6. **The map is always from a perspective** — "Find MY Ingroup" not "THE map"
7. **Temperature matters** — T=2.0 made everything flat, T=1.0 doubled discoveries
8. **Following lists are highest-ROI API spend** — 50 accounts = 27K edges for $5
9. **Seed eligibility makes propagation 10x faster** — 183s → 17s with cleaner seeds
10. **The export was the shipping bottleneck** — 331 → 16,226 accounts by fixing one function
11. **twitterapi.io endpoint is `/user/followings` not `/user/following`** — cost 30 min to debug
12. **personalization.js has 711 Twitter-assigned interest tags** — strongest untapped signal if CA team parses it

---

## NEXT SESSION PRIORITIES

1. **Deploy** — `cd public-site && vercel --prod` (16,226 accounts ready)
2. **Send CA team message** — lists + feed JSONL + personalization.js
3. **Fetch more following** — next 50 accounts (~$5, ~25K edges, $13.55 remaining)
4. **Complete mention graph** — re-run `build_mention_graph.py --limit 5000000`
5. **Complete quote graph** — re-run `build_quote_graph.py --limit 1000000`
6. **Wire mention/quote into propagation** — add as weighted edges
7. **Within-community sub-clustering** — detect splits
8. **Holdout recall check** — re-run `verify_holdout_recall.py` with enriched graph
