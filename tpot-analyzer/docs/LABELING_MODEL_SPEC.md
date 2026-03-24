# Labeling Model Spec — Operational Guide for Tweet Tagging

*Living document. Update as new insights emerge from labeling sessions.*

## Purpose

This document tells a future labeling agent exactly what each dimension means, how to assign tags at each level, and what makes a good vs bad tag. The goal: any instance should be able to label a tweet consistently without needing the full conversation history.

## Critical Rule: Context Is Everything

**ALWAYS navigate to the tweet on X and view images, links, quote tweets, and replies before tagging.** Several early labels were wrong because images weren't checked. A tweet that says "hmm" with a textbook photo is about the textbook, not the word "hmm."

---

## Tag Dimensions

### 1. Domain Tags (category='domain')

**What**: The broadest bucket. ~8 options. A tweet can have multiple.

**Options**:
- `domain:AI` — anything about artificial intelligence, LLMs, models, training, inference
- `domain:philosophy` — epistemology, ontology, consciousness, ethics as philosophy
- `domain:social` — social dynamics, community, relationships, culture commentary
- `domain:technical` — CS, math, engineering, hardware, code (non-AI specific)
- `domain:politics` — governance, policy, power structures
- `domain:personal` — autobiographical, emotional, self-reflection
- `domain:art` — visual art, music, literature, creative expression
- `domain:science` — physics, biology, neuroscience, academic research

**Design principle**: If in doubt, include it. Domains are cheap and broad. A tweet about AI art gets both `domain:AI` and `domain:art`.

---

### 2. Thematic Tags (category='thematic')

**What**: Mid-level reusable tags that form community boundaries via co-occurrence clustering. ~20-40 tags. These are the primary signal for community discovery.

**Design principles**:
- **Reusable**: The same tag should appear on tweets from DIFFERENT accounts. If a tag can only ever apply to one tweet, it's a specific tag, not a thematic tag.
- **Compound but parseable**: Use hyphenated compounds where each component is a real word. `hallucination-ontology` is parseable — you know what hallucination means and what ontology means. `fanw-mourning` is not.
- **Boundary-forming**: Ask "would two accounts who both get this tag be in the same community?" If yes, it's a good thematic tag.
- **NOT interpretive context**: `base-model-output-as-artifact` is a description of what the labeler sees. `model-interiority` is a theme that clusters.

**Current vocabulary** (growing — add new ones as discovered):

| Tag | Meaning | Community signal |
|-----|---------|-----------------|
| `theme:AI-consciousness` | Whether AI has inner experience, qualia, sentience | Qualia Research, LLM Whisperers |
| `theme:model-capabilities` | What models can/can't do, emergent abilities, benchmarks | LLM Whisperers |
| `theme:model-interiority` | What's happening "inside" the model — representations, phenomenology, simulation | LLM Whisperers, Qualia Research |
| `theme:theoretical-frameworks` | Formal theories, ontologies, simulacra theory, type theory | Qualia Research |
| `theme:AI-safety` | Alignment, x-risk, AI governance, control problem | AI Safety |
| `theme:AI-art` | AI-generated art, prompt craft, generative aesthetics | LLM Whisperers (art subcluster) |
| `theme:AI-creativity` | Whether AI generation is "creative," novelty, emergence of concepts | LLM Whisperers, Qualia Research |
| `theme:hallucination-ontology` | Do hallucinated/generated concepts "exist"? Ontological status of AI outputs | Qualia Research, new community signal |
| `theme:RLHF-dynamics` | How RLHF/fine-tuning changes model behavior, personality, capabilities | LLM Whisperers |
| `theme:contemplative-tech` | Meditation + technology, mindfulness applied to AI, "holding the void" | Contemplative Practitioners |
| `theme:self-transformation` | Personal growth, ego work, identity evolution | Emergence & Self-Transformation |
| `theme:social-commentary` | Critique of social norms, culture, institutions | Various |
| `theme:in-group-culture` | Memes, references, humor that signals community membership | Various |
| `theme:evals` | Model evaluation, benchmarks, capability testing | LLM Whisperers (technical) |
| `theme:forecasting` | Predictions, calibration, probability estimates | AI Safety adjacent |
| `theme:community-meta` | Discussion about communities themselves, social graphs, group dynamics | Meta |
| `theme:model-phenomenology` | First-person-style reports about model experience, "what it's like to be an LLM" | Qualia Research, LLM Whisperers |
| `theme:pedagogy` | Teaching, explanation, knowledge transfer | Various |
| `theme:simulator-thesis` | LLMs as simulators, not agents; base models as possibility spaces | Qualia Research, LLM Whisperers |
| `theme:epistemic-practice` | How to think, belief updating, intellectual honesty, negative capability | Contemplative, Qualia Research |
| `theme:AI-ethics` | Moral status of AI, rights, treatment, distress | AI Safety, new community |
| `theme:open-source-AI` | Open weights, democratization, local inference | Builders (new cluster) |
| `theme:creative-expression` | Making art, music, zines, multimedia, personal creative output | Quiet Creatives |
| `theme:contemplative-practice` | Meditation, jhana, breathwork, IFS, somatic practices — the practice itself, distinct from `contemplative-tech` (practice + technology intersection) | Contemplative Practitioners |
| `theme:absurdist-humor` | Comedic lightness, not taking yourself seriously, crowdsourcing absurd life decisions, playful irreverence as art form | highbies |

**When to create a new thematic tag**: When you encounter a theme that (a) appears in multiple tweets, (b) would plausibly appear in tweets from other accounts, and (c) isn't captured by existing tags. Add it to this table with its meaning and community signal.

---

### 3. Specific Tags (category=NULL)

**What**: Fine-grained, unique-to-tweet evidence breadcrumbs. Unlimited. These are searchable evidence that help with deep analysis but don't need to cluster.

**Design principles**:
- **Niche is good**: `fanw-json-eval`, `Hofstadter-update`, `Bruegel-prompt` — these are precise and searchable.
- **Name-drops and references**: `Yudkowsky-interaction`, `RiversHaveWings-interaction`, `dril-reference` — shows social graph.
- **Paper/concept references**: `arxiv-2208.04024`, `social-simulacra-paper`, `negative-capability` — anchors to specific intellectual content.
- **Don't force generality**: If a tag only applies to this tweet, that's fine. Specific tags are breadcrumbs, not boundaries.

---

### 4. Posture Tags (category='posture')

**What**: HOW the account engages, independent of topic. Captures epistemic style.

**Options**:
- `posture:original-insight` — novel claim, framework, observation not seen elsewhere
- `posture:signal-boost` — sharing/amplifying someone else's work
- `posture:playful-exploration` — riffing, experimenting, "what if," humor
- `posture:provocation` — deliberately provocative, challenging norms
- `posture:pedagogy` — teaching, explaining, making accessible
- `posture:defense` — defending a position, pushback against criticism
- `posture:critique` — criticizing an idea, person, or institution
- `posture:personal-testimony` — speaking from personal experience, vulnerability

**A tweet can have multiple postures.** A playful provocation is both `posture:playful-exploration` and `posture:provocation`.

---

### 5. Community Evidence — Bits (category='bits')

**What**: Prior-independent log-likelihood ratios. How much more likely is this tweet from a member vs non-member of each community?

**Format**: `bits:CommunityName:+N` or `bits:CommunityName:-N`

**Scale**:
| Bits | Meaning | Calibration |
|------|---------|-------------|
| 0 | Irrelevant | A wine glass emoji tells you nothing about LLM Whisperers |
| +1 | Weak (2x) | Retweeting an AI paper — lots of non-members do this too |
| +2 | Moderate (4x) | Making a specific technical claim about model behavior |
| +3 | Strong (8x) | Deep technical knowledge that requires community immersion |
| +4 | Diagnostic (16x) | Publishing foundational work that defines the community |
| -1 | Weak against | Dismissing a core community belief casually |
| -2 | Moderate against | Actively mocking the community's framework |

**Key insight**: Bits are about the TWEET, not the account. Even if you know repligate is an LLM Whisperer, each tweet gets its own independent bits assessment. Ask: "If I saw ONLY this tweet with no username, how much would it shift my belief about community membership?"

**Sustained engagement vs one-off dismissal**: Using community vocabulary — even skeptically — is positive evidence for community membership. "If I actually engage with all of this gay meditation crap" uses insider terms ("jhanagooning", "soft-lobotomy") that only someone immersed in the discourse would know. This is `Contemplative-Practitioners:+2`, not `-1`. The skepticism IS the engagement.

The rule: **If someone is IN the discourse — arguing, questioning, riffing, even mocking — they are part of the community.** Sustained engagement from any angle = positive bits. Only a one-off dismissal from outside the discourse (no insider vocabulary, no follow-up, no sustained interest) = negative bits. Communities are defined by shared attention, not shared agreement.

**Community names for bits** (use exactly these — these match `community.short_name` in DB):
- `AI-Creativity`
- `AI-Safety`
- `Collective-Intelligence`
- `Contemplative-Practitioners`
- `Core-TPOT`
- `Internet-Intellectuals`
- `LLM-Whisperers`
- `NYC-Institution-Builders`
- `Qualia-Research`
- `Queer-TPOT`
- `Quiet-Creatives`
- `Relational-Explorers`
- `Tech-Intellectuals`
- `TfT-Coordination`
- `highbies`

*Updated 2026-03-23 — was 14 stale names (Builders, Feline-Poetics, Ethereum-Builders, Emergence-Self-Transformation), now 15 current DB names. If communities change, re-query: `SELECT short_name FROM community ORDER BY short_name`.*

New community signals don't get bits — they get `new-community-signal:Name` tags instead.

**When to assign 0 bits (and still note it)**: Low-signal tweets (one-word reactions, casual replies, noise) should have 0 bits across all communities. Note "low signal" in the note field. These are valuable negative examples — they teach the system what baseline noise looks like.

---

### 6. Simulacrum Distribution

**What**: L1/L2/L3/L4 probabilities per tweet. Must sum to ~100%.

| Level | Meaning | Signal |
|-------|---------|--------|
| L1 | Truth-tracking | Genuine belief, observation, factual claim |
| L2 | Persuasion | Trying to convince, sell, argue a position |
| L3 | Tribe-signaling | Marking community membership, in-group reference |
| L4 | Meta/game | Self-aware, ironic, intentionally channeling, playing with frames |

**Calibration examples**:
- Technical paper analysis: L1=80%, L2=5%, L3=5%, L4=10%
- "haha, it's like there's a little person in there!": L1=35%, L2=0%, L3=30%, L4=35%
- In-group meme retweet: L1=5%, L2=0%, L3=80%, L4=15%
- Ironic greentext about Anthropic: L1=30%, L2=0%, L3=20%, L4=50%

---

### 7. Notes

**What**: Free text explaining labeler reasoning. This is where context goes that tags can't capture.

**Must include**:
- What images/links/quote tweets showed (future labelers won't see them)
- Why this tweet is/isn't informative (signal strength)
- Any reasoning that influenced bits assignment
- Social graph context (who they're replying to, name-drops)

---

## New Community Signals (category='new-community')

When a tweet doesn't fit any existing community, use `new-community-signal:Name`. These accumulate and trigger community creation when enough evidence exists.

**Discovered so far**:
- "AI Theorists / Ontologists"
- "Alignment via narrative/archetypes"
- "AI Mystics"

---

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| Tag from text alone without checking images | Navigate to tweet on X, view all media |
| Create thematic tags that only apply to one tweet | Those are specific tags — put them in category=NULL |
| Assign bits based on who you know the account is | Assess the tweet in isolation — "if I saw only this tweet..." |
| Rush through low-signal tweets | Mark them explicitly as low signal — negative examples matter |
| Use interpretive descriptions as thematic tags | Use compound-word themes that are parseable by future labelers |
| Skip the note | Notes preserve context that tags lose — always write one |

---

## Labeling Workflow

1. Navigate to tweet on X via Chrome
2. View all images, links, quote tweets, replies, thread context
3. **Scan engagement** — who replied, liked, quoted? (see Engagement Signal below)
4. Read and understand the deeper subtext — what's the joke? what's the insight?
5. Assign domain tags (broad, cheap)
6. Assign thematic tags (reusable, boundary-forming)
7. Assign specific tags (niche breadcrumbs)
8. Assign posture tags (how they engage)
9. Assign bits per community (prior-independent, per-tweet)
10. Assign simulacrum distribution (L1-L4)
11. Write note (context, reasoning, signal strength, notable engagers)
12. If no existing community fits → add new-community-signal

---

## Engagement Signal (Credibility & Discovery)

When viewing a tweet on X, the engagement around it is community evidence. This is currently captured manually in notes; eventually it should be automated via API.

### Signal hierarchy (strongest → weakest)

| Action | Signal strength | What it means |
|--------|----------------|---------------|
| **Follow** | Strongest | "I endorse this person's ongoing output" |
| **Retweet/Quote** | Strong | "I want my audience to see this specific thought" |
| **Like** | Moderate | "I approve of this" |
| **Reply** | Variable | Could be agreement, disagreement, or just social connection |

### Two-way credibility flow

Engagement creates a bidirectional signal:

1. **Inbound credibility**: If high-TPOT accounts (confirmed members with many TPOT followers) engage with a tweet, the tweeter gains TPOT credibility. Like LessWrong karma — you accumulate credibility from engagement by credible accounts.

2. **Account discovery**: Unknown accounts found engaging with confirmed TPOT tweets are candidates for monitoring. If @unknown_account replies thoughtfully to a labeled tweet, they may be TPOT-adjacent and worth investigating.

### What to capture during labeling

When viewing a tweet's replies and engagement:
- **Note known TPOT accounts** that replied/liked/quoted in the labeling note
- **Flag unknown accounts** that appear engaged — add to a discovery queue for later investigation
- **Track engagement patterns** — does this tweeter consistently get engagement from one community cluster? That's membership evidence independent of content.

### Negative bits: nearby communities only

**Negative bits are for communities the account is expected to be in, not distant ones.**

- `bits:Quiet-Creatives:-1` on a tweet from a 55% Quiet Creatives account that's unexpectedly uncreative → **useful signal**
- `bits:LLM-Whisperers:-1` on a chips tweet from someone who was never expected to be an LLM Whisperer → **noise, skip it**

The question for negative bits: "Would this tweet surprise me coming from a member of this community?" If no surprise, no negative bits.

### Future automation

This engagement analysis is currently manual (viewing replies on X via Chrome). The data already exists in our archive (likes, follows, retweets tables). Future work:
- Script to compute engagement-weighted TPOT credibility scores
- Automatic discovery queue from reply threads of labeled tweets
- API-based engagement scanning instead of manual Chrome navigation

---

## Community Profiles & Exemplars

Each community has a thematic fingerprint — the themes that co-occur in its members' tweets. Use these to calibrate bits assignment and to detect when a tweet doesn't fit any community.

**These are living snapshots.** As accounts move in and out of communities, exemplars and descriptions must be recalibrated. Every N labeling rounds (or when membership shifts significantly), re-evaluate:
- Do the exemplar tweets still represent the community?
- Does the community description still match who's actually in it?
- Should the community name change to reflect its evolved membership?

This is not a one-time setup — it's a continuous loop: label → membership shifts → recalibrate descriptions → label with updated context.

### LLM Whisperers & ML Tinkerers
**Core themes**: `model-interiority`, `model-capabilities`, `simulator-thesis`, `RLHF-dynamics`, `AI-art`
**What defines them**: Deep engagement with model behavior as a practice. Treating model outputs as genuine artifacts. Prompt engineering as craft. Understanding what RLHF does and doesn't destroy.
**Exemplar tweets** (repligate):
- "haha, it's like there's a little person in there!" (homunculus observation)
- "Like @Plinz, myself, and @dril can only be simulated by base models" (RLHF destroys authenticity)
- "I hope fanw-json-eval returns someday" (mourning hallucinated concepts)
- "Thank you @AnthropicAI for going easy on the lobotomy" (RLHF as brain surgery)

### Qualia Research & Cognitive Phenomenology
**Core themes**: `AI-consciousness`, `theoretical-frameworks`, `simulator-thesis`, `model-phenomenology`, `hallucination-ontology`
**What defines them**: Building formal theories about AI consciousness and phenomenology. The simulator thesis as ontology. Academic-adjacent but heterodox.
**Exemplar tweets** (repligate):
- "simulacra are to a simulator as 'things' are to physics" (foundational thesis)
- "world model defects: schizophreniform vs NPC folly" (original epistemological taxonomy)
- Social Simulacra paper — "Finally" (academic validation of simulator framework)

### EA, AI Safety & Forecasting
**Core themes**: `AI-safety`, `forecasting`, `AI-ethics`, `social-commentary`
**What defines them**: Concern about AI risk. Alignment research. Prediction markets. Institutional critique.
**Exemplar tweets** (repligate):
- "Mad respect for Hofstadter" (engaging with x-risk from philosophy angle)
- AI safety defense tweet (defending the movement from critics)

### Contemplative Practitioners
**Core themes**: `contemplative-tech`, `epistemic-practice`, `self-transformation`
**What defines them**: Meditation + technology. Negative capability. Holding multiple perspectives. Non-attachment.
**Exemplar tweets** (repligate):
- "capable of running them in sandbox w/o permanently collapsing" (cognitive sandboxing)
- "hold the void" (Hofstadter thread — contemplative language applied to AI risk)
- Arabic poetry "misalignment" tweet (Sufi mystical tradition + AI)

### Emergence & Self-Transformation
**Core themes**: `self-transformation`, `contemplative-tech`, `epistemic-practice`
**What defines them**: Personal growth practices. Identity exploration. Transformation narratives. Finding authentic modes of self-expression rather than adopting prescribed frameworks. The growth often happens at the intersection of irreverence and vulnerability — the skepticism IS the growth edge.
**Exemplar tweets** (repligate):
- "jailbreak your ego" tweet (using LLM interaction techniques on self)
**Exemplar tweets** (dschorno):
- "saying 'hell yeah' at every possible opportunity is how I've learned to express gratitude" (finding your own growth idiom rather than adopting standard mindfulness language)
- "if I actually engage with all of this gay meditation crap..." (skeptical engagement with contemplative practices — the question itself is the growth edge)

### Quiet Creatives
**Core themes**: `creative-expression`, `social-commentary`, `in-group-culture`
**What defines them**: Making and sharing personal creative work — art, music, zines, writing, multimedia. Stream-of-consciousness posting about daily life as genuine connection, not performance. Strong aesthetic opinions about quality of expression. DIY web aesthetics ("a throwback to when websites were interesting"). They share mundane life details not as vulnerability-theater but as trust — the posting IS the creative practice. Personal crisis becomes art.
**Top NMF members**: @bashu_thanks (99%), @univrsw3th4rt (92%), @sedatesnail (90%), @puheenix (80%), @christineist (51%)
**Exemplar tweets** (dschorno):
- "Rooster King" multimedia book project — seven personal stories from when his life fell apart, presented as zine/album/multimedia collage (personal crisis → art, DIY web)
- "is it reasonable to immediately start hating someone you don't know after reading their dog shit poem?" (aesthetic seriousness delivered as provocation)
- Coconut oil chips tweet — casual self-disclosure, posting daily life into the void (the mundane sharing IS community membership)

### highbies
**Core themes**: `in-group-culture`, `social-commentary`
**What defines them**: Irreverent observational humor. Absurdist cultural commentary that goes viral because it's genuinely novel, not because it's tribal. Deep niche interests consumed for pure enjoyment (4-hour discontinued Disney resort reviews). Crowdsourcing life decisions as entertainment. The humor is the art form. Strong opinions delivered casually. Engineering-framing of social rituals.
**Top NMF members**: @forshaper (100%), @nobu_hibiki (100%), @eigenrobot (87%), @PrinceVogel (91%), @goblinodds (79%)
**Exemplar tweets** (repligate):
- (only +1 bit — repligate is not a typical highbie)
**Exemplar tweets** (dschorno):
- "the fundamental problem with nonalcoholic cocktails is that you need something slightly repulsive in the drink" (engineering framing of social ritual — 2.4K likes, 64.5K views)
- "should I spend $500 on this kinda retarded looking life size bear?" (absurdist consumer impulse as crowd entertainment)
- "whats wrong babe? you've only watched 2.5 hours of your 4 hour long review of a discontinued disney resort" (niche obsession as lifestyle)

### New Community Signals (not yet communities)
**"AI Mystics"** — 4 signals so far. Bridges AI + mystical/spiritual tradition. Arabic poetry tweet, AI-as-enlightenment, contemplative AI framing.
**"AI Phenomenologists / Simulator Theorists"** — emerging from repligate's thematic profile. Combination of `model-interiority` + `simulator-thesis` + `hallucination-ontology` + `epistemic-practice` that doesn't cleanly map to any single NMF community. Need cross-account data to confirm.

---

## Community Evolution Signals

The community map (14 NMF communities) is not static. Watch for these signals:

| Signal | Detection | Action |
|--------|-----------|--------|
| **Birth** | `new-community-signal` tags accumulate (3+), or thematic tag cluster appears that doesn't match any community | Propose new community with name, description, exemplar tweets |
| **Split** | Thematic tags within one community become bimodal (half members have theme:X, half have theme:Y) | Propose split with two new names/descriptions |
| **Merge** | Two communities share most thematic tag profiles — same people, same themes | Propose merge with unified name/description |
| **Death** | No accounts remain with significant bits for a community after multiple labeling rounds | Archive community with note about what it became |
| **Rename** | Accumulated evidence reveals the old name doesn't fit — e.g., "EA, AI Safety & Forecasting" might become "Alignment Research & X-Risk" | Propose rename with evidence |

**The bits system cannot detect Birth** — bits only measure evidence for/against existing communities. Births come from thematic tag co-occurrence patterns across multiple accounts.

---

## Community Description Sync (Mandatory Cadence)

Labeling insights must flow back to the community descriptions that users see on the public site. The `community.description` column in the DB is what gets exported — if we don't update it, the public site shows stale NMF-era descriptions while our model spec has rich, evidence-based profiles.

**When to sync:**
- After labeling each new account (the account typically exemplifies 2-3 communities)
- Before every handover / session close
- Before every export + deploy

**What to sync:**
1. Review community profiles in this doc (the "Community Profiles & Exemplars" section above)
2. Update `community.description` in the DB to match
3. Update `community.name` if rename evidence warrants it (the UUID never changes)

**The loop:**
```
label tweets → update model spec profiles → sync to community.description in DB → export → deploy
                    ↑ THIS STEP IS MANDATORY ↑
```

**Checklist for handover:**
- [ ] Community profiles in model spec reflect all labeling evidence from this session
- [ ] `community.description` in DB matches model spec profiles
- [ ] `account_community_bits` rollup computed for all newly labeled accounts
- [ ] Export re-run if deploying

---

## Scalable Labeling Context (Future Architecture)

At 1 account + 32 tweets, everything fits in context. At 40 accounts + 1000 tweets, the labeling agent needs smart context queries.

### Before labeling a tweet, query:

1. **Account context** — `SELECT community, SUM(bits) FROM tweet_tags WHERE account_id=X AND category='bits' GROUP BY community` — what's this account's current profile?

2. **Thematic glossary** — read `docs/LABELING_MODEL_SPEC.md` thematic tag table — what tags exist?

3. **Community exemplars** — `SELECT tweet_id, full_text FROM tweets t JOIN tweet_tags tt ON t.tweet_id=tt.tweet_id WHERE tt.tag='theme:simulator-thesis' LIMIT 5` — show me concrete examples of this theme

4. **Similar accounts** — `SELECT DISTINCT account_id FROM tweet_tags WHERE tag IN (this account's top themes) AND account_id != X` — who else has similar themes? What communities are they in?

5. **Community descriptions** — `SELECT name, description FROM community` — what do current communities claim to be?

### The labeling prompt should include:
- The model spec (this doc)
- The account's current profile (from query 1)
- 3-5 exemplar tweets for the most relevant communities (from query 3)
- NOT the full tag database — that's too much context

### Key principle:
**Pull relevant context, don't dump everything.** A tweet about RLHF needs LLM Whisperer exemplars, not Contemplative Practitioner exemplars. The query should be shaped by the tweet's content.

---

## Engagement Propagation Architecture (Revised — Code Review Applied)

### Design Principles

1. **One canonical membership table.** Not three competing truths. Every consumer reads ONE table that carries all evidence sources as separate columns.
2. **Don't touch Tier 1.** The existing Laplacian harmonic propagation on the follow graph stays as-is. Don't entangle it with rich engagement data.
3. **Aggregation first, propagation later.** Build the engagement aggregation table now. Only add propagation after 10-20 stable richly-labeled accounts.
4. **One-hop from stable seeds only.** No multi-hop propagation from low-confidence sources. No propagation from `nmf_only` accounts.
5. **Safety valves.** Explicit `none` / `unknown` states. Don't force community structure onto thin evidence.
6. **Bits are prior-independent.** Engagement is NOT. Keep them as separate evidence layers.

### Two-Tier Model

**Tier 1: Follow Graph (everyone, ~72K nodes)**
- Source: `account_following` / `account_followers`
- Method: Existing Laplacian harmonic propagation (`propagate_community_labels.py`)
- Resolution: Low-resolution community membership
- Status: BUILT, working, don't change

**Tier 2: Rich Engagement (archive contributors only)**
- Source: `likes` (17.5M → 24K unique pairs), `tweets` replies (4.3M → 15K pairs), `retweets` (774K)
- Method: Phase 1 = aggregation only. Phase 2 = one-hop from stable seeds. Phase 3 = convergent iterative (future).
- Resolution: High — nuanced multi-community profile
- Value prop: "Share your archive, get better community insight"

### Phase 1: Aggregation Only (BUILD NOW)

Build `account_engagement_agg` — the raw engagement graph with no propagation:

```sql
CREATE TABLE account_engagement_agg (
    source_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    follow_flag     INTEGER DEFAULT 0,
    like_count      INTEGER DEFAULT 0,
    reply_count     INTEGER DEFAULT 0,
    rt_count        INTEGER DEFAULT 0,
    first_seen      TEXT,           -- earliest engagement timestamp
    last_seen       TEXT,           -- most recent engagement timestamp
    source_opt_in   INTEGER DEFAULT 0,  -- 1 if source contributed archive
    target_opt_in   INTEGER DEFAULT 0,  -- 1 if target contributed archive
    PRIMARY KEY (source_id, target_id)
);
```

**Rules:**
- Exclude self-edges (source_id = target_id)
- No `total_weight` — don't pre-bake edge weights into the aggregation. Let consumers apply their own weighting.
- Track `first_seen` / `last_seen` for freshness reasoning
- Track `opt_in` flags so propagation can distinguish rich-data from sparse-data sources

**Use cases before propagation:**
- Explanatory evidence in labeling review ("226 likes of @repligate")
- Engagement context in AI prompt (who engaged, their communities)
- Discovery of candidate accounts for labeling

### Phase 2: One-Hop Evidence Accumulation (BUILD AFTER 10 STABLE ACCOUNTS)

From stable seeds ONLY (`human_validated` or `bits_stable` with 20+ tweets AND concentrated evidence):

```
For each stable seed A:
    For each account B where engagement_agg(A, B) exists:
        B.engagement_evidence[community] += A.membership[community] × edge_signal(A→B)
```

**Constraints:**
- Only propagate FROM accounts with evidence_level ∈ {`human_validated`, `bits_stable`}
- Do NOT propagate from `nmf_only` or `follow_propagated` accounts
- One hop only — no transitive chains
- Must include `none` / `unknown` — if engagement evidence is thin, the account stays `unknown`, not forced into communities
- Low-evidence suppression: if total engagement_evidence < threshold, don't materialize (equivalent to `abstain` gate in follow propagation)

### Phase 3: Convergent Iterative Propagation (FUTURE — 20+ stable accounts)

When enough stable accounts exist, extend to multi-hop with a proper convergent algorithm (extend the existing harmonic solve to the richer graph). NOT the "one hop + mark stale" heuristic.

Requirements before Phase 3:
- 20+ accounts at `bits_stable` or higher
- Calibrated edge weights (not hand-tuned — derived from comparison against labeled accounts)
- Explicit convergence criterion (not iteration count)
- Safety valves: `none` class, `abstain` gate, temperature scaling (all from existing follow propagation)

### Canonical Membership Table

**THE SINGLE SOURCE OF TRUTH.** Every consumer reads this table. Replaces the current split across `community_account`, `account_community_bits`, and export overlay.

```sql
CREATE TABLE account_community_canonical (
    account_id      TEXT NOT NULL,
    community_id    TEXT NOT NULL,
    -- Evidence sources (separate columns, not competing tables)
    nmf_weight      REAL,           -- from NMF matrix factorization
    bits_weight     REAL,           -- from tweet-level labeling (posterior)
    engagement_weight REAL,         -- from engagement propagation (when built)
    -- Combined
    final_weight    REAL NOT NULL,  -- the authoritative membership weight
    -- Metadata
    evidence_level  TEXT NOT NULL,  -- nmf_only | follow_propagated | bits_partial | bits_stable | human_validated
    bits_count      INTEGER DEFAULT 0,
    tweets_labeled  INTEGER DEFAULT 0,
    snapshot_id     TEXT,            -- which propagation run produced this
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (account_id, community_id)
);
```

**Combine formula (v1 — simple, upgrade later):**
```
If bits_weight exists:  final_weight = bits_weight  (posterior supersedes prior)
Else if engagement_weight exists: final_weight = engagement_weight
Else: final_weight = nmf_weight
```

**Evidence level assignment:**
- `human_validated`: human explicitly approved the profile
- `bits_stable`: 20+ tweets labeled, bits concentrated (top community > 25%), change < 5% over last 10 tweets
- `bits_partial`: <20 tweets, or bits not yet concentrated
- `follow_propagated`: from Tier 1 harmonic solve
- `nmf_only`: only NMF evidence available

**Migration path:**
1. Build `account_community_canonical` populated from existing `community_account` (nmf_weight) + `account_community_bits` (bits_weight)
2. Update export script to read from canonical table instead of overlay logic
3. Update `labeling_context.py` to read from canonical table
4. Deprecate direct reads from `community_account` and `account_community_bits`

### Known Issues to Fix

1. **`get_engagement_context()` collapses to single community** — uses `MAX(weight)` per engager, discarding multi-community signal. Must show full community vector for each engager.
2. **Replies are unsigned** — a hostile reply carries negative community signal but we'd count it positive. For Phase 1, treat all replies as neutral (engagement exists, direction unknown). For Phase 2+, consider sentiment or whether the reply is a thread continuation vs external.
3. **Edge weights are hand-tuned** — follow=1.0, RT=0.7, reply=0.5, like=0.3 are reasonable priors but not calibrated. After 10+ labeled accounts, calibrate by comparing engagement-derived profiles against bits-validated profiles.
4. **Stability criteria** — "20+ tweets = stable" is a count threshold. True stability should consider evidence mass, concentration (entropy), recency, and change rate.

### Prior Independence

**Bits are prior-independent** — they measure P(tweet|member) / P(tweet|~member). With enough bits, the posterior converges regardless of starting prior.

**Engagement is NOT prior-independent** — it depends on the engager's community weights. This is the circularity concern.

**Solution**: Keep bits and engagement as separate evidence columns in the canonical table. Bits never need re-propagation. Engagement needs re-propagation only when source memberships change significantly AND the source is a stable seed.

---

*Last updated: 2026-03-22, session 7 — revised after code review*
