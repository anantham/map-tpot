# Security remediation: source-only remote-base review

Date: 2026-10-02. Base: `6f030442b58ee56d74a1b0af7921e9168ca58eef`.
Branch: `codex/security-tpot-source-only-20261002`.

The scan's 19 findings were hypotheses. Source inspection and synthetic tests
validated the supported boundaries below. Flask reachability was not established;
its findings concern the local/private analyst API, not a claimed public service.
The patch changes source, configuration, tests and documentation only. It carries
no personal records, data migrations or inherited unpublished commits.

## Findings and dispositions

| Finding | Result and remaining decision |
| --- | --- |
| T01 paid card abuse | Signed expiring request capabilities; atomic Redis budget/nonce/NX-lock/concurrency reservation before paid work; failures remain charged conservatively. Sponsored generation is disabled by default until an approved worst-case provider charge is verified. Anonymous cached reads and BYOK UX remain available. |
| T02 gallery ownership | Publication capability binds owner, handle and content digest, rejects replay and requires exact configured owned Blob storage. Quotas reserve before writes/paid work. |
| T03 public Git artifacts | Default-deny changed-path allowlist and CI prevention reject unknown locations and sensitive artifacts. Allowed source/docs still require human content review. Historical exposure remains; deletion, visibility changes and history cleanup need separate authorization. |
| T04 expensive graph work | Curator authentication and shared process-independent bounded admission. Unsupervised whole-graph analysis/metrics return 503 until a worker with hard runtime/memory enforcement is implemented. |
| T05 feedback workloads | Finite bounded inputs, transactional 20,000-row admission and 30-day expiry for new feedback. Historical rows are preserved; physical cleanup needs review. |
| T06 Golden mutations | Curator authorization covers reads and mutations through the central policy. |
| T07 logging workloads | Bounded entries; frontend logs 1 MiB plus three backups, API logs 5 MiB plus five; shared locks, owner-only files and symlink rejection. Existing unsafe/oversized files fail closed. |
| T08 cache/graph workloads | TTL/LRU count and byte caps, validated numeric controls, bounded neighborhoods and retained/serialized output limits. |
| T09 publication projection | Explicit field policy, immutable digest-addressed release uploads and exact-digest approval. Automatic export no longer publishes. Human review of candidate values remains necessary. |
| T10 extension ingestion | Optional unauthenticated ingestion does not grant analyst read/admin/purge access. Those operations require curator authorization. |
| T11 cluster mutations | All cluster/private operations require curator authorization; mutation behavior remains covered by regression tests. |
| T12 private reads | Default-deny central route policy plus origin-scoped analyst client token. Notes/source routes already required authorization at this base; that narrower scan claim is disputed. |
| T13 DNS rebinding | Public-address validation, pinned connection peer, original TLS hostname/Host, redirect revalidation and four DNS worker slots with no waiting queue. |
| T14 unbounded outbound responses | Deadlines, encoded/decoded/framing caps, bounded redirects and enrichment work, single-frame raster validation; Pillow pinned. |
| T15 archive bounds | Byte, record, depth, section, string and time limits before persistence. |
| T16 unsafe cookie pickle | Legacy pickle is rejected; validated JSON cookies use approved domains and atomic owner-only storage. Recapture is required rather than unsafe automatic migration. |
| T17 graph artifact pickle | Checked typed NPY/NPZ/CSR and JSON metadata replace executable deserialization; header/dtype/shape/expansion bounds precede allocation. Legacy artifacts require rebuilding and frozen-manifest recertification. |
| T18 gallery retention/storage | 500 handles, three versions/handle, 90-day visibility, 100 global/day, five/handle/day, two concurrent and 1,500 lifetime uploads. Existing untrusted records are hidden; physical deletion/retention migration is separately gated. |
| T19 cookie permissions | New directories 0700/files 0600; existing cookie files must be regular, current-user-owned and 0600. Directory walking rejects symlinks and atomic writes do not clobber. Existing parent directory owner/mode and cookie hard-link counts are not validated; review existing local directory placement separately. |

## Verification and limits

Fresh-base aggregate: **1,933 Python passed, five skipped** (77.63 s; 20 inherited
SciPy warnings), **265 public tests / 33 files**, **794 graph tests / 52 files**,
**six Node publication contracts**, and both production builds succeeded.
The graph build retains inherited large-chunk warnings. Python skips concern
unavailable Supabase credentials and legacy database migration inputs; no security
contract was skipped. Public tests used an explicitly disposable persistence-free
Redis Unix socket, never production Redis. No paid provider requests, live exploit
probes, private chat reads or Blob writes occurred.

The sparse worktree excluded personal/unknown artifacts before checkout. Only the
unchanged static `data/golden/taxonomy.yaml` and dated provider price-card JSON
were included for existing schema/planning tests. An initial run with both absent
failed 72 tests plus five setup cases; restoring these two public configuration
files made the complete suite pass. The inherited `medium_graph` binary fixture
was deliberately not materialized: its two cluster verifier commands remain
unverified locally. Independent synthetic artifact compatibility tests passed.
At this initial checkpoint, GitHub CI was the next environment check; subsequent
hosted results are recorded below.

Independent fresh-base review found 167/169 original source changes byte-identical
to the previous reviewed patch. Two differences reflect absent older-base private
blueprints, with the central policy retained. It passed 244 Python boundary tests,
42 artifact compatibility tests, 117 public tests, 121 analyst-client tests and six
Node tests. These overlap aggregate evidence and are not summed into a total.

Required verifier reruns also passed: public 108 plus six Node contracts, Flask
60, outbound 74, local/archive/artifact/publication 51 plus six Node contracts;
463 Python source files audited with zero executable deserialization consumers.
CI discovery 25/25, docs hygiene 9/9, API contracts 23 frontend paths/77 backend
routes/zero gaps. These checks overlap the aggregate suites.

Human-readable verification commands, from `tpot-analyzer/` with dependencies:

```sh
python scripts/verify_security_public.py --redis-socket /tmp/tpot-security-redis-20261002.sock
python scripts/verify_security_flask.py
python scripts/verify_security_outbound.py
python scripts/verify_security_local_publication.py
python scripts/verify_ci_discovery.py --base 6f030442b58ee56d74a1b0af7921e9168ca58eef
python scripts/check_publication_files.py --base 6f030442b58ee56d74a1b0af7921e9168ca58eef
python scripts/verify_docs_hygiene.py
python scripts/verify_api_contracts.py
```

## Calibration and milestone evidence

Original implementation start: 11:21:48 UTC / 16:51:48 IST. Original estimate:
three hours (range two–four hours), dependent on dependencies and
independent review. Local reviewed handoff sampled ready at 12:28:28 UTC /
17:58:28 IST: **66m40s actual**, faster because explicit parallel scopes, synthetic
fixtures and separate safety-disabled paths reduced migration work. This did not
complete deployment or historical cleanup. The public tranche's exact completion
was not sampled; its verified run/review upper bound was 17:46:47 IST.

Fresh remote-base/publication follow-on start: 12:31:14 UTC / 18:01:14 IST, separate
from implementation. Estimate 25–40 minutes, confidence 0.80: ten minutes for base
and sparse checkout, 15–25 for regression, five for final review/commit (overlap).
Independent source re-review finished 12:43:03 UTC / 18:13:03 IST, 7m39s versus its original
25–40 minute estimate, aided by byte-equivalence; final config/docs review is a later milestone. PR, CI and Codex review completion
are external dependencies and are not represented as complete by local test results.

## Publication and deployment gates

This branch is explicitly authorized for GitHub publication and Codex review.
It was initially published as a draft; the owner subsequently authorized readiness.
Both Vercel configurations suppress automatic deployment for this branch only,
using [documented Git configuration](https://vercel.com/docs/project-configuration/git-configuration).
Production settings are unchanged; merge and deployment remain unapproved.
[Codex GitHub review](https://developers.openai.com/codex/integrations/github) is
verified separately through the actual PR trigger/reaction/review, not inferred
from installing the GitHub connection.

Before any separately approved rollout: install locked dependencies; provision
matching strong curator/card signing secrets outside source; configure exact owned
Blob origin and standalone compatible Redis; keep sponsored generation off until
billing ceilings and reservation amounts are approved; migrate the old budget
ledger conservatively or start on a new UTC day; rebuild/recertify safe artifacts;
recapture JSON cookies; decide legacy gallery/feedback retention and historical
Git cleanup. No existing data was deleted, credentials rotated, repository
visibility changed, branch merged or service deployed during this patch.


## Hosted runtime follow-up — 2026-10-02

Draft PR #11 was created at 12:51:35 UTC / 18:21:35 IST: 20m21s from the
separate fresh-base start, versus the 25–40 minute forecast. Source-only head
`1f8109faff8f2057101cdb88dd653610d3577ba2` was verified against remote metadata.
A manual Codex request was acknowledged by the connector bot at 12:52:05 UTC;
this is not proof of completed review or the automatic draft-to-ready trigger.
Read-only Vercel deployment metadata showed no deployment after the branch push.

First hosted CI: public and graph tests/builds passed; both inherited cluster
verifiers at granularity 25 and 40 passed. Python 3.11.16 returned 1,932 passes,
five skips and one failure: its newer HTTP parser rejected >100 trailers earlier
than the local 3.11.15 parser, exposing a raw HTTPException rather than the
guarded BlockedURLError contract. This was a supported-runtime error contract
gap; the response was already closed and no excess response was accepted.

Two deterministic public safe_urlopen/read tests reproduced raw HTTPException
and IncompleteRead before the correction. The production expected-parser error
tuple now normalizes HTTPException (including IncompleteRead) and closes the
stream. The adversarial trailer test is retained unchanged. Focused outbound
verification passed 76 tests; complete Python regression passed 1,935 tests,
five skips and 20 inherited warnings in 78.31 seconds. The strengthened parser
module rerun passed 22 tests, checking closure before context exit. Independent
outbound re-review passed 76/76 and an unmocked truncated-chunk diagnostic at
12:59:05 UTC. One earlier 50 ms timer assertion was scheduler-sensitive under
concurrent load and passed on rerun; no response acceptance was observed. The
new-head hosted rerun and completed Codex review were still pending at that checkpoint. Follow-up estimate: 10–15 minutes for correction,
independent review and CI, with hosted review completion an external dependency.

## PR review corrections and aggregate checkpoint

Hosted CI on `9b1346dfc2eef5b66fdf2a00e4025165ea62d741` passed all three
jobs, including Python 3.11.16 (1,935 passed, five skipped, 94.90 seconds) and
both binary-fixture cluster verifiers. PR #11 became ready with explicit owner
approval at 13:03:01 UTC / 18:33:01 IST, 31m47s after the fresh-base start,
within its 25–40 minute estimate. The parser correction plus hosted green result
took 8m39s from the 12:54:22 checkpoint, versus the separate 10–15 minute estimate.

Codex's manual review completed at 13:03:51 UTC against the older first head
`1f8109faff`, identifying five supported gaps. These are corrected:

- Unknown publication paths now default to deny, including unrecognized exports.
- Hierarchy, membership, teleport and graph-search aliases share analyst workload
  admission. This closes authenticated concurrent workload bypass; it was not an
  authorization bypass. Hard per-request CPU/time/memory supervision remains open.
- The debug cookie consumer validates owned JSON before logging, database or
  browser activity; legacy pickle candidates require recapture.
- Gallery Lua validates every key type and canonical quota counter before writes;
  read-only gates and pre-serialization prevent the reviewed deterministic partial
  writes. The reviewed key-type and counter corruptions fail without mutating
  state. Paid-budget reservation
  and release received the same correction, including exhausted-budget cleanup.
- Interrupted immutable uploads resume only when owned-store metadata and bounded
  exact bytes match the approved digest. Existing objects are never overwritten.
  Independent review additionally reproduced mutable caller buffers during lookup;
  bounded synchronous copies preserve the approved bytes before asynchronous work.

Each correction has a reproduced failing contract followed by a passing regression.
Integrated checkpoint: **1,976 Python passed, five skipped** (47.26 seconds),
**318 public tests / 34 files**, **14 Node publication tests**, public production
build passed; graph source is unchanged since its 794-test/build pass. Required
Flask verifier passed 65; local verifier passed 87 Python plus 14 Node and audited
464 source files with zero unsafe executable deserialization consumers. Independent
review completed 13:26:50 UTC: Flask 81, local Python 65, Node 14 and real-Redis
contracts 85 passed, with no remaining blocker in these corrections. These scopes
overlap aggregate results and must not be summed. Production Blob compatibility
was checked against installed SDK code only; a live request was not authorized.

Correction phase forecast: 30–60 minutes from approximately 13:06 UTC, confidence
0.80, through review and hosted CI; automatic Codex queue time is external.
Flask tranche: 13:06:33–13:16:44, **10m11s** versus 20 minutes, confidence 0.90.
Local/publication tranche: 13:06:20–13:27:40, **21m20s** versus 35 minutes,
confidence 0.85. Its revised estimate slipped three minutes because independent
review added the mutable-buffer reproduction and repair. Gallery code/review was
ready by approximately 13:16 versus its 25–40 minute estimate, confidence 0.95;
the exact completion instant was not sampled. New-head hosted CI and automatic
EveryPush review remain to be observed after the substantive ready-PR push; no
additional manual review comment is used for this trigger test.

The debug script remains inherited size debt at 480→454 LOC; its extracted cookie
helper is 33 LOC. Historical disclosure, legacy migration/retention, safe-artifact
recertification, billing approval, merge and deployment gates remain unchanged.
