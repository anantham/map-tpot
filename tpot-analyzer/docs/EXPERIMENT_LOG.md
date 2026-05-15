# Experiment Log

> Hypotheses tested, results observed, lessons learned. This is institutional memory — what we tried, what worked, what didn't, and why. Each entry records the question, the method, the data, and the verdict so future sessions don't re-run failed experiments or miss validated insights.

*Last updated: 2026-04-15 (Session 12)*

---

## EXP-006: Does topic-seed ingestion actually hand off into active learning?

**Date:** 2026-04-15
**Question:** The new `fetch_topic_seeds.py` flow claims to (1) ingest advanced-search topic tweets, (2) stage authors in `frontier_ranking`, and (3) let `scripts.active_learning --round 1` fetch those authors next. Do the current helper contracts actually support that?

**Hypothesis:** The original implementation is broken at two contract boundaries: it logs API calls with the wrong function signature and stores raw `advanced_search` payloads without parsing them into the `enriched_tweets` schema. Even if corrected, the current round-1 selector will still suppress those authors because it excludes any account already present in `enriched_tweets`.

**Method:** Performed static review of `scripts/fetch_topic_seeds.py`, `scripts/fetch_tweets_for_account.py`, and `scripts/active_learning.py`. Added focused regression tests that simulate raw `advanced_search` rows, then verified selection behavior for accounts with only `topic_seed` rows versus mixed `topic_seed` + normal fetch rows.

**Result:** **CONFIRMED.** The initial implementation would fail on `log_api_call(...)` and fed `store_tweets(...)` the wrong data shape. After repair:
- raw search hits are parsed through `parse_tweet(...)`,
- search spend is logged through the real enrichment-log contract,
- staged authors land in `frontier_ranking`,
- accounts with only `topic_seed` rows remain eligible for round 1,
- accounts with any non-`topic_seed` enrichment remain suppressed.

**Lesson:** Topic-seed search hits are contextual preload data, not proof that an account has already gone through the account-level fetch/label loop. Dedup has to respect fetch provenance, not just table presence.

**Next step:** Run `scripts/verify_topic_seed_ingestion.py` against the real `archive_tweets.db` after the next topic-search batch to confirm staged-author counts and round-1 eligibility on production data.

---

## EXP-001: Can higher-k NMF split ideological sub-communities?

**Date:** 2026-03-25
**Question:** EA & Forecasting contains mech-interp people, governance people, agent-foundations people, forecasters, and e/acc sympathizers. Can NMF at k=20 or k=24 separate them?

**Hypothesis:** If sub-communities have distinct follow patterns, higher k should produce factors that align with ideological facets.

**Method:** Ran NMF on the 800K-edge follow+like matrix (4,214 accounts × 268K targets) at k=16, k=20, and k=24. Compared factor compositions.

**Result:** **FAILED.** Higher k fragments existing communities into social sub-clusters (who follows whom within the group), NOT ideological facets. The same accounts appear across multiple factors. At k=24, EA doesn't split into mech-interp vs governance — it splits into "@bayeslord's cluster" vs "@torulane's cluster" vs "@strangestloop's cluster."

**Why:** Everyone in alignment follows @ESYudkowsky, @KatjaGrace, @tobyordoxford. The follow graph is identical across ideological facets. Mech-interp people and governance people attend the same conferences, follow the same accounts. They differ in what they WRITE about, not who they FOLLOW.

**Lesson:** Follow-graph NMF finds social clusters. Content analysis finds ideological facets. Don't conflate the two. See CLAUDE.md anti-pattern #9 (Signal Conflation).

**Next step:** Two-level labeling — LLMs tag sub-community facets (theme:mech-interp, theme:ai-governance) from tweet content. Cluster tags to discover sub-community boundaries.

---

## EXP-002: Do bio embeddings separate communities?

**Date:** 2026-03-25
**Question:** If we embed 15K account bios with sentence-transformers, do the embeddings cluster by community?

**Method:** Embedded 15,182 bios with `all-MiniLM-L6-v2` (384-dim). Computed community centroids from 343 seeds. Measured inter-community cosine similarity and intra-community coherence.

**Result:** **PARTIAL.** Some communities clearly separate by bio content:
- TfT-Coordination (0.51-0.69 similarity to others) — very distinct bios
- LLM-Whisperers (0.60-0.76) — technical bios stand apart
- AI-Safety (0.62-0.80) — quantitative/alignment language
- Highbies (0.51-0.78) — distinct voice

But others are nearly identical:
- Core-TPOT ↔ Internet-Intellectuals: 0.86 cosine — same vocabulary
- Contemplative ↔ Quiet-Creatives: 0.84 — overlapping language
- Core-TPOT ↔ Queer-TPOT: 0.83 — shared TPOT voice

Intra-community coherence: 0.38-0.53 (moderate). Tightest: Collective-Intelligence (0.53), TfT-Coordination (0.50). Loosest: Highbies (0.38), Qualia-Research (0.39).

**Lesson:** Bio embeddings are useful as a SECONDARY signal — especially for cold-start accounts without follow data. Not a replacement for graph structure. Best for: confirming community membership, distinguishing TfT/LLM-Whisperers from everyone else, bio-based search.

**Data stored:** `bio_embeddings` table (account_id, 384-dim BLOB, bio_source, created_at).

---

## EXP-003: What signal separates "famous-adjacent" from "TPOT member"?

**Date:** 2026-03-25
**Question:** @elonmusk scores 0.012 with 30 seed neighbors. @eigenrobot scores 0.058 with 92 seed neighbors. The graph can't tell them apart. What can?

**Tested signals:**

| Signal | Method | Result | Verdict |
|--------|--------|--------|---------|
| **Concentration** (seed_nbrs / inbound) | Computed for all placed accounts | @googlecalendar = 0.50, @eigenrobot = 0.66 | **FAILED** — low-degree noise inflates concentration |
| **Spread** (entropy of seed-neighbor vector) | Measured community entropy | @repligate = 0.952, @elonmusk = 0.927 | **FAILED** — TPOT communities overlap too much, everything is high-spread |
| **Score × neighbors composite** | Swept thresholds | @sama (0.56) = TPOT median | **FAILED** — popular tech people have many real TPOT connections |
| **Broadcast ratio** (following/followers) | From profile cache | @elonmusk = 0.000005, @eigenrobot ≈ 0.15 | **WORKS** but need follower counts (fetched for 9.3K accounts) |
| **Reciprocity** (mutuals / inbound from seeds) | Computed for accounts with outbound data | Famous < 0.06, TPOT > 0.17 | **CLEAN SEPARATION** — 3x gap, no overlap in samples |

**Key finding:** Reciprocity is the cleanest separator. Community membership is bidirectional — you're TPOT not because TPOT follows you, but because you follow TPOT back. Famous accounts are one-way: TPOT follows them, they don't follow TPOT.

**Limitation:** Only 14% of placed accounts have outbound edge data. The `check_follow` API endpoint can spot-check reciprocity for the rest (~10 per-pair checks per account).

**Decision:** Accept famous accounts as "adjacent/faint" rather than filter them out. TPOT IS tech-adjacent. Use celebrity concentration filter (follower-count based) for accounts with > 100K followers. Frontend UX fix (hide faint from community pages by default) is better than data-level filtering.

---

## EXP-004: Does NMF v2 (800K edges, k=16, with likes) validate v1 ontology?

**Date:** 2026-03-24 (Session 10c)
**Question:** Does doubling the graph and adding like signals destroy or confirm the 16-community structure?

**Method:** Re-ran NMF (k=16, follow+RT+like, like_weight=0.4) on 800K-edge graph (was 441K in v1). Formal factor alignment via feature overlap (greedy matching, threshold 0.1).

**Result:** **CONFIRMED.** 10/14 v1 factors survived with >= 17.5% overlap. 6 new births at k=16 that map cleanly to communities we already named by hand. 4 disappearances (Crypto/Web3 dissolved, Tools-for-Thought absorbed).

**Key shifts:**
- Core TPOT narrowed to @visakanv-adjacent nucleus
- Sensemaking split into essayist-flavored + builder-flavored
- Internet Essayists + Tech Philosophers merged at one level, split at another
- Crypto/Web3 dissolved — not a real TPOT community

**Lesson:** The 16-community ontology is real structure, not a sparse-data artifact. More data sharpens boundaries rather than blurring them. The community that disappeared (Crypto) was the weakest signal.

**Data:** v2 run saved as `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95` in `community_run` table. Not yet promoted to primary (v1 still active).

---

## EXP-005: Does tweet labeling agree with NMF graph placement?

**Date:** 2026-03-26
**Question:** If we label tweets for accounts already classified by NMF (graph-based), do the tweet-derived community assignments agree?

**Hypothesis:** If both signals capture the same underlying community structure, they should agree most of the time. Disagreements reveal accounts where social affiliation (follows) diverges from intellectual identity (content).

**Method:** Selected 15 NMF-only seeds (1 per community, weight > 0.3, no prior tweet labels). Ran through the enriched labeling pipeline (3-model LLM ensemble with bio, engagement partners, mention communities, RT source, sub-community facets, content profile). Compared NMF dominant community vs tweet-derived dominant community. 12 of 15 produced enough tags for comparison (3 had no tweets available).

**Result:** **42% exact match, 58% top-3 match.**

| Account | NMF (follows) | Tweets (content) | Verdict |
|---------|--------------|-------------------|---------|
| @NunoSempere | AI-Safety | AI-Safety | MATCH |
| @technoshaman | Collective-Intelligence | Collective-Intelligence | MATCH |
| @realpilleater | Core-TPOT | Core-TPOT | MATCH |
| @v01dpr1mr0s3 | LLM-Whisperers | LLM-Whisperers | MATCH |
| @Lithros | Highbies | Highbies | MATCH |
| @AnniePosting | Queer-TPOT | Highbies | partial (Queer-TPOT in top-3) |
| @taijitu_sees | Quiet-Creatives | Contemplative-Practitioners | partial |
| @rndmcnlly | AI-Creativity | Tech-Intellectuals | DIFFER |
| @sharanvkaur | Internet-Intellectuals | Highbies | DIFFER |
| @archived_videos | Qualia-Research | Highbies | DIFFER |
| @LChoshen | TfT-Coordination | Tech-Intellectuals | DIFFER |
| @petersuber | Tech-Intellectuals | TfT-Coordination | DIFFER |

**Pattern in disagreements:** All 5 "DIFFER" accounts follow one community but write content that fits another. @rndmcnlly follows AI art accounts but tweets about philosophy. @sharanvkaur follows essayists but posts highbie content. @LChoshen and @petersuber are mirror images — each assigned to the other's community by the opposite signal. These are genuine bridges where social scene ≠ intellectual identity.

**The 5 exact matches** are accounts where social and intellectual identity align perfectly — @NunoSempere IS EA through and through, @v01dpr1mr0s3 IS pure LLM Whisperers.

**Lesson:** Neither NMF (follows) nor tweet labeling (content) is "right" alone. They capture different dimensions:
- **Follows** = who you listen to, your social scene, where you hang out
- **Tweets** = what you think about, your intellectual identity, what you amplify

The combination is the truth. An account that follows Qualia researchers but tweets Highbie content is genuinely straddling both worlds. The disagreement IS the signal, not an error to resolve.

**Implication for seed criteria:** Accounts where NMF and tweets agree are the highest-confidence seeds (both signals converge). Accounts where they disagree should be flagged as bridges, not forced into one community. This suggests a confidence metric: `source_agreement = 1 if NMF_top == tweet_top else 0.5 if NMF_top in tweet_top3 else 0`.

**Data:** Cross-validation results for 12 accounts stored in tweet_tags + account_community_bits. NMF assignments in community_membership table (run `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95`).

---

## EXP-006: Can the local DB support a Phase 1 community-correctness audit without new fetches?

**Date:** 2026-03-26
**Question:** Can we build the first external-audit + human-review benchmark from the current local `archive_tweets.db`, or do we need another fetch pass first?

**Hypothesis:** Core and boundary TPOT accounts should mostly have enough local context already, but famous-adjacent hard negatives will often only exist as `profiles` rows without local tweet text.

**Method:** Queried `profiles`, `tweets`, `enriched_tweets`, `community_account`, and `account_community_gold_*` while assembling the Phase 1 pilot slate. Checked core candidates, boundary candidates, and famous-adjacent hard negatives for local text availability and current community assignments.

**Result:** **PARTIAL.** The local DB is sufficient to ship the pilot substrate now:
- core and boundary items generally have strong local tweet coverage
- current ontology / target-community IDs are all available locally
- `account_community_gold_*` tables already exist and can accept Phase 1 imports

But most hard negatives only have bios and profiles locally:
- `karpathy`, `pmarca`, `lexfridman`, `naval`, `hubermanlab`, `dwarkesh_sp`, and similar accounts are present in `profiles`
- most have `0` local `tweets` and `0` `enriched_tweets`

**Lesson:** The benchmark can start now, but the runner must degrade gracefully for hard negatives. Grok can still be used as an external auditor on bio-only rows, but those rows should be explicitly flagged as `missing_local_posts` so reviewers know the evidence basis is thinner.

**Data stored:** `data/evals/phase1_membership_audit_accounts.json`, `data/evals/phase1_membership_audit_review_sheet.csv`

**Next step:** Run the pilot with the current mixed-context slate, then decide whether Phase 1.1 needs a focused fetch pass for hard negatives before scaling the benchmark.

---

## EXP-007: Can archive-only active learning label what archive accounts talk about without spending Twitter API credits?

**Date:** 2026-03-26
**Question:** Can the active-learning pipeline use local archive tweets plus LLM labeling to infer content identity, while avoiding any new twitterapi.io spend for archive-backed accounts?

**Hypothesis:** Yes, if archive loading adapts to the real `tweets` schema and archive-only mode gates every paid context path, then locally archived tweets can drive LLM labeling with zero new Twitter API spend.

**Method:** Started with the archive-safe handle pool (`/tmp/tpot_archive_active_learning_handles.txt`) and ran `python -m scripts.active_learning --round 1 --archive-only`. First run failed on a schema mismatch (`like_count` assumed, real DB has `favorite_count`). Patched `load_archive_tweets()` to inspect `PRAGMA table_info(tweets)` and normalize real/archive-test schemas. A second smoke run exposed a second leak: reply tweets still called `thread_context` through twitterapi.io. Patched `src/archive/thread_fetcher.get_thread_context(... allow_api=False)` and threaded `allow_paid_api=not archive_only` through `scripts.active_learning.py`. Verified with smoke runs, then ran the only true archive-backed frontier tranche: `uh_cess`, `vyakart`, `vorathep112` with `--archive-only --archive-limit 5`.

**Result:** **Confirmed, with two hidden-paid-path fixes required.**
- `spent` stayed flat at `5.05`
- `reply_fetch_rows` stayed `0`
- `thread_context_cache` stayed flat at `310` after the final fixed runs
- `archive_enriched_rows` grew from `0` to `30`
- `archive_enriched_accounts` grew from `0` to `6`
- `label_sets_active_learning` grew from `1510` to `1527`
- `tweet_tags` LLM bits grew from `4005` to `4045`
- Frontier tranche outcome:
  - `uh_cess` → ambiguous (`LLM-Whisperers`, `highbies`, `Collective-Intelligence`)
  - `vyakart` → ambiguous (`Tech-Intellectuals`, `Collective-Intelligence`, `Core-TPOT`)
  - `vorathep112` → ambiguous (`highbies`, `Quiet-Creatives`, `Relational-Explorers`)

**Lesson:** "Archive-only" was not a single switch; it required closing three separate paid paths: timeline/search fetches, reply-community fetches, and thread-context fetches. Once those were all gated, the pipeline started using tweet content as intended. Also, only 3 not-yet-enriched archive accounts are currently in `frontier_ranking`, so a much larger archive sweep would be a bulk labeling job, not active learning.

**Data stored:** Results persisted in `data/archive_tweets.db` tables `enriched_tweets`, `tweet_label_set`, and `tweet_tags`. Smoke/probe account outcomes include `0xosprey`, `33asr`, `5matthewdub`; active-learning frontier tranche includes `uh_cess`, `vyakart`, `vorathep112`.

**Next step:** Decide whether to (a) keep using uncertainty-ranked archive tranches only, or (b) build a separate bulk archive-labeling queue for the remaining archive-backed accounts that are outside `frontier_ranking`. Also persist per-model label rows so `verify_active_learning` can report real agreement coverage.

---

## EXP-008: Multi-scale tweet clustering vs NMF communities

**Date:** 2026-03-29
**Question:** Does clustering tweet content at multiple scales discover structure that follow-graph NMF misses? Are NMF communities content-coherent, or purely social?

**Hypothesis:** NMF communities are defined by follow patterns (social tribes). Tweet content should capture a different dimension (intellectual interests). If so, AMI between the two should be low, and some NMF communities should scatter across many content clusters.

**Method:**
1. Exported 50K random authored tweets as CSV from archive
2. Embedded with `text-embedding-embeddinggemma-300m` (dim=768) on RTX 3080 via LM Studio
3. 23,808 tweets successfully embedded (model crashed twice at ~12K, used `--resume`)
4. K-means clustering at k=2,4,8,16,32,64 on L2-normalized embeddings
5. Rolled up tweet cluster memberships to 309 accounts
6. Cross-referenced against NMF primary community assignments
7. Computed cross-scale nesting purity and AMI/ARI

**Result:** **CONFIRMED — NMF and tweet content are nearly independent signals.**

Cross-scale nesting purity (tweet clusters):
- k=2→4: 0.928 (strong hierarchical structure)
- k=4→8: 0.841 (real sub-clusters)
- k=8→16: 0.666 (moderate)
- k=16→32: 0.518 (dissolving)
- k=32→64: 0.521 (noise)

NMF→tweet purity (does NMF community map to a tweet cluster?):
- At k=2: avg 0.61 — some signal. Quiet-Creatives 0.96, TfT 0.86.
- At k=8: avg 0.42 — most NMF communities scatter across content clusters.
- At k=16: avg 0.29 — near random. Core-TPOT, highbies, Internet-Intellectuals have no content coherence.

Adjusted Mutual Information (NMF vs tweet clusters):
- Peak AMI at k=16: **0.080** (0=independent, 1=identical)
- Peak ARI at k=16: **0.040**
- Both barely above random — these are genuinely orthogonal dimensions.

Communities with HIGH content coherence (social tribe ≈ intellectual tribe):
- Quiet-Creatives (0.96 at k=2), Queer-TPOT (0.45 at k=16), AI-Safety (0.47 at k=32)

Communities with LOW content coherence (social tribe ≠ intellectual tribe):
- Core-TPOT, highbies, Internet-Intellectuals — scatter everywhere. Defined by social position, not content.

Reverse analysis: tweet clusters are also NMF-diverse. At k=16, cluster_1 (n=43) mixes AI-Creativity, AI-Safety, and Qualia-Research — they write about similar things but are socially distinct.

**Lesson:** Follow graph and tweet content measure orthogonal dimensions of community structure. An account in AI-Safety (by follows) who tweets about contemplative practice is a bridge that only a multi-view system can detect. NMF alone would call them AI-Safety. Content alone would call them Contemplative. The truth is both. This validates the multi-view ensemble prior architecture from ADR 016.

**Data stored:** `data/embed_experiment.db` — tables: tweet_embedding (23,808 rows), tweet_cluster (6 scales), account_cluster_histogram (309 accounts × 6 scales), cluster_run (6 entries). Also tweets table with account_id for rollup joins.

**Next step:** Build multi-view account descriptor combining graph view (NMF/propagation), semantic view (tweet cluster histograms), taste view (like cluster histograms), and interaction view (quote/reply patterns). Fit ensemble prior on gold labels. This becomes the replacement for NMF-as-sole-prior.

---

## EXP-009: View agreement as confidence signal for holdout detection

**Date:** 2026-03-30
**Question:** Does graph-semantic agreement predict TPOT membership better than graph confidence alone? Should we boost confidence when views agree and penalize when they disagree?

**Hypothesis:** Accounts where graph-view and semantic-view agree on community assignment are more reliably classifiable. Agreement = higher confidence, disagreement = lower confidence or bridge account.

**Method:**
1. Used 238 seed accounts with both views (graph NMF weights + k=8 tweet cluster histograms) as training set
2. Trained separate KNN classifiers (k=5, cosine) on graph-only and semantic-only views
3. For 71 holdout TPOT members with both views, computed: graph community prediction, semantic community prediction, and whether they agree
4. Measured detection rate under different confidence strategies
5. Tested combined scoring: graph_conf * agreement_factor

**Result:** **HYPOTHESIS REJECTED — view disagreement is the signal, not agreement.**

82% of holdout TPOT members have views that DISAGREE (graph community ≠ semantic community). Only 18% agree.

Detection rates:
- Graph KNN conf > 0.3: 100% (all 71 detected)
- Propagation score > 0.05: 62% (44/71)
- Views AGREE + graph conf > 0.3: only 18% (13/71)
- Views DISAGREE: 82% (58/71)

The combined scoring (boosting agreement, penalizing disagreement) HURTS — it pushes real TPOT members down the ranking because they're bridges.

Bridge examples from holdout (all confirmed TPOT):
- @visakanv: graph=Internet-Intellectuals, semantic=Contemplative
- @repligate: graph=LLM-Whisperers, semantic=Core-TPOT
- @RomeoStevens76: graph=Contemplative, semantic=AI-Creativity
- @patio11: graph=Tech-Intellectuals, semantic=Collective-Intelligence
- @adityaarpitha: graph=AI-Safety, semantic=Quiet-Creatives

**Lesson:** TPOT is definitionally a cross-cutting meta-community. Its members follow one social tribe but intellectually range across several. View disagreement is a *feature* of TPOT membership, not noise. A "pure" account (follows and tweets about the same thing) is less likely to be TPOT — they'd be in a single-topic community instead.

This reframes the multi-view architecture:
- **Graph view's job**: detect proximity to TPOT seeds (works at 100% recall)
- **Semantic view's job**: characterize *what kind* of TPOT member (intellectual profile), NOT whether they're TPOT
- **View disagreement's job**: identify bridge accounts and multi-community members (the most interesting TPOT members)
- **Confidence**: should NOT penalize disagreement. Instead: graph confidence for TPOT membership, view disagreement for richness/bridge detection.

**Data stored:** Analysis run in-memory on `data/archive_tweets.db` + `data/embed_experiment.db`. No new tables created.

**Next step:** Revise ADR 017 to reflect that views serve different purposes (detection vs characterization vs bridge detection), not a single ensemble vote. The semantic view enriches the account description rather than replacing the graph-based community assignment.

## EXP-010: Can Blob-backed site data bypass gitignored public exports without fighting Vercel deploy limits?

**Date:** 2026-04-09
**Question:** Can we serve fresh `data.json` / `search.json` to the public site by uploading them to Vercel Blob and proxying them through site-owned API routes, instead of relying on gitignored files being present in each deployment?

**Hypothesis:** Uploading the two generated JSON files to fixed public Blob pathnames (`public-site/data.json`, `public-site/search.json`) will solve the stale-data problem cleanly. The only remaining risk is whether Vercel deployment of the new proxy routes is blocked by the project's `rootDirectory` behavior.

**Method:**
1. Inspected the frontend fetch path and confirmed it hardcoded `/data.json` and `/search.json`.
2. Added local code for:
   - shared frontend endpoint constants,
   - `GET /api/data` and `GET /api/search` Blob proxy routes,
   - a `node scripts/upload-public-site-data.mjs` uploader,
   - a human-readable verification script `scripts/verify_public_site_blob.py`.
3. Ran targeted frontend tests, the public-site build, and the Python export test suite.
4. Uploaded local `public/data.json` and `public/search.json` to Vercel Blob with stable pathnames and overwrite enabled.
5. Probed the direct Blob URLs and the public `amiingroup.vercel.app/api/data` and `/api/search` routes.
6. Tried three deployment paths for the new code: direct deploy from `public-site`, deploy from repo root, and local prebuild + prebuilt deploy.

**Result:** **PARTIALLY CONFIRMED.**

What worked:
- Blob upload succeeded.
- Direct Blob URLs serve the current export:
  - `data.json` = `25,637,670` bytes
  - `search.json` = `16,492,299` bytes
- Local code is sound:
  - frontend targeted tests: `43 passed`
  - `npm run build`: passed
  - `pytest tests/test_export_public_site.py -q`: `40 passed`

What failed:
- Public routes are still `404` because the new code is not yet deployed.
- Vercel CLI deploy attempts continue to recurse the configured project root:
  - from `tpot-analyzer/public-site`: path becomes `.../tpot-analyzer/public-site/tpot-analyzer/public-site`
  - from repo root: CLI ignores the existing link and tries to infer a new project from the workspace folder name
  - `vercel build --prod` only worked after locally nulling the ignored `.vercel/project.json.settings.rootDirectory`, but `vercel deploy --prebuilt --prod` still failed against the remote root-directory setting

**Lesson:** Blob is a valid fix for runtime data delivery; the remaining blocker is Vercel deployment mechanics, not the Blob approach or the app code. The project has a deploy-path mismatch between Git-integrated `rootDirectory=tpot-analyzer/public-site` and the Vercel CLI's local deploy resolution.

**Data stored:**
- Blob URLs:
  - `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/data.json`
  - `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/search.json`
- Verification output:
  - local `tpot-analyzer/scripts/verify_public_site_blob.py`
  - public URL probes against `https://amiingroup.vercel.app`

**Next step:** Ship the new code through the Git-integrated deployment path or reconfigure project-level deploy settings so the proxy routes can go live; once that deploy lands, `/api/data` and `/api/search` should immediately serve the already-uploaded Blob data.

---

## EXP-011: Parameterizing Directed Personalized PageRank for Subfield Resolution

**Date:** 2026-04-15
**Question:** If we parameterize the teleport probability (`alpha`) in Directed Personalized PageRank (instead of a globally hardcoded 0.15), can we force the math engine to isolate hyper-specific intellectual subfields inside dense macro-communities?
**Hypothesis:** Higher teleport probabilities force random walks to be shorter and more highly localized to the immediate seed neighborhoods, reducing the "washing out" smoothing effect across large macro hubs, solving our Subfield mapping boundary problem.
**Method:** 
1. Expose `alpha` parameter in `src/propagation/types.py` through to `compute_ppr`.
2. Ran `scripts.propagate_community_labels` at `alpha=0.15` (baseline wide), `alpha=0.45` (tight), and `alpha=0.85` (hyper-local).
3. Compared shadow-node assignments, "Seeds Absorbed Ratio", unassigned abstain count, and maximum Lift scaling.
**Result:** **HYPOTHESIS CONFIRMED.** Higher alpha creates extreme subfield localization:
- At `alpha=0.15`: 91.4% abstained. Max Lift for "LLM Whisperers" was 68.8x. Walk wandered deeply into generic graph.
- At `alpha=0.45`: 85.7% abstained. Max Lift for "LLM Whisperers" scaled to 388.5x. Tight clustered assignments.
- At `alpha=0.85`: 83.1% abstained. Max Lift for "LLM Whisperers" exploded to 5361.6x. Solved in 6 iterations instead of 55. We isolated purely the mathematically closest connections.
**Lesson:** The teleport probability `alpha` behaves directly like focal length for our clustering lens. By setting `alpha=0.15` for the global graph (identifying macro hubs) and then rerunning at `alpha=0.45` or higher solely inside the filtered subsets (e.g. `AI-Safety` only), we trivially slice granular subfields apart without Goodhart-ing or over-smoothing.
**Data stored:** Output logged to `docs/diagnostics/alpha_0.15.txt`, `_0.45.txt`, and `_0.85.txt`.
**Next step:** Integrate hierarchical propagation into the ingestion pipeline, ensuring AI-Safety / mechanistic interpretability seeds acquired via the topic search API are given high `alpha` localized propagation spaces.

---

## Template for future experiments

```markdown
## EXP-NNN: [Question in one line]

**Date:** YYYY-MM-DD
**Question:** [What are we trying to learn?]
**Hypothesis:** [What we predicted and why]
**Method:** [What we did — specific scripts, data, parameters]
**Result:** [What happened — with numbers]
**Lesson:** [What this means for future work]
**Data stored:** [Where the results live in the DB/filesystem]
**Next step:** [What this enables or blocks]
```
