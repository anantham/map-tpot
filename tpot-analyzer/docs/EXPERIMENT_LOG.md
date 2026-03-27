# Experiment Log

> Hypotheses tested, results observed, lessons learned. This is institutional memory — what we tried, what worked, what didn't, and why. Each entry records the question, the method, the data, and the verdict so future sessions don't re-run failed experiments or miss validated insights.

*Last updated: 2026-03-26 (Session 11)*

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
