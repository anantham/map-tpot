# ADR 019: Versioned Research Data and Artifact Manifests

- Status: Accepted
- Date: 2026-07-26
- Group: Data / Reproducibility
- Authors: Computational Peer + Human Collaborator

## Issue

Community Archive publishes its bulk enriched-tweet export at one mutable URL:

`https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/enriched_tweets/enriched_tweets.parquet`

The object is updated in place. A path alone therefore does not identify the data
used by an experiment, and replacing the project's existing local data would
remove the frozen baseline needed to compare clustering and propagation changes.
The per-account archives also contain following and follower observations whose
absence in a later export is not, by itself, evidence that a relationship ended.

The graph, spectral, propagation, and public-site artifacts currently have only
partial provenance. We need a safe acquisition boundary now and a compatible
identity contract for derived artifacts next.

## Decision

### Preserve the baseline and add immutable snapshots

Existing databases, per-account JSON caches, adjacency matrices, embeddings, and
propagation outputs remain a frozen comparison baseline. A refresh does not
overwrite or silently promote them.

Each bulk export is acquired into:

`data/community_archive/snapshots/<snapshot_id>/`

`snapshot_id` is derived from the canonical URL and the remote validators
available at probe time: `ETag`, `Last-Modified`, and `Content-Length`.
Observation time is used for the timestamp component only when the server does
not provide `Last-Modified`. A new remote identity creates a new directory; a
completed snapshot directory is not mutated in place.

### Treat acquisition as a validated transaction

The acquisition workflow must:

1. issue a metadata probe before downloading;
2. require a positive `Content-Length` and refuse objects above a caller-set
   hard byte cap;
3. stream the response to a temporary file rather than buffering it in memory;
4. reject an observable source change between probe and download, including an
   `ETag`, `Last-Modified`, or `Content-Length` mismatch;
5. require the received byte count to match the probed length;
6. compute SHA-256 while streaming, flush and `fsync` the temporary file, then
   atomically publish the final Parquet path without replacing an existing file;
7. inspect the Parquet schema and record row count, distinct account count,
   columns, minimum and maximum tweet `created_at`, archive-upload-linked rows,
   rows with no archive-upload ID, and source/Snowflake timestamp disagreements;
8. write `manifest.json` atomically **last**, without replacing an existing
   manifest.

A directory without a valid manifest is incomplete and must not be consumed as
a research input. Remote validators identify a candidate version; the recorded
SHA-256 is the local content identity used for deep verification.

The manifest also records the acquisition code's Git SHA and dirty-state flag.
This establishes who, what, and when without pretending that tweet
`created_at` is ingestion freshness.

### Do not infer deletions from absence

Following, follower, like, and similar relationship records are observations,
not guaranteed point-in-time snapshots with explicit deletion events.
Refresh/import code must not delete a stored social relationship merely because
it is absent from a later archive or export. Until the source supplies explicit
end/deletion semantics, these tables represent an accumulated union of observed
edges. A future current-state view may be materialized separately, with its
inference policy and observation window recorded.

### Extend the same identity model to derived artifacts

A later phase will add compatibility manifests for adjacency, spectral, seed,
propagation, and export bundles. At minimum these manifests should bind:

- source snapshot IDs and content hashes;
- ordered node-ID digests and graph/topology digests;
- seed/label and typed-edge digests;
- requested and effective algorithm parameters;
- producer Git SHA and dirty state; and
- hashes and dimensions of every derived file.

Consumers must reject incompatible node order, graph identity, or configuration
rather than relying on matching array lengths or filenames.

## Assumptions

- `ETag`, `Last-Modified`, and `Content-Length` are useful change validators but
  are not substitutes for a cryptographic content hash.
- The canonical export retains tweet/account IDs as strings and may encode
  `created_at` either as a timezone-aware Arrow timestamp or a canonical UTC
  string.
- Tweet `created_at` measures content coverage; source validators and upload
  metadata measure acquisition/ingestion freshness.
- The enriched-tweet Parquet export does not establish a complete,
  point-in-time social graph.
- Missing relationships cannot safely be interpreted as removals without
  explicit source semantics.
- Keeping the existing baseline is worth the additional disk usage because it
  enables controlled before/after experiments.

## Constraints

- The canonical object is large, mutable, and hosted outside this repository.
- Research data and generated artifacts remain gitignored; manifests are the
  portable provenance boundary, not Git LFS.
- Downloads may be interrupted or the remote object may change while a client
  is reading it.
- Snapshot retention and deletion are explicit maintenance actions, not part of
  refresh.

## Positions Considered

### Overwrite one local `enriched_tweets.parquet`

Rejected. It is simple but destroys the previous experimental input, makes
partial downloads dangerous, and leaves old derived artifacts looking valid.

### Destructively mirror the latest upstream state

Rejected. The source does not provide sufficient deletion semantics for social
relationships, so absence-based deletes would convert uncertainty into false
facts.

### Query the REST API for every analysis

Rejected for bulk work. Row limits, timeouts, network variability, and mutable
results undermine reproducibility. The API remains useful for bounded probes.

### Store every data object in Git

Rejected. The corpus is too large; Git records acquisition code and decisions,
while snapshot manifests and hashes identify external data.

### Versioned, validated local snapshots

Accepted. This preserves experimental controls, fails loudly on incomplete or
changing downloads, and provides a foundation for artifact compatibility.

## Consequences

- A refresh is additive and may require substantial disk space.
- Analyses must name the snapshot manifest they consumed rather than selecting a
  mutable `latest` file implicitly.
- A completed manifest is the commit marker for a snapshot directory.
- Existing per-account archive tables remain append/replace hybrids; they are
  not retroactively claimed to be exact current-state mirrors.
- Pruning snapshots requires a separate, explicit retention decision.
- The first phase covers the bulk enriched-tweet export. Per-account raw archive
  inventory and relationship-state materialization remain future work.

## Verification

The human-facing snapshot verifier checks manifest structure and cross-field
invariants, source identity, directory identity, required columns, byte length,
SHA-256, dataset row partitions, time bounds, and acquisition-code identity. An
optional Parquet rescan compares recorded dataset metrics with the file rather
than inferring that every missing `archive_upload_id` came from streaming.
Snowflake-derived bounds and bounded mismatch samples make upstream timestamp
anomalies visible instead of silently treating textual `created_at` as truth.

## Related Decisions and Artifacts

- ADR 004: Precomputed Graph Snapshots
- ADR 005: Blob Storage Import
- ADR 015: Data Pipeline Architecture
- ADR 018: Propagation Engine and Confidence Scoring
- `src/archive/snapshot.py`
- `src/archive/snapshot_contract.py`
- `src/archive/snapshot_dataset_validation.py`
- `src/archive/snapshot_inspection.py`
- `src/archive/snapshot_manifest.py`
- `src/archive/snapshot_quality.py`
- `src/archive/snapshot_validation.py`
- `src/archive/snapshot_workflow.py`
- `scripts/refresh_community_archive_snapshot.py`
- `scripts/verify_community_archive_snapshot.py`
- `docs/modules/archive.md`
