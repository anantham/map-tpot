# Prior Improvement Roadmap — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Goal:** Improve community detection prior by integrating unused signals, then use better data to inform ontology decisions.

---

## Problem Statement

The system sits on massive untapped signal:
- **17.5M raw likes** — but only ~24K resolve to author-attributed edges via archive tweet JOIN. The NMF signal is "resolved like-author edges" (251 sources → 302 targets), a partial structural signal over archive-visible targets, not a full liked-author graph.
- **4.3M replies** — unsigned (valence unknown)
- **5.5M tweets** — only 446 labeled across 20 accounts
- **Bookmarks, lists** — never parsed/fetched
- **Simulacrum levels** — labeled but unused downstream

Community detection uses only follows + retweets. The current 15 communities feel wrong — "Emergence & Self-Transformation" appears in almost every account's top-4, suggesting a catch-all rather than a real community.

## Key Design Decisions (Settled)

### 1. Latent Object
**Decision:** Independent overlapping memberships + explicit unknown.

An account's 40% Builders score doesn't reduce its 35% Contemplative score. Matches TPOT social reality. The propagation system already has a "none" column + abstain gate.

### 2. Prior Formation Strategy
**Decision:** Data-first, then ontology review.

Don't fix categories blind. Add likes to NMF, re-run as a new snapshot, compare against known accounts, THEN decide what ontology surgery is needed.

Rationale: Resolved like-author edges will likely shift community boundaries in ways that resolve some category confusion. Building lifecycle operators before re-running with better data risks optimizing around categories you'll replace.

### 3. Prior Strength (future work)
**Decision:** Virtual evidence rule, calibrated by data richness.
- Full archive, dense follows: NMF prior worth 3-5 virtual tweets
- Shadow account, many confident neighbors: 2-3 tweets
- Sparse shadow: 0.5-1 tweet
- Invisible: no prior, unknown

Not implemented yet — needs ablation to calibrate. Tier D work.

### 4. Update Mechanism (future work)
**Decision:** Simulacrum-weighted bits.
- L1 (sincere proposition) = 1.5x
- L2 (strategic) = 1.0x
- L3 (performative/in-group) = 2.0x
- L4 (pure simulacrum) = 0.5x

Starting prior on weights, not gospel. Tier C work.

### 5. Reply Valence (future work)
**Decision:** Conservative. Free heuristics first (author-liked-reply, mutual-follow), cheap LLM later. Never dump unsigned replies into the prior.

---

## Signal Framework

The roadmap is not a list of data sources to wire up. It's a framework for deciding which signals to trust, how much, for whom, and in what order.

### Signal Taxonomy

Each signal has a **type** (what kind of evidence it provides):

| Type | What it captures | Examples |
|------|-----------------|----------|
| **Identity** | Self-described attributes | Bio text, display name, profile links |
| **Affinity** | Positive engagement with content/people | Likes, bookmarks, follows |
| **Curation** | Deliberate amplification/organization | Retweets, quote tweets, X Lists |
| **Discourse** | Conversational relationships | Replies, mentions, thread depth |
| **Exposure** | Algorithmic/passive consumption | Feed contents, browse behavior |
| **Topology** | Structural graph properties | Co-followed matrix, triadic closure, betweenness, degree distribution |
| **Temporal** | Change over time | Follow timestamps, posting cadence, engagement recency |

### Coverage Matrix

Not all signals apply to all accounts:

| Signal | Seeds (~328) | Shadow (~95K) | Privacy | Noise | Roadmap status |
|--------|:---:|:---:|---------|-------|----------------|
| **Follows** | Full | Partial (as targets) | Public | Low | LIVE (NMF) |
| **Retweets** | Full | As RT targets only | Public | Low | LIVE (NMF 0.6x) |
| **Resolved like-author edges** | ~79% | No | Public | Low | LIVE (NMF 0.4x) |
| **Liked tweet text** | Full (17.5M) | No | Public | Medium | Tier B: CT1-CT3 |
| **Reply graph (unsigned)** | Full | Partial | Public | High (valence unknown) | Tier B: R1-R2 (heuristic signing) |
| **Bookmarks** | Unknown | No | Semi-private | Very low | Not parsed from archive |
| **Bio text** | Full | ~72K in resolved_accounts? | Public | Low | Tier C: SP4 (needs verification) |
| **Tweet URL domains** | Full | No | Public | Low | Not on roadmap |
| **Co-followed matrix** | Computable | Computable | Public | Low | Not on roadmap |
| **Mention graph** | Extractable | Partial | Public | Medium | Not on roadmap |
| **Quote graph** | In tweets, not normalized | Partial | Public | Medium | Not on roadmap |
| **Thread depth** | Extractable | Partial | Public | Low | Not on roadmap |
| **Mutual follow** | Computable | Partial | Public | Very low | Not on roadmap |
| **X Lists** | API fetch | API fetch | Public | Medium (noisy curation) | Deferred |
| **Bluesky follows** | Free API | Free API | Public | Low (identity resolution hard) | Deferred |
| **Feed contents** | Stream monitor | Stream monitor | **Private** | Low | **Research-only** |
| **Browse behavior** | Stream monitor | Stream monitor | **Private** | Low | **Research-only** |
| **Profile location** | ~72K | ~72K | Public | Medium | Descriptive only |
| **Posting cadence** | All tweets | No | Public | High | Descriptive only |
| **Display name patterns** | ~72K | ~72K | Public | High | Descriptive only |
| **Account age** | ~72K | ~72K | Public | Low | Descriptive only |

### Fusion Policy

Signals are not equal. They serve different roles in the pipeline:

| Role | When to use | Examples |
|------|------------|---------|
| **Structural prior** | Core input to NMF/propagation. Must be high-coverage, low-noise, interpretable. | Follows, retweets, resolved likes |
| **Content validation** | Independent check on structural communities. Confirms or challenges ontology. | Liked tweet text (CT1-CT3), tweet URL domains, bio text |
| **Weak reranker** | Adjusts confidence or breaks ties for borderline accounts. Not strong enough alone. | Mutual follow, posting cadence, profile location, display name |
| **Human-review signal** | Provides context for manual labeling but never enters automated pipeline. | Feed contents, browse behavior, search queries |
| **Ablation candidate** | Could become a structural prior after evaluation shows it helps. | Bookmarks, co-followed matrix, mention graph, quote graph |

### Governance

| Tier | Data class | Can enter public pipeline? | Can be exported? |
|------|-----------|:---:|:---:|
| **Public** | Follows, RTs, likes, bios, tweets, lists | Yes | Yes |
| **Opt-in consented** | Feed contents, browse behavior (via community-archive Chrome extension) | Yes — users explicitly install extension to share this data for research | Aggregated signals only (co-feed clustering, community assignment). Don't expose individual feed contents. |
| **Semi-private** | Bookmarks, DM-adjacent signals | With consent only | Aggregated only |

**Note on feed data:** Users who install the community-archive Chrome extension are explicitly opting in to share their feed/browse data for community research. This is consensual, not scraped. The signal (what X's algorithm shows you) is arguably the richest community signal available — X already computed the affinity graph. The analysis is about the VIEWER's community membership, not the tweet authors'.

### Evaluation Plan

No signal enters the structural prior without ablation:
1. Add signal to dev pipeline
2. Measure: does holdout recall improve?
3. Measure: does community coherence (human spot-check) improve?
4. If yes to both → promote to structural prior
5. If only one → keep as weak reranker or content validation
6. If neither → drop

### Signals to Promote (next)

Based on the framework, these signals should move from "not on roadmap" to specific tiers:

| Signal | Recommended role | Recommended tier | Justification |
|--------|-----------------|-----------------|---------------|
| **Co-followed matrix** | Ablation candidate → structural prior | Tier B | One matrix multiply. Captures "social consensus about who belongs together." Arguably stronger than direct follows for community detection. |
| **Tweet URL domains** | Content validation | Tier B | Near-deterministic: lesswrong.com → AI-Safety, QRI → Qualia-Research. Cheap to extract, validates ontology. |
| **Bookmarks** | Ablation candidate → structural prior | Tier B | Strongest deliberate signal (stronger than likes). Parse from archive JSON, no API cost. Volume unknown until parsed. |
| **Mention/quote graph normalization** | Ablation candidate | Tier C | Extractable from tweets table. Mentions = active attention. Quotes = critical engagement. Both need normalization before use. |
| **Mutual follow distinction** | Weak reranker | Tier C | Reciprocal edges are stronger community evidence. Cheap to compute from existing follows. |
| **Bluesky cross-reference** | Content validation (external) | Tier D | Free API but hard identity resolution. Independent validation of X-derived communities. |

---

## Priority Tiers

### Tier A — Do Now (unblocks everything)

| ID | Item | Effort | Why first |
|----|------|--------|-----------|
| S1 | Push commits (10+ ahead of origin) | 1 command | Hygiene |
| E1 | Automate bits rollup + verify | ~50 LOC | Rollup exists for 20 accounts but is manual; script must reproduce current state |
| D2+D5 | Add resolved like-author edges to NMF feature matrix | ~40-60 LOC | ~24K resolved pairs (251→302 accounts), partial structural signal |
| O4 | Re-run NMF as NEW snapshot (not in-place) | ~10 LOC + compute | Compare old vs new without destroying current state |

### Tier B — Ontology review + signal improvements (needs new snapshot)

| ID | Item | Depends on | Why this tier |
|----|------|------------|---------------|
| O5 | Compare old/new on known accounts (Romeo, Nick, repligate, visakan) | O4 | First diagnostic step |
| O1+O2 | Ontology review with user's domain knowledge | O5 | Human gate |
| L1-L3,L6 | Only the lifecycle operators actually needed | O1+O2 | Build only what ontology review demands |
| P6a | Time-weight retweets/replies with exponential decay | O5 | Retweets and replies have real engagement timestamps; follows and likes do NOT (follows have no timestamp; likes use liked-tweet created_at which is a bad proxy for like time). Apply `exp(-lambda * age_days)` during matrix construction for RT/reply signals only. |
| R1-R2 | Author-liked-reply + mutual-follow valence | Independent | Free positive-reply heuristics, signs the unsigned replies. Role: discourse signal. |
| P1 | Simulacrum-weighted bits (L3=2x, L1=1.5x, L2=1x, L4=0.5x) | E1 + stable ontology | Makes existing labels work harder once categories are trusted |
| CT1 | Topic modeling on 17.5M liked tweet texts → 20-30 macro-interest vectors | Independent | Role: content validation. Orthogonal to graph — content fingerprint of what each seed pays attention to. |
| CT2 | Profile each seed account by their like-topic distribution | CT1 | Each seed gets a distribution over the 20-30 content vectors. |
| CT3 | Compare content-derived profiles against graph-derived NMF communities | CT2 + O5 | Strongest ontology validation: graph+content agreement = real community. |
| CF1 | Co-followed matrix | Independent | Role: ablation candidate → structural prior. One matrix multiply: `F^T @ F` gives accounts-followed-by-same-people similarity. Captures social consensus. |
| UD1 | Tweet URL domain extraction + community mapping | Independent | Role: content validation. Near-deterministic: lesswrong.com → AI-Safety, QRI → Qualia-Research. Cheap validation signal. |
| BK1 | Parse bookmarks from archive JSON | Independent | Role: ablation candidate → structural prior. Strongest deliberate signal (saved-for-later > likes). Volume unknown until parsed. |
| FD1 | Feed co-occurrence matrix from community-archive-stream | Independent | Role: ablation candidate → structural prior (opt-in consented tier). Users explicitly install Chrome extension to share feed data. X's algorithm already computed community affinity — this is the richest signal available. Query Supabase for streamed tweets + originator_id. Build accounts × tweets-seen matrix. Export aggregated community signals only, not individual feed contents. |

**Why content vectors matter:** The graph tells you who listens to whom. The liked-text corpus tells you what they actually care about. These are independent signals. A community that shows up in both graph AND content is real. A community that only shows up in graph (people follow each other but like different things) may be a social cluster, not an intellectual community. A content cluster with no graph community may be an emerging interest that hasn't formed social structure yet.

**Practical notes:**
- 17.5M documents is large but standard for topic modeling (sparse TF-IDF + NMF scales fine)
- No API cost — text is already in the `likes.full_text` column
- The content vectors could also be used downstream for shadow account classification (if a shadow account's retweeted text clusters in "meditation + neuroscience," that's evidence for Contemplative)

**Freeze point:** After Tier B, canonical seed memberships are frozen in `community_account`. This becomes the boundary condition for shadow projection.

### Tier C — Shadow Projection (re-propagate with fixed ontology)

NMF gives the ontology and soft labels on the seed/core set (~327 accounts). Projecting to the ~95K shadow graph is a separate semi-supervised learning problem. The infrastructure exists (`scripts/propagate_community_labels.py`, 822 LOC) but is not currently gated as a roadmap phase with its own metrics.

| ID | Item | Depends on | Notes |
|----|------|------------|-------|
| SP1 | Freeze canonical seed memberships after Tier B | Tier B complete | Write to `community_account` with source='human' for curated seeds |
| SP2 | Re-run `propagate_community_labels.py` with updated ontology | SP1 | Harmonic label propagation on follow graph with updated boundary conditions |
| SP3 | Calibrate `none` / `abstain` / export thresholds on holdout seeds | SP2 | Current abstain_mask was disabled as "too conservative" (`export_public_site.py:208`). This needs its own calibration step. |
| SP4 | Bio prior for sparse-but-promising shadow nodes | SP2 | Role: weak reranker. Keyword-match bios against community descriptions ("jhanas, vipassana" → Contemplative). No ML needed for first pass. |
| MQ1 | Normalize mention/quote graph from tweets table | SP1 | Role: ablation candidate. Mentions = active attention, quotes = critical engagement. Extract `A mentioned B` and `A quoted B` edges. |
| MF1 | Mutual follow distinction | SP1 | Role: weak reranker. Reciprocal follow edges are stronger community evidence than one-way. Cheap to compute. |
| SP5 | Three-band export | SP3 | Replace current binary (colored/grayscale) with three bands: **exemplar** (curated seeds, high confidence), **confident** (high-confidence propagated shadow accounts), **frontier** (uncertain candidates for human review / labeling queue) |

**Why three bands matter:** The current export compresses propagation output into a binary (classified vs propagated). The propagation model actually produces uncertainty, entropy, and abstain signals. Exposing three bands lets the public site be honest about confidence without requiring thousands more labeled accounts. Community pages can show curated exemplars, projected members, and an uncertain frontier — each with appropriate visual treatment.

### Tier D — Calibration + shipping

| ID | Item |
|----|------|
| E3 | Ablation ladder (baseline → +likes → +likes+time_decay) |
| P2 | Prior strength calibration (virtual evidence rule) |
| R5 | Cheap LLM reply valence (batch) |
| S2-S5 | Public site updates (about page, cards, community pages with updated data) |

### Demoted / Deferred

| ID | Item | Why |
|----|------|-----|
| D1 | Parse bookmarks | Not obviously more valuable than likes right now |
| D3 | Fetch X Lists | Validates communities, but after ontology settles |
| D6 | Co-like matrix | Speculative, wait for ablation |
| R3 | Same-community reply heuristic | Circular dependency |
| R5-R6 | LLM/fine-tuned classifier | Too early |
| P3 | Explicit unknown state | Propagation already handles this |
| P7 | Degree correction | TF-IDF already covers most of it |

---

## Tier A Execution Details

### S1: Push commits
```bash
git push origin main
```

### E1: Automate bits rollup
- Read `tweet_tags` WHERE category='bits', parse `community:direction:bits_value`
- Aggregate per (account_id, community_id) → total_bits, tweet_count, pct
- Write to `account_community_bits` (table already exists, populated for 20 accounts)
- **Success criterion:** script reproduces current 20-account state exactly (not "first automation from manual baseline" — the data is already there, this is about reproducibility and future-proofing)
- Verify: diff automated output against ALL 20 existing accounts, not just @repligate/@dschorno
- Ship as `scripts/rollup_bits.py` with `scripts/verify_bits_rollup.py`

### D2+D5: Likes into NMF
- **Prerequisite:** `build_engagement_graph.py` must have been run (it has — 24,501 pairs with likes > 0)
- **Data source:** Use pre-aggregated `account_engagement_agg.like_count` (NOT raw 17.5M-row likes table)
- **Coverage:** Verification script must report actual coverage dynamically (do NOT hardcode thresholds — counts change as archive grows). As of 2026-03-22: ~79% of NMF accounts have likes data.
- In `cluster_soft.py`, add `build_likes_matrix()`:
  - Query `account_engagement_agg` for like_count per (source_id, target_id) WHERE like_count > 0
  - Build sparse matrix: accounts × liked-authors (same account_id space as follows)
  - TF-IDF normalize (same transformer as follows/retweets)
- Concatenate: `hstack([normalize(follows_tfidf), normalize(retweets_tfidf) * 0.6, normalize(likes_tfidf) * weight])`
  - Note: weight is applied AFTER normalization (matching existing pattern at cluster_soft.py:188-189)
- Weight TBD (start with 0.4, calibrate later)
- Update `signal` field in `community_run` to 'follow+rt+like'
- **Double-weighting note:** An account appearing in both follows AND likes columns is a feature, not a bug — following AND liking someone IS stronger community evidence
- **Layer 1 persistence must save like features:** Update `_save_run()` to persist top-N like features per factor into `community_definition` with `feature_type='like'`, alongside existing `follow` and `rt` slices. Without this, `verify_likes_nmf.py` cannot do factor alignment on persisted runs — it would only work on in-memory artifacts.
  ```python
  # Current: only saves follow + rt slices of H
  H_follow = H[:, :len(targets_f)]
  H_rt     = H[:, len(targets_f):]

  # After: also save like slice
  H_follow = H[:, :len(targets_f)]
  H_rt     = H[:, len(targets_f):len(targets_f)+len(targets_r)]
  H_like   = H[:, len(targets_f)+len(targets_r):]
  # ... save top 10 like features per factor as feature_type='like'
  ```

### O4: Re-run NMF as new Layer 1 run
- This is a **Layer 1** operation: new `community_run` row with signal='follow+rt+like', new `community_membership` rows
- Layer 2 (curated communities, branch/snapshot system) is NOT touched — comparison happens at Layer 1
- Run at k=12, k=14, k=16 to check sensitivity (cheap — minutes each)

**Run identity fix (REQUIRED):** The current `run_id` construction at `cluster_soft.py:303-307` hashes only `k + account_ids + date`. It does NOT include the signal mix or likes weight. A same-day re-run at the same k will overwrite the existing Layer 1 run instead of preserving it.

Fix: include every run-shaping parameter in the hash input:
```python
# Before (BROKEN — collides on same-day reruns with different signals or weights):
h = hashlib.sha1(f"{args.k}{aid_str}".encode()).hexdigest()[:6]

# After:
signal = "follow+rt+like"  # parameterized
like_w = 0.4               # parameterized
rt_w = 0.6                 # parameterized
h = hashlib.sha1(f"{args.k}{signal}{rt_w}{like_w}{aid_str}".encode()).hexdigest()[:6]
run_id = f"nmf-k{args.k}-{signal}-lw{like_w}-{date}-{h}"
```
This ensures that k=14 with likes at 0.4 and k=14 with likes at 0.6 produce distinct run_ids even on the same day. Also update the hardcoded `signal="follow+rt"` at line 318 to use the actual signal mix.

**Factor alignment (REQUIRED for comparison):** NMF factor indices are arbitrary — "Community 3" in the old run may correspond to "Community 7" in the new run. The comparison script `verify_likes_nmf.py` must align factors before showing side-by-side deltas.

Alignment strategy: match old and new factors by top-feature overlap in the H matrix. Features are keyed as `feature_type:target` tuples (e.g. `follow:12345`, `rt:username`, `like:67890`) — not raw target IDs — because the same account can appear under multiple modalities and raw-ID matching would inflate overlap between unrelated factors.
```
For each new factor f_new:
  features_new = {f"{type}:{target}" for type, target in top_20_features(f_new)}
  For each old factor f_old:
    features_old = {f"{type}:{target}" for type, target in top_20_features(f_old)}
    overlap = |features_new ∩ features_old| / max(len(features_new), len(features_old))
  best_match[f_new] = argmax(overlap)
  match_quality[f_new] = max(overlap)
```
Factors with match_quality < 0.3 are flagged as "new / unmatched" — possible community births.
Unmatched old factors are flagged as "disappeared" — possible deaths.

**Note:** Old runs only have `follow` and `rt` features. New runs add `like` features. This means cross-signal alignment will naturally show lower overlap scores for factors that are primarily like-driven. That's informative, not a bug — it reveals which communities are most affected by the new signal.

- Ship comparison as `scripts/verify_likes_nmf.py`:
  - Align factors between old and new runs using H-matrix feature overlap
  - For each known account, show old vs new community weights (aligned)
  - Print account coverage metric dynamically (not hardcoded)
  - Highlight: factors that shifted most, unmatched new factors, disappeared old factors

---

## Success Criteria

1. Bits rollup script reproduces current 20-account `account_community_bits` state exactly
2. Likes matrix integrated into cluster_soft.py, using pre-aggregated engagement table
3. Run identity includes signal mix — old and new runs coexist in `community_run` table
4. New NMF Layer 1 runs produced with signal='follow+rt+like' at k=12,14,16
5. `scripts/verify_likes_nmf.py` shows factor-aligned comparison on known accounts
6. Account coverage reported dynamically (not hardcoded thresholds)
7. Unmatched factors flagged as potential community births/deaths
8. User reviews comparison and decides: ontology surgery needed? which k? proceed?

## Decision Gate (after Tier A)

If the likes-enriched NMF does NOT meaningfully change community structure:
- Try higher likes weight (0.6, 0.8 instead of 0.4)
- Try different k values
- Fallback: switch to ontology-first (build lifecycle operators, manually restructure, then re-run)
- Do NOT proceed to Tier B calibration work against unchanged communities

---

## Assumptions

- Main bottleneck is bad prior structure, not missing UI
- Likes are likely to shift communities more than bookmarks
- Ontology changes should be evidence-led, not operator-led
- The re-run with likes will either fix part of the category problem or make failure modes obvious

## Risks

- Likes might NOT meaningfully change communities (follows could dominate). Mitigation: try different weights (0.4, 0.6, 0.8). See Decision Gate above.
- New NMF run might produce completely different communities that are hard to compare. Mitigation: factor alignment via H-matrix feature overlap; old Layer 1 run persists; unmatched factors flagged explicitly.
- Compute: resolved likes are pre-aggregated to ~24K pairs in `account_engagement_agg` (only likes whose tweet_id joins to an archived author). The sparse matrix is ~327×302, trivial for NMF.
- Signal scope: this is a partial structural signal over archive-visible targets, not a full liked-author graph. The 17.5M raw likes mostly lack author attribution. Future work could use liked tweet TEXT as content evidence (much larger corpus, no author recovery needed), or fetch author metadata via API.
- ROADMAP_NEXT.md may conflict with this spec. This spec is canonical for prior improvement work; ROADMAP_NEXT should be updated to reference it.
