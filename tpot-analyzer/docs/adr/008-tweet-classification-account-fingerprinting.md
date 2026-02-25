# ADR 008: Tweet-Level LLM Classification as Account Fingerprinting Foundation

- Status: Proposed
- Date: 2026-02-25
- Deciders: Human collaborator + computational peer
- Group: Data pipeline, clustering, UI/UX
- Related ADRs: 001-spectral-clustering-visualization, 006-shared-tagging-and-tpot-membership, 007-observation-aware-clustering-membership

---

## Issue

The current clustering pipeline uses graph structure (mutual follow network) and account metadata (follower count, bio text) as node features. This fails to capture the defining characteristic of TPOT communities: **aesthetic and epistemic style** — how people say things, not just who they follow.

The result: graph-adjacent accounts (e.g., journalists who follow many TPOT accounts) are indistinguishable from community members. Community boundaries are structurally plausible but semantically wrong.

---

## Context

1. **TPOT is vibe-based, not topic-based.** Membership is defined by epistemic style and aesthetic sensibility, not by explicit affiliation or topic. Two accounts can be structurally identical in the follow graph but one is TPOT and one is not.

2. **We have rich content data.** The Community Archive Supabase instance holds 11.5M tweets and 13.6M liked tweets from 334 accounts — untapped in the current pipeline.

3. **Existing taxonomy.** The team has developed a tweet classification taxonomy across three orthogonal axes:
   - **Epistemic/Simulacrum axis**: l1 (truth-seeking, empirical), l2 (persuasion, rhetorical), l3 (tribal signaling, identity performance)
   - **Functional/social axis**: aggression, dialectics, personal, information, commentary, insight, advertising, obvious, meta, art
   - **Topic axis**: meditation, alignment, and others (extensible)

4. **Liked tweets reveal latent preferences.** What accounts like (but don't post) is a distinct signal from what they post — reveals aesthetic alignment across the observability boundary.

5. **Community boundaries are fuzzy.** TPOT has subcultures (woo post-rats, buddhists, EAs, e/acc, alignment, anime pfp, gender discourse) that overlap in a Venn diagram, not partition cleanly. Hard cluster membership misrepresents the structure.

6. **Different users interpret the space differently.** One analyst's "woo" cluster is another's "meditation adjacent rationalist." The system should not hardcode any single labeling.

---

## Decision

Adopt a **two-layer architecture** separating content-aware structure discovery from per-user semantic labeling:

### Layer 1: Content-Aware Embedding (universal, runs once)

Replace current node features with a richer account fingerprint vector:

```
account_fingerprint = [
  posted_tweet_distribution,   # fraction l1/l2/l3, aggression, dialectics, etc.
  liked_tweet_distribution,    # same axes, but over liked tweets (passive signal)
  graph_features,              # mutual ratio, degree, clustering coefficient
  bio_embedding,               # existing
]
```

Tweet classification via **LLM few-shot classification** (OpenRouter, frontier model):
- Each tweet classified independently on all three axes
- Output: probability distribution per axis (not hard labels)
- Classification governed by a human-curated **golden dataset** (`taxonomy.yaml`)
- Cost-controlled: configurable tweets-per-account, rolling updates as new tweets arrive

Account fingerprint aggregates per-tweet distributions across all posted and liked tweets.

Clustering runs on these fingerprints: spectral micro-clustering → Ward linkage → adaptive expansion. Same pipeline, richer input.

### Layer 2: Per-User Semantic Labeling (configurable, per-user)

Users label ~20-50 exemplar accounts with their own community taxonomy (e.g., "woo", "EA", "e/acc", "anime pfp"). The system:
1. Fits a soft classifier over the shared embedding using those exemplars as anchors
2. Assigns each account a **probability distribution over user-defined communities**
3. Overlapping communities emerge naturally from accounts with high scores on multiple centroids

Different users get different community views over the same underlying structure. Labels are stored per-user, not globally.

### Active Learning Loop

The golden dataset quality is maintained via:
1. Human labels a small set of tweets (50–200 to start)
2. LLM classifies held-out set → Brier score computed per axis per model
3. High-entropy predictions (model uncertain) surfaced to human for arbitration
4. Human labels "scissor tweets" (hard cases that force taxonomy precision) → golden set grows
5. Multi-model benchmark: same golden set run against multiple LLMs to identify best-calibrated model for this taxonomy

### Broadcast to Broader Graph

The 334 accounts with full tweet archives serve as **anchor accounts** with rich fingerprints. The broader follow/following-only accounts (no tweet data) are positioned relative to these anchors via graph proximity — inheriting soft community scores from their neighborhood in the embedding.

---

## Assumptions

1. LLM few-shot classification can reliably distinguish l1/l2/l3 given good golden examples. **This is the critical assumption to validate first** (pilot: 500 tweets, Brier score check).
2. Account tweet distributions are stable enough to be meaningful fingerprints (500–2000 recent tweets is sufficient sample size).
3. Liked tweet `fullText` in the community archive is sufficient for classification despite no author attribution.
4. The 334 anchor accounts are representative enough of TPOT to serve as an embedding scaffold for the broader graph.
5. Per-user labeling of ~20-50 exemplars is sufficient to define community regions in the embedding.

---

## Constraints

- LLM classification cost: ~$0.00063/tweet at Kimi K2.5 rates. Pilot (500/account × 334) ≈ $105. Budget flag required.
- Community archive data is public (anon key published in community-archive repo). No privacy concerns for the 334 accounts.
- Liked tweet author is unknown in archive — liked distribution captures "what kind of content does this person engage with" not "which accounts".

---

## Consequences

**Enables:**
- Meaningful clustering of TPOT subcultures by epistemic style, not just follow structure
- Venn diagram visualization of overlapping communities (soft membership)
- Any user can define their own community taxonomy and see boundaries shift
- The 334 anchor accounts become a semantic coordinate system for the broader TPOT graph

**Requires before clustering recompute:**
- Community archive fetch complete (data pipeline — in progress)
- Golden dataset validated (Brier score plateau)
- Classification pipeline built and run on 334 accounts

**Breaking changes:**
- Node feature vector format changes (new schema)
- Cluster IDs will shift as clustering runs on new features — any saved cluster references become stale
- Soft membership scores replace hard cluster membership in the API

**Follow-up ADRs likely needed:**
- ADR 009: Venn visualization and soft membership API contract
- ADR 010: Per-user labeling storage and workspace model

---

## Positions Considered

**A. Keep graph-only clustering, add text embeddings to scoring only**
- Pros: No changes to core clustering pipeline
- Cons: Clustering still finds structurally-adjacent communities, not aesthetic ones. Content only used at retrieval time, not as primary signal.

**B. Use pre-trained tweet embeddings (e.g., sentence-transformers)**
- Pros: No LLM API cost, runs locally
- Cons: General embeddings don't capture the specific l1/l2/l3 distinctions that are diagnostic of TPOT subcultures. No Brier score calibration.

**C. Fine-tune a small classifier on labeled examples**
- Pros: Fast inference, no per-call API cost
- Cons: Needs hundreds of labeled examples per category to fine-tune well. LLM few-shot is more practical at this scale and more aligned with the active-learning loop design.

**D. (Chosen) LLM few-shot with active learning loop**
- Pros: Captures nuanced l1/l2/l3 distinctions with relatively few golden examples; active learning loop ensures golden set improves over time; Brier score gives calibration signal; any user can customize examples.
- Cons: API cost per classification run; latency for rolling updates.
