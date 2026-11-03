# Flask security boundary and workload hardening — 2026-10-02

Scope: T04, T05, T06, T07, T08, T10, T11, T12. Work completed in the isolated
security worktree; no commits, remote publication, deployment, credential changes,
private database inspection, paid calls, or live exploit probes were performed.

## Assessment and calibration

Actual start: approximately 16:54 IST / 11:24 UTC. Original estimate: 70 minutes,
finish around 18:05 IST; confidence 0.85. First assessment sent to parent within
10 minutes, before the parent's combined-plan deadline.

| Milestone | Original target (IST) | Actual / revised |
|---|---|---|
| Validate route gaps and identify reusable auth | 17:04 | Before 17:04 |
| Curator boundary and ingestion/admin separation | 17:20 | 17:01 |
| Resource caps and authenticated frontend plumbing | 17:40 | 17:08 |
| Regression, independent diff review, handoff | 18:05 | Revised 17:20; completed by 17:18 |

The estimate shortened because existing fail-closed curator auth could be reused
centrally, source findings were directly reproducible, and the existing Python
venv plus copied JS dependencies were available. Final confidence: 0.90 for the
covered synthetic contracts; no claim about production deployment or reachability.

## Validated findings and changes

- **T04:** anonymous full-graph metrics and analysis were accepted. A central
  default-deny policy now requires `TPOT_CURATOR_TOKEN` on known Flask routes.
  Heavy graph/discovery/Golden work shares non-queued admission with background
  analysis: one active task per shared snapshot root by default, configurable
  1..4 with worker agreement. See the independent-review follow-up below: the
  two unsupervised whole-graph HTTP endpoints are now disabled entirely. Invalid
  metric seeds/weights/alpha/filters are rejected before graph construction.
- **T05:** feedback persisted every entry and loaded the whole table. New records
  have bounded identifiers, finite 0..1 scores, a 4 KiB context ceiling, a
  transactional 20,000-row quota, and a recorded 30-day expiry. Expired records
  disappear from memory/reports; physical expiry cleanup occurs on subsequent
  feedback writes. Historical rows have no expiry and are preserved. SQL excludes
  oversized historical contexts and loads at most the quota into memory.
- **T06/T11:** Golden labels, predictions, evaluations, taxonomy/tag writes and
  cluster label POST/DELETE now require the central curator gate before stores.
- **T07:** frontend logs accept only bounded JSON entries (8 KiB), constrained
  levels and string messages. Files rotate at 1 MiB with 3 backups. Request IDs
  are sanitized and limited to 64 characters. The central gate authenticates logs.
- **T08:** graph/discovery caches now enforce TTL, LRU entry limits and byte
  ceilings using serialized size plus retained Python object size. Defaults:
  graph 8 entries, discovery 64 entries, 16 MiB each, 300-second TTL. The inner
  discovery compatibility cache is bounded to 100 entries / 16 MiB / one hour.
  Keys are fixed-size digests of validated canonical requests, so ignored JSON
  properties cannot generate unique cache entries. `use_cache=false` is honored.
  Inner results include graph identity to prevent reuse between different graphs.
  Discovery extraction caps returned neighborhoods at 5,000 nodes and consumes
  at most 100 predecessors and successors per node using bounded iterators.
- **T10:** open ingestion authorizes `/feed_events` only. Settings, raw events,
  account exposure summaries, and purge require a curator token independently of
  the ingestion policy or extension token. Ingest receipts omit settings and local
  firehose paths. Standalone extension-blueprint registration has the same gate.
- **T12:** Golden/private graph/account/community reads now require curator auth.
  Counterevidence: research notes and their source routes already had explicit
  `curator_only` at this HEAD; the scan's anonymous-notes claim is inapplicable.
  The central gate reinforces that existing protection. Only minimal health and
  deliberate extension ingestion are anonymously allowlisted; OPTIONS carries no
  private payload. The separate public-site snapshot UX is unchanged.

The graph-explorer fetch wrapper attaches the existing curator header to all its
private Flask clients, preserving read/write UX. It adds credentials only for the
configured backend origin and `/api/` path; unrelated origins and static assets
receive none. Cookie/ambient credentials are not accepted by server auth, so
browser-origin forgery without the explicit token fails closed. CORS remains
limited to configured analyst origins.

## Evidence and verification

The first RED test reproduced the anonymous metrics bypass: expected 401, got
400 from the route's validation (the protected route executed). A second RED test
accepted oversized feedback (200 instead of 400). Both are now rejected before
side effects. Synthetic tests cover missing configuration (503), missing/wrong
credentials (401), authenticated private reads and mutation, preflight behavior,
open-ingestion/admin separation, finite values, quotas across two store instances,
expiry preserving legacy records, workload admission/release, cache count/bytes/TTL,
and finite log rotation.

- Relevant Python regression tranche: **226 passed** across 19 files, including
  new security contracts plus API, analysis, feedback, discovery, extension,
  Golden, and cluster regressions. Final extraction/cache hardening additionally
  passed **43 focused tests**; subsequent expiry, immutable-cache, and neighborhood-ceiling hardening passed
  **68 focused tests**.
- Full graph-explorer aggregate: **819 passed** across 58 files.
- Human verifier: `python scripts/verify_security_flask.py`; **60 contracts passed**.
- `git diff --check`: passed.
- Graph production build: succeeded (1,154 modules, 1.67 seconds); inherited
  static/dynamic logger-import warning remains.

Reproduce Python checks with the existing canonical venv's Python executable and
this worktree's `tpot-analyzer` as cwd. Tests use temporary synthetic stores, never
the canonical source or real personal databases. JS command:
`node node_modules/vitest/vitest.mjs run src --configLoader runner`, from
`graph-explorer`.

## Residuals and operator deployment steps

Flask public reachability is unverified; these changes harden an analyst API and
do not establish that it was publicly deployed. Admission is now shared across
all cooperating processes using one snapshot root. Cache/rate-limit storage remains
per process. Whole-graph metrics and background analysis HTTP entry points are
unavailable until an actual bounded supervisor is implemented; authentication or
configuration flags cannot re-enable the removed unbounded implementations.
Other private graph reads/discovery still use shared admission and bounded
parameters/caches, and can remain expensive on a large approved snapshot.

Historical feedback deletion and shrinking existing SQLite/log files require
separate approval. No historical records were removed here. Expiry physically
cleans only newly TTL-marked rows when the next feedback write occurs; idle
storage cleanup is a separate operator maintenance choice. Shared rotation preserves
finite frontend/server log growth. Unsafe or oversized existing files fail closed
and require separately approved archival/permission repair before writing resumes.

Before an approved deployment: review the patch, provide a strong matching
`TPOT_CURATOR_TOKEN` and `VITE_TPOT_CURATOR_TOKEN` only in the private analyst UI,
provide `TPOT_EXTENSION_TOKEN` for guarded ingestion, retain a restrictive CORS
origin list, and verify authenticated read/write + anonymous denial in staging.
The frontend token is already intentionally bundled for this private local UI;
do not publish that analyst bundle or its secrets. Token rotation/deployment
were not performed. Historical feedback above quota returns 507 until an
explicitly approved review/export/cleanup resolves it.

## File size / maintenance notes

Discovery was split from 593 to 239 LOC; request schema 81, projection 172, and
neighborhood extraction 72 LOC. All newly added Python modules are below 300.
Inherited `graph-explorer/src/data.js` remains 748 LOC (one auth import added), and
several existing regression files are above 300 LOC; those need focused future
client/test decomposition. Golden/state monoliths were not modified by this work;
the central policy avoided expanding them. Parent owns shared WORKLOG, ROADMAP,
index and experiment-log integration, so no competing edits were made there.

## Exact owned change manifest (paths under tpot-analyzer)

Backend modified: `src/api/server.py`, `src/api/discovery.py`,
`src/api/log_routes.py`, `src/api/routes/analysis.py`,
`src/api/routes/graph.py`, `src/api/routes/discovery.py`,
`src/api/routes/extension.py`, `src/api/routes/extension_read_routes.py`,
`src/api/services/analysis_manager.py`, `src/api/services/cache_manager.py`,
`src/api/services/signal_feedback_store.py`.

Backend added: `src/api/security_policy.py`, `src/api/workload_validation.py`,
`src/api/feedback_limits.py`, `src/api/discovery_request.py`,
`src/api/discovery_projection.py`, `src/api/discovery_subgraph.py`,
`src/api/services/bounded_cache.py`.

Frontend modified: `graph-explorer/src/accountsApi.js`,
`graph-explorer/src/communitiesApi.js`, `graph-explorer/src/communityGoldApi.js`,
`graph-explorer/src/data.js`, `graph-explorer/src/discoveryApi.js`,
`graph-explorer/src/fetchClient.js`, `graph-explorer/src/labelingApi.js`,
`graph-explorer/src/logger.js`, and corresponding existing tests
`communitiesApi.test.js`, `communityGoldApi.test.js`, `discoveryApi.test.js`,
`fetchClient.test.js`, `labelingApi.test.js` in the same directory.
Frontend added: `graph-explorer/src/analystFetch.js`,
`graph-explorer/src/analystFetch.test.js`.

Python existing fixture/contracts updated: `tests/test_api.py`,
`tests/test_api_contract_routes.py`, `tests/test_api_autocomplete.py`,
`tests/test_discovery_endpoint_matrix.py`, `tests/test_discovery_routes.py`,
`tests/test_extension_routes.py`.
Python new security tests: `tests/test_security_flask_boundary.py`,
`tests/test_security_resource_limits.py`.
Verification/docs added: `scripts/verify_security_flask.py`, this diagnostic.

All changes are left unstaged for root integration. Build output is ignored.
Shared documentation, publication files, outbound transport helpers, and
`cluster/state.py` belong to other agents and were not edited by this work.

## Independent-review follow-up — global bounds and fail-closed analysis

The first tranche closed anonymous access but did not fully close T04's resource
property: a trusted whole-graph request still had no hard wall-clock/memory
supervisor, and admission/log serialization were process-local. Independent review
correctly distinguished that mitigation from resource closure. This is a scope
calibration correction to the initial handoff, not evidence of production exposure.

Follow-up actual start: 17:19:55 IST / 11:49:55 UTC. Additional original estimate:
35 minutes (finish around 17:55 IST), confidence 0.85. Milestones: shared admission
and disabled unsafe endpoints in 15 minutes; shared log rotation and adversarial
process/filesystem tests in 25; final review/evidence in 35. Those implementation
milestones completed ahead of schedule. Final verified handoff: 17:43:32 IST /
12:13:32 UTC, actual 23 minutes 37 seconds against the original 35 minutes.
Revised additional estimate stayed 35 minutes despite a final concurrent-create
failure adding diagnosis/regression work. Confidence after review: 0.90 for these
synthetic contracts. The original assessment had omitted the cross-process and
whole-graph supervisor requirement.

**T04 closure:** `/api/analysis/run` and valid `/api/metrics/compute` return 503 with
`BOUNDED_SUPERVISOR_REQUIRED`, even with correct curator credentials. No config or
environment opt-in can enable the removed unbounded implementations. Malformed
metric input still returns 400. `/analysis/status` declares `whole_graph_runs=false`.
Private status, feedback, presets, approved graph reads and discovery remain
available through the authenticated client. Restoring whole-graph HTTP computation
is an explicitly unavailable capability, rather than an unbounded deployed path.

Admission for the remaining expensive endpoints now uses shared POSIX `flock`
leases in the configured snapshot root. The root must belong to the current user
and cannot be writable by group/others or contain symlink components. Its private
`.tpot-security-runtime` directory must be 0700; lock files must be 0600, owned,
single-link regular files, opened with `O_NOFOLLOW` and pinned directory descriptors.
Workers use the same persisted capacity and reject conflicting capacity settings.
There is one global slot by default; blocked work returns 429 without queuing.
Unsafe/unavailable coordination returns 503. Request teardown, process exit, and
worker-thread startup failure release leases. Tests inspect only newly created
coordination metadata and synthetic files, never analyst records.

**T07 closure:** frontend and API logs both use one cross-process append/rotation
helper. A shared lock serializes size checks, rotation and writes; lock waits are
bounded to 0.5 seconds. Frontend storage remains 1 MiB plus 3 backups; server
storage is 5 MiB plus 5 backups with 16 KiB capped entries. Symlinks, hardlinks,
unsafe owners/modes and pre-existing oversized retention files are rejected before
writes or rotation. The implementation preserves unsafe/historical files for
separately approved archival or permission repair. No existing real log was
modified or deleted during this work.

Additional owned files: new `src/api/filesystem_locks.py`,
`src/api/bounded_logs.py`, `tests/test_security_cross_process.py`; modified existing
`tests/conftest.py` to keep all full-app snapshot fixtures' logs synthetic,
`tests/test_analysis_routes.py` and `tests/test_api.py` for the deliberately disabled
whole-graph contract, and `tests/test_security_integration.py` for the private-read
contract. The five stale anonymous-read assumptions now assert 401 plus an error-only
response, then validate the authenticated projection. Analysis route code is 136
LOC; its inherited regression file was reduced below 300 LOC.

Follow-up validation: **183 targeted Python tests passed**, including the private
read regression and the disabled whole-graph contract. An earlier final run found
an intermittent macOS ENOENT during simultaneous creation of the shared log lock.
The helper now opens existing files first, then uses exclusive creation with at
most three retries for a competing creator/ENOENT; all file integrity checks remain.
Five separate three-process rotation cases and deterministic retry/bounded-failure
contracts passed. The independent reviewer read the change and passed **22 expanded
cross-process tests**, reporting no blocker (its earlier boundary/resource review
passed 53 contracts). The final human verifier passed **60 contracts**.
`git diff --check` passed. No frontend source changed in this follow-up; the earlier
819-test aggregate and successful graph build remain applicable.

### Concrete route to restore the disabled capability

A future runner should execute typed metrics/analysis jobs in a separate container
or worker environment with enforceable memory limits, CPU/pid ceilings, a parent
wall-clock timeout that kills the entire job group, bounded result files, and the
same shared admission lease. Suggested initial envelope for a staging experiment:
120 seconds, 2 GiB memory, 32 MiB result JSON, one job globally. These are starting
limits requiring validation on an approved synthetic representative graph, not
claims that the real full graph fits. The existing API can then submit/status-poll
jobs and expose only validated results. Do not apply `RLIMIT` to Flask's main
process, and do not claim macOS advisory RSS limits are a hard memory cap.

Implementation estimate for that additional capability: approximately 3 hours,
confidence 0.75, contingent on choosing an available environment with enforced
memory/process limits and validating result compatibility. Container/runtime setup
and deployment need a separate concrete decision/approval. Until then, the two
HTTP entry points stay disabled. No runner, persistent service, new access grant,
container installation or production configuration was created here.

Before an approved deployment, all Flask workers must point at the same owned,
canonical snapshot root and safe log root. Existing runtime capacity changes must
be handled as an operator maintenance action after stopping active workers;
do not unlink an active lock file to bypass capacity. Permission repair or archival
of existing logs is separately reviewable work, and was not performed. Caches and
rate-limit counters remain per process, although their own limits are finite.
