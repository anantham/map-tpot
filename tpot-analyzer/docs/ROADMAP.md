# Roadmap

Public methodology/source edition, 20 October 2026. This board describes code
capabilities and remaining research, not the contents of a private dataset.

## Current bounded slice: clean publication

| Item | Commitment |
| --- | --- |
| Outcome | Share reviewed Review/search/recovery code, invented tests and methods without unpublished personal research |
| Integration owner | Primary publication integrator; batch workers do not commit or publish |
| Authoritative source | Accepted local `main`; original private history and dirty files are preserved |
| Publication checkout | Isolated `codex/publication-methods-20261020`, rooted at the existing public main |
| Finite acceptance | Source-port audit; synthetic combined acceptance; graph tests; changed-source lint/build; docs/data boundary; independent review; outgoing-history inspection |
| Remaining dependency | Final outgoing-history and remote branch verification; main merge/deployment remain separate |
| Next evidence checkpoint | Exact tested publication commit and remote branch identity, reported separately from deployment |

## Implemented capabilities

- [x] Document end-to-end enrichment + explorer refresh workflow in `docs/PLAYBOOK.md`
- [x] Curator-scoped overlapping tags, exclusions, revisions and optional notes.
- [x] Joined Review cards for qualified posts, websites, work and contact clues.
- [x] Literal all-evidence search with exact-account matching and source witnesses.
- [x] Separate directed follow/reply/repost exploration with coverage qualifiers.
- [x] Hide-and-recover graph experiment and inspectable candidate paths.
- [x] Rebuildable relationship/post indexes and retained release rollback bindings.
- [x] Private data exclusions and a tracked-path verification command.

Implemented does not mean complete data, calibrated probabilities, generalization
or independent confirmation of identity/competence. See the
[methodology](guides/DISCOVERY_METHODS.md) and [data boundary](guides/DATA_BOUNDARY.md).

## Next user journeys, in order

1. Consolidate existing authorized evidence in small reviewed batches. Show newly
   connected sources in Review without rewriting raw evidence or tags.
2. Map coverage deficits for a curator's own followed-account universe. Keep an
   old roster distinct from a verified current roster; incomplete sources stay unknown.
3. Let the curator tag and correct accounts while reading their evidence. Use
   disagreements and missing coverage to suggest a useful next review, not to
   pressure users into fixed abstract definitions.
4. Run a prospective, interleaved comparison of graph and lexical baselines.
   Measure novel useful finds per review minute, not only known-member recall.
5. Only then prioritize separately approved acquisition/semantic-model experiments
   against specific coverage or ranking failures and explicit cost caps.

## Testing Coverage

- Existing whole-app lint debt: 15 errors and 2 warnings in legacy UI files,
  byte-identical to the public base. All 80 changed JavaScript files pass scoped
  lint; no rules were disabled. Broad lint is not a CI gate today. Repair the
  legacy files in a separate tested slice rather than hiding their diagnostics.
- Avoid collection-time synthetic environment leakage; live-network checks need
  explicit dependency markers in addition to credential-dependent skips.
- Prospective candidate usefulness, including unknown/abstain and off-top-rank samples.
- Seed-shuffle nulls and robustness across source versions, curators and tag revisions.
- Distinguish missing edges, unreachable examples and genuine low-rank failures.
- Fresh-clone behavior without private inputs; never simulate empirical validation.

## Features & Analysis

- Source-qualified cross-platform identity claims and contradiction review, not
  automatic person merges from matching names/domains.
- Richer interaction/context representations, tested against cheap baselines.
- Optional budgeted acquisition and active learning; neither is yet a proven
  optimizer of human attention or “bits” of community certainty.

## Deferred from this publication

No live-service restart, dataset activation, paid fetching, outreach, public
contact directory or merge of private history. Historical experiment inputs and
operational diaries are not public reproducibility artifacts.
