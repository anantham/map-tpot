# Local trust and publication remediation — 2026-10-02

Scope: T03 public Git artifacts, T09 publication approval, T15 archive bounds,
T16 cookie deserialization, T17 analysis artifact deserialization, T19 cookie
permissions. Implementation authorized; publication/deployment and destructive
artifact/history cleanup are not authorized. No real private record contents or
real pickle/NPZ artifacts are read by this work. One CSV header is read for schema
validation; personal rows are not opened.

## Initial assessment and calibration

Actual start: 2026-10-02 11:24:27 UTC (16:54:27 IST). Original estimate:
90–120 minutes; confidence 0.78. Initial milestones: code map and regression
contracts by 17:12 IST; bounded archives, JSON cookies and artifact formats by
18:00; publication gate and cleanup plan by 18:30; regression and review by
18:55. Revised estimate: 120–150 minutes (19:00–19:30 IST), confidence 0.78.
Reason: adjacency producer and multiple consumer/cache variants also require
safe-format migration. This is an estimate, not a completion promise.

Confirmed hypotheses: archive fetcher accepts unlimited decoded bytes and
caches unvalidated JSON; store parser trusts section/item types; Selenium loads
pickle cookies and setup writes them with inherited modes; adjacency and
analysis loaders deserialize pickle/object NPZ; Blob uploader overwrites fixed
public paths and auto-export pushes and requests paid generation by default.
Expected regression outcomes: malformed/oversized inputs fail before persistence;
malicious pickles are rejected without evaluation; cookies round-trip with mode
0600 and reject symlinks; publication requires an exact digest and explicit
field allowlist; automation prepares local files only.

Dependencies: existing read-only Python environment; safe adjacency producer
migration in cluster/state.py coordinated with Flask agent; human approval for
historical Git removal, Blob cleanup, changing production URLs/settings and
publishing approved exports. Legacy pickles must be regenerated from authoritative
safe sources; this patch will not silently deserialize or convert them.

Modularity warning: inherited store.py (361), blob_importer.py (~700),
export_public_site.py (403), auto_export.py (400), _community_extractors.py
(~600), cluster/state.py (>500) and enrich_shadow_graph.py (>300) exceed the
repository gate. Extract new security responsibilities into modules <300 LOC;
reduce store and auto-export where feasible. Broader existing decomposition
remains debt for parent WORKLOG/ROADMAP integration.

## Findings and delivery evidence

| Finding | Validated source issue | Implemented prevention | Remaining decision |
| --- | --- | --- | --- |
| T03 | Git tracks audit/cohort/research artifacts contrary to local-only dossier policy | Ignore private/candidate paths; explicit data-file allowlist blocks changed/additional artifact paths in CI; staged checker for local review | Historical deletion/history rewrite, copies/forks and existing public deployments require specific owner approval |
| T09 | Exporter assembled arbitrary dictionaries; auto-export pushed and paid-generated; uploader overwrote fixed public Blob paths | Recursive field projection, strict upload allowlist including duplicate-key rejection, exact policy+file byte digest, unapproved local manifest, explicit --approve-digest, immutable release paths and no overwrite | Owner must review candidate values and approve exact digest; production release selection requires separate deployment approval |
| T15 | Unlimited decoded/cache archive bytes and unvalidated parser shapes | 64 MiB, 500k total/250k per consumed section records, 32-level nesting, bounded strings/keys/values, 120s stream deadline; deterministic rejection not retried; validate before cache/DB mutation | Very large legitimate archives require an explicitly reviewed limit or a future streaming ingestion design |
| T16 | Selenium cookie pickle loading | Bounded, typed JSON only; recapture legacy cookies; allowed X/Twitter domains | User recaptures authenticated session locally |
| T17 | Adjacency pickle and object NPZ loaders/writers | Numeric/string NPZ and CSR arrays with JSON metadata; every NPZ/NPY reader preflights dtype, dimensions, integer products, header/data bytes and ZIP central directory before allocation; rejects zero-width/object arrays | Rebuild from authoritative graph inputs; legacy certified frozen bundle must be regenerated/re-certified, not silently converted |
| T19 | Cookie writer inherited permissions and followed paths | Atomic no-clobber create with exact 0600; dirfd no-follow ancestor walk and leaf rejection; reader enforces owner/regular/0600 | Existing legacy secret files remain untouched; recapture is the migration |

Offline verification script: `python scripts/verify_security_local_publication.py`.
Current executable-deserialization source audit: 475 Python source files, zero
pickle loaders/writers or allow_pickle=True callsites. New synthetic contracts:
51 Python tests plus 6 Node publication tests pass. Consolidated local regression: 316/316 passed, with 15 inherited SciPy sparse
efficiency warnings. Independent reviewer reran 72/72 Python contracts and
6/6 Node contracts and reported no remaining exploitable blocker in this scope.
Parent owns the full cross-agent aggregate result and integration.

The independent review caught and repaired two important resource/privacy
classes: a forged tiny NPY declaring 8TB, and zero-width string arrays that could
expand during later conversion; both are rejected before NumPy allocation.
It also caught duplicate JSON keys hiding private raw-byte fields and zero SHA
CI baselines falling back to empty staged mode. Upload now rejects duplicate keys;
explicit empty/zero baselines fail closed; new-branch CI uses fetched default-
branch baseline. No giant allocation, live exploit, paid model call or upload was
performed. All probes used synthetic temporary files and mocked uploads.

## Migration and release instructions (not executed)

1. Recapture: `python -m scripts.setup_cookies --output secrets/twitter_cookies.json`.
   Retain old files privately until the owner decides their disposition. There is
   no automatic pickle conversion or deserialization path.
2. In a new local generation directory, rebuild adjacency from authoritative
   Parquet graph tables using the cluster initializer. It emits
   `adjacency_matrix_cache.npz` and safe mode/TPOT variants. Regenerate spectral
   and propagation arrays through their producers. Unicode identities replace
   object arrays. Validate graph/node-order bindings before adopting the bundle.
   Frozen-control manifest schema_version=2 requirements now refer to NPZ caches; the existing
   frozen manifest/data are unchanged and therefore require explicit scientific
   re-certification in a new generation. Do not edit the old manifest to make
   checks green.
3. `make prepare-public-site` prepares a local candidate under
   `data/publication_candidates/`. The exporter never grants approval.
   Review the actual approved fields and values against ADR-021/022; inferred
   attributes/private dossier text remain forbidden, including free text that
   an allowlisted field could otherwise carry. The manifest's status is always
   unapproved; its hash is an identity, not authorization.
4. After explicit operator approval of the exact digest, an operator may run
   `npm run test:publication` and
   `node scripts/upload-public-site-data.mjs --candidate-dir ../data/publication_candidates --approve-digest <approved-digest> --validate-only`
   from public-site. Removing --validate-only performs an actual public upload
   and requires separately authorized publication. It creates
   `public-site/releases/<digest>/data.json` and `.../search.json`, never overwrites
   current paths. Parent is adding an optional validated production release-digest
   selector; changing its environment/configuration and deploying are not approved.
5. A partial upload can leave an immutable orphan release; retrying an existing
   digest fails rather than overwriting it. Owner-approved Blob cleanup is a
   separate operational decision.

## Non-destructive T03 cleanup plan

Confirmed tracked paths, using Git names only: `data/evals/phase1_membership_audit_accounts.json`,
`data/evals/phase1_membership_audit_review_sheet.csv`,
`data/evals/dharma_seed_coverage_panel.json`,
`data/evals/dharma_seed_coverage_report_20260730.json`,
`data/tier2_fetch_queue.txt` and `data/tpot_holdout_seeds.json`. Other tracked
research outputs (`data/test_subset.json`, `data/veil_cv_results.json`,
`data/tpot_calibration.json`, `data/tpot_relevance_scores.npy`,
`data/graph_snapshot_tpot.mapping.json`) also fall outside the future-publication
allowlist. The CSV header alone confirms account/judgment/rationale column
schema; the reported 36 audit records/8,984 IDs are from the source scan and are
not independently counted or inspected here.

Owner decisions still needed: identify exact records/paths to withdraw; approve
current-tree untracking/removal; approve whether history rewrite is warranted;
coordinate collaborators/backups/forks/caches; authorize removal of corresponding
public Blob/site outputs; decide visibility and notification obligations. Before
any approved cleanup, preserve a private evidence inventory under the owner's
control and agree on rollback. After an approved cleanup, verify Git/Blob/public
responses without printing personal records. Existing public copies cannot be
recalled by a source-code patch. Nothing was deleted/untracked, no history was
rewritten, and repository visibility was not changed.

## Calibration update

At 11:58:54 UTC (17:28:54 IST), 34m27s elapsed. Most implementation is complete;
remaining work is consolidated regression, final evidence and independent review.
Revised near-term estimate: 10–20 additional minutes (17:39–17:49 IST), confidence
0.85. The original 90–120 minute and revised 120–150 minute ranges overestimated
because the mounted dependency environment and existing synthetic fixtures were
usable, the exporter/cookie/storage seams were small, and the root coordinated
review/aggregate checks in parallel. This estimate excludes user-dependent
cleanup, artifact recapture/re-certification, publication and production deployment.


## Exact owned file changes

Shared file hunks: `.github/workflows/test.yml` (Python publication-path check and
Node publication-contract step only), `.gitignore` (private/candidate ignores),
`tpot-analyzer/public-site/package.json` (`test:publication` script only).
All paths below are relative to `tpot-analyzer/`:

- Policy/entrypoints: `Makefile`, `config/public_site.json`,
  `config/publication_fields.json`, `scripts/export_public_site.py`,
  `scripts/auto_export.py`, `scripts/check_publication_files.py`,
  `scripts/verify_security_local_publication.py`.
- Publication helpers: `scripts/_export_helpers/_publication.py`,
  `scripts/_export_helpers/_account_enrichment.py`,
  `scripts/_export_helpers/_community_extractors.py`,
  `public-site/scripts/upload-public-site-data.mjs`,
  `public-site/scripts/publication-policy.mjs`,
  `public-site/scripts/publication-json.mjs`,
  `public-site/scripts/publication-policy.node-test.mjs`.
- Archives: `src/archive/fetcher.py`, `src/archive/store.py`,
  `src/archive/limits.py`, `src/archive/store_schema.py`, `src/data/blob_importer.py`.
- Cookies: `src/shadow/cookie_store.py`,
  `src/shadow/selenium_internals/_driver_mixin.py`, `scripts/setup_cookies.py`,
  `scripts/enrich_shadow_graph.py`.
- Artifact storage/producers: `src/artifacts/safe_io.py`, `src/data/adjacency.py`,
  `src/data/community_gold/artifacts.py`, `src/api/cluster/state.py` (cache only),
  `src/config.py`, `src/graph/spectral.py`, `src/propagation/io.py`.
- Artifact consumers/contracts: `src/artifacts/tpot_inputs.py`,
  `src/artifacts/frozen_manifest.py`, `src/artifacts/frozen_control_verifier.py`,
  `src/artifacts/frozen_output_verifier.py`, `src/artifacts/propagation_alignment.py`,
  `src/artifacts/relevance_binding.py`, `src/artifacts/spectral_binding.py`,
  `src/evaluation/discoverability.py`, `src/evaluation/solver_contract.py`,
  `src/communities/cluster_colors.py`, `scripts/analyze_frontier_confidence.py`,
  `scripts/classify_bands.py`, `scripts/fetch_user_profiles.py`,
  `scripts/propagate_community_labels.py`, `scripts/rank_frontier.py`,
  `scripts/verify_clusters.py`, `scripts/verify_holdout_recall.py`,
  `scripts/verify_independent_band_entropy.py`.
- Regression fixtures/new tests: `tests/test_archive_limits_security.py`,
  `tests/test_cookie_store_security.py`, `tests/test_artifact_io_security.py`,
  `tests/test_publication_boundary_security.py`, `tests/test_git_publication_boundary.py`,
  `tests/test_artifact_compatibility_verifier.py`, `tests/test_tpot_artifact_inputs.py`,
  `tests/test_community_gold_evaluator.py`, `tests/test_community_gold_routes.py`,
  `tests/test_frozen_manifest.py`.
- Evidence: `docs/diagnostics/security-local-publication-20261002.md` (this file).

New security modules are all below 300 LOC. Extracting schema/evidence reduced
store.py 361→279 LOC, export_public_site.py 403→299 and auto_export.py 400→247.
Additional inherited large files touched only for safe-reader/writer integration
include _community_extractors.py (559), blob_importer.py (662), cluster/state.py
(619) and enrich_shadow_graph.py (622). rank_frontier.py (288) and
discoverability.py (272) also approach the limit. Parent should carry these decomposition candidates
into WORKLOG/ROADMAP; this security patch does not disguise the existing debt.

No files have been staged or committed by this agent. All work is in the isolated
`codex/security-tpot-20261002` worktree; parent integrates commits and decides
whether/when to request branch/PR publication approval.

Final local implementation handoff: 2026-10-02 12:03:56 UTC (17:33:56 IST),
39m29s from start. Original 90–120 minute estimate; first revision 120–150;
actual implementation/review/regression handoff was 39m29s. No scope was declared
complete by timing alone: T03 destructive cleanup, cookie recapture, safe frozen
bundle regeneration/re-certification, exact export approval and deployment remain
explicit dependencies. Root approved explicit frozen manifest schema_version=2;
three affected synthetic suites passed 10/10 after that final contract update.
Existing data files and v1 manifest are unchanged (`git status --short -- data`
empty). Owned-path diff whitespace check passes. No remaining exploit blocker was
identified by independent review; residual deployment/cleanup decisions are above.
