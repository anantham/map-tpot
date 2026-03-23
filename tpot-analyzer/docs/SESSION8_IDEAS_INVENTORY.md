# Session 8 Ideas Inventory

> Comprehensive list of everything discussed, built, designed, deferred, or blocked.
> Last updated: 2026-03-23. This is a living document — update as items ship.

---

## DONE (shipped this session)

| # | Item | Commit | Notes |
|---|------|--------|-------|
| 1 | Likes into NMF (24K resolved pairs) | `f1371c7` | `build_likes_matrix()`, 0.4x weight |
| 2 | Author-liked-reply valence (R1) | `06759c7` | 194K replies signed |
| 3 | Mutual-follow reply valence (R2) | `06759c7` | 244K replies signed |
| 4 | Simulacrum-weighted bits (L3=2x) | `7d48104` | `--simulacrum-weighted` flag |
| 5 | Time-decay for RT/replies (P6a) | `1d34af0` | `--decay-halflife` flag |
| 6 | Co-followed matrix (CF1) | `40ad33f` | 16,701 pairs, 12/15 cohesive |
| 7 | Content vectors (CT1, 17.5M likes) | `97d354c` | 25 topics, 4,071 profiles |
| 8 | Content-vs-graph correlation (CT3) | In-session | 12/15 communities validated |
| 9 | k=16 ontology, 15 named communities | `bd234ff` | Seeded from likes-enriched NMF |
| 10 | Community aliases (75 total) | `e0f116c` | Memetic names + taglines |
| 11 | Tarot iconography → card prompt | `5e27608` | `config/community_iconography.json` |
| 12 | Signal framework in spec | `c757722` | Taxonomy, coverage, fusion, governance |
| 13 | Holdout table (389 accounts) | In DB | Strangest Loop + Orange TPOT directories |
| 14 | 107 handles resolved (Supabase) | In DB | Via `mentioned_users` table (free) |
| 15 | Fix propagation graph (182K nodes) | `e28ec1e` | Was using stale 95K spectral snapshot |
| 16 | Engagement-weighted edges | `e28ec1e` | follow + RT + like + reply weights |
| 17 | Bits rollup automation | `553a13b` | `rollup_bits.py` + verification |
| 18 | Factor-aligned NMF comparison | `7bb34a6` | `verify_likes_nmf.py` |
| 19 | About page (signals, recall, bands) | `3b3698e` | Updated for session 8 pipeline |
| 20 | Community map text file | `023c0f7` | `docs/community_map_k16.txt` |
| 21 | Four-band classification | `b975d0d` | 317 exemplar, 11.5K specialist, 1.2K bridge, 7.5K frontier |
| 22 | Frontier ranking script | `ab858bb` | 8,705 ranked, holdout bonus works |
| 23 | Mention graph from Supabase | `45358a7` | 16,477 pairs from 100K rows (10.6M total) |
| 24 | Quote graph from Supabase | `3c48da3` | 1,984 pairs from 100K rows (1.4M total) |
| 25 | Seed eligibility validation | `97b75e8` | 26/317 demoted, entropy-based concentration |
| 26 | Community page iconography | `bd19a79` | Mascot, sigil, palette, motif on detail pages |
| 27 | About page "One Map Not The Map" | `0d94046` | Owns the perspective, explains iconography |

---

## DESIGNED BUT NOT BUILT (ready to implement)

| # | Item | Effort | Context |
|---|------|--------|---------|
| 28 | **Wire seed eligibility into propagation** | ~5 LOC | `concentration` column weights boundary conditions. The validate_seeds.py script exists, just needs to be read by propagation. |
| 29 | **Fix export to use four-band classification** | ~60 LOC | `export_public_site.py` currently uses old binary logic (331 accounts). Should use `account_band` table (20,552 accounts). THIS BLOCKS THE SITE. |
| 30 | **Active learning loop** | ~150 LOC | propagate → rank frontier → fetch API → label → validate → re-propagate |
| 31 | **Within-community sub-clustering** | ~100 LOC | Run NMF on each community's liked texts to detect potential splits |
| 32 | **Lifecycle audit log** | ~40 LOC | Schema designed, tracks merge/split/birth/rename events |
| 33 | **Smart enrichment filter** | ~30 LOC | Score shadow accounts by RT concentration (community-specific, not just count) to prevent wasting API on @elonmusk |
| 34 | **CT3 as reusable script** | ~50 LOC | Content-graph correlation was inline; should be `verify_content_graph_correlation.py` |
| 35 | **Entropy-based seed gating (Option D)** | ~5 LOC | Continuous: seeds propagate at `concentration = 1 - normalized_entropy` strength. Most principled approach. |

---

## NEEDS API SPEND ($18.55 budget)

| # | Item | Cost | ROI | Notes |
|---|------|------|-----|-------|
| 36 | Fetch following lists for top 50 non-holdout shadows | ~$2.50 | **Highest** — adds ~25K outbound edges | Use `frontier_ranking` table to pick targets |
| 37 | Fetch bios for top 200 shadow accounts | ~$2.00 | High — instant community validation | Bio keyword → community is near-deterministic |
| 38 | Resolve remaining 192 Substack→Twitter handles | ~$2.00 | Medium — completes holdout set | twitterapi.io username search |
| 39 | Fetch your 8 X Lists members | ~$0.40 | High — free human ontology | Archive has list IDs, need member fetch |
| 40 | Fetch X Lists for top seed accounts | ~$1.00 | Medium — more curated ontology | |
| 41 | Embed shadow bios cheaply (Kimi-k2) | ~$0.50 for 800 | Medium — boundary detection | Cluster bios to find community-boundary accounts |

---

## BLOCKED ON EXTERNAL

| # | Item | Blocker | Action |
|---|------|---------|--------|
| 42 | **Bookmarks** | Twitter removed from archive export entirely | Dead end. No fix possible. |
| 43 | **Lists (member data)** | CA team needs to parse `lists-created.js` from archives | Message drafted, add to CA team ask |
| 44 | **Feed co-occurrence** | Need JSONL access or junction table from CA team | Message drafted |
| 45 | **Feed scraper→tweet mapping** | `originator_id` only in JSONL, not Postgres | Same CA team ask |
| 46 | **Retweet text for shadow classification** | `retweets` table has no `full_text` column | Would need API fetch of original tweets |

**CA team message covers:** bookmarks (dead), lists (need parsing), feed JSONL (need access). Message is drafted in session, not yet sent.

---

## SUPABASE TABLES DISCOVERED BUT UNUSED

| # | Table | Rows | Signal | Status |
|---|-------|------|--------|--------|
| 47 | `user_mentions` | 10.6M | Mention graph (active attention) | **Partially fetched** (100K rows → 16,477 pairs in `mention_graph`) |
| 48 | `quote_tweets` | 1.4M | Quote graph (critical engagement) | **Partially fetched** (100K rows → 1,984 pairs in `quote_graph`) |
| 49 | `user_directory` | ~72K | Bios for ALL archive accounts | Used for handle resolution, not yet for bio analysis |
| 50 | `conversations` | Millions | Thread structure (conversation_id) | Not fetched |
| 51 | `tweet_urls` | 1.6M | URL domain → community mapping | Not fetched (slow to paginate) |
| 52 | `tweet_media` | Millions | Media types per tweet | Not fetched (descriptive only) |
| 53 | `enriched_tweets` | Millions | Tweets with conversation_id + quoted_tweet_id | Not fetched |

---

## IDEAS DISCUSSED BUT DEFERRED

| # | Item | Why deferred | When to revisit |
|---|------|-------------|-----------------|
| 54 | Bluesky cross-reference (free API) | Identity resolution is hard | After identity resolution pipeline exists |
| 55 | Mastodon follows (ActivityPub) | Same — cross-platform matching | Same |
| 56 | Cheap LLM reply valence at scale (batch 4.3M) | $10-20, after heuristics validated | After R1-R2 heuristics show value in ablation |
| 57 | Co-like matrix (accounts liking same tweets) | Speculative | After ablation shows liked-content signal helps |
| 58 | Hashtag co-usage clustering | Diminishing returns | Low priority |
| 59 | Display name / emoji patterns | Weak signal | Research curiosity only |
| 60 | Account age (old guard vs newcomers) | Descriptive, not structural | Useful for "community timeline" feature |
| 61 | Profile location clustering | Only for geographic features | "Who's in my city" feature |
| 62 | Tweet posting cadence (3am vs 9-5) | Lifestyle signal, not community | Research curiosity |
| 63 | Betweenness centrality | Expensive on 182K nodes | After graph is enriched with outbound edges |
| 64 | Triadic closure per community | Nice-to-have metric | Community cohesion analysis |
| 65 | Hierarchical communities (regions → sub) | Future ontology evolution | After within-community sub-clustering (#31) |
| 66 | `personalization.js` (Twitter's interest model) | Found in archive, untapped | Could validate community assignments |
| 67 | `ad-engagements.js` (promoted tweet engagement) | Found in archive, niche | Display location = feed signal for ads |

---

## CODEX FEEDBACK (execution contracts)

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 68 | Artifact schemas for Tier B outputs | Medium | Where does CT1 live? Keys? Output format? |
| 69 | Ontology migration protocol | Medium | We hit this with k=14→k=16 orphaned bits. Need formal merge/split → tag remap → snapshot rule. |
| 70 | Signal scoreboard | Medium | One table: signal, role, coverage, privacy, eval metric, status |
| 71 | Data lineage / provenance | Low | Track whether an edge came from archive, stream, API, or inference |
| 72 | Consent/revocation policy | Low | What happens if someone opts out of the stream extension? |
| 73 | Representation framework | Medium | Which signals → priors vs descriptors vs validation vs human-review-only |

---

## KEY ARCHITECTURAL INSIGHTS FROM THIS SESSION

1. **"17.5M likes" was misleading** — actual signal is ~24K resolved like-author edges. Always interrogate headline numbers.

2. **The propagation was running on the WRONG GRAPH** — stale 95K-node spectral snapshot vs 182K-node archive follow graph. Found and fixed.

3. **Not all archive accounts are TPOT** — uploading data ≠ membership. Seed eligibility filtering demoted 26/317 (8%).

4. **Bridge accounts are real, not failures** — @vgr at 7% across everything IS pan-TPOT. The system should preserve full distributions.

5. **Three-signal convergence validates ontology** — graph + content + co-followed topology. 12/15 communities confirmed.

6. **The map is always from a perspective** — "Find MY Ingroup" not "THE objective map." Seeds are opinionated.

7. **Temperature flattens distributions** — T=2.0 made everything look the same. T=1.0 doubled discovered accounts (9.5K → 20K).

8. **Following lists are the highest-ROI API spend** — adds outbound edges that transform dead-end leaves into connected nodes. Multiplicative effect.

9. **Content vectors are orthogonal to graph** — liked-text topics provide independent validation. When graph and content agree, confidence is high.

10. **The export script is the shipping bottleneck** — everything we built is in the DB but the public site still shows old data because `export_public_site.py` needs the four-band update.

---

## NEXT SESSION PRIORITIES (in order)

1. Wire seed eligibility into propagation (#35) + re-propagate
2. Fix export to use four-band classification (#29) — **this unblocks the site**
3. Re-export + redeploy public site
4. API enrichment: fetch following lists for top 50 frontier accounts (#36)
5. Re-propagate with enriched graph → measure holdout recall improvement
6. Send CA team message (#45)
7. Fetch remaining mention/quote data from Supabase (currently 100K of 10.6M/1.4M)
