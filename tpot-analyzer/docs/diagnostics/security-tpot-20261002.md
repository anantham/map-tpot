# TPOT security remediation disposition — 2026-10-02

Implementation, synthetic verification and a local review patch are authorized.
Remote branch/PR publication, deployment, production settings, credential rotation,
repository visibility changes and destructive data/history cleanup are not authorized.
Parent task owns user communication and any publication approval request.

## Source identity and scope

Source report: private Library file `libfile_28cac862c0b081918bfc19285ea48f22`,
`Project_Security_Review_2026-10-02.docx`, read through Library without editing it.
Report contents were sufficient; no cloud pathname was treated as a local file.
The scanned/deployed commit supplied by the user was
`6f030442b58ee56d74a1b0af7921e9168ca58eef`. The canonical Mac checkout was
`/Volumes/AirBackup/home/Documents/Ongoing Local/Project 2 - Map TPOT - clean-main`,
at descendant `04d3b890dd4ae1a1392000c8a333382e0aa40332` on
`codex/curator-review-shell`. Its dirty documentation/acquisition work and the older
dirty TPOT checkout were preserved. Production deployment/state was not inspected.

All remediation is in branch `codex/security-tpot-20261002`, isolated worktree
`/Users/aditya/Documents/Codex/2026-10-02/task-4/tpot-security`.
Root AGENTS.md was read; canonical `.agents/skills` was absent. User-authorized
separate agents handled Flask, outbound, gallery and local/publication work, with
a separate read-only reviewer. No unrelated repository was changed.

## All 19 findings

"Fixed" below describes the reviewed code contract, not an executed production
rollout. "Mitigated" identifies an intentionally disabled capability or a remaining
historical/operational decision. Source hypotheses were checked before patching.

| ID | Validated disposition and delivered behavior | Evidence / remaining boundary |
|---|---|---|
| T01 | Mitigated: anonymous/unauthorized force is denied; signed exact-body grants, atomic integer-microdollar reservations before provider work, honored NX locks, nonrefunded spend/nonces, bounded concurrency and response/deadline caps. Sponsored generation defaults disabled. Public approved cache and browser BYOK remain available. | Real disposable Redis tests race duplicates, final budget and concurrency; provider mocked. Actual billed upper bound must be established before enabling sponsored work. Reservation ledger is bounded; no claim that current image billing fits it. |
| T02 | Fixed for new publication: signed single-use owner/content approval, schema2 ownership, validated/reencoded raster data, exact owned Blob origin/path, atomic global/handle/concurrent/lifetime quotas, bounded pages/versions and 90-day visibility. | Actual Sharp decoding + Redis Lua tests. Legacy records hidden; physical storage cleanup/owner migration remain unapproved. |
| T03 | Prevention implemented; historical exposure blocked on explicit cleanup decision. CI changed-path allowlist and ignores reject newly committed private/candidate artifacts. | Git path names and one CSV schema header only; report's personal record/ID counts were not independently recounted. Existing tracked files/history/copies remain untouched; do not push this branch without publication review. |
| T04 | Mitigated: private auth plus shared nonqueued process admission; `/analysis/run` and `/metrics/compute` disabled unconditionally pending a real bounded worker supervisor. | Synthetic cross-process tests; no production reachability claim. Remaining authenticated lightweight graph reads/discovery can still be expensive on a large approved snapshot. |
| T05 | Fixed for new feedback growth: transactional 20,000-row quota, finite inputs, 4KiB context, 30-day TTL, bounded memory reads. | Independent-store quota and expiry tests. Legacy rows preserved; historical cleanup and idle physical expiry maintenance need approval. |
| T06 | Fixed: Golden label/prediction/evaluation/taxonomy/tag mutations default-denied without curator auth. | Missing/wrong/configuration-denial and authenticated positive contracts. |
| T07 | Fixed for new log growth: authenticated bounded entries, finite rotating frontend/API logs, shared filesystem locks. | Concurrent rotation/permission tests. Existing oversized/unsafe logs fail closed; archival/repair unperformed. |
| T08 | Fixed: validated canonical request keys, TTL/LRU/count/serialized+retained-byte ceilings, bounded discovery neighborhoods, no-cache respected. | Cache pressure/TTL/immutable result and schema tests. Caches remain finite per process. |
| T09 | Fixed prevention: recursive field projection, strict duplicate-key rejection and upload field allowlist, candidate manifest, approval of exact data/search/policy digest, immutable no-overwrite releases. Auto-export prepares local candidates only. | Synthetic export and Node upload contracts. Allowlisted free text still requires human value review; publication/production release selection not authorized. |
| T10 | Fixed: deliberate open ingestion authorizes ingestion only; admin/settings/read/purge independently require curator auth, including standalone blueprint. | Open/token-gated ingestion matrices and private admin denial/positive contracts. |
| T11 | Fixed: cluster label mutation requires curator auth before stores. | Backend auth contracts and analyst-client header routing tests. |
| T12 | Fixed private Golden/graph/account/community reads. Scan's anonymous research-note/source claim disputed at current HEAD: these routes already had curator-only gates. | Central default deny reinforces existing note auth; health/OPTIONS and deliberate ingestion alone allowlisted. Flask public exposure remains unverified/local analyst context. |
| T13 | Fixed scoped enrichment transport: resolve bounded DNS, pin public peer, verify peer, preserve original TLS name/Host, revalidate every redirect, ignore proxies/caller credentials. | Synthetic DNS/TLS/socket tests only. Four stalled OS resolver threads exhaust capacity and fail closed until they return. |
| T14 | Fixed new enrichment fetches: absolute deadlines include TLS/headers/body, framing+encoded+decoded byte caps, compression-bomb checks, image pixel/frame limits and link/image count bounds. | Synthetic streaming/compression/image tests. Existing caches untouched; no live URL probing. |
| T15 | Fixed: archive decoded/cache bytes, depth, sections/records/strings and wall time bounded; validate before cache or database mutation. | Temporary synthetic malformed/large archives; no personal archive reads. |
| T16 | Fixed: bounded typed JSON cookies; pickle rejected without loading, approved X/Twitter domains only. | Malicious synthetic pickle rejection and JSON round trip. Legacy cookie recapture required. |
| T17 | Fixed executable/artifact-allocation boundary: safe numeric/string NPY/NPZ and CSR arrays/JSON metadata throughout producers/consumers; preflight ZIP directory, NPY header/dtype/shape/size before allocation. Frozen contract explicitly schema2. | Tiny forged 8TB header, zero-width dtype, object/pickle and compatibility contracts. Old frozen data/manifest untouched; safe regeneration and scientific re-certification required. |
| T18 | Fixed: crawler redirect and gallery reads require retained schema2 owned raster objects; no arbitrary remote fetch/redirect. Browser cache migration hides old remote URLs, preserves local BYOK raster, validates new card-shaped Blob URLs. | Endpoint/decoder/URL/cache tests. Server enforces exact configured store; frontend pattern alone is not an ownership proof. |
| T19 | Fixed future cookie writes/reads: no-follow owned directory walks, atomic no-clobber0600 JSON, regular owner/type/mode checks, private directories. | Temporary permission/symlink contracts. Existing real secret files not read, chmodded or rotated. |

Detailed source evidence, exact scoped file inventories and residuals:
[Flask](security-flask-20261002.md), [outbound](security-outbound-20261002.md),
[gallery](security-gallery-20261002.md), [local/publication](security-local-publication-20261002.md).
The complete combined changed-path manifest is
[security-tpot-20261002-files.txt](security-tpot-20261002-files.txt).

## Verification and independent review

Initial RED contracts reproduced anonymous paid force, fail-open quota storage,
unapproved gallery bytes/URLs, missing private gates, oversized feedback, pagination
loss and unsafe local formats. Independent review additionally found gallery nonce
replay consuming quota, tiny forged NPY allocations, zero-width string conversion,
duplicate JSON keys, zero-SHA CI baselines, outbound header/TLS deadline gaps and
same-grant generation polling. These were repaired and exercised with synthetic
contracts. The final waiting path performs one admission POST and at most three
cache-only GETs; final202 remains waiting, never an undefined image success.
Publication of approved existing BYOK pixels does not start another paid request.
Navigation derives grant readiness; grants stay only in tab memory.

Integration evidence as of 12:11UTC (17:41IST): full offline Python aggregate
**1970 passed,5 skipped,20 inherited SciPy warnings** in98.05s; full public-site
**265 passed across33 files** with disposable Redis and mocked provider/Blob;
strict Node publication **6 passed**; graph-explorer **819 passed across58 files**
and production build. Public production build succeeded after the small ResultArea
extraction. A separate177-case run reproduced an intermittent cross-process log creation
race. Bounded open-existing/exclusive-create retries fixed it;183focused tests,
60Flask verifier contracts and22independent cross-process tests passed.

Independent evidence (overlapping, not additive):249 Python security/compatibility,
91 public UI/API,6 Node publication,121 private-client tests passed. Reviewer found no remaining code blocker after the final log fix and reviewed
the full19-finding matrix at12:15:41UTC/17:45:41IST. Human verifiers are `scripts/verify_security_public.py`,
`verify_security_flask.py`, `verify_security_outbound.py` and
`verify_security_local_publication.py`. Redis contracts must not be skipped for
security sign-off. CI provides an isolated Redis service; local verification used
a temporary Unix socket, no TCP or persistence. Test target guards reject production
URLs. Final commands/results and reviewer verdict are recorded below.

Public-site compatible dependency remediation ended at Sharp0.35.5, Vite8.3.2 and
Vitest4.1.11; `npm audit fix` reported0 vulnerabilities. No model call, live exploit,
production Redis/Blob access, personal-record inspection, persistent access or
deployment occurred. Tests use temporary synthetic stores and mocked external APIs.

## Milestones and calibration

Verified root start:11:21:48UTC /16:51:48IST. Original estimate3hours, range2–4hours,
retained throughout. Initial assessment arrived at parent by verified upper bound
11:24:51UTC /16:54:51IST, before17:04IST combined-plan deadline. A prior16:57
timestamp label was corrected; it was not an actual observed start/completion.

| Root milestone | Original target IST | Measured progress / current estimate |
|---|---|---|
| Public paid-budget/gallery fix and contracts |17:45|Final265 run started17:44:26; verified completed upper bound17:46:47; exact completion was not sampled|
| Flask/local boundaries and scoped regression |18:40|First Flask handoff17:18; local handoff17:33:56; outbound17:25:39; log concurrency follow-up completed17:43:32 (23m37s versus35estimate)|
| Aggregate, independent review, docs and local commits |19:50|At17:42 integration is ahead of original estimate; revised handoff18:15 contingent on log fix/review and hygiene checks|

Scoped estimates retained: gallery70–90minutes, measured about21minutes from its
first recorded assessment to independent-review milestone; outbound80minutes,
actual31m01s; Flask70minutes to first handoff about24minutes plus35-minute
cross-process follow-up; local90–120, revised120–150 due producer/consumer format
compatibility, actual39m29s. Shared existing Python/JS dependencies and parallel
authorized work shortened estimates; review added concrete work, not completion
certainty. Root current confidence0.88 in synthetic remediation coverage; lower
confidence in operational migrations and actual provider billing until validated.
Estimates exclude owner cleanup decisions, new bounded-analysis runner and deployment.

## Reviewable deployment sequence — not executed

1. Review this local patch and exact changed paths; obtain separate parent/user
   authorization before any branch/PR publication. Existing public-Git artifacts
   must be considered before pushing. Do not delete or rewrite them without exact
   cleanup approval. Preserve dirty canonical work during eventual integration.
2. Install updated Python/Node requirements in a new approved environment. Recapture
   cookies as JSON. Regenerate safe graph caches and a new schema2 frozen bundle,
   verify node-order/provenance bindings and scientifically re-certify; preserve
   old data and manifest. No legacy pickle conversion is provided.
3. Keep Flask private. Configure existing curator/extension token mechanisms and
   matching private analyst UI/CORS in an approved staging environment; do not
   publicly publish the token-bearing analyst bundle. Cooperating workers share
   the same owned snapshot/log roots and capacity. Do not unlink active lock files.
   Whole-graph HTTP work remains unavailable until an independently bounded runner
   is implemented; proposed3hour runner work needs a runtime/limits decision.
4. Configure a strong capability-signing secret, exact owned CARD_BLOB_BASE_URL and
   standalone Redis in approved preview. Gallery Cluster cross-slot storage is
   unsupported/fails closed. Issue offline short-lived exact-body generation or
   gallery capabilities using `public-site/scripts/mint-card-capability.cjs`.
   Generation body must include the browser's exact `force:false`/`force:true`.
   Subject approval is an operator publication policy, not verified social login.
5. Leave CARD_SPONSORED_ENABLED disabled. Before enabling, independently establish
   a provider-enforced worst-case image/text charge at the fixed model/parameter/
   price filters, make reservation at least that ceiling and verify uncertainty
   behavior without spending until authorized. The new ledger uses
   `card:{admission}:budget:<UTCdate>` rather than old `budget:<UTCdate>`;
   seed conservatively from approved accounting or wait for a new UTC day. Never
   erase prior spend, reset nonces or reduce reservations to bypass controls.
6. Dry-run legacy gallery ownership and exact owned-object retention manifests;
   approve migration/deletion independently. Until then legacy entries stay hidden
   and hard lifetime ceilings prevent unbounded new uploads. Do not reset that
   ceiling without confirmed approved cleanup. Cached redirects can persist6minutes.
7. Prepare public snapshot candidate, review fields AND values, approve exact digest
   separately, validate-only before any public upload. Immutable release upload and
   optional PUBLIC_SITE_RELEASE_DIGEST selection are separate authorized actions.
   Invalid selector fails closed; unconfigured selector preserves existing dataset
   paths until an approved rollout. Existing public snapshots are not retrospectively
   audited or removed by this patch.
8. Run human verifiers and aggregate suites in synthetic staging, verify approved
   cache/BYOK/public gallery and authenticated analyst UX, then obtain deployment
   approval. No rollout, credential rotation, visibility change or history cleanup
   is implied by the local security commit.

## Maintenance

GenerateCard and generate-card were split below300LOC; ResultArea was extracted
so App also fits. Discovery, archive/export/publication and outbound responsibilities
were extracted. Other inherited monoliths remain explicitly tracked in ROADMAP
and WORKLOG; unrelated scientific/UI refactoring was not mixed into this patch.

## Final integration evidence

- Post-log-fix offline Python aggregate:1976passed,5skipped,20 inherited SciPy
  warnings in91.96s. Three Supabase connectivity tests require a live secret and
  two legacy-database migration tests require a real unavailable database; neither
  was run. One subsequently added CI private-scope regression passed separately;
  its synthetic .md/.py sentinels exercise all excluded private roots.
- Public aggregate after final ResultArea extraction:265/265 across33files; actual
  disposable Redis DB2/3/4 and raster decoder, mocked provider/Blob. Public production
  build succeeded. Earlier graph aggregate819/819 and productionbuild remain valid;
  no graph source changed after that run. Strict Node publication6/6.
- Required human verifiers: public108contracts/noRedis skips +6Node; Flask60;
  outbound74; local51Python +6Node,476-source nonexecutable-loader audit. All pass.
- API contract23frontend paths/80routes/0gaps, CI hygiene25/25, docs hygiene9/9
  and diff whitespace pass. API verifier was rerun with a fresh private temporary
  log root; prior0644test logs correctly failed closed and were not chmodded.
- Final independent review: no codeblocker, with249Python/22cross-process/91public/
  40App-cache-publication/6Node/121private-client passes (overlapping, not summed).
  Late CI conflict scanning is limited to source/document extensions and excludes
  data, Related data, docs/private and docs/dossiers in root/project layouts.
- Exact179changed paths are listed in the companion manifest. No paths under
  data or Related data changed. A local commit/patch will record final hashes; no
  branch, PR, deployment, production setting or historical data change was published.

## Safe publication recommendation — publication still paused

Path-only Git inspection finds the cached `origin/main` at the scanned commit
6f030442b58ee56d74a1b0af7921e9168ca58eef. Its current remote freshness has not
been checked. The audited categories already exist at that cached remote base:
external Related-data archive; audit/review and coverage cohorts; queue/holdout
identifiers; graph identity mappings; calibration/relevance/evaluation artifacts;
scientific/price manifests. There are no data/Related-data path changes between
that base and the canonical04d3b890 parent. This establishes path ancestry only,
not content approval, current remote state or an absence of historical disclosure.

Do not push the current security branch as-is: it also carries unpublished
canonical commits between the cached remote and04d3b890, which are outside this
security publication approval. A source-only patch was generated from the reviewed169source/config/test/CI paths.
Using a disposable alternate Git index seeded from that cached remote commit,
`git apply --cached --check` passed without reading/materializing private artifact
contents or changing the branch/real index. This is an applicability check, not
a full regression run on the older base. After explicit parent/user approval, fetch only
the intended repository's current remote metadata/ref and verify the chosen base.
Prepare a fresh local branch on that approved existing base; apply only the
reviewed source/config/test/CI/docs patch, never data files, archives, credentials
or old scientific artifacts. If context or dependencies require preceding local
changes, surface and review those separately; do not silently include all commits
from the canonical branch or squash the entire remote-to-worktree delta. Repeat
aggregate/security checks and a path-only committed-diff publication gate.

A clean source-only patch can avoid introducing NEW artifact blobs in the branch
delta if it applies to that approved base and all final changed paths pass the
allowlist. It cannot remove or remedy historical private artifacts already in
the base/history, and a draft PR can draw attention to them. Resolve the owner's
publication policy for inherited artifacts before even that publication. Existing
public contents/copies, visibility changes, deletion and history rewriting need
a separate exact cleanup decision. Local commits and review patch remain private
workspace deliverables; no base was fetched, branch published or data deleted.

Public milestone calibration correction: the final265-test run logged START
17:44:26IST, not completion. Independent review reported17:45:41IST; root's
verified completed-run/review clock upper bound is17:46:47IST. Do not invent an
actual completion time or definite1m47slip from that upper bound. Original17:45
public target and conditional18:15handoff are retained; late waiting/cache/readiness
review fixes and ResultArea extraction are the concrete added work.

Local implementation commit:0b38e22 (`fix(security): enforce TPOT trust and
resource boundaries`). Staging exposed trailing blank lines in four new modules;
the final follow-up removes them and includes diagnostics. The final combined
base-to-HEAD whitespace check is the sign-off boundary. A source-only review patch
is available outside Git in the task workspace; it cleanly applies to cached6f030
using an alternate index, but needs full regression on the refreshed approved base
before publication. Nothing was pushed.
