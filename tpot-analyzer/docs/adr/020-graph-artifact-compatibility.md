# ADR 020: Graph Artifact Compatibility

- Status: Accepted
- Date: 2026-07-26
- Group: Graph / Reproducibility
- Authors: Computational Peer + Human Collaborator

## Issue

Graph, adjacency, spectral, and propagation files can have plausible filenames
and dimensions while describing different node domains or orders. Positional
array operations then produce incorrect results without necessarily failing.
The current full graph has 95,057 ordered nodes; the active propagation artifact
has 298,347 nodes but overlaps the graph at only 358 IDs, while the legacy
training propagation artifact has the compatible 95,057-node domain and order.

We need an explicit compatibility contract before combining these artifacts.

## Decision

### The graph node list defines the ordered domain

The graph's ordered node list is authoritative. Every adjacency row/column,
spectral row, membership row, and derived account vector must either already
use that exact order or be explicitly reindexed to it by account ID.

Matching lengths, filenames, or modification times are not evidence of
compatibility.

### Adjacency must reconstruct exactly

A cached adjacency is compatible only when reconstruction from the authoritative
ordered nodes and graph edges produces the same:

- matrix shape;
- nonzero structure and count;
- edge weights; and
- ordered node and topology digests.

Any mismatch invalidates the cache. Consumers fail closed instead of continuing
with the nearest-looking matrix.

Construction semantics are part of the identity. The frozen full cache is
`directed_edge_rows`; the frozen TPOT runtime cache is
`directed_plus_mutual_reverse`. These are distinct methods, even when a
particular induced subgraph happens to have the same nonzero count. The current
API cache-rebuild path adds reverse entries for mutual edges and therefore
cannot be assumed to reproduce the pinned full-cache digest.

### Propagation compatibility is ID-based

A propagation candidate must contain unique node IDs and cover 100% of the graph
node domain.

Candidate-list order expresses scientific intent, such as preferring a
production artifact over an explicitly named fallback. For each candidate:

1. **Full coverage is mandatory.** Partial, duplicate, or ambiguous domains
   are rejected.
2. **Exact order is a transport shortcut.** Use rows directly when candidate
   IDs exactly equal the graph node list.
3. **A full superset is reindexed.** Accept only through an account-ID join that
   selects every graph node in authoritative order. Verify full coverage,
   uniqueness, output shape, and final ordered-ID equality.

Implicit truncation, positional slicing, or array broadcasting is prohibited.
An exact-order candidate does not automatically outrank an earlier compatible
candidate; row order is not a scientific selection criterion.

Propagation score semantics are also load-bearing. `classic` propagation emits
probability-simplex rows. `independent` propagation emits nonnegative Lift
scores that need not be bounded by one or sum to one. Generic compatibility
validation accepts either representation when declared, but the current TPOT
relevance equation assumes probabilities and therefore rejects independent
Lift artifacts.

### Bind calibration and provenance

The compatibility slice implemented here binds:

- a committed frozen-control record with expected byte size and SHA-256 for all
  15 scientific files used by the control;
- graph source-file hashes, ordered node digest, topology structure and value
  digests, dimensions, and adjacency construction;
- propagation file hash, source and aligned node digests, membership shape,
  score mode/semantics, and community ordering;
- calibration threshold, counts, holdout split, calibration objective, and
  relevant code hashes; and
- exact selected-node, Parquet-subset, spectral-row, and runtime-cache output
  reproduction.

A complete newly generated artifact manifest must additionally bind:

- requested and effective propagation parameters;
- seed/label provenance; and
- producer Git SHA and dirty state.

Missing or contradictory identity, calibration, or provenance fields cause a
closed failure with a descriptive mismatch report.

The existing calibration predates the compatibility record. During migration
it may be used only when runtime reconstruction proves the adjacency and
propagation identities, recomputed relevance exactly equals the saved float32
vector, and the saved threshold exactly reproduces core, halo, total, and
ordered selected-node output. This exception is reported as legacy runtime
validation; every newly written calibration must embed provenance and its exact
method record.

### Publication is a separate safety boundary

The current builders may write only to absent output paths. A cooperating-writer
lock prevents two processes from targeting the same new prefix, but a set of
files is not an atomic publication unit. Replacing the active bundle requires
immutable generation directories, a manifest validated before publication, and
one atomically replaced generation pointer. Readers must resolve the pointer
once, load into local state, validate the whole generation, and only then swap
runtime state.

### Current fallback

The legacy `community_propagation_train.npz` artifact is the current compatible
fallback because its node domain and order match the authoritative full graph.
The active `community_propagation.npz` artifact is incompatible with direct
positional or ID-reindexed consumption because 94,699 graph IDs are absent from
its larger but largely different domain. It becomes eligible only if the graph
is rebuilt for that same node universe or propagation is regenerated for the
current graph.

This fallback is a reproducible control, not validated current group truth. It
contains 14 communities plus `none`, has no declared mode, and all 15 solver
flags are false with 800 recorded iterations. Its community UUIDs have no
overlap with the active artifact's 16-community schema. The missing mode is
treated as legacy classic only when its file matches the committed certified
SHA-256 and its rows satisfy the probability-simplex contract. New mode-less
artifacts are rejected.

## Assumptions

- Account IDs are stable string identities across graph and propagation files.
- Graph node order is intentional and load-bearing.
- Exact reconstruction is affordable as a verification step before expensive
  downstream analysis.
- Calibration affects score meaning even when matrix shapes and IDs match.
- Non-convergence and taxonomy age can change scientific meaning without
  breaking artifact compatibility.
- A loud refusal is safer than producing an untraceable community map.

## Alternatives Considered

### Trust matching dimensions

Rejected. Equal dimensions do not prove equal IDs, order, topology, community
order, or calibration.

### Truncate or positionally slice supersets

Rejected. Superset row order is not guaranteed to contain the graph domain as a
prefix.

### Always use the newest artifact

Rejected. Recency is not compatibility; the active propagation artifact is the
current counterexample.

### ID-aware, manifest-bound validation

Accepted. It permits safe supersets while preserving deterministic graph order
and failing visibly on incomplete provenance.

## Consequences

- Artifact selection becomes deterministic and explainable.
- Existing cache consumers must verify reconstruction or carry a compatible
  manifest before reuse.
- Superset propagation files require an explicit reindexing implementation.
- Legacy fallback remains available without silently changing current results.
- Incompatible artifacts produce actionable errors rather than best-effort
  output.
- Read-only experiments can pin and verify the frozen control now.
- Regeneration or deployment remains blocked on versioned producer provenance,
  explicit adjacency semantics, and atomic generation publication.

## Verification

A human-facing verifier must report graph node count, adjacency shape and
nonzeros, reconstruction equality, propagation coverage, order status, reindex
status, dimensions, score semantics, solver convergence, calibration identity,
expected file sizes/hashes, exact relevance reproduction, selected-node output,
both spectral bindings, Parquet subsets, runtime adjacency semantics, and the
selected fallback. Any failed required check returns a nonzero exit status.

## Related Decisions

- ADR 004: Precomputed Graph Snapshots
- ADR 018: Propagation Engine and Confidence Scoring
- ADR 019: Versioned Research Data and Artifact Manifests
