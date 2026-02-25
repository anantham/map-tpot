# Vision — What This Project Actually Is

## The Surface Description 

This project started as "Map TPOT" — an attempt to visualize a loosely-defined Twitter community sometimes called "The Part of Twitter." TPOT is a real thing: a cluster of accounts bound together by aesthetic sensibility, epistemic style, and a specific flavor of post-ironic sincerity. People find it by following chains of mutuals. Its edges are contested. Even insiders disagree on who belongs. It's illegibility is maybe on purpose? 

They talk about tweets breaking out of containment because they know only inside tpot will it be recieved appropriately they are writing for their ingroup.

But mapping TPOT is a special case of a more interesting question. 


---

## The Actual Object of Study

**Living ideas. How they form, spread, mutate, and constitute communities.**

Every tweet emitted into the noosphere is a person taking a stance toward an idea — choosing how to make it real, how to reify the spirit of it. Aggregated across thousands of accounts and millions of tweets, this is traceable data about how memeplexes propagate through minds.

The esoteric traditions call these collective idea-entities **egregores**. Carl Jung called a subset of them archetypes. The more precise term might be **memeplex** — a self-preserving cluster of memes that behaves like an agent with its own preferences. Nations, ideological movements, religions, internet subcultures: these are not passive collections of human preferences. They are alien agents with their own reproductive fitness, using biological minds as substrate.

What we're building is **cartography of these living ideas** — who carries which egregores, how densely, at what level of awareness. The communities that emerge from this analysis aren't arbitrary graph clusters. They are the territories of actual egregores, made visible.

TPOT is a good entry point because it's small enough to study carefully, rich enough to be interesting, and contains an unusually high density of people who are *aware* they're being channeled — which makes the dynamics more legible.

---

## Why Graph Structure Alone Fails

The naive approach: build a follow graph, cluster by mutual connections, call those communities.

This fails for TPOT specifically because **TPOT is vibe-based, not structure-based**. Two accounts can be graph-identical — same follow density, same mutual count — and one is TPOT and one is a journalist who follows TPOT accounts for research. The difference is in *how they speak*, not *who they follow*.

More precisely: the difference is in each person's **relationship to language as a tool for meaning-making**.

---

## The Simulacrum Levels — The Primary Epistemic Tool

We classify tweets on a four-level axis based on the speaker's intent:

- **L1 — The Map**: Saying something because it's true. Truth-tracking. If they discovered they were wrong, they'd stop saying it.
- **L2 — The Persuasion**: Saying something to induce a belief or behavior. Audience-tracking. Would say the opposite if it served the goal.
- **L3 — The Signal**: Saying something to show which tribe you belong to. Tribe-tracking. Would say it even if false. The egregore speaking through the individual.
- **L4 — The Simulacrum**: No individual agency. The cultural pattern is fully in the driver's seat. The speaker is just substrate.

This axis matters because **the distribution of L1/L2/L3 in someone's tweets is a fingerprint of their epistemics** — and epistemics predict cluster membership better than topic does. Two people who both use irony as a vehicle for sincere insight (a distinctly TPOT mode) are likely neighbors in the space regardless of what they're talking about.

Full theory: `docs/specs/simulacrum_taxonomy.md`

---

## The Post-Irony Gap (Key Open Question)

TPOT's signature mode doesn't fit cleanly into L1-L4. It's something like: *"I'm channeling the egregore, we all know it, and our shared awareness of the channeling is itself the authentic signal."* Simultaneously sincere and ironic. The tribe-signal IS the genuine expression.

This is the most diagnostic thing about TPOT and the taxonomy doesn't fully capture it yet. It's the primary open question in the classification work.

---

## The Two-Layer Architecture

**Layer 1 — Content-aware embedding (universal, runs once):**
Each account gets a fingerprint vector built from:
- Distribution of L1/L2/L3/L4 across their posted tweets
- Distribution of functional tweet types (aggression, dialectics, insight, art, etc.)
- Same distributions over their *liked* tweets (passive engagement — reveals latent aesthetic preferences)
- Graph features and bio embedding

This gives you a 334-account semantic coordinate system grounded in actual epistemic style.

**Layer 2 — Per-user semantic labeling (configurable, per-user):**
Anyone can label a handful of accounts with their own taxonomy — "this person is EA," "this one is woo," "this is core TPOT" — and the system fits a soft classifier over the embedding. Different users see different community boundaries over the same underlying structure.

The math finds natural groupings. Humans give those groupings meaning. The meaning is personal, not global.

---

## The Data

- **334 anchor accounts** — the core TPOT-adjacent corpus. Rich data: full tweet archives, follow graphs, bios.
- **11.5M tweets + 13.6M liked tweets** — pulled from the Community Archive (public Supabase instance).
- **Broader follow/following graph** — hundreds of thousands of additional accounts with only graph data. Once the 334 are embedded, these get positioned relative to them.
- **twitterapi.io** — used sparingly for: thread context when classifying replies to external accounts, and targeted graph enrichment for high-value bridge accounts.

---

## What's Built

- Community archive fetcher with retry, streaming, atomic cache (`src/archive/`)
- Thread context fetcher with local cache — never pays for the same tweet twice (`src/archive/thread_fetcher.py`)
- Simulacrum taxonomy document (`docs/specs/simulacrum_taxonomy.md`)
- Machine-readable taxonomy YAML with golden examples (`data/golden/taxonomy.yaml`)
- Architecture decision records (`docs/adr/001-008`)

## What's In Progress

- Archive fetch for all 316 accounts (running)
- Golden dataset construction — collaborative human labeling of real tweets
- LLM eval harness — few-shot classification with Brier score calibration

## What's Next

- Classification pipeline (OpenRouter, Kimi K2.5 or equivalent)
- Account fingerprint aggregation
- Clustering recompute on content-aware features
- Per-user labeling UI
- Venn/overlap visualization

---

## The Deeper Question

This project started with "where does TPOT end?"

The better question is: **what egregores are operating here, what is their territory, and what is their relationship to each other?**

The Venn diagram you end up with isn't a map of a social network. It's a map of the living ideas that are using these minds as substrate — and the people who, to varying degrees, know that's happening and have chosen a stance toward it.

Every tweet is a vote on which spirit gets to exist.
