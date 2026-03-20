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

## Distribution: How This Reaches Users

### Two User Types

**Power users** clone the repo, feed their own API keys, and run the full pipeline locally. They label tweets, shape community boundaries, name their clusters, and produce a personal ontology of their corner of Twitter. The labeling UI, classification pipeline, and clustering tools are all local-first — computation happens on your machine, data stays on your disk. A power user IS the admin of their own instance.

**Casual users** visit a published URL and type their Twitter handle. They see where they sit in the power user's community map — soft membership percentages across named communities. No account needed, no API keys, no local setup. Just curiosity and a handle.

### The Casual User Experience

The MVP experience is a lightweight static site (Vercel or equivalent). The flow:

1. **Landing page** — search bar. "Find your ingroup."
2. **Type your handle** — instant client-side lookup against a pre-computed static JSON index.
3. **Results card** — soft community placement as percentage bars with human-curated community names. "80% Post-rationalist, 15% AI Safety, 5% Woo." Provocative-by-design — the labels are part of the appeal.
4. **Downloadable PNG** — "Share your card" button generates a screenshot-ready image client-side (canvas-to-PNG, zero server cost). This is the viral mechanic.
5. **"Explore the map" link** — optional deeper view. A simplified cluster visualization showing the user's position in the full community landscape. Heavier to load, but available for the curious.

**If the handle isn't found:** a banner with three paths to get included:
- DM the power user directly (fastest — they add your data to their local pipeline)
- Upload your Twitter data export to the [Community Archive](https://github.com/community-archive) (benefits the whole community)
- Clone the repo and become a power user yourself

This creates a **growth flywheel**: people want to see their results, so they contribute their data. The power user periodically re-fetches the latest community archive accounts and re-publishes with an expanded index.

### The Publishing Workflow

All computation happens locally. Publishing is just exporting the results:

1. Power user runs the full pipeline locally: labeling, classification, clustering, community naming
2. A build step exports the results as **static JSON** — every account's community membership scores, community metadata (names, colors, descriptions), and a simplified cluster layout for the map view
3. The static site (a lightweight React/Vite app) ships with this JSON baked in. Client-side lookup, client-side rendering, client-side PNG generation. Zero backend in production.
4. Deploy to Vercel/Netlify/GitHub Pages. Cost: free or near-free.
5. To update: re-run the pipeline with new data, re-export, re-deploy.

The published site is a **read-only snapshot** of the power user's analysis at a point in time. It does not connect to any backend, database, or API. The full research tools (labeling UI, LLM interpretation, branch management) stay local-only.

### Open Source Strategy

**Current model (v1):** One repo, framework and data bundled. Someone who clones it gets the tool AND the specific TPOT analysis (community labels, graph snapshots, golden dataset). They can fork and modify, run their own labeling, publish their own version.

**Future model (if demand exists):** Separate the framework (the pipeline, the UIs, the static site generator) from the data (a specific power user's community ontology). The framework becomes a reusable tool; each power user maintains their own data repo. This separation happens only if multiple people actually want to run their own analyses — premature abstraction otherwise.

### What Gets Published vs What Stays Local

| Artifact | Published (static site) | Local only (power user) |
|----------|------------------------|------------------------|
| Community names + colors | Yes | Yes |
| Account membership scores | Yes (pre-computed JSON) | Yes (live in SQLite) |
| Simplified cluster layout | Yes (for map view) | Yes (full spectral data) |
| Account handles + display names | Yes (public Twitter data) | Yes |
| Tweet text / labels / golden dataset | No | Yes |
| Labeling UI | No | Yes |
| LLM interpretation | No | Yes |
| Branch management | No | Yes |
| Classification pipeline | No | Yes |
| API keys / secrets | No | Yes (in .env) |

---

## The Deeper Question

This project started with "where does TPOT end?"

The better question is: **what egregores are operating here, what is their territory, and what is their relationship to each other?**

The Venn diagram you end up with isn't a map of a social network. It's a map of the living ideas that are using these minds as substrate — and the people who, to varying degrees, know that's happening and have chosen a stance toward it.

Every tweet is a vote on which spirit gets to exist.
