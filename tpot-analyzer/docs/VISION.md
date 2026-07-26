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

This project uses **living ideas** and **egregores** as interpretive metaphors.
The empirical work is narrower: map observable patterns in public content and
interaction, test whether those patterns help people discover communities, and
preserve alternative explanations when they do not.

TPOT is a useful entry point because it is bounded enough to study carefully,
rich enough to be interesting, and contains unusually self-referential public
language about memes, in-groups, irony, and participation.

---

## Applied Mission — Finding People for Niche Coordination

This project maps overlapping niche subcultures in public online discourse so
talent-constrained community-building projects can discover potential
collaborators whom ordinary marketing and keyword search miss. Examples include
local and open-source LLM builders, forecasters, interface designers,
second-brain practitioners, and people seriously engaged with contemplative
practice.

The product should return evidence-backed candidate hypotheses, not a ranking
of human worth:

- likely affiliation with a user-defined community;
- observable domain-relevant contribution or competence;
- explicitly expressed interest in participating;
- the evidence coverage and provenance behind each inference; and
- uncertainty, ambiguity, and plausible alternative interpretations.

These are separate quantities. Community affiliation does not prove competence;
fluent discourse does not prove achievement; public interest does not prove
availability.

The map is a discovery aid for human community builders. It is not an automated
hiring system, psychological diagnosis, sensitive-identity inference, or
outreach/spam engine. Its job is to make promising evidence inspectable and help
a human decide where further investigation is worth the time.

---

## Why Graph Structure Alone Fails

The naive approach: build a follow graph, cluster by mutual connections, call those communities.

This is insufficient for TPOT because a structurally nearby account may be a
participant, observer, critic, or journalist. Authored content and interaction
context may distinguish these cases, but that incremental value is a
falsifiable hypothesis rather than a premise.

One candidate signal is how public language functions in context. It must be
tested against simpler graph, topic, and embedding baselines.

---

## The Simulacrum Levels — A Research Construct

We annotate tweets on a four-level axis as a provisional description of how a
message functions in its observed context:

- **L1 — The Map**: Saying something because it's true. Truth-tracking. If they discovered they were wrong, they'd stop saying it.
- **L2 — The Persuasion**: Saying something to induce a belief or behavior. Audience-tracking. Would say the opposite if it served the goal.
- **L3 — The Signal**: Saying something to show which tribe you belong to. Tribe-tracking. Would say it even if false. The egregore speaking through the individual.
- **L4 — The Simulacrum**: The message appears dominated by a circulating
  cultural pattern rather than a locally inspectable truth claim.

This taxonomy can be useful only as an uncertain, context-dependent annotation
of public messages. It is not a measurement of private intent, agency,
intelligence, developmental attainment, or a person's fixed psychological
stage. Claims that it predicts community membership better than simpler content
or graph baselines remain hypotheses to be tested on held-out labels.

Full theory: `docs/specs/simulacrum_taxonomy.md`

---

## The Post-Irony Gap (Key Open Question)

TPOT's signature mode doesn't fit cleanly into L1-L4. It's something like: *"I'm channeling the egregore, we all know it, and our shared awareness of the channeling is itself the authentic signal."* Simultaneously sincere and ironic. The tribe-signal IS the genuine expression.

This may be a useful diagnostic signal, but the taxonomy does not yet capture
it reliably. Its incremental value is an open classification question.

---

## The Four-Part Evidence Architecture

1. **Versioned event substrate:** preserve public observations, direction,
   timestamp, source, and provenance. The substrate grows; each evidence
   snapshot is immutable and addressable.
2. **Typed views:** derive separate authored-content, engagement, graph,
   profile, artifact, and temporal-context views. They are not collapsed into
   one supposedly universal edge or fingerprint.
3. **Observable descriptors:** extract topics, entities, stance, functional
   message annotations, and evidence spans without giving the extractor graph
   communities or user labels. Descriptors are recomputed when evidence,
   preprocessing, model, prompt, or schema identity changes.
4. **User-scoped task heads:** fit separate affiliation, observable competence,
   and publicly expressed participation-interest estimates for a versioned
   ontology. Graph is available here as its own typed view; coverage and
   provenance condition the estimates rather than becoming a hidden target.

Group affinities overlap independently rather than being forced to sum to one.
Message style remains a separately versioned descriptor, and evidence coverage
remains observed metadata. Every user owns an immutable, superseding history of
judgments over versioned evidence.

The math proposes structure. Humans define what a boundary means. The meaning
is personal and contingent, not global or permanent.

---

## The Data

The corpus and graph are mutable observations with different freshness and
coverage. Counts do not belong in this vision document. Current identities,
cutoffs, coverage, and known gaps are recorded in `docs/DATA_INVENTORY.md`,
versioned Community Archive manifests, and the experiment documents indexed by
`docs/index.md`.

Community Archive evidence is exhausted and deduplicated before paid
acquisition. Stored follows, followers, likes, retweets, replies, quotes,
mentions, co-follows, authored content, and temporal context remain typed rather
than being treated as interchangeable edges.

TwitterAPI.io is used only for missing evidence whose expected development-set
value justifies its monetary and human-review cost. Local-first inference is
the target policy, contingent on the planned benchmark. Current generation
paths still include OpenRouter and serverless calls; any remote action must be
explicit, disclose the complete outbound payload, and produce an egress receipt.
Static lookup and local research should not require remote inference.

---

## What's Built

- Community archive fetcher with retry, streaming, atomic cache (`src/archive/`)
- Thread context fetcher with local cache — never pays for the same tweet twice (`src/archive/thread_fetcher.py`)
- Simulacrum taxonomy document (`docs/specs/simulacrum_taxonomy.md`)
- Machine-readable taxonomy YAML with golden examples (`data/golden/taxonomy.yaml`)
- Typed directed graph signals, immutable account/tweet judgments, deterministic
  train/dev/test splits, provenance manifests, and human-facing verification
  scripts
- An experimental LM-Studio-compatible embedding script; reproducible local
  generation/extraction is not yet integrated or benchmarked
- Architecture decision records (`docs/adr/`)

## What's In Progress

- Correcting the membership semantics and solver assumptions falsified by the
  2026-07-26 audit
- Growing explicit positive, negative, and abstain judgments without exposing
  the sealed test set
- Replacing heuristic acquisition ranking with budgeted, falsifiable
  value-of-information experiments

## What's Next

- Local-first, graph-blind structured evidence extraction
- Independent overlapping affinity and competence heads
- A dossier-based blind-review interface with immutable corrections
- Offline mask/reveal comparison against random and existing heuristics
- A small paid acquisition microtrial only after the offline policy earns it

## The Learning Flywheel

Human attention is a budget alongside dollars and compute. The interface should
surface a compact evidence dossier, allow investigation and save/resume, and
hide model suggestions until the human has recorded an initial judgment.

After each judgment, the system should show an honest before/after account:
the prior prediction, realized surprise, posterior change, affected candidate
rankings, and change on the development set. The sealed test set is evaluated
once, after every choice for that run is final. A correction creates a new
judgment that supersedes rather than erases the old one, preserving ontology
version, evidence/context hash, timestamp, and notes.

Sometimes the truthful result is “this label did not improve the model.” The
product should show that rather than manufacturing progress.

---

## Distribution and Publication Boundary

Power users shape local, personal ontologies; casual users may inspect only
explicitly approved snapshot fields. Local-first does not mean local-only, and
public evidence does not make private dossiers or sensitive inferences
publishable. The current product flow, remote-egress disclosure, static-snapshot
semantics, and field-level boundary live in
`docs/product/2026-07-26-publishing-and-privacy-boundary.md`.

---

## The Deeper Question

This project started with "where does TPOT end?"

The better question is: **what egregores are operating here, what is their territory, and what is their relationship to each other?**

The hoped-for result is not just a social-network partition. It is an
inspectable, revisable map of how public ideas, practices, and collaborations
co-occur—without claiming access to private awareness or choice.

Every tweet is a vote on which spirit gets to exist.
