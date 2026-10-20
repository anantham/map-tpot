# Roadmap

Public methodology/source edition, 20 October 2026. This board describes code
capabilities and remaining research, not the contents of a private dataset.

## Current bounded slice: documentation navigation

| Item | Commitment |
| --- | --- |
| Outcome | A new reader reaches methods, setup, architecture and history from the root README |
| Integration owner | Primary publication integrator |
| Authoritative source | Published source checkpoint `3a33bbc`; private main and its dirty files remain untouched |
| Publication checkout | Isolated `codex/publication-methods-20261020` |
| Finite acceptance | Three navigation regressions; 11 docs checks including entrypoint links; data boundary; independent review; exact outgoing diff and remote SHA |
| Remaining dependency | Commit/remote verification of the reviewed docs-only follow-up; main merge/deployment remain separate |
| Next evidence checkpoint | Updated README and docs hub on the verified publication branch |

The source publication at `3a33bbc` passed all three
[hosted CI jobs](https://github.com/anantham/map-tpot/actions/runs/39383251387).
This navigation slice reuses that unchanged application evidence; it changes no
application behavior, private source, tag or runtime binding.

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

- Triage remaining loose historical docs in small batches with link and privacy
  checks. New topic-specific docs follow the [folder guide](index.md#documentation-folders);
  do not bulk-rename application or data paths just to tidy the root.
- Source-qualified cross-platform identity claims and contradiction review, not
  automatic person merges from matching names/domains.
- Richer interaction/context representations, tested against cheap baselines.
- Optional budgeted acquisition and active learning; neither is yet a proven
  optimizer of human attention or “bits” of community certainty.

## Deferred from this publication

No live-service restart, dataset activation, paid fetching, outreach, public
contact directory or merge of private history. Historical experiment inputs and
operational diaries are not public reproducibility artifacts.
