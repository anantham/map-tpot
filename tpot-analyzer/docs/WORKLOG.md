# Worklog - TPOT Analyzer

## Repository Preservation and Canonical-Main Consolidation (2026-08-23)

- [2026-08-23 13:10–13:42 IST] **Preserved, classified, integrated, and verified
  every intentional repository surface before the main push (Codex GPT-5)**
    - **Hypothesis / fallback:** confidence `0.94` that both divergent commit
      lines and the 51-path raw worktree snapshot could be consolidated without
      importing legacy sync/generated residue. Any unique legacy file, missing
      snapshot content, absent recovery asset, upstream drift, or failed gate
      was a stop condition. Recovery remained the six dated refs plus the
      standalone bundle; main stayed at `7cfb45f` throughout investigation.
    - **Preservation:** recorded exact refs for community archive `00214b4`,
      local-first `bb9a29e`, personal ontology `d1cd76b`, raw-first `81d844d`,
      the 51-path tree `bf2e61f`, and parked stash `21e50c0`. The 54,913,504-byte
      bundle verifies at SHA-256
      `f3ac9c2543ea403f90ae71176da2b99c4878c48da4c0fba7a3a34d9b7667a86b`.
    - **Legacy quarantine:** a read-only normalized content/history scan covered
      all 1,362 dirty records: 705 are represented in preserved current/history
      content and 657 are approved exclusions (653 `sync-conflict-*`, two
      generated Community Archive snapshot files, two registered worktree
      directories). Unique intentional residue is zero. The legacy checkout was
      not reset, cleaned, pulled, merged, or deleted.
    - **History integration:** `ab4204c` merges the 42-commit raw line;
      `26d6375` merges five personal-only commits and unions the two append-only
      conflicts (`docs/EXPERIMENT_LOG.md`, `docs/WORKLOG.md`). `014b081` repairs
      the raw branch's `docs/index.md:156` trailing blank-line gate.
    - **Snapshot decomposition:** `2fc2827` restores backend tag vocabulary and
      meta-notes (`src/api/routes/account_tags.py:1-252`,
      `src/data/account_tag_{schema,vocabulary}.py`, `account_tags.py:1-290`,
      `tag_meta_notes.py:1-141`, and tests); `572e1aa` restores source-section
      proposal binding (`research_notes_source.py:1-271`,
      `research_notes_sections.py:1-100`, and tests); `0e8740f` restores the 36
      graph-explorer workspace paths; `c7a8952` restores the product amendment,
      roadmap/worklog record, and `verify_tagging_workspace_ux.py:1-297`.
      Coverage is 47 byte-identical paths, two EOF-whitespace repairs, and two
      ordered Worklog/Roadmap unions: 51/51 represented.
    - **Consolidation gate (`scripts/_repository_consolidation_checks.py:1-222`,
      `scripts/verify_repository_consolidation.py:1-60`):** checks cleanliness,
      conflicts, whitespace, exact refs/dispositions, snapshot equivalence,
      stash exclusion, raw worktree hash, bundle hash/verification, live legacy
      classification, and optional pushed equality. It reports concrete counts
      and recovery-oriented next steps.
    - **Verification:** Louvain `2/2`; docs hygiene `9/9`; API contracts `23`
      frontend paths, `77` routes, `0` gaps; cluster fixtures at granularities
      25 and 40; Python `1,768 passed, 5 skipped` with 20 existing SciPy sparse
      warnings; public site `212/212`; graph explorer `791/791`; production
      builds green; tagging/data-safety verifier `10/10`. Node gates used the
      CI-pinned `22.23.1` after clean `npm ci` installs.
    - **Environment findings:** the first API-contract attempt was blocked from
      writing `logs/api.log` by the sandbox, then passed unchanged with normal
      checkout write permission. Default Node 26 was not used for release
      claims. Existing non-failing React `act(...)`, canvas debug, dynamic-
      import, chunk-size, and SciPy warnings remain visible and were not
      goodharted into this repository-only scope.
    - **Disposition at this checkpoint:** the integration branch is green and
      54 commits ahead of the fetched `origin/main`. Only local `main` will be
      fast-forwarded and pushed. Recovery refs, worktrees, legacy quarantine,
      bundle, and the parked prototype stash remain intentionally local.

## Raw-First Retrieval Slice 6H — Operator-Centered Tagging Workspace (2026-08-03)

- [2026-08-03 21:52 IST] **Moved the extensional judgment loop into the
  operator's primary workspace while preserving 93 real click events (Codex
  GPT-5 with focused storage and adversarial UX peers)**
    - **Hypothesis / fallback:** confidence `0.86` that evidence → centered
      judgment → consequence → collapsed audit reduces curation friction
      without changing tag semantics. Lost rows, auto-written proposals,
      overwritten note history, or a retrieval score shown as confidence were
      falsifiers; fallback was to retain the existing mutation API and revert
      presentation only.
    - **Judgment surface (`graph-explorer/src/AccountTagPanel.jsx:1-152`,
      `ResearchNotesInbox.jsx:1-209`, `researchNotes/AccountTagPanel.css:1-271`,
      `ResearchNotesReview.css:1-137`):** centers the working extension on wide
      screens, preserves evidence-first DOM order responsively, separates
      named `IN` / `NOT IN` regions, exposes retraction independently, and puts
      collapsed recent history last. Judgment loading/mutation moved into
      `useAccountTagWorkspace.js:1-133`; the queue rail moved into
      `ResearchNotesQueuePanel.jsx:1-89` at the actual feature seam rather than
      being split only to satisfy line count.
    - **Vocabulary and suggestions (`TagAutocomplete.jsx:1-96`,
      `tagSearch.js:1-58`, `TagSuggestions.jsx:1-142`,
      `src/data/account_tag_vocabulary.py:1-37`):** keyboard-accessible exact/
      prefix/substring/edit-distance reuse, history-backed vocabulary that
      survives full retraction, and collapsible Takes suggestions that remain
      inert until explicit `IN` / `NOT IN` action. Dismissal is explicitly
      browser-session scoped. Stale/invalid proposal artifacts are quarantined
      without hiding edited Takes text or its queue; old/current source
      receipts and the non-automated regeneration boundary are visible.
    - **Refresh-safe scratch state (`manualResearchStore.js`,
      `useManualResearchState.js`):** pasted accounts, frontier additions, and
      account-note drafts use a versioned browser-local store with provenance,
      merge without duplicate handles, survive remount, and fall back visibly
      to in-memory state on malformed/quota-limited storage.
    - **Working meaning (`TagMetaNote.jsx:1-112`,
      `src/data/tag_meta_notes.py:1-141`, `account_tag_schema.py:1-95`,
      `src/api/routes/account_tags.py:1-252`, `accountsApi.js:1-129`):** adds an
      authenticated append-only note per canonical `(ego, tag_key)`. Blank save
      is an explicit clear event; previous versions remain. The prose is a
      curator reflection, never an enforced definition or stronger evidence
      than the examples.
    - **Consequence language (`WorkingTagImpact.jsx:1-234`):** replaces system
      jargon with “Candidates this tag surfaces,” keeps “Model opinion — none
      yet” separate, and hides graph method detail behind progressive
      disclosure. No membership percentage or cluster-existence claim was
      introduced.
    - **Data safety (`scripts/verify_tagging_workspace_ux.py:1-297`):** the live
      DB is opened with SQLite `mode=ro` plus `query_only`; schema initialization
      runs only on a temporary consistent backup. Checkpoint observation was
      `current=93`, `events=93`, `accounts=52`, `tags=31`; migration preserved
      the two core counts and row digests and passed SQLite quick-check before
      and after. The verifier does not call a network, model, or paid API.
    - **Verification:** `python3 scripts/verify_tagging_workspace_ux.py` →
      `10/10` checks; backend `24 passed`; frontend `47 passed`; `$0` spend.
      Full regressions: Python `1,698 passed, 5 skipped`; graph explorer
      `786 passed`; production build and scoped ESLint passed.
      Initial behavior-first tests failed on the old workflow as predicted, and
      the historical-vocabulary test first reproduced tag disappearance before
      the extraction fixed it (EXP-041).
    - **Known limits / next:** lexical fuzzy search is not semantic similarity;
      suggestion dismissal is browser-session scoped; scratch state is local,
      not server-synced; tag-note reads are bounded; proposal regeneration is
      external; candidate ranking is uncalibrated retrieval. Serve the
      revision, perform live wide/narrow QA, then test one add/retract and one
      meta-note version cycle before adding model machinery.

## Raw-First Retrieval Slice 6G — Visible Takes-to-Frontier Flywheel (2026-08-02)

- [2026-08-02 13:40–16:06 IST] **Connected Aditya's existing notes to an
  exact-tag, zero-spend feedback loop and kept cluster claims falsifiable
  (Codex GPT-5 with runtime, source-import, frontier, and adversarial-review
  peers)**
    - **Hypotheses:** the local runtime could be made reproducible (`0.98`), all
      57 Takes accounts could reopen with inert source-backed proposals
      (`0.90`), and source-side selectivity could expose an immediate judgment
      effect (`0.72`). A useful ranking was predicted before calibrated
      membership; a cohesion claim required observed inter-anchor evidence.
    - **Runtime (`scripts/dev_runtime.py:1-282`, `scripts/start_dev.sh:1-196`,
      `scripts/wait_for_backend.sh:1-31`, `graph-explorer/vite.config.js:1-30`,
      `src/api/server.py:1-190`):** resolve the canonical 11.35-GiB archive
      read-only, keep tag state in this worktree, share one unprinted ephemeral
      curator token between Flask and Vite, fix the UI at localhost:5184, and
      fail clearly on missing paths/dependencies/occupied ports. Replaced only
      the identified four-hour-old API process on port 5001 and launched the
      repaired paired runtime.
    - **Takes import (`src/api/routes/research_notes_source.py:1-217`,
      `researchNotesApi.js:1-58`, `useResearchNotesInbox.js:1-187`):** the
      authenticated private route returns exact text/hash/size/mtime plus 115
      model-proposed, non-gold suggestions for 57/57 handles. It sets
      `private, no-store`, validates the proposal artifact against the exact
      source hash, and never writes a tag. Missing configuration remains an
      explicit empty state and manual paste remains available.
    - **Exact target (`src/data/account_tag_queries.py:1-84`,
      `src/data/follow_frontier_archive.py:1-115`,
      `src/graph/target_follow_frontier.py:1-267`,
      `src/api/routes/research_notes.py:198-229`):** select anchors only by
      `(ego, tag_key)`, contrast positive/negative source-selectivity support,
      read one pinned archive transaction, and report coverage plus observed
      reachability/pair/cross-boundary edges. Corrupt polarity, missing tag DB,
      and archive failures fail closed. Missing edges remain unknown; status is
      evidence availability, never cluster existence or probability.
    - **Visible loop (`ResearchNotesInbox.jsx:1-250`,
      `AccountTagPanel.jsx:1-257`, `TagSuggestions.jsx:1-67`,
      `useWorkingTagSelection.js:1-72`, `WorkingTagImpact.jsx:1-219`):** reopen
      Takes automatically, show each source quote and proposal type, require one
      curator click for `IN` / `NOT IN`, refresh only that tag, retain the prior
      response, and display anchor/candidate/rank movement. The active default
      prefers a community-affiliation proposal. The screen explicitly labels
      selective follows as the only current channel and shows observed
      structure separately from uncomputed cluster confidence. Extracting the
      tag selection/revision state reduced the coordinator from 300 to 250 LOC
      at the feature seam.
    - **Adversarial result / real smoke:** initial topology names implied
      held-out recovery/cohesion and were rejected. Renamed them to observable
      stored-edge facts, made claimed-degree fallback explicit, filtered
      self-edges, and made missing/corrupt tag state fail closed. Disposable
      RomeoStevens76 + TVacha positive and SuttaSlime negative anchors produced
      542 candidates, but only `0.192` observed/effective positive-edge
      coverage, no covered negative neighborhood, and zero observed positive
      pair links. Ranking is useful; cluster existence is unsupported.
    - **Verification:** backend focused regression `39 passed`; frontend
      focused contract `21 passed`; full graph-explorer `761 passed`; Vite
      production build succeeds; scoped ESLint and `git diff --check` pass.
      Human scripts report runtime 7/7, frontier 5/5, and flywheel 6/6. The new
      integrated verifier is read-only and found/fixed two entrypoint defects
      before passing from plain `python3`.
    - **Live state/scope:** browser is open on Research Notes with all 57 Takes
      accounts. `@nicefryroll` selects `neo-buddhist`; with zero curator tags it
      truthfully begins at zero anchors/candidates. No proposal was accepted on
      Aditya's behalf. Persistent tag state remains `current=0, events=0`.
      Spend is `$0`; no twitterapi.io, OpenRouter, remote social-data, or gold
      write occurred.
    - **Next:** Aditya supplies the first judgments by clicking proposals or
      adding/removing tags. The UI will show the observed delta. After several
      covered positives and explicit negatives, run a frozen ranking bake-off;
      then add typed engagement and post-content channels as separable evidence.

## Raw-First Retrieval Slice 6F — Extensional Tagging Workspace (2026-08-01–02)

- [2026-08-01 17:34–2026-08-02 11:16 IST] **Shipped the smallest evidence-first, reversible
  account-tagging loop without manufacturing model confidence (Codex GPT-5
  with focused implementation, documentation, and adversarial-review peers)**
    - **Hypothesis (`0.78`):** the existing ego/account/tag projection could
      support multi-tag include/exclude/remove beside raw evidence if each
      mutation also produced inspectable history. Slash tags, cross-account
      async state, implicit provenance, identity switching, or a legacy score
      presented as target-specific position were registered falsifiers;
      fallback was the non-writing documentation contract.
    - `graph-explorer/src/ResearchNotesInbox.jsx`, `AccountTagPanel.jsx`, and
      `researchNotes/useResearchNotesInbox.js` now combine raw dossier evidence,
      reusable tag palette, independent `IN` / `NOT IN` assignments,
      first-class removal, queue classification state, and recent action
      history. Model position is explicitly unavailable and the queue remains
      manual until a target-scoped producer exists.
    - `src/api/routes/account_tags.py` extracts the focused curator-private
      route surface. `src/data/account_tags.py`, `account_tag_history.py`, and
      `account_tag_schema.py` preserve the current projection while appending
      transactional set/remove events, backfill legacy current rows once, and
      expose source plus evidence-binding status. Mutations require an explicit
      allowlisted curation source; UI writes declare human and verification
      scripts declare verification.
    - **Adversarial result:** the first implementation was rejected. Review
      found slash-containing tags could not be removed, stale loads/mutations
      could cross account navigation, queue rows hid tag state, handle fallback
      could silently change identity, verifier writes could pollute the human
      ego, absent provenance defaulted to human, and non-string tag JSON escaped
      validation. The slice now uses request invalidation and identity-keyed
      panels, an archive-ID gate that prevents unresolved handle writes,
      isolated verifier egos, fail-closed provenance, strict tag type
      validation, and a JSON-body removal route that preserves leading slashes.
      Live browser QA found one further product falsifier: the ontology owner
      was incorrectly required to be a graph node. Research Notes now accepts a
      session-local curator identity independently of the active graph ego and
      scopes loaded state by both curator and account.
      Final privacy/state review found anonymous tag-summary/GRF derived reads,
      curator casing that could split an extension, and failed reloads that
      appeared empty and writable. Derived reads now require curator auth, this
      UI canonicalizes the curator handle, and unknown tag state clears the
      queue cache, locks mutation, and offers Retry.
      Durable alias reconciliation remains required before any future
      handle-only write path is allowed.
    - **Verification:** 94 impacted Python tests and 121 expanded frontend
      tests pass; the suite covers the curation panel, clients, and private
      derived reads; the production Vite build passes with 1,121 transformed
      modules; the Research Notes verifier passes 13/13 checks; verifier scripts
      compile; and pure JS files plus documentation checks pass.
      `npm ci` restored the lockfile-pinned worktree runtime. Live browser QA
      loaded RomeoStevens76 plus 20 archived posts, displayed the empty current
      extension and unavailable model position, then completed an add/remove
      cycle with both sourced events retained in history.
    - **Runtime findings:** the worktree-local archive path was an existing
      zero-byte SQLite file, and the first frontend/backend port pairing was not
      in the CORS allowlist. QA therefore used the real archive explicitly and
      read-only, an isolated temporary snapshot/tag database, and an explicit
      local CORS origin. `npm ci` reported 23 dependency advisories (2 low, 8
      moderate, 11 high, 2 critical); no automatic audit fix was attempted.
    - **Scope:** no real account was persistently tagged, no project database or
      Community Gold schema was changed, and no external social-data, model, or
      paid API call, retry, debit, or spend was used. `npm ci` was the only
      dependency-network-capable step. The temporary QA tag was removed from the
      current projection; only its set/remove history remains in the disposable
      store. The 468-LOC live tagging verifier was safety-patched only; its
      responsibility split is recorded as debt rather than disguised by more
      module multiplication.
    - **Next:** let the curator inspect the sandboxed surface, connect an
      explicit persistent local tag store before lasting curation, add a
      queue-wide classification overview, collect 30 human examples under
      stable archive IDs, freeze `tag-v1`, and only then falsify a target-scoped
      score producer and disagreement ordering.

## Extensional Tagging Contract — Documentation Amendment (2026-08-01)

- [2026-08-01 17:09 IST] **Reframed personal social tags as mutable examples,
  with evaluation freezes instead of abstract definition gates (Codex GPT-5)**
    - **Hypothesis/result:** Research Notes plus ego/account/tag state can
      support reversible multi-tag curation without new gold schema; the
      all-tag GRF cannot supply a target-specific position. Inspection
      supported the first claim and rejected the second (EXP-035).
    - **Decision:** no intensional definition prompt; preserve `IN`, `NOT IN`,
      and removal history behind the mutable extension; freeze `v1`/`v2` only
      for evaluation and measure drift. Working tags remain non-gold, no new
      Community Gold module/schema is allowed before 30 human task-scoped
      judgments, and model/disagreement views wait for target-scoped output.
    - **Files:** ADR 021 appends the decision at lines 251–295;
      `docs/ROADMAP.md` makes the UI/freeze/producer sequence active;
      `docs/EXPERIMENT_LOG.md` records EXP-035; `docs/index.md` marks the
      amendment. No new document was added.
    - **Scope:** documentation only. No account was tagged, no Community Gold
      row/module or model artifact was created, and no database, network, or
      paid API was used.
    - **Next:** ship the evidence-first add/exclude/remove workspace and its
      history; collect 30 examples; freeze the first extension; then falsify a
      target-scoped producer before model position or disagreement ordering.

## Raw-First Retrieval Slice 6E — Model-Provisional Note Extraction (2026-08-01)

- [2026-08-01 14:55 IST] **Used the existing takes to reduce the first human
  gate to reusable ontology questions, without creating gold (Codex GPT-5 plus
  one context-isolated reading)**
    - **Hypothesis (`0.75`):** the dated takes alone would support both proposed
      answers for 7–9 of 12 accounts, leaving at most 3–5 accounts for human
      adjudication. More than 25% unresolved/abstaining slots or collapse of the
      two questions would falsify that expectation. Fallback was a private
      non-training artifact and grouped clarification, not paid acquisition or
      another persistence module.
    - Two same-family model readings used only the exact 10,311-byte takes
      snapshot. The primary reading was explicitly unblinded because it had
      already seen the panel strata; the context-isolated reading received only
      the takes and 12 handles and was instructed not to inspect the panel,
      protocol, logs, or strata. Exact agreement was required for a provisional
      consensus label.
    - **Result:** the confident-account prediction was rejected. The readings
      agreed on 18/24 slots (`75%`), leaving 6 `REVIEW` slots and 6 consensus
      `ABSTAIN` slots; only two accounts had two decisive consensus answers.
      The ambiguity did not require 24 clicks, however: all six disagreements
      collapse into three reusable rules—bare `dharma` shorthand, broad
      tantric/esoteric retrieval, and the scope of `not dharma`.
    - The private mode-0600 artifact
      `data/private/research-notes/dharma-boundary-pretrial-v1/model-provisional-pass-20260801T091859Z.json`
      binds the takes/panel/protocol/producer hashes, both rationales, exact
      source-line ranges, consensus rule, and explicit `may_train=false`,
      `may_score=false`, and `may_replace_human_pass=false` permissions. Its
      SHA-256 is `081cdb6deb80fc2086fbaba1d847434c87f56b11456f81e303beb7ac6a5809cf`.
    - **Verification:** JSON parse passed; 12/12 unique handles and 12/12 source
      ranges matched the hashed takes; permissions are 0600; no network,
      credential, external model API, database write, paid call, or spend
      occurred. This same-family agreement is a robustness diagnostic, not
      human reliability, ontology validation, or a ranking benchmark.
      Docs hygiene passed 9/9 and personal-ontology documentation passed 21/21.
      The existing inbox verifier passed its 23 backend tests, takes snapshot,
      and 10/11 aggregate checks; its sole failed check was environmental—the
      isolated worktree has no local Vitest binary. Two shared-runtime attempts
      then stopped at dependency resolution before test execution. No frontend
      source changed, and the loop was stopped rather than adding a repo symlink
      or a fourth environment workaround.
    - **Next:** resolve the three rule questions once, propagate those answers
      across the six affected slots, and acquire/review evidence only for the
      remaining true abstentions. Do not run the ranking bake-off against these
      model-derived labels as if they were Aditya's judgments.

## Raw-First Retrieval Slice 6D — Minimal Post-Abort Correction (2026-08-01)

- [2026-08-01 13:10 IST] **Fixed the demonstrated parser and privacy defects,
  then stopped disproportionate verifier work (Codex GPT-5)**
    - **Hypotheses:** confidence `0.98` that the documented `data.tweets`
      nesting explained the rejection and `0.98` that unconstrained exception
      text could disclose private values. Predicted REDs were the old envelope
      error and visible handle/tweet sentinels; both occurred. Fallback was the
      untouched aborted bundle, no retry, and no network/spend.
    - `src/evaluation/dossier_response_contract.py:133-198` now validates and
      returns the nested list; `dossier_snapshot_transform.py:107-167` consumes
      that value. Nested behavior is covered in the modified dossier executor,
      evidence, fail-closed, and snapshot tests and the six-check synthetic
      operator script.
    - `scripts/run_dossier_pretrial_acquisition.py:8-287` now encloses client
      open, acquisition, persistence, transforms, diagnostics, and client close
      in one fixed public-safe boundary. `dossier_private_diagnostics.py:1-45`
      stores only phase, exception class, and message hash. Sentinel,
      single-execution, close, diagnostic-write, and direct-entrypoint behavior
      is covered by `tests/test_dossier_cli_private_boundary.py:1-112` and
      `tests/test_dossier_script_entrypoints.py:1-35`.
    - Offline replay accepted all 20 captured tweet objects without emitting
      identity or content. No credential, HTTP call, debit, judgment, or project
      inference-model call occurred in this correction.
    - **Verification:** 57 targeted parser/privacy tests pass; the human-readable
      synthetic script reports 6/6; hermetic regression reports 1,655 passed,
      two skipped, and 20 existing sparse-matrix warnings. Docs hygiene,
      compilation, and `git diff --check` pass.
    - **Scope stop:** a generalized verifier prototype entered an open-ended
      tamper loop and multiplied modules under the 300-LOC gate. Human review
      correctly rejected that trade: it protected a four-call, zero-debit abort
      while the corpus still had no durable judgments. The prototype is parked,
      not shipped; the LOC gate is henceforth a review signal, not evidence of
      lower coupling.
    - **Next:** run the registered $0 ontology-boundary test, persist its first
      real judgments, then run the $0 ranking bake-off. Paid retry remains later
      and requires evidence that acquisition is binding plus fresh authorization.

## Raw-First Retrieval Slice 6C — First Live Dossier Attempt (2026-08-01)

- [2026-08-01 10:36 IST] **Rejected live-completion readiness while confirming
  the fail-closed boundary (Codex GPT-5 with three read-only peer audits)**
    - **Hypothesis (`0.90`):** the committed exact-plan chain would turn its
      first live responses into a completed blind dossier snapshot. Registered
      falsifiers were any schema/identity mismatch, missing durable event,
      retry, private console leak, or debit beyond the 3,846-credit local
      reserve. Fallback was an immediate no-retry stop with private evidence.
    - Executed plan `2470a84f…` once from commit `a4bb7a0`: frozen 12-account
      4/6/2 panel, maximum 26 calls, 12 profiles plus at most 240 recent tweets,
      and USD 0.03846 planned exposure. No panel, target, or action adapted to a
      response.
    - **Observed falsifier:** after the before-balance call and one validated
      profile, the first recent-tweets HTTP-200 response was rejected. The
      strict parser expected top-level `tweets`; the actual response used
      `data.tweets`, which existing `docs/TWITTERAPI_ENDPOINTS.md` and
      `scripts/fetch_tweets_for_account.py` already record. This is a local
      schema-contract/test gap, not evidence of corrupt returned data.
    - The captured nested list had 20 structurally valid, unique tweets; every
      author identity bound to the validated profile. These are aggregate
      integrity checks only, not content interpretation or a usable dossier.
    - The abort path then made its reserved after-balance call and stopped:
      four HTTP-200 requests total, four durable attempt/response/observation
      triples, one validated profile action, one rejected tweet action, zero
      retries/substitutions, and **0 measured credits debited**.
    - Private output remained confined to the ignored mode-0700 run directory;
      every file is mode 0600, with no symlinks or temporary files. Receipt
      SHA-256 `2b128d5e…`, partial-record artifact SHA-256 `20f76028…`, and all
      three frozen source byte hashes recomputed successfully. No completed
      evidence artifact, snapshot, judgment, or model call exists.
    - **Files recorded:** `docs/EXPERIMENT_LOG.md:1-69` (EXP-032) records the
      falsified hypothesis and methodology;
      `docs/experiments/2026-07-31-dharma-boundary-pretrial.md:3-129` records
      the halted protocol state and private artifact provenance; and
      `docs/ROADMAP.md:558-577` records the parser, privacy-boundary,
      live-verifier, and reauthorization gates. This entry is
      `docs/WORKLOG.md:3-46`. No new document or `docs/index.md` entry was
      needed.
    - **Next:** behavior-first support for the documented nested envelope,
      private-safe post-network failures, and a reusable live-bundle verifier.
      Do not rerun this attempt; any second paid attempt needs fresh explicit
      authorization after local verification.

## Raw-First Retrieval Slice 6B — Adversarial Pre-Spend Gate (2026-07-31)

- [2026-07-31 21:33 IST] **Rejected first-pass live readiness and hardened the
  private execution boundary (Codex GPT-5 with three computational-peer audits)**
    - **Hypothesis (`0.85`):** the EXP-030 final receipt and no-retry path were
      sufficient for one live run. Falsifiers were trackable private output,
      paid evidence lost on interruption, renamed holdout leakage, false-green
      dry preflight, unreplayable inputs, or a non-enforceable advertised cap.
      Fallback remained zero spend and the unchanged unbound preview.
    - The audit rejected readiness: output paths were unrestricted; safe
      responses lived only in memory; holdout exclusion used handles only; the
      mutable logical holdout and exact source files were not bundled; static
      plan validation occurred after dry preflight; and provider billing has no
      server-side dollar ceiling.
    - `dossier_bundle_io.py` and `dossier_execution_bundle.py` now enforce the
      resolved ignored private root, atomic exclusive fsynced 0600 artifacts,
      exact source copies, a private logical holdout snapshot, and per-call
      attempt/response/observation files before the executor proceeds.
    - `dossier_http_transport.py`, `dossier_transport_contract.py`, and
      `dossier_transport_observation.py` retain the fixed origin/allowlist and
      no-retry behavior while durably recording credential-free JSON bodies;
      rejected bodies retain only sanitized status/timing/byte hashes.
    - `holdout_snapshot.py`, `dossier_execution_preflight.py`, and
      `dossier_acquisition_executor.py` validate the full plan before credential
      access, bind the 368-handle/288-ID logical exclusion set, and stop after a
      matching profile ID before that target's tweets.
    - The runner preserves receipt, raw records, and canonical evidence before
      client close/transform, derives the snapshot ID from the frozen panel,
      rejects wrong local reserves before bundle/key access, and keeps private
      execution failures out of console output. Snapshot validation now rejects
      tweet IDs duplicated across accounts.
    - **Budget semantics:** 3,846 credits/USD 0.03846 is the pinned local reserve
      for exactly 26 no-retry calls, not a provider-enforced billing ceiling;
      the final balance measures any deviation after it occurs.
    - **Verification:** 145/145 focused tests, synthetic verifier 6/6, real
      private preflight, Python compilation, file-size gates, docs hygiene, and
      `git diff --check` pass. Network, credential read, provider response,
      database write, judgment, and spend remain zero.
    - Broad local regression: 1,648 passed and two skipped. The only three
      failures were pre-existing live Supabase calls in
      `tests/test_connection.py`; that file is not marked `requires_supabase`
      and failed DNS under restricted network. The isolation gap is recorded
      in ROADMAP rather than hidden or changed in this feature commit.

## Raw-First Retrieval Slice 6 — Fail-Closed Dossier Execution (2026-07-31)

- [2026-07-31 21:15 IST] **Completed the zero-spend executor, evidence, and
  snapshot chain (Codex GPT-5 with four computational-peer audits)**
    - **Hypothesis (`0.90`):** exact artifact preflight plus an injected,
      no-retry transport can turn one frozen plan into reproducible blind
      dossiers while stopping on the first hash/schema/identity/cap mismatch.
      Falsifiers were any unrecorded attempted call, retry, response-body leak
      into the receipt, mutable evidence, holdout overlap, or accepted drift.
      Fallback: keep the plan unexecuted and retain the unbound preview.
    - `src/evaluation/dossier_execution_preflight.py:1-296` binds the real plan,
      raw panel bytes, semantic price card, 4/6/2 strata, exact target intents,
      and read-only historical holdout exclusion before credentials/network.
    - `dossier_execution_contract.py`, `dossier_acquisition_executor.py`,
      `dossier_executor_types.py`, and `dossier_response_contract.py` implement
      exact acceptance, balance/action sequencing, strict provider envelopes,
      canonical timestamps and decimal identities, attempted-call receipts,
      descriptive sanitized failures, and no retries.
    - `dossier_http_transport.py` fixes the provider origin, three endpoints,
      parameter sets, timeout, credential redaction, and defensive private
      response capture; it takes an injected key rather than reading one.
    - `dossier_receipt_validation.py`, `dossier_evidence_artifact.py`,
      `dossier_snapshot_transform.py`, and `src/data/research_notes_snapshot.py`
      keep raw evidence private, reconcile every call/hash/balance, strip to
      display fields, and build immutable per-account and snapshot hashes.
    - Rejected an initial 298-LOC artifact module that met the numeric gate by
      packing constants onto long lines. The final SRP split is 213/207 LOC;
      this directly applies the project's Metric Gamer warning.
    - `scripts/run_dossier_pretrial_acquisition.py:1-264` defaults to no-spend
      preflight; live mode requires the exact total reserve, explicit env file,
      and a new private 0700 directory, writing 0600 receipt/raw/evidence/
      snapshot artifacts. `scripts/verify_dossier_pretrial_execution.py:1-197`
      gives human-readable synthetic verification.
    - **Verification:** 120/120 focused tests, synthetic verifier 6/6, real
      private preflight 10/10 aggregate fields, Python compilation, file-size
      gates, and `git diff --check` pass. No network, credential read, API
      response, database write, human answer, or paid credit yet.

## Raw-First Retrieval Slice 5B — Provenance-Link Correction (2026-07-31)

- [2026-07-31 20:45 IST] **Re-hashed the still-unexecuted plan after its
  profile-documentation slug proved noncanonical (Codex GPT-5)**
    - Prediction (`0.90`): the endpoint and prices would remain unchanged but
      the official source identity and every downstream semantic hash would
      change. Fallback: preserve prior private plans as superseded and make no
      request until preflight recognizes only the corrected hash.
    - Official references confirmed `/twitter/user/info` with a `data` object
      and top-level `tweets` for recent posts, but the canonical profile page is
      `get_user_by_username`, not the stored `get_user_info` slug.
    - `data/manifests/twitterapiio_price_card_20260730.json` and its pinning
      test now bind semantic SHA-256 `eab5a081…`; no price changed.
    - The replacement mode-0600 plan is `2470a84f…`, still 26 maximum calls,
      3,846 reserved credits, and USD 0.03846. The `3c66b735…` plan was retained
      as superseded alongside `f352851e…`; all remain unexecuted.
    - EXP-029 and the focused pretrial protocol record the falsifier and
      downstream invalidation. Focused acquisition tests pass 30/30; paid spend
      remains USD 0.

## Raw-First Retrieval Slice 5A — Telemetry-Reserve Correction (2026-07-31)

- [2026-07-31 20:05 IST] **Superseded the unexecuted dossier plan after a
  pricing assumption failed (Codex GPT-5)**
    - **Hypothesis and falsifier:** assumed the documented balance endpoint was
      free. Confidence was only `0.55`; absence of an authoritative price or a
      hard-cap boundary that passed without reserving the calls would reject
      it. Fallback was to spend nothing and widen the reserve.
    - **RED:** at a 3,830-credit cap, the old evidence-only planner incorrectly
      accepted 3,816 credits even though the required before/after balance
      observations were outside its budget.
    - **GREEN:** `src/evaluation/dossier_acquisition_plan.py:1-258` now emits a
      schema-v2 plan with two explicit `conservative_unverified` telemetry
      calls and counts their 30-credit reserve toward the hard cap.
      `tests/test_dossier_acquisition_plan.py:1-167` covers the exact manifest
      and boundary; `scripts/verify_acquisition_plan_contract.py:1-220` reports
      evidence and telemetry separately.
    - **Private receipt:** retained unexecuted plan `f352851e…` under an
      explicitly superseded filename. The replacement mode-0600 plan is
      `3c66b7353e393bb0b266000261204345bfce2031dbc617301e5ae600bc07fd56`:
      26 maximum calls, 3,846 reserved credits, USD 0.03846 under the unchanged
      USD 0.05 cap; holdout overlap remains zero and local coverage remains
      5/12 profiles and 1/12 timelines.
    - **Docs:** EXP-028 records the rejected assumption; ADR 022, ROADMAP, and
      the pretrial protocol carry the additive correction.
    - **Verification:** focused planner tests 12/12 and real private verifier
      7/7. No API/OpenRouter call, credential read, response, or paid credit.

## Raw-First Retrieval Slice 5 — Formative Acquisition Planning (2026-07-31)

- [2026-07-31 19:16 IST] **Falsified local-only dossier readiness and froze a
  non-executing USD 0.05 acquisition plan (Codex GPT-5 with three
  computational-peer audits)**
    - **Hypotheses, predictions, confidence, fallback**
        - `H-A1` (`0.70`): the private 12-account Dharma panel already has
          comparable profile plus recent-post coverage. Expected: most
          accounts have both locally; fewer than half falsifies readiness.
        - `H-A2` (`0.95`): current provider prices permit one standardized
          profile-plus-20-post dossier per account below USD 0.05. A stale or
          malformed card, cap overflow, or unverifiable price identity
          falsifies the plan.
        - `H-A3` (`0.95`): planning can remain credential-free and incapable of
          execution while pinning every target, action, reserve, price card,
          selection manifest, and canonical plan hash. Any environment/API
          access or `authorizes_execution=true` falsifies the separation.
        - Fallback: do not reuse either legacy fetcher. If the plan cannot be
          proved safe, continue with the visibly unbound UI and collect no
          trial answers or paid evidence.
    - **Investigation loop**
        - Attempt 1/3: a read-only canonical-archive coverage query rejected
          `H-A1`: 5/12 selected accounts have profiles and 1/12 has any local
          authored tweets; the populated timeline is not a comparable current
          dossier.
        - Attempt 2/3: code and peer audits rejected both historical paid
          fetchers for this run because their price assumptions, dry-run
          boundary, cap granularity, response receipts, and provenance are not
          safe enough for a new paid call.
        - Attempt 3/3: current official pricing plus pure behavioral contracts
          confirmed `H-A2` and `H-A3`. The exact fixed plan reserves USD
          0.03816 below a USD 0.05 cap and contains no execution capability.
    - **Changes (files + why)**
        - `data/manifests/twitterapiio_price_card_20260730.json`: extend the
          dated tracked card with official profile and recent-tweet prices and
          endpoint identities; the semantic card hash is
          `f795e1704f5d8bb0337f1d1deb3e81276750a98dd4485dac7285ff6f2f9dd2bb`.
        - `src/evaluation/acquisition_manifest.py:1-124`: isolate shared
          canonical JSON, handle, timestamp, exact-decimal cap, and self-hash
          rules so neither action planner approaches the 300-LOC boundary.
        - `src/evaluation/acquisition_plan_contract.py:1-186`: add the pure
          followings plan contract, worst-case 398-credit page reserve, and
          freshness/cap validation. It has no transport, credentials, or write
          path.
        - `src/evaluation/dossier_acquisition_plan.py:1-231`: add the pure
          fixed profile/recent-tweet dossier planner with atomic actions,
          selection-manifest binding, one-page bounds, deterministic target
          ordering, and hard-cap failure.
        - `tests/test_acquisition_plan_contract.py:1-168` and
          `tests/test_dossier_acquisition_plan.py:1-144`: behaviorally cover
          exact reserves, price/card drift, duplicates, invalid handles/pages,
          stale/future prices, cap overflow, deterministic hashing, and the
          non-execution flag. Dossier tests began against an intentional
          `NotImplementedError` RED implementation.
        - `scripts/verify_acquisition_plan_contract.py:1-214`: add the required
          human-facing verifier; it reports costs, counts, hashes, historical
          holdout overlap, local coverage, and the next gate without printing
          private identities. Optional plan output is exclusive and mode 0600.
        - `.gitignore`: exclude `data/private/`; the real panel and plan stay
          local with mode 0600 and are not staged.
        - `docs/EXPERIMENT_LOG.md` EXP-027, `docs/ROADMAP.md`,
          `docs/experiments/2026-07-31-dharma-boundary-pretrial.md`, and ADR
          022 record the falsification, plan / execute boundary, exact
          pre-answer cost, and remaining receipt gate. The focused pretrial
          extraction also returns the parent pilot below the 300-LOC gate.
    - **Private receipts and measured result**
        - Selection manifest SHA-256:
          `ce680f1a88fb9d4b2dd1af169c1ce741eaca3e9d3dcaa83f834f6d1cbfdc83ce`;
          12 accounts; `4/6/2` pre-answer strata; historical holdout overlap 0.
        - Plan semantic SHA-256:
          `f352851ed285493445bb2baecc3ef69714bc9db71ab945b3abe63b0c360fb8ab`;
          24 maximum calls; 12 profiles; 240 tweets; 3,816 credits; USD
          0.03816 under the USD 0.05 hard cap.
        - `authorizes_execution=false`. No credential was read and actual
          provider/OpenRouter spend remains USD 0.
    - **Verification**
        - Acquisition/dossier/seed price contracts → 33/33 passed.
        - Real private-plan verifier → 6/6 passed and wrote only the ignored
          mode-0600 plan.
        - Python compilation and `git diff --check` passed; all new production
          files remain under 300 LOC.


## Raw-First Retrieval Slice 4 — Independent-Band Quarantine (2026-07-30)

- [2026-07-30 18:55 IST] **Falsified independent-Lift entropy and blocked its
  stale bands from classification, export, and acquisition ranking (Codex
  GPT-5 with three read-only computational-peer audits)**
    - **Hypotheses, predictions, confidence, fallback**
        - `H-E1` (`0.99`): normalized entropy must be finite, bounded in
          `[0,1]`, and invariant to positive row scaling. A negative, >1, or
          scale-dependent result falsifies the implementation.
        - `H-E2` (`0.65`): correcting row normalization will preserve current
          specialist/bridge/frontier assignments. Any changed assignment makes
          it a taxonomy change requiring held-out evaluation.
        - `H-E3` (`0.80`): the entropy predicate contributes information to
          active banding. Removing it without changing a band falsifies this.
        - `H-E4` (`0.90`): stored bands and active membership affinities share
          one propagation run. Timestamp/count skew falsifies this.
        - Predicted safe outcome: centralize valid compositional entropy but
          fail closed for independent display bands rather than inventing new
          thresholds. Fallback: if a compatible evaluated band contract
          already existed, bind it to the exact artifact receipt; none was
          found.
    - **Investigation loop**
        - Attempt 1/3:
            - hypothesis: the current calculation is Shannon entropy over Lift.
            - test: reproduce it on the active NPZ, apply a 7x scale transform,
              and add synthetic scale/bounds/negative-input regressions.
            - result: rejected — historical values ranged
              `-1190.1798..1.9756`, with 30,434 outside `[0,1]`; the RED suite
              failed 4/4 for the intended reasons.
        - Attempt 2/3:
            - refined hypothesis: correct row normalization is a
              behavior-preserving numerical fix.
            - test: compare current bands with corrected entropy and with the
              entropy predicate removed.
            - result: rejected — correction changes 1,793 bands, while deleting
              the predicate changes zero. Specialist precedence also
              overwrites qualified bridges.
        - Attempt 3/3:
            - final hypothesis: blocking new classification is sufficient.
            - test: trace `account_band` through public export and
              `rank_frontier`, compare its creation timestamp/counts with the
              active NPZ, and add downstream regressions.
            - result: rejected — stale SQLite rows bypassed the classifier,
              public export joined them to a newer NPZ, and the ranker used
              synthetic `none` Lift as `1-p_none`. Both consumers now share the
              fail-closed mode guard.
    - **Changes (files + why)**
        - `src/propagation/entropy.py:1-43` adds one scale-invariant,
          non-negative row-entropy primitive with explicit zero-row
          convention.
        - `src/propagation/bands.py` owns classic thresholds, requires an
          explicit artifact mode plus coherent node/community dimensions,
          raises the descriptive independent-mode exception, and preserves
          pure historical classic classification.
        - `src/propagation/engine.py:24-33` delegates solver entropy to the
          shared primitive instead of clipping every Lift above one.
        - `scripts/classify_bands.py:1-212` becomes a thin classic-only
          persistence CLI and shrinks below the 300-LOC gate.
        - `scripts/_export_helpers/_community_extractors.py` first validates
          the supplied propagation artifact, then rejects every existing
          unbound `account_band` table even when the artifact is valid classic
          mode. `scripts/export_public_site.py` catches only that named
          quarantine error, logs it, and emits the safer classified-only
          fallback. This inherited 556-LOC helper and 388-LOC orchestrator
          remain decomposition debt; the safety patch does not broaden their
          refactor.
        - `scripts/rank_frontier.py` rejects both unsupported propagation
          artifacts and every unbound band table at its reusable loader
          boundary before zero uncertainty, synthetic `none` Lift, or
          version-skewed classic rows can steer API acquisition.
        - `scripts/analyze_frontier_confidence.py:15-31,61` rejects the same
          artifact before compositional entropy can be called confidence or
          combined with probability-like thresholds.
        - `scripts/_active_learning_helpers/frontier_quarantine.py`,
          `_account_selection.py`, `scripts/active_learning.py`, and
          `scripts/fetch_following_for_frontier.py` reject every current
          `frontier_ranking`-dependent automatic acquisition entry point
          before a database/API-key/spend path runs. Explicit handles remain
          available and receive no stale score or community metadata. The
          separate zero-outbound following selector remains an unvalidated
          coverage heuristic and is not claimed as an information-value
          policy.
        - `scripts/fetch_topic_seeds.py` now stores parsed tweets/profiles
          without writing an artificial `frontier_ranking` score;
          `scripts/verify_topic_seed_ingestion.py --handles-output` creates an
          inspectable explicit-handle handoff instead. EXP-006 is additively
          marked superseded.
        - `scripts/fetch_tweets_for_account.py` adds a source-exclusion option
          to the existing freshness check, and
          `_account_selection.select_accounts_by_handle` ignores
          topic-search-only rows while still suppressing fresh account-level
          enrichment. It also normalizes `@` prefixes and deduplicates resolved
          account IDs before work can be scheduled.
        - `scripts/verify_active_learning.py` now recommends only explicit
          reviewed handles and no longer presents the quarantined automatic
          selector or historical automatic seed promotion as next actions.
        - `scripts/resolve_band_usernames.py` rejects its standalone
          `account_band` selection before database/network work. Its old
          Supabase resolver remains as migration evidence, not an advertised
          executable utility.
        - `src/propagation/types.py:61-66` corrects the result contract:
          independent rows are raw Lift and uncertainty is a zero placeholder,
          not a simplex plus measured uncertainty.
        - `tests/test_propagation_entropy.py` covers scale/bounds, >1 Lift
          preservation, overflow-safe finite Lift, negative input, and exact
          classic tiny-weight compatibility. `tests/test_band_classification.py`
          covers explicit mode, artifact dimensions/masks, classifier, export,
          ranker, and analysis fail-closed behavior. Both new modules remain
          below 300 LOC; falsifiers were observed red before implementation.
        - `tests/test_account_band_quarantine.py` adds the release-review
          falsifiers: a valid but unrelated classic artifact cannot legitimize
          SQLite band rows, and direct ranker-loader callers cannot bypass the
          guard. `tests/test_export_public_site.py` and the end-to-end export
          assertion now require classified-only fallback output. The inherited
          855-LOC ordered `tests/test_pipeline_e2e.py` scenario is recorded for
          decomposition rather than expanded.
        - `tests/test_acquisition_frontier_quarantine.py` covers the CLI,
          reusable account-selection API, frontier-follow selection,
          band-username resolution, and the manual-handle escape hatch.
          `tests/test_fetch_topic_seeds.py` covers the explicit handles-file
          handoff. Historical ranking-query regressions remain isolated behind
          a private helper until a replacement policy exists.
        - `scripts/verify_independent_band_entropy.py:1-248` provides the
          required read-only ✓/✗ verifier with hashes, counts, entropy ranges,
          scale delta, legacy table metrics, boundaries, and next action.
        - `public-site/src/About.jsx` calls hosted specialist, bridge,
          frontier, and faint labels stale quarantined metadata rather than
          current findings; it describes the seeds as mixed NMF,
          LLM-ensemble, and curator inputs and explains that current export
          suppresses every unbound band row. `About.truthfulness.test.jsx`
          protects those copy contracts. The roughly 1,080-LOC About monolith
          was warned and recorded as debt; this slice makes copy-only edits.
        - `docs/adr/018-propagation-engine-and-confidence.md` receives an
          additive 2026-07-30 decision amendment; `docs/EXPERIMENT_LOG.md`
          records EXP-024; `docs/ROADMAP.md`, `docs/index.md`, and `README.md`
          remove current/shipped claims and preserve historical documents as
          explicitly superseded evidence.
    - **Measured result**
        - Active artifact: SHA-256 prefix `1d12f3371205260d`, independent mode,
          298,347 accounts, 16 community columns.
        - Correct entropy range: `0..0.975667`; values outside `[0,1]`: `0`;
          maximum delta after 7x scaling: `0`.
        - Stored table: 298,347 rows, 16,065 negative entropy rows; all 6,964
          stored specialists are negative. Counts and timestamp identify an
          older run than the active NPZ.
        - No real band, SQLite, NPZ, JSON export, hosted site, ranking,
          Community Gold judgment, API request, or paid acquisition was
          created or changed.
        - The active database's 8,727 existing `frontier_ranking` rows remain
          intact but cannot drive current automatic selection or
          frontier-ranked following fetches.
    - **Verification**
        - RED: `tests/test_band_classification.py` → 4/4 expected failures
          before the entropy and classifier changes; downstream export and
          ranker tests each then failed for “did not raise” before their
          guards.
        - GREEN: final entropy/band/acquisition/topic/fetch/export tranche →
          `111 passed`.
        - Full offline Python non-Selenium/non-Supabase suite (explicitly
          excluding the unmarked live `test_connection.py`) → `1,503 passed,
          2 skipped`; warnings are the existing SciPy sparse-mutation warning.
          The three live connection tests skip cleanly without credentials
          when rerun with network access.
        - Full public-site suite → `212 passed`; production Vite build passed.
        - About truthfulness focused contract → `1 passed`.
        - Real-data read-only verifier → `6/6` checks passed, including the
          unbound-consumer boundary, and printed all metrics above.
        - Documentation verifiers → docs hygiene `9/9`; personal-ontology
          documentation `21/21`.
        - Independent review also found that ADR-013 cluster coloring treats
          synthetic independent `none` Lift and zero uncertainty as
          probability/confidence. That separate rendering-contract repair is
          recorded in `docs/ROADMAP.md`; cluster visuals were not silently
          changed in this banding slice.
        - Final adversarial release review found three P2 gaps and each was
          falsified and closed: unrelated classic artifacts could legitimize
          unbound bands; a private legacy frontier selector was re-exported by
          the public orchestrator; and About called mixed-source seeds
          well-classified/human-classified. The follow-up review also found
          that classified fallback rows were searchable but excluded from
          community member lists; a page-level RED regression reproduced the
          empty communities, and the exporter now includes only direct
          `classified`/`exemplar` seed rows while still excluding all
          propagated band tiers. Final band/export/active-learning/E2E tranche
          passed `96/96`, About truthfulness passed `1/1`, public site passed
          `212/212`, and the production Vite build passed.

## Raw-First Retrieval Slice 3 — Named-Seed Coverage Triage (2026-07-30)

- [2026-07-30 18:30 IST] **Implemented a zero-spend, read-only Dharma seed
  coverage and acquisition-cost report (Codex GPT-5 with three read-only
  computational-peer audits)**
    - **Hypotheses, predictions, confidence, fallback**
        - `H-C1` (`0.95`): a versioned seed panel can pin the intended numeric
          identities without silently accepting conflicting handle lookups.
          Any conflicting numeric ID is surfaced while the panel remains
          authoritative.
        - `H-C2` (`0.80`): explicit direct/inverse archive and shadow following
          views contain a nonempty stored-key neighborhood for each of the four
          named Dharma seeds. A zero union falsifies this; unavailable sources
          make the union partial but do not erase observed rows.
        - `H-C3` (`0.40`): the later local follow rows can be attributed to a
          provider, fetch run, and time. Missing row-level source/run/time
          fields falsify this.
        - `H-C4` (`0.90` arithmetic; `0.45` retrieval quality):
          source-selectivity can rank current candidates, but improvement over
          raw support requires future frozen development/holdout judgments.
        - Predicted outcome: use current local evidence before spending API
          credits; price only complete refreshes, never a locally inferred
          gap. Fallback: if every neighborhood remained sparse, price a
          seed-specific acquisition tranche; if provenance remained unknown,
          keep rows usable only as explicitly unattributed observations.
    - **Investigation loop**
        - Attempt 1/3:
            - hypothesis: EXP-021's `538/10/0/0` diagnostic represents current
              named-seed coverage.
            - test: compare independent project-root and sibling archive
              databases by inode, table counts, per-seed target digests, and
              candidate universe.
            - result: rejected — database selection changed stored-key unions
              from `735/225/1/2` to `957/2,323/226/58` and candidates from
              `894` to `3,305`.
        - Attempt 2/3:
            - refined hypothesis: the public Community Archive REST topology
              can independently close the four current follow lists.
            - test: inspect current public account profiles and direct/inverse
              following/follower table counts without paid requests.
            - result: rejected for topology closure — profiles were current,
              but public relationship rows were absent or partial for three
              seeds. The canonical Parquet tweet snapshot was still refreshed
              and deep-verified at zero cost.
        - Attempt 3/3:
            - final hypothesis: the active local database is sufficient for a
              zero-cost ranking but cannot prove acquisition provenance.
            - test: inspect schema, rowid batches, stale fetch-state/log rows,
              shadow metadata, and run the query-time report with explicit
              paths and pinned SQLite read snapshots.
            - result: confirmed for operational retrieval; falsified for
              provenance. The later batch has no provider, fetch time, or run
              ID and is labeled only as unattributed SQLite evidence.
    - **Changes (files + why)**
        - `data/evals/dharma_seed_coverage_panel.json:1-39` pins the four
          user-named probes and timestamped Community Archive profile-count
          receipts; these are retrieval seeds, not exhaustive membership
          labels.
        - `data/manifests/twitterapiio_price_card_20260730.json:1-40` freezes
          the verified credits/USD, endpoint pagination, minimum-call, and
          item-tier assumptions used by the cost estimator.
        - `src/evaluation/seed_coverage_contract.py:1-200` validates panels,
          computes page-tier full-refresh cost, compares receipts/digests, and
          derives explicit falsification results.
        - `src/evaluation/seed_coverage_io.py:1-192` handles JSON/database
          receipts, missing-table semantics, and identity/name lookup.
        - `src/evaluation/seed_coverage_content.py:1-95` deep-verifies and
          caches one immutable Parquet content/reply projection per process so
          path comparison does not scan the same 920 MB snapshot twice.
        - `src/evaluation/seed_coverage_follow.py:1-108` keeps direct/inverse
          sources separate, constructs the stored-key union, preserves shadow
          provenance, and canonicalizes known seed aliases for ranking.
        - `src/evaluation/seed_coverage.py:1-177` pins read snapshots before
          receipts/queries, orchestrates the adapters, invokes the existing
          source-selectivity primitive, and states that scores are uncalibrated.
        - `tests/test_seed_coverage.py:1-240`,
          `tests/test_seed_coverage_contract.py:1-100`, and
          `tests/test_seed_coverage_io.py:1-31` behaviorally cover price tiers,
          concurrent-writer WAL snapshot isolation, source
          separation/deduplication, known seed-alias exclusion, pinned identity
          conflicts, content/ranking semantics, comparison receipts/digests,
          derived attribution status, and missing-table `unavailable`
          behavior. RED-first truthfulness fixes renamed shadow direct/inverse
          following and removed non-comparable claim-versus-union ratios.
        - `scripts/verify_seed_coverage_triage.py:1-189` prints explicit
          implementation checks and falsification statuses,
          seed metrics, ranked candidates, path dependence, cost, boundaries,
          and next steps; JSON output is no-clobber.
        - `data/evals/dharma_seed_coverage_report_20260730.json` freezes the
          historical query-time result and input receipts. Its SQLite inputs
          are explicitly mutable; the report is not an immutable source
          snapshot and cannot be exactly regenerated after their WALs advance.
        - `docs/EXPERIMENT_LOG.md` adds EXP-023 and an additive EXP-021
          amendment; `docs/ROADMAP.md` records the candidate-review surface,
          canonical data root, edge extract, ingestion provenance, shadow
          orientation, and typed-edge follow-ups.
    - **Data and cost receipts**
        - Community Archive snapshot
          `20260730T045247Z-4913d0183e39`: 8,511,975 tweets, 34,917 accounts,
          newest event `2026-07-30T04:24:20Z`, SHA-256
          `24843080391b664ed8a138cd65362a4c65756c95459858e19aca98ed7e87e471`.
        - Named-seed stored-key unions: RomeoStevens76 `957`, TVachaW `2,323`,
          realityacid108 `226`, SuttaSlime `58`. Mixed-time aliases mean these
          are neither current-follow counts nor completeness denominators.
        - Latest-snapshot authored rows: `14,542/290/7/1`; incoming non-self
          reply rows: `2,947/360/6/47`.
        - Source-selective candidate count: `3,305`; top row
          `danielbrottman` is supported by all four seeds. No precision or
          membership conclusion is drawn before held-out review.
        - Verified full-refresh quote: 3,571 credits, USD `0.03571`; actual
          twitterapi.io spend: USD `0`. The report itself makes no network
          request; the earlier public Community Archive refresh also cost USD
          `0`.
    - **Verification and limitations**
        - Behavior-first contracts began with expected `NotImplementedError`
          failures. The WAL snapshot regression then reproduced visibility of
          a writer commit after `BEGIN` but before the first read; the retained
          reader pins a real SELECT snapshot and the concurrent-writer test is
          green.
        - `pytest tests/test_seed_coverage.py
          tests/test_seed_coverage_contract.py
          tests/test_seed_coverage_io.py tests/test_source_selectivity.py
          tests/test_archive_snapshot.py
          tests/test_archive_snapshot_validation.py
          tests/test_snapshot_comparison.py -q` → `33 passed`.
        - Final real-data verifier → 4/4 implementation checks passed;
          H-C1/H-C2/H-C4 were not falsified, H-C3 was falsified; 3,305
          candidates; path deltas `+222/+2,098/+225/+56`; full-refresh quote
          USD `0.03571`. The builder exposes local paths only and does not
          execute acquisition; spend is recorded separately as an operational
          USD `0` observation, not inferred by the verifier.
        - `python -m py_compile` across all Slice 3 modules/tests and
          `git diff --check` passed.
        - `scripts/verify_docs_hygiene.py` → `9/9`; module invocation of
          `scripts.verify_personal_ontology_docs` → `21/21`.
        - The regenerated report timestamp is generated after its database
          receipts and queries; it postdates every recorded DB/WAL mtime.
        - All SQLite opens use `mode=ro` and `PRAGMA query_only=ON`; WAL
          visibility and concurrent-writer snapshot isolation are tested.
          Deep snapshot verification runs before opening the database read
          snapshots. Missing tables report `unavailable`, not observed zero.
        - A peer audit confirmed price arithmetic, artifact hashes, no secrets,
          and current shadow-row interpretation. It also caught the mutable-WAL
          reproducibility boundary, ambiguous shadow field names, and a
          mixed-union delta name; all are now explicit.
        - Current `shadow_edge` producer code and row metadata support the
          following interpretation used here, but reference documentation
          contradicts itself. Historical writer/version audit remains debt.
        - No logical database row/schema write, model inference, paid X
          request, Community Gold schema/module, UI, or deployment is part of
          this slice. Opening the WAL databases read-only created normal
          SQLite runtime sidecars (a 0-byte WAL and 32 KiB SHM) beside the
          selected sibling database.

## Raw-First Retrieval Slice 2 — Research Notes Inbox (2026-07-30)

- [2026-07-30 16:07 IST] **Implemented and synthetically verified the blind
  paste-and-review thin slice (Codex GPT-5 with three implementation peers and
  an independent adversarial review)**
    - **Hypothesis, prediction, confidence, fallback**
        - `H1` (`0.90`): messy notes can become a deduplicated review queue
          whose dossier contains only allowlisted raw evidence and no legacy
          recommendations. A leaked community/weight/role field, lost source
          line, or unsafe profile URL falsifies it.
        - `H2` (`0.95`): preview mode can fail closed by rejecting `frameId`,
          refusing all writes, ignoring mutable client target text, and naming
          current SQLite evidence as mutable and not snapshot-bound. Any
          enabled save, frozen-evidence wording, or hidden-role-dependent
          progress falsifies it.
        - `H3` (`0.45`): the surface will make real curation motivating and
          cheap enough to reach 30 judgments. Synthetic behavior cannot confirm
          this; review time, abstention, correction rate, and held-out retrieval
          change will. If the dossier is insufficient, add the smallest
          evidence view justified by observed abstentions rather than another
          substrate.
    - **RED / GREEN evidence**
        - Parser contracts began with 3 expected failures; the retained parser
          passes 3/3.
        - Dossier API contracts began with 7 expected failures; focused backend
          and adjacent auth/integrity contracts now pass 23/23.
        - App/API wiring began with 4 expected failures and inbox behavior with
          3 expected failures. The retained focused frontend tranche passes
          19/19.
        - Direct visual inspection exposed a context-free network error; a RED
          regression now requires the failing handle. An adversarial link test
          then reproduced unsafe `javascript:` website rendering and singular
          count errors; both are fixed and green.
        - Independent review falsified the first synthetic write design:
          mutable current rows were labeled as frame-bound, editable
          environment text could contradict the immutable task, a
          training-readable count leaked hidden role membership, and retry was
          not idempotent. RED contracts now require explicit frame rejection,
          session-only drafts, and no client-defined target; the write path and
          its unused client helpers were removed.
    - **Changes (files + current line ranges)**
        - `src/api/routes/research_notes.py:1-180` adds one curator-only,
          read-only dossier endpoint with explicit profile/tweet fields and
          capture times, mutable-source metadata, strict limits, and explicit
          rejection of unimplemented frame binding.
        - `src/api/server.py:32,161` registers the dossier blueprint.
        - `tests/test_research_notes_routes.py:1-202` exercises auth, blind raw
          payloads, descriptive missing-account errors, invalid limits, capture
          provenance, and mandatory frame rejection using temporary SQLite.
        - `graph-explorer/src/researchNotes/parseResearchNotes.js:1-41` parses
          handles and X/Twitter profile or tweet-author URLs, preserves the
          first source line, and deduplicates case-insensitively.
        - `graph-explorer/src/researchNotes/researchNotesApi.js:1-31` fetches an
          authenticated dossier and retains account context in network errors.
        - `graph-explorer/src/researchNotes/RawDossier.jsx:1-102` renders only
          the allowlisted profile and authored posts, with safe external links,
          capture times, mutable/snapshot status, and a no-recommendations
          boundary.
        - `graph-explorer/src/researchNotes/useResearchNotesInbox.js:1-81`
          owns only the session queue, raw evidence loading, dossier retry, and
          draft fields. It contains no persistence call.
        - `graph-explorer/src/ResearchNotesInbox.jsx:1-140` and
          `ResearchNotesInbox.css:1-266` provide the two-pane paste, dossier,
          draft judgment, error, session-only warning, and responsive layout.
        - `graph-explorer/src/App.jsx` mounts `?view=research-notes` as a
          top-level view without accepting reviewer/target semantics from
          environment configuration.
        - `scripts/verify_research_notes_inbox.py:1-192` prints 8 explicit
          ✓/✗ checks, file sizes, the no-real-data boundary, and the next gate.
        - `docs/EXPERIMENT_LOG.md` EXP-022 records the method, falsifiers,
          synthetic-only result, and snapshot provenance limitation.
        - `docs/ROADMAP.md` marks the blind thin slice shipped while retaining
          snapshot-addressed evidence, real activation, and UX measurement as
          open work.
    - **Verification**
        - `scripts/verify_research_notes_inbox.py` under the project dependency
          environment: 8/8 checks passed; 23 backend and 19 frontend contracts.
          A first invocation under a bare UV interpreter failed descriptively
          because that interpreter did not include pytest; rerunning under the
          project venv passed and did not alter code or data.
        - Graph explorer: 759/759 tests passed; scoped ESLint passed with zero
          warnings; production Vite build succeeded with inherited dynamic
          import and bundle-size warnings.
        - In-app browser: pasted two accounts, confirmed deduplication,
          queue switching, raw dossier rendering, and disabled preview save
          against a disposable fixture database. No real archive DB was opened.
    - **Scope, assumptions, and debt**
        - No schema, Community Gold module, real ontology/frame/role/judgment,
          prediction, API fetch, paid acquisition, or deployment was added.
        - A profile plus up to 20 authored posts is not assumed to prove
          competence, affiliation, endorsement, Kegan stage, simulacrum level,
          or durable intent. Those remain separately defined targets.
        - The endpoint reads current local rows and says so; it cannot accept a
          frame. Real saving remains gated on a server-derived canonical task,
          snapshot-addressed evidence/context verification, an idempotency key,
          and role-independent cumulative progress.
        - The first combined inbox component crossed 300 LOC during
          implementation and was split into presentation, controller, raw
          dossier, parser, and transport modules before integration. No new
          production file exceeds 300 LOC. Adversarial simplification reduced
          the route from 268 to 180 LOC, controller from 266 to 81 LOC, and
          backend test from 299 to 202 LOC.

- [2026-07-31 18:45 IST] **Validated full-block import against the real takes
  snapshot without activating gold writes (Codex GPT-5 with a read-only peer
  audit)**
    - **Hypothesis, prediction, confidence, fallback**
        - `H1` (`0.95`): block boundaries can recover the intended subjects
          and their complete rationale while treating handles inside evidence
          as citations. Expected: 57 subjects, no `cisco`/`ai4bharat`, both
          explicit co-subject/display-name cases present, and zero exact-span
          mismatches. Fallback: retain the raw span and require explicit
          curator confirmation for ambiguous block syntax rather than adding
          handle-specific exceptions.
    - **RED / GREEN evidence**
        - The behavior-first fixture reproduced the old failure: employer
          mentions on their own lines became separate queue subjects and the
          surrounding rationale was split away.
        - The first real-file probe still returned 59 rows, specifically
          exposing that standalone mentions inside a continued bio need a
          boundary condition. The refined rule requires a standalone mention
          to begin at a blank/separator boundary or after a narrowly detected
          display-name line.
        - The retained parser returns 57 subjects on the dated 10,311-byte
          snapshot, includes `meaningaligned` and `chrislakin`, excludes the
          two employer citations, and has zero `sourceText !==
          input.slice(sourceStart, sourceEnd)` mismatches.
    - **Changes (files + why)**
        - `graph-explorer/src/researchNotes/parseResearchNotes.js:10-184`:
          replace line-only subject discovery with block-aware profile
          boundaries, explicit co-subject handling, display-name retention,
          and immutable source offsets/text separate from the editable note.
        - `graph-explorer/src/researchNotes/parseResearchNotes.test.js:5-189`:
          add behavioral falsifiers for exact source slicing, embedded and
          standalone evidence citations, shared co-subject context, and
          display-name-plus-handle blocks.
        - `scripts/verify_research_notes_inbox.py:5,77-112,195-245`: add an
          optional read-only `--takes-file`/`--expected-count` check that
          prints snapshot hash, byte and subject counts, false-subject list,
          and exact-span errors without copying private notes into the repo.
        - `docs/EXPERIMENT_LOG.md` EXP-025 records the hypothesis, two-stage
          falsification, dated snapshot receipt, and methodological lesson.
        - `docs/ROADMAP.md` records account/question-keyed provisional drafts
          and the safe paid-acquisition replacement as explicit follow-up.
    - **Verification**
        - Focused Vitest RED: 1/5 failed for the intended standalone-citation
          reason; GREEN: 5/5 passed.
        - `scripts/verify_research_notes_inbox.py --takes-file <private-file>
          --expected-count 57` under the project dependency environment → 9/9
          checks passed, including 23 backend contracts and the focused
          frontend tranche.
        - Snapshot receipt: SHA-256
          `b9e9d616c0a79933f7f6a33dbf6cad0990e4ca1611fe48af5904a7d610e30cc0`;
          10,311 bytes; 57 subjects; zero false employers; zero span errors.
    - **Scope and debt**
        - The private raw file remains outside git. No archive row, gold
          judgment, ontology, task, frame, API request, paid credit, or public
          artifact changed.
        - The UI still has one draft shared across accounts; account/question
          keyed provisional drafts are the next product slice. Real save stays
          locked because evidence is mutable and unbound and retries are not
          idempotent.

- [2026-07-31 19:02 IST] **Added the paired Dharma boundary pretrial UI and
  repaired evidence-review ergonomics (Codex GPT-5)**
    - **Hypothesis, prediction, confidence, fallback**
        - `H1` (`0.90`): separate account/question-keyed drafts can expose
          retrieval relevance and social affiliation as distinct provisional
          targets without creating schema or implying gold. Navigation loss,
          one shared answer, enabled saving, or task-like certainty falsifies
          it. Fallback: keep only a discussion mockup and revise the questions
          before any persistent contract.
        - `H2` (`0.75`): both questions can remain usable while reviewing a
          20-post dossier. If the evidence pushes controls out of practical
          reach, the layout fails even when its state tests pass. Fallback:
          colocate evidence and controls rather than truncating evidence to
          make the test pass.
    - **RED / GREEN and visual evidence**
        - The new two-account behavioral contract began with two expected
          failures because no paired groups or account-keyed draft state
          existed. The retained UI passes switching, disagreement, editable
          note, queue progress, and disabled-save checks.
        - The first live visual pass falsified `H2`: controls rendered several
          screens below 20 long posts. A sticky side panel now keeps dossier
          and probes co-present on desktop; below 1,150 px the controls stack
          above evidence. A live read-only `nosilverv` dossier showed both
          questions in the first viewport.
        - The live session accepted retrieval `IN` plus affiliation `OUT` and
          exposed `@nosilverv 2/2 drafted` with both buttons pressed. This is a
          UI exercise, not a domain judgment or trial result; nothing was
          persisted.
    - **Changes (files + why)**
        - `graph-explorer/src/researchNotes/useResearchNotesInbox.js:14-60,
          87-104`: replace one navigation-reset draft with state keyed by
          normalized account and probe ID while keeping notes per account.
        - `graph-explorer/src/ResearchNotesInbox.jsx:12-25,65-99,125-179`:
          render explicit retrieval/social-affiliation probes, disagreement
          semantics, per-account progress, and non-gold/save-lock wording.
        - `graph-explorer/src/ResearchNotesInbox.test.jsx`: add the public
          two-account navigation/disagreement contract and flush dossier
          transitions without React `act(...)` warnings.
        - `graph-explorer/src/ResearchNotesInbox.css` and
          `graph-explorer/src/researchNotes/ResearchNotesReview.css:1-113`:
          extract review-control styles before the original stylesheet crossed
          300 LOC; add sticky desktop co-presence and narrow-screen stacking.
          Final files are 213 and 113 LOC.
        - `scripts/verify_research_notes_inbox.py:180-205,256-260`: verify the
          paired formative semantics and account/question-keyed draft markers;
          the script remains below 300 LOC (264).
        - `docs/experiments/2026-07-26-budgeted-personal-ontology-local-first-pilot.md:73-111`:
          preregister the zero-spend 12-account/two-pass boundary pretrial,
          exact questions, descriptive measures, and falsifiers without
          publishing private panel identities.
        - `docs/EXPERIMENT_LOG.md` EXP-026 records the visual falsification and
          repair; `docs/ROADMAP.md` separates the shipped session UI from the
          still-unrun formative pretrial.
    - **Verification**
        - Focused frontend tranche → 22/22 passed; scoped ESLint passed.
        - Research Notes verifier with the private dated takes snapshot → 11/11
          checks passed; adjacent backend/auth/integrity tranche → 23/23.
        - Production Vite build passed (inherited dynamic-import and 500 kB
          chunk warnings remain); docs hygiene → 9/9.
        - In-app browser inspected the live local UI with the existing archive
          opened through the dossier route's SQLite `mode=ro`/`query_only`
          contract. No remote request or paid credit occurred.
    - **Scope and next gate**
        - Drafts remain browser-session-only and explicitly non-gold. The
          protocol cannot run durably until timing/investigation capture and a
          blinded second-pass receipt exist.
        - Real saving still requires a canonical task, snapshot-bound context,
          server-side context verification, idempotent retry, and role-neutral
          progress. No Community Gold schema/module was added.

## Raw-First Retrieval Slice 1 — Source Selectivity (2026-07-30)

- [2026-07-30 15:32 IST] **Implemented and tested the minimal
  source-side selectivity primitive (Codex GPT-5 with a computational-peer
  implementation pass)**
    - **Hypotheses and falsifiers**
        - `H1` (`0.95`): distinct seed follows weighted by
          `1 / max(observed_out_degree, claimed_following_count)` should make a
          selective seed contribute more than a broad seed. Duplicate
          inflation, seed/self handling, invalid claims, nondeterminism, or
          hidden normalization would falsify the arithmetic contract.
        - `H2` (`0.55`): source-selective ranking should improve held-out
          Recall@K over raw distinct-seed support. A time/topology-split
          comparison showing no stable gain, or worse precision/reciprocal
          rank, falsifies it. This remains untested until 30 real scoped
          judgments support a frozen development/holdout split.
    - **Scope correction**
        - The first peer implementation reached 556 lines across a library,
          loaders, tests, and verifier while remaining synthetic-only. It was
          held rather than accepted. The retained slice is 269 lines total:
          104 implementation, 94 behavioral tests, and 71 human verifier.
          It adds no schema, adapter, API, UI, or new Community Gold module.
    - **Changes (files + current line ranges)**
        - `src/graph/source_selectivity.py:1-104` ranks non-seed candidates,
          deduplicates observations, uses the larger observed/claimed degree,
          and returns explicit per-seed degree-unknown/coverage diagnostics.
        - `tests/test_source_selectivity.py:1-94` covers discrimination,
          duplicate resistance, seed/self behavior, fallback semantics,
          determinism, and the fact that the signal can exceed one.
        - `scripts/verify_source_selectivity.py:1-71` prints four explicit
          ✓/✗ checks, concrete counts/scores, the semantic boundary, and the
          next held-out comparison.
        - `docs/EXPERIMENT_LOG.md` EXP-021 records the method, real diagnostic,
          assumptions, falsifiers, negative result, and next step.
        - `docs/ROADMAP.md` marks the primitive complete while keeping
          comparative retrieval validation open.
    - **Read-only real-data diagnostic**
        - Four named seeds yielded two usable neighborhoods: RomeoStevens76
          538 observed / 667 claimed, TVachaW 10 / 2,182, while SuttaSlime and
          realityacid108 remained degree-unknown in the following view.
        - The scorer returned 542 candidates. Five accounts supported by both
          usable seeds led at `0.001957546`, but raw support ranked the same
          five first. This validates operational arithmetic only; it is not
          evidence of improved retrieval or any community membership.
        - The diagnostic used a read-only point-in-time local SQLite view but
          did not freeze its query, output artifact, or database hash. The
          counts are provisional and must not be treated as reproducible
          evidence. It made no API, network, model, label, or database write.
    - **Verification**
        - Focused and adjacent graph behavior: 11/11 passed across
          `test_source_selectivity.py`, `test_observation_model.py`, and
          `test_graph_builder.py`.
        - The first direct verifier run failed with `ModuleNotFoundError: src`
          despite the tests passing. Adding the same direct-execution project
          root bootstrap used by existing verifiers made the advertised
          invocation pass 4/4. This was an invocation defect, not a scoring
          failure.
        - Documentation hygiene passed 9/9 and `git diff --check` was clean at
          the documentation checkpoint.
        - Personal-ontology documentation contracts passed 21/21 via module
          invocation. Direct script invocation exposed a pre-existing
          `ModuleNotFoundError: scripts`; fixing that unrelated verifier is
          recorded under Developer Experience rather than mixed into this
          commit.
        - Independent adversarial review found no mathematical implementation
          blocker, then caught an untested ranking tie-break, ambiguous
          `unknown` semantics, and overconfident diagnostic provenance. Exact
          score/support/account ordering is now tested; the field is
          `degree_unknown`; and the live counts are explicitly provisional.
    - **Assumptions and fallback**
        - Follows are treated as equal units of attention; seed correlation,
          time, typed engagement, stance, missing-not-at-random coverage, and
          durable numeric/`shadow:*` identity reconciliation are not modeled.
        - The score is unbounded and is not a probability, confidence, interval,
          or membership.
        - No production caller consumes the primitive yet. The next coverage
          slice must use it or it remains an experimental phantom consumer.
        - If held-out retrieval does not improve, retain raw support and test
          log-inverse/capped weighting or typed evidence without changing the
          holdout. No paid acquisition is justified by this result.
## Off-platform evidence channel + selectivity weighting (2026-07-30)

- [2026-07-30 17:50 IST] **Bio-link resolution, vision ensemble, selectivity
  scoring (Claude Opus 5)**
    - **Why**
        - `profiles.website` was populated for 230 of 26,098 rows, read in exactly
          one place (`src/communities/preview.py:33`) and never fetched. Accounts
          whose substance lives off-platform were invisible to all three existing
          channels.
        - Operator goal shifted to sourcing attendees for an interface-alignment
          programme, which made *who vouched for a candidate* matter more than how
          many did.
    - **Added**
        - `src/enrichment/site_features.py` — pure HTML → features (images,
          outbound links, feeds, interstitial redirect targets).
        - `src/enrichment/site_classify.py` — auditable scoring into 12 site types;
          abstains as `unknown` rather than guessing.
        - `src/enrichment/vision.py` — local ollama ensemble; trust gates on
          independent agreement, not self-reported confidence.
        - `src/propagation/selectivity.py` — selectivity-weighted co-following;
          direction never symmetrised.
        - `scripts/resolve_bio_links.py`, `scripts/caption_site_images.py`,
          `scripts/build_bio_link_review.py`.
        - `scripts/fetch_following_for_frontier.py` — new `--handles` mode for
          seeds the graph has never observed (graph-ranked modes structurally
          cannot reach them).
        - Tables `bio_link_profile` (composite PK, gzipped HTML cache) and
          `bio_link_image_verdict`.
    - **Defects found and fixed (all with red-first regression tests)**
        - `urljoin` raised `ValueError` on unbalanced-bracket hrefs, killing a
          230-page run at item 119. The regression test immediately exposed a
          *second* unguarded call site; all URL parsing now routes through
          `safe_host`.
        - HTML entities left undecoded corrupted 201 image URLs and 23 identity
          links. Repaired offline from the HTML cache via `--reclassify` — zero
          refetching.
        - `resolve_tco_url` labelled every failure "t.co did not resolve" when in
          most cases t.co resolved fine and the *destination* failed. Replaced with
          a two-stage probe reporting `resolve:` and `fetch:` separately;
          `resolved_url` is now recorded even when the fetch fails.
        - URL regex excluded `)`, so the paren-balancing branch beneath it was
          unreachable.
    - **Verification**
        - Backend `1,417 passed, 5 skipped`. ~70 new tests across
          `tests/test_bio_links.py` and `tests/test_selectivity.py`.
    - **Known defects NOT fixed (carried forward)**
        - `scripts/insert_seeds.py` still applies `abs()` at 9 sites, stranding
          **488** pieces of negative evidence; `account_community_bits` holds
          **0** negative rows. This is the largest available source of the OUT
          labels the evaluation floor requires.
        - **145** `new-community-signal:*` tags (Psychonauts, Somatic-Coaching,
          Post-Rationalist, Contemplative-Alignment) have no consumer.
        - `scripts/classify_bands.py:157` computes entropy on unbounded Lift.
        - `docs.github.com` inflates the GitHub identity-link count by ~60%.
        - The operator ranks inside their own candidate list; no self-exclusion.
        - Nothing reads `bio_link_profile` or `bio_link_image_verdict` yet —
          this commit adds capability, not a consumer.
    - **Data acquired**
        - 40 operator-named accounts resolved; ~61k following edges; **$0.35**.
        - See EXP-019 and EXP-020.
## Personal-Ontology Slice 1 — Evaluation Integrity (2026-07-26)

- [2026-07-28 12:13 IST] **Independent final release verification
  (Codex GPT-5)**
    - **Outcome**
        - Credential-free Python: `1,449 passed, 5 skipped`, with 20 existing
          SciPy sparse-efficiency warnings.
        - Public site: `190/190` tests passed; the production Vite build
          completed successfully.
        - Graph explorer: `741/741` tests passed; the production Vite build
          completed successfully. Existing Node experimental-storage,
          React `act(...)`, dynamic-import, and bundle-size warnings remain
          non-failing.
        - Human verifiers: Slice 1 `6/6`, documentation contracts `21/21`,
          documentation hygiene `9/9`, and GRF affinity smoke checks `10/10`.
        - `git diff --check` passed after the documentation integration.
    - **Files verified**
        - Community Gold and regression surfaces under
          `src/data/community_gold/`, `src/api/routes/community_gold_integrity.py`,
          `tests/test_*community_gold*`, `tests/test_slice1_*`, and
          `tests/test_terminal_delivery*.py`.
        - Score-contract surfaces under `src/api/cluster/`,
          `src/graph/membership_grf.py`, `graph-explorer/src/`, and
          `public-site/src/`.
        - Methodology records and human-readable verifiers under `docs/` and
          `scripts/verify_*`.
    - **Non-blocking debt found**
        - The full graph-explorer lint command is not green: `15` errors and
          `2` warnings remain across pre-existing `ClusterTour`, `Labeling`,
          `TweetCard`, test-import, empty-catch, Fast Refresh, and hook
          dependency debt. The changed membership assertions/builds/tests are
          green, but this release does not claim a repository-wide lint pass.
          The stale completed roadmap item was reopened rather than expanding
          this integrity slice into an unrelated frontend cleanup.

- [2026-07-28 11:24 IST] **Adversarial integrity and score-semantics hardening
  (Codex GPT-5 with three read-only computational-peer audits)**
    - **Hypotheses and falsifiers**
        - Complete table/index structural validation should reject
          name-compatible migration impostors; the falsifier was a malformed
          table or partial index accepted by preflight/postflight.
        - A terminal access envelope should bind the stored actor assertion and
          time as well as frame, release, roles, and label heads; the falsifier
          was post-write `accessed_by`/`accessed_at` tampering that still
          verified. This detects mutation but does not authenticate the actor.
        - Final schema/release falsifiers were: a terminal head
          created after the release cutoff; incomplete attestation of full
          judgment history and lineage; mutation when opening a future-schema
          database; weakened partial-index predicates or UNIQUE/CHECK clauses;
          a silent/absent schema marker; fractional count values; and nullable
          `TEXT PRIMARY KEY` columns. Nine expected-failing tests represented
          ten concrete hostile shapes because the weakened-CHECK case was
          parameterized; the repaired focused suite passed 101/101.
        - Per-target anchor isolation should prevent one subculture label from
          changing another. The current falsifier is that
          `list_anchor_polarities(ego)` aggregates across tag keys while the
          endpoint/cache has no ontology/task/community target.
        - Missing expected-following data must remain unknown; the falsifier
          was the prior fabricated `1.0` coverage.
        - GRF output, entropy/degree uncertainty, public-card intensity, and
          NMF shares must survive explicit zero/missing cases without becoming
          probabilities or confidence intervals.
        - Node 26's experimental global web storage, rather than product code,
          caused the graph-explorer full-suite failures; prediction was that
          disabling it would restore jsdom `localStorage`.
    - **Changes (files + current line ranges)**
        - `src/data/community_gold/migration_table_specs.py:1-208`,
          `migration_table_contracts.py:1-112`, and
          `migration_index_contracts.py:1-101` validate NOT NULL, CHECK,
          foreign-key, UNIQUE, index-column, uniqueness, and partial-predicate
          structure.
        - `src/data/community_gold/terminal_access_envelope.py:1-86` binds
          frame, registry, caller-asserted actor, time, access receipt, release
          manifest, and released-head count; verification recomputes the
          envelope but does not authenticate the original assertion.
        - `src/data/community_gold/integrity_triggers.py:1-176` and
          `ontology_frame_triggers.py:1-137` split trigger responsibilities
          below 300 lines without changing their registry.
        - `src/api/cluster/membership_coverage.py:1-35`,
          `src/graph/membership_grf.py:1-186`, and the graph-explorer/public
          evidence surfaces preserve unknown coverage and use uncalibrated
          affinity/heuristic-signal language.
        - `public-site/src/About.jsx`,
          `CommunityCard.jsx:1-245`, and `App.jsx:19-267` distinguish
          compositional NMF shares, PPR Lift, GRF affinity, heuristic
          uncertainty, and coverage; unregistered intervals are hidden and
          the acquisition flywheel is labeled planned.
        - `graph-explorer/src/setupTests.js:1-63` supplies a conditional
          standards-shaped in-memory `Storage` only when Node 26 shadows
          jsdom's implementation.
        - `public-site/src/About.jsx`, ADR 012/013 dated amendments,
          `docs/modules/communities.md`, `docs/index.md`, `docs/ROADMAP.md`, this
          worklog, EXP-018, and the Slice 1 plan/debt ledger record producer-specific
          edge views, legacy empirical caveats, score/coverage semantics, actor
          and delivery limits, target-collapse risk, and remaining provenance debt.
        - `scripts/verify_personal_ontology_docs.py` now protects ADR 007,
          ADR 011, ADR 012, and ADR 013 amendments. Their declarative needles
          were extracted to `scripts/_personal_ontology_adr_contracts.py`, keeping
          the verifier at 291 LOC and the helper at 51 LOC.
          `scripts/verify_membership_grf.py` reports the settings path and exact
          JSON read/parse error instead of silently replacing malformed input.
    - **Verification**
        - Prior integrated checkpoint (superseded by the final hardening):
          focused backend 114/114; credential-free Python 1,425
          passed/five skipped; public site 189/189; graph explorer 730/730;
          synthetic verifier 6/6.
        - Final hostile-shape falsification: nine expected failures covering ten
          concrete shapes. After repair: focused Community Gold 101/101,
          synthetic Slice 1 verifier 6/6, and verifier unit test 1/1.
          Largest scoped implementation file: 264 LOC; largest regression file:
          260 LOC.
        - **A1 idempotent terminal replay — GREEN:** the RED phase
          deliberately produced 11/11 expected failures across two focused test
          files. They cover lost-response recovery; exact payload/`accessedAt`
          replay; actor, reviewer, receipt, and frame conflicts; corruption;
          sealing; concurrent requests; no post-commit reload; and HTTP 409 with
          no leaked rows. Final delivery tests pass 12/12, the broader Community
          Gold/Slice 1 surface passes 102/102, and the human verifier passes 6/6.
          The first release fully verifies before commit and its rollback test
          passes; an identical retry returns exact judgments/access metadata,
          preserves the original `accessedAt`, uses one row, and marks
          `replayed=true`; conflicts map to HTTP 409 with no rows; corruption
          fails closed; concurrent calls converge; and the route no longer
          reloads after commit. Maximum route size is 270 LOC and the new
          delivery module is 262 LOC. `accessedBy` remains caller-asserted.
        - Documentation contract: 21/21; docs hygiene: 9/9; standalone GRF
          affinity verifier: 10/10. The first docs run exposed one case-sensitive
          verifier needle (20/21); correcting that contract produced 21/21.
          A no-filesystem malformed-settings stub emitted the precise
          `JSONDecodeError` and failed its parse check instead of silently
          substituting empty settings.
        - Core handoff and final documentation integration both passed
          `git diff --check`.
    - **Limits**
        - No live/archive refresh, API request, provider/LLM inference, external
          write, or paid action occurred. Synthetic GRF/evaluator computation is
          not a live model run. Public empirical counts remain point-in-time
          until a source/run manifest is exposed.
        - The public export still mixes NMF/bits shares, classic simplex values,
          and independent Lift under one `weight` field. Explicit per-score
          semantics remain required before the card can format every producer
          without ambiguity.
        - A1 now handles lost-response retry through exact idempotent replay,
          but a shared curator token still does not authenticate `accessed_by`.
          Principal-derived actor identity remains a live-release gate.
        - Membership anchors, cache, and response are not target-scoped, so
          synthetic binary tests do not validate overlapping multi-subculture
          inference. Coverage is also unknown when numerator and denominator
          lack compatible source/generation/as-of provenance.

- [2026-07-26 16:29 IST] **Implemented a synthetic-only, fail-closed
  ontology/holdout substrate (Codex GPT-5 with three independent
  computational-peer audits)**
    - **Goal**
        - Extend the existing Community Gold adapter with versioned personal
          ontology/task identity, immutable global account roles, typed score
          semantics, append-only human judgments, and a one-use terminal
          release before modeling or paid acquisition begins.
        - Preserve the 167 imported labels without fabricating ontology,
          evidence-generation, stable-identity, negative, or calibration
          meaning.
    - **Hypotheses and falsifiers**
        - `H1` (`0.90`): an additive nullable migration preserves legacy rows;
          falsifier was row/identity drift or restart failure.
        - `H2` (`0.85`): caller-supplied role catalogs, strata, and integer
          quotas yield deterministic exclusive roles and nominal quota
          probabilities conditional on a genuinely precommitted random seed;
          falsifiers were registry reuse, cross-registry reassignment,
          whitespace split-brain, missing accounts, or nonpositive terminal
          probability. A seed/randomization receipt remains a real-use gate.
        - `H3` (`0.90`): purpose-gated reads keep terminal labels out of
          training/selection; falsifiers were returned or SQL-fetched sealed
          heads, repeated terminal access, or post-release writes.
        - `H4` (`0.95`): structurally separate predictions cannot masquerade
          as judgments; falsifiers were legacy/scoped leakage, mutable payloads,
          missing score semantics, or a forgeable probability claim.
        - `legacy_unbound` remains a curator-authenticated writable
          compatibility surface, isolated from versioned study reads and
          excluded from scientific evaluation. No parallel database/store was
          introduced.
    - **Initial failures that paid down assumptions**
        - Reopening after two valid scoped corrections recreated the legacy
          global unique index and raised `IntegrityError`.
        - Extra role rows were ignored by projection verification.
        - A corrupt terminal row consumed the one-use receipt before failing.
        - The same role-registry ID accepted a different seed/allocation; a new
          caller-selected registry could reassign the same accounts; terminal
          release did not seal sibling task frames; empty or reviewer-filtered
          releases burned the holdout; ontology groups remained appendable;
          judgment heads could be deleted/rewound; and earlier schema-v2 shapes
          were not upgradable transactionally.
        - Arbitrary hashes could claim `calibrated_probability`; prediction and
          terminal receipt/manifest hashes were not recomputed; role whitespace
          produced a later access `KeyError`; missing method outputs became
          score zero; the legacy evaluator emitted Brier/ECE for uncalibrated
          scores; and the live GRF API/UI called a coverage-blended affinity a
          probability with a fabricated 95% interval.
        - Behavior-first tests reproduced each defect before the corresponding
          migration, trigger, registry, digest, canonicalization, query, or
          release-manifest repair.
    - **Changes (files + intent)**
        - `src/data/community_gold/`: transactional additive schema version 3;
          validated upgrades from the earlier v2 access shape; replace-on-open
          integrity triggers; immutable
          ontology/group/task projections; global role registry; frozen frame
          projection; evidence-bound append-only judgment heads; SQL-level
          purpose access; separate immutable predictions; generation-level
          sealing; complete single-reviewer terminal coverage manifests;
          tamper-checked access receipts; future-schema refusal; and explicit
          `legacy_unbound` compatibility filtering.
        - `src/data/community_gold/candidate_pool.py` was extracted in commit
          `17217a0` before role work; pure frame/allocation contracts landed in
          `549de93`. New responsibilities remain in focused files below 300
          lines.
        - `src/data/community_gold/evals.py` and
          `evaluation_reporting.py` restrict the legacy evaluator to
          train→development diagnostics, report prediction missingness and
          development class support, keep calibration eligibility false, and
          suppress Brier/ECE until registered probabilities exist.
        - `src/api/cluster/membership.py` and
          `graph-explorer/src/AccountMembershipPanel.jsx` now expose the live
          GRF result as uncalibrated `affinity`; evidence coverage and heuristic
          uncertainty remain separate and no confidence interval is claimed.
        - `src/api/routes/community_gold_integrity.py`,
          `src/api/routes/community_gold.py`, and `src/api/server.py`: register
          the canonical route family in the production factory and protect
          every Community Gold route with the existing fail-closed curator
          token.
        - `scripts/_personal_ontology_slice1_fixture.py`,
          `_personal_ontology_slice1_checks.py`, and
          `verify_personal_ontology_slice1.py`: network-free synthetic verifier
          with explicit checks, complete in/out/abstain terminal coverage,
          nominal inclusion probability, digests, and next steps.
        - Focused behavior tests cover migration/restart, frame/role identity,
          global registry reuse, history/head integrity, legacy isolation,
          prediction immutability, sealed release, API/auth behavior, evaluator
          claims, and verifier network isolation.
    - **Empirical legacy baseline**
        - A read-only point-in-time SQLite inspection found 167/167 active labels,
          all `in`, one reviewer, no corrections, only `handle`/`source`
          evidence, and mixed 81 shadow / 54 handle / 32 numeric IDs.
          No source hash/snapshot/query receipt was recorded, so this is not an
          immutable baseline or freshness claim.
        - These rows cannot calibrate; they remain `legacy_unbound`. Candidate
          alias mappings are not accepted without immutable receipts.
        - Full method and result records are EXP-017 and EXP-018 in
          `docs/EXPERIMENT_LOG.md`.
    - **Verification**
        - Final focused Community Gold, personal-ontology, adversarial
          migration, route/auth, verifier, and GRF semantics surface: 114 tests
          passed.
        - Final credential-free suite: 1,425 passed with five expected skips
          and zero failures.
        - Synthetic verifier: 6/6 passed; role mix
          `4 model-development / 1 policy-development / 2 terminal / 3
          frame-only`, four complete terminal heads spanning `in/out/abstain`,
          nominal minimum terminal probability `.166667`, and content-addressed
          frame/role/release digests.
        - No real ontology, role, judgment, prediction, release, API request,
          provider/LLM inference, data download, or paid action occurred.
          Synthetic GRF/evaluator computation did run.
    - **Residuals**
        - Real identity resolution, seed precommit/randomization proof,
          quotas/strata, explicit real negatives and abstentions, 20/20 class
          support, calibration records, simplex-vector finalization, and IPW
          versioned evaluation remain future work.
        - Community Gold UI modules remain orphaned and reveal model/group
          information; they were intentionally not wired.
        - Historical acquisition holdout fail-open behavior is outside Slice 1
          and must be repaired before spend.

## Personal-Ontology Documentation Foundation (2026-07-26)

- [2026-07-26 13:30 IST] **Specified overlapping discovery semantics,
  budget-constrained evidence acquisition, and a local-first implementation
  sequence (Codex GPT-5 with three independent computational-peer reviews)**
    - **Goal**
        - Turn the approved research direction into a documentation-only
          foundation: an applied mission, precise task meanings, falsifiable
          acquisition policy, USD 100 planned pilot, thin implementation
          slices, and an explicit refactor/debt boundary.
        - Reuse the existing Community Gold, frontier-ranking,
          active-learning, enrichment-log, fetcher, and dossier surfaces rather
          than designing parallel stacks.
    - **Hypotheses and predicted outcomes**
        - Independent affiliation heads should represent genuinely overlapping
          communities more faithfully than normalized shares; this is rejected
          if blind human judgments are reliably mutually exclusive or a
          simplex/hierarchy calibrates better on equivalent evidence.
        - Typed graph, content, interaction, artifact, and time-correct context
          should improve retrieval over simple baselines; each modality is
          rejected when cost-matched mask/reveal intervals show no practical
          development gain.
        - Local models may replace some hosted inference only if the frozen
          benchmark meets schema, evidence-span, proper-score, and correction
          thresholds. Installed weights alone are not implementation evidence.
        - An adaptive policy should beat random, degree, entropy, and current
          frontier baselines per dollar/human minute; it is rejected before
          live expansion if retrospective value calibration fails.
    - **Assumptions, confidence, and fallback**
        - `0.95` that separating affiliation, competence, public participation
          interest, style, and observed coverage removes a real semantic defect.
        - `0.75` that local structured extraction will clear the registered
          non-inferiority threshold; fallback is embeddings/statistical heads
          plus pinned hosted audits, never unmeasured local routing.
        - `0.65` that value-of-information ranking will beat the current
          heuristic after selection-bias controls; fallback is the strongest
          simple randomized or fixed baseline.
        - No paid API call, model download, data mutation, label change, or
          runtime behavior change is authorized by this phase.
    - **Changes (files + intent)**
        - `docs/VISION.md` and
          `docs/product/2026-07-26-publishing-and-privacy-boundary.md`: define
          the applied mission, four-part evidence architecture, overlapping
          affinity language, remote-egress disclosure, and field-level
          publication boundary without growing the vision into a monolith.
        - `docs/adr/021-independent-overlapping-membership-and-evidence-semantics.md`:
          separate task targets/coverage, evaluation integrity, reuse boundary,
          decision-level falsifiers, and prior-ADR relationships.
        - `docs/adr/022-budget-constrained-active-evidence-acquisition.md`:
          define typed actions, development-risk reduction, constrained batch
          policy, conditional local-first cascade, receipts, temporal controls,
          random audit, and stop rules.
        - `docs/experiments/2026-07-26-budgeted-personal-ontology-local-first-pilot.md`:
          plan the USD 0/USD 10/USD 70/USD 20 tranches, exact 20% randomized
          audit, quantitative falsifiers, egress allowlist, and sealed outcomes.
        - `docs/experiments/2026-07-26-personal-ontology-evaluation-methods.md`:
          freeze the eligible universe and probability sampling, separate
          challenge/calibration/policy/extraction panels, define abstention and
          the scalar primary endpoint, add a probability-audited novel-account
          cohort, prohibit evaluation reuse, and distinguish offline policy
          promotion from the terminal task-head test.
        - `docs/plans/2026-07-26-personal-ontology-active-discovery-implementation.md`
          and `personal-ontology-refactor-ledger.md`: sequence ten gated thin
          slices and record keep/repair/retire, monolith, embedding-provenance,
          and safe-parallelization debt.
        - `docs/index.md` and `docs/ROADMAP.md`: index the new canonical
          records, mark precise supersessions, retire stale price guidance, and
          expose follow-on work.
        - `scripts/verify_personal_ontology_docs.py`: read-only, human-facing
          documentation contract verifier required by the phase.
        - Final line map: `docs/VISION.md:1-224`, publishing boundary `:1-90`,
          ADR 021 `:1-249`, ADR 022 `:1-267`, pilot `:1-268`, evaluation
          methods `:1-251`, implementation plan `:1-274`, refactor ledger
          `:1-108`, verifier `:1-217`, `docs/index.md:8-147`, and
          `docs/ROADMAP.md:40-585`.
    - **Documentation debt**
        - `docs/PROJECT_STRUCTURE.md` is required by `AGENTS.md` but absent.
          The refactor ledger records the gap; this phase does not invent a
          replacement without determining the intended canonical source.
        - `WORKLOG.md`, `ROADMAP.md`, and `EXPERIMENT_LOG.md` already exceed the
          300-line working-set limit; decomposition remains tracked work.
    - **Verification**
        - Independent review rejected the first draft's purposive-panel
          calibration, reusable test checkpoints, ordinary-bootstrap adaptive
          stopping, additive mutual-information utility, and post-selectable
          metrics. Final review also removed zero-probability evaluation roles
          and scoped all population-weighted claims to \(U_{\mathrm{eval}}\).
        - Final personal-ontology verifier: 14/14 passed. Existing docs-hygiene
          verifier: 9/9 passed. Every new doc is below 300 lines and
          `git diff --check` is clean.
        - Python syntax compilation passed with `PYTHONPYCACHEPREFIX` directed
          to `/tmp`; the first default-cache attempt failed descriptively
          because the isolated clone could not create `scripts/__pycache__`.
        - No entry is added to `docs/EXPERIMENT_LOG.md` because this phase runs
          no scientific measurement.

## Frozen Membership and Discoverability Assumption Audit (2026-07-26)

- [2026-07-26 11:53 IST] **Turned the approved assumption plan into
  reproducible falsification harnesses and refreshed corpus evidence
  (Codex GPT-5 with three parallel computational peers)**
    - **Goal**
        - Test the frozen solver, soft-membership, threshold, taxonomy, graph
          sampling, direction, and degree assumptions without modifying the
          frozen control or mistaking a negative finding for execution failure.
        - Refresh and compare the mutable Community Archive tweet export while
          keeping topology freshness and paid live API collection separate.
    - **Hypotheses and predicted falsifiers**
        - The frozen uncertainty formula should reproduce within `1e-6`;
          configured PPR `max_iter=1` must not exceed one iteration; dangling
          PPR mass must remain within `1e-9` of one.
        - Frozen rows must beat empirical-prior and uniform Brier/log-loss
          baselines; top-class confidence must have ECE ≤ `.05`; at least half
          of recalled propagation-heldout calibration accounts must be core;
          an information-equivalent factor split must keep core Jaccard ≥ `.95`
          and core-count change ≤ 5%.
        - Final selection Jaccard must remain ≥ `.95/.90/.85` under
          1%/5%/10% stored-edge deletion.
        - Capture-center, edge-direction/reciprocity, and degree mechanisms
          should pass their predeclared structural detection thresholds.
        - A newer Community Archive corpus must add rows and advance its newest
          tweet; archive linkage keeps pace only if linked rows cover the delta
          and missing upload IDs do not grow.
    - **Result**
        - Community Archive corpus advance confirmed:
          snapshot `20260726T045149Z-37a97fa3e057`, 8,321,675 rows,
          34,698 accounts, newest tweet 2026-07-26T04:26:07Z, SHA-256
          `99e93da98bb9fbdbddaa46a9e7f00da7ae501144294c123155e4d56447a8e9bd`.
          Versus July 25: +3,425 rows, +14 accounts, +87,038 seconds.
          Linkage pace rejected: +0 archive-linked rows and +3,425 missing IDs.
        - Historical uncertainty post-processing fingerprint confirmed at
          maximum error
          `3.6783e-08`. PPR iteration plumbing rejected (requested one;
          observed 90/90/90) and dangling-mass conservation rejected
          (mass `.21375` versus reciprocal control `1.0`).
        - About/NMF correspondence rejected: the page describes independent
          overlapping percentages, but `cluster_soft.py` row-normalizes every
          account's factor weights to a compositional sum of one.
        - Soft-target predictive agreement rejected: model/prior/uniform Brier
          `.586815/.505926/.517078`, log loss
          `3.737831/2.620363/2.708050`; hard dominant-class confidence
          calibration also rejected at ECE `.094255`. The empirical prior is
          in-sample, but the independent uniform baseline also beats the model.
          Calibration-set core interpretation rejected at 0 core, 53
          halo-only, and 2 missed. These 55 accounts were held out from
          propagation but reused to select τ, so this is not threshold
          generalization. Equal split-all taxonomy invariance rejected at core
          Jaccard `.405714` and total-selection Jaccard `.576469`.
        - Bounded fixed-membership edge-loss selection survived:
          minimum Jaccards `.990984/.961264/.922418`.
        - Capture/direction/degree mechanisms confirmed: 1.731% capture centers
          touch 100% of shadow edges; 80.336% degree-one nodes; seed reach
          39.944% forward, 66.780% reverse, 99.991% undirected, 6.425% mutual;
          exact 175 core + 8,809 halo selection with an 80.176-point
          degree-one versus degree≥51 selection-rate gap.
    - **Assumptions, confidence, and fallback**
        - `0.99` that results bind to the frozen manifest and named snapshot
          hashes; every scientific loader fails closed on identity errors.
        - `0.98` that current outputs are useful deterministic ranking/control
          evidence; `0.15` that they are calibrated current group probabilities.
        - Edge-loss support is conditional (`0.95`) on fixed memberships and
          tests only degree/relevance/core/halo recomputation, not propagation.
        - On any identity, leakage, serialization, or runtime failure, return
          exit `1` and preserve prior evidence. Scientific falsification
          returns `0` in measurement mode and `2` only under an explicit strict
          gate. Do not patch the producer or overwrite the frozen bundle.
    - **Changes (files + why)**
        - `src/archive/snapshot_comparison.py:1-195`,
          `scripts/compare_community_archive_snapshots.py:1-125`,
          `tests/test_snapshot_comparison.py:1-168`: verified immutable
          baseline/candidate comparison, exact count/linkage deltas, samples,
          no-clobber JSON, falsifiers, and `0/1/2` CLI behavior.
        - `src/evaluation/solver_contract.py:1-281`,
          `scripts/verify_propagation_solver_contract.py:1-90`,
          `tests/test_solver_contract.py:1-152`: historical uncertainty
          post-processing fingerprint, bounded config-plumbing probe,
          dangling-mass control, and future-fix-safe behavioral verdict tests.
        - `src/evaluation/frozen_membership.py:1-195`,
          `membership_scoring.py:1-117`, `membership_stress.py:1-105`,
          `scripts/evaluate_frozen_membership.py:1-136`,
          `tests/test_frozen_membership_evaluation.py:1-190`: leakage-safe
          holdout metrics, stable ties, probability baselines, ECE, taxonomy
          intervention, fixed-membership edge loss, and strict result gate.
        - `src/evaluation/discoverability.py:1-270`,
          `discoverability_topology.py:1-78`,
          `scripts/verify_network_discoverability.py:1-113`,
          `tests/test_discoverability_evaluation.py:1-202`: modular directed,
          any-direction, and reciprocal graph views; components/reachability;
          capture and degree measurements; exact fixed seed panel; no-clobber
          evidence.
        - `Makefile:1-84`: expose snapshot comparison and individual/combined
          assumption-verifier targets.
        - `docs/experiments/2026-07-26-membership-discoverability-audit.md:1-199`,
          `docs/EXPERIMENT_LOG.md` (EXP-015/016), `docs/ROADMAP.md`, and
          `docs/index.md`: durable methodology, falsifiers, exact results,
          limitations, future work, and discoverable documentation intent.
    - **Verification**
        - Full deep snapshot comparison passed both hashes and identities;
          strict mode returned the expected `2` for linkage falsification.
        - `make verify-research-assumptions` completed all three evidence lanes.
          Solver and membership strict modes returned expected `2`;
          discoverability strict mode returned `0`.
        - Focused plus adjacent Python surface: `63 passed`.
        - Independent pre-commit construct-validity review narrowed the
          uncertainty claim, split predictive agreement from hard-label ECE,
          exposed calibration-set reuse, and found the missing-degree report
          edge case. All four findings were corrected without changing an
          observed metric or scientific outcome.
        - Credential-free backend suite: initial restricted-sandbox attempt
          stopped with 20 `PermissionError` setup errors when existing API
          logging could not create `logs/api.log`; the prescribed rerun with
          normal workspace write access passed:
          `1,338 passed, 5 skipped, 20 warnings`.
        - Docs hygiene: `9 passed, 0 failed`; remote fetch succeeded and
          `origin/main` remains `7cfb45f` with this branch five commits ahead
          before the current commit.
        - All new implementation modules are at most 281 lines;
          `git diff --check` passes.
    - **Residuals / attention boundaries**
        - No production solver, membership, threshold, About-page, or graph
          artifact was changed. Architecture must first choose compositional
          shares versus independently overlapping affinities.
        - No TwitterAPI.io call was made and the clean clone has no credentials.
          Attention is required only before credential use or material spend.
        - The new tweet snapshot does not refresh follower topology. Raw archive
          relationship inventory, multi-center temporal holdouts, end-to-end
          censoring, verified negatives, and NMF restart stability remain
          roadmap work.
        - The backup-synchronized 1,337-entry damaged checkout remains
          quarantined. Promoting this clean clone and archiving/removing the old
          path is a separate path-changing/destructive attention boundary.

## Frozen Graph Artifact Compatibility Baseline (2026-07-26)

- [2026-07-26 08:56 IST] **Made the existing graph-to-TPOT chain safe for
  controlled, read-only assumption experiments (Codex GPT-5)**
    - **Goal**
        - Establish whether graph, adjacency, propagation, calibration,
          selected TPOT subgraph, and spectral artifacts actually belong
          together before testing network discoverability or soft group
          membership.
        - Prevent future builders from combining arrays by filename/position or
          overwriting the certified frozen control.
    - **Hypotheses**
        - `H1` (`0.98`): the 95,057-node cache exactly reconstructs from the
          ordered graph nodes and 319,771 edge rows.
        - `H2` (`0.65`): the newer 298,347-node active propagation is a full
          superset that can be safely reindexed to the graph.
        - `H3` (`0.90`): the 95,057-node train propagation plus saved threshold
          exactly generated the frozen 8,984-node TPOT output.
        - `H4` (`0.95`): strict identity/reproduction checks can make the
          frozen chain a deterministic control without claiming it is fresh or
          scientifically validated ground truth.
    - **Predicted outcome**
        - Exact sparse reconstruction either proves cache binding or fails with
          differing-cell counts; propagation candidates are accepted only with
          complete unique ID coverage; calibration must reproduce exact
          relevance, counts, ordered selection, Parquet subsets, spectral rows,
          and runtime adjacency semantics.
    - **Result**
        - `H1`, `H3`, and `H4` confirmed; `H2` rejected. The active propagation
          overlaps only 358 graph IDs and omits 94,699.
        - `community_propagation_train.npz` has exact graph order and reproduces
          175 core + 8,809 halo = 8,984 selected nodes at
          `tau=0.05644444444444444`.
        - The saved float32 relevance vector reproduces exactly (SHA-256
          `e08d5a87fdf096f7c7751de2cedbc2a01871831e2afc72a6b7022da496b576dd`);
          mapping, node/edge Parquets, both spectral artifacts, and TPOT runtime
          adjacency also bind exactly.
        - Compatibility exposed two scientific caveats instead of hiding them:
          the legacy control uses a 14-community schema disjoint from the
          active 16-community independent-Lift schema, and 0/15 legacy solver
          classes converged (all recorded 800 iterations).
        - The historical threshold “F1” label was corrected to
          positive-recall/graph-compactness harmonic utility; it contains no
          negative-class precision signal.
    - **Confidence**
        - `0.99` that the frozen files are internally identity-compatible.
        - `0.98` that the branch now fails closed on positional, score-semantic,
          calibration-method, or output-binding contradictions.
        - `0.20` that the legacy soft memberships should be interpreted as
          calibrated current group probabilities without new experiments.
        - `0.10` that the frozen follow topology is current; the fresh
          Community Archive Parquet is tweet-only.
    - **Fallback plan**
        - If any compatibility check fails, retain the hash-pinned frozen
          control and investigate the named artifact. Never truncate, select by
          modification time, delete/rebuild the adjacency cache, weaken
          convergence evidence, or overwrite flat outputs.
    - **Changes (files + why)**
        - `src/artifacts/adjacency_binding.py:1-124`,
          `digests.py:1-60`: exact node/order/topology/value identity and
          explicit directed versus mutual-reverse construction semantics.
        - `src/artifacts/propagation_alignment.py:1-215`,
          `propagation_schema.py:1-140`, `tpot_inputs.py:1-110`: complete-ID
          candidate selection, safe superset reindexing of known node arrays,
          mode-aware classic probability versus independent Lift validation,
          and TPOT probability-semantic enforcement.
        - `src/artifacts/provenance.py:1-216`,
          `selection_binding.py:1-80`, `spectral_binding.py:1-170`,
          `relevance_binding.py:1-51`: graph/propagation compatibility records
          plus exact relevance, selection, and spectral binding.
        - `data/manifests/frozen_control_compatibility.json`,
          `src/artifacts/frozen_manifest.py:1-107`: persist and verify expected
          byte sizes and SHA-256 for all 15 scientific files in the frozen
          control, preventing same-shape membership or embedding replacement.
        - `src/artifacts/calibration_method.py:1-116`,
          `calibration_record.py:1-183`, `calibration_output.py:1-89`,
          `tpot_calibration.py:1-69`: holdout leakage/count checks, honest
          objective naming, method/code hashes, no-clobber calibration output,
          and threshold-to-artifact binding.
        - `src/artifacts/output_reservation.py:1-36`,
          `tpot_bundle_output.py:1-43`: cooperating-writer lock, absent-path
          reservation, and exact ordered sidecar output. This deliberately does
          not claim atomic multi-file publication.
        - `src/artifacts/frozen_control_verifier.py:1-221`,
          `frozen_output_verifier.py:1-134`,
          `scripts/verify_artifact_compatibility.py:1-46`: modular
          human-readable end-to-end verifier with ✓/✗ metrics, convergence
          warning, hashes, and next action.
        - `scripts/build_tpot_spectral.py:1-268`: replace filename/positional
          propagation choice and default threshold fallback with compatibility
          binding, exact legacy reproduction, score-mode checks, output
          reservation, and absent-prefix-only output.
        - `scripts/calibrate_tpot_threshold.py:1-252`: require train-only
          propagation plus fully resolved non-leaking holdout, remove production
          fallback, rename the objective, reject infeasible recall floors, and
          write new outputs without replacement.
        - `src/graph/spectral.py:1-260`, `spectral_types.py:1-33`,
          `spectral_validation.py:1-64`,
          `src/graph/tpot_relevance.py:1-173`: split types/validation below 300
          lines, validate spectral identities and actual dimensions, and
          centralize safe symmetrized degree statistics.
        - `tests/test_artifact_*.py`, `tests/test_calibration_*.py`,
          `tests/test_frozen_manifest.py`,
          `tests/test_output_reservation.py`,
          `tests/test_propagation_artifact_alignment.py`,
          `tests/test_relevance_binding.py`,
          `tests/test_selection_artifact_binding.py`,
          `tests/test_spectral*.py`, and `tests/test_tpot_*.py`: behavioral
          contracts for every compatibility and no-clobber boundary.
        - `docs/adr/020-graph-artifact-compatibility.md`,
          `docs/EXPERIMENT_LOG.md` (EXP-014), `docs/ROADMAP.md`, and
          `docs/index.md`: record the decision, empirical evidence, limitations,
          and next experiments.
        - `Makefile:8-47`: expose `make verify-artifact-compatibility` without
          making gitignored research data a clean-checkout baseline dependency.
    - **Verification**
        - `make verify-artifact-compatibility`: all frozen-chain checks pass;
          pins 15 files/27,272,597 bytes and reports the 0/15 convergence
          warning rather than treating it as success.
        - Focused compatibility, calibration, relevance, output, and spectral
          surface: `99 passed`.
        - Credential-free backend suite with normal local log/database write
          access: `1307 passed, 5 skipped, 20 warnings`.
        - Docs hygiene: `9 passed, 0 failed`; `git diff --check` passes.
        - All new or materially expanded implementation files are below 300
          lines.
    - **Residuals**
        - This is a compatibility record, not the complete producer manifest:
          effective propagation parameters, seeds, source database cutoffs,
          producer Git state, and taxonomy generation still need binding.
        - Multi-file candidate output is reserved/no-clobber but not atomically
          published. Immutable generation directories plus a validated manifest
          and atomic pointer are required before replacement/deployment.
        - The API rebuild path uses different adjacency construction semantics
          from the pinned full cache.
        - The legacy propagation producer still overwrites flat artifacts and
          is not safe for regeneration; a versioned producer is roadmap work.

## Versioned Community Archive Snapshot Foundation (2026-07-26)

- [2026-07-26 07:06 IST] **Implemented and live-probed a non-destructive,
  evidence-grade bulk snapshot path (Codex GPT-5)**
    - **Goal**
        - Make current Community Archive tweet data acquirable without
          overwriting the certified frozen baseline, silently trusting a
          mutable URL, or combining an incomplete transfer with old derived
          artifacts.
    - **Hypotheses**
        - `H1` (`0.90`): the mutable canonical Parquet object is newer than its
          release-page label and the local 2026-03-22 tweet cutoff.
        - `H2` (`0.98`): strict HEAD/GET validator equality, two independent
          byte ceilings, streamed SHA-256, no-clobber publication, Parquet
          schema checks, and a manifest written last are sufficient for a safe
          acquisition boundary.
        - `H3` (`0.95`): preserving old relationship observations is safer than
          interpreting absence from a later archive as an unfollow/unlike.
    - **Predicted outcome**
        - Probe-only mode performs one HEAD and no writes; a changed or
          oversized response is rejected before publication; completed
          snapshots are immutable and reusable only after deep verification;
          the frozen baseline remains untouched.
    - **Result**
        - `H1` confirmed by the live probe: the object was modified
          2026-07-25 even though its release title said 2026-07-13, and the
          one-row live API probe reached 2026-07-26 versus the local
          2026-03-22 cutoff.
        - `H2` confirmed as a safety boundary. After commit `48f8daa`, the first
          full-body attempt transferred all bytes with a clean producer Git
          state, then refused to manifest because live `created_at` is a
          canonical UTC string rather than the predicted Arrow timestamp.
          The candidate remained incomplete and did not affect the baseline.
        - The refined string parser rescanned all 8,318,250 rows successfully
          and exposed 108 source/Snowflake disagreements larger than one second,
          including five impossible pre-Twitter source timestamps.
        - Attempt 2/3 reacquired the unchanged remote object after commit
          `7b405bb`, wrote the manifest last, and passed independent deep hash
          plus full Parquet verification. Snapshot acquisition is complete.
        - `H3` retained as ADR 019's conservative data contract. The official
          pair-key upsert ingest does not delete absent following/follower
          pairs, so those source tables are themselves accumulated
          observations rather than exact current-state snapshots.
    - **Confidence**
        - `0.99` that no completed snapshot can be silently overwritten by this
          workflow.
        - `0.98` that a mid-transfer change visible through ETag,
          Last-Modified, length, or received bytes is rejected.
        - `0.99` that this snapshot's observed string-ID and canonical UTC
          string-time schema is now represented accurately; the original Arrow
          timestamp-only assumption was rejected by the full-file test.
    - **Fallback plan**
        - On validator, cap, schema, hash, or manifest failure, leave the frozen
          baseline active and do not create a commit-marker manifest. Re-probe
          the source; never weaken checks to accept a candidate.
    - **Changes (files + why)**
        - `.gitignore:20-23`: ignore large versioned Community Archive snapshot
          bodies and manifests.
        - `Makefile:8-47`: add safe HEAD-only probing and explicit snapshot
          verification targets.
        - `src/archive/snapshot.py:1-205`: model remote identity, parse
          validators, enforce positive length and streaming byte caps, hash
          while streaming, reject HEAD/GET drift, and publish with unique
          temporary files plus no-clobber links.
        - `src/archive/snapshot_contract.py:1-25`: isolate filenames, schema
          version, required columns, and human-facing check records.
        - `src/archive/snapshot_dataset_validation.py:1-149`: isolate dataset
          count, partition, column, sample, cutoff, and timestamp-quality
          invariants.
        - `src/archive/snapshot_inspection.py:1-204`: validate Parquet ID/time
          representations and scan coverage, linkage, samples, and quality.
        - `src/archive/snapshot_manifest.py:1-98`: create provenance manifests
          and publish them last without replacement.
        - `src/archive/snapshot_quality.py:1-147`: compare source timestamps
          with eligible tweet Snowflake times and retain bounded anomalies.
        - `src/archive/snapshot_validation.py:1-226`: verify source/directory
          identity, structural types, cross-field byte/count invariants,
          required columns, cutoffs, code identity, and optional deep SHA-256.
        - `src/archive/snapshot_workflow.py:1-136`: orchestrate new acquisition
          versus verified immutable reuse and reject unmanifested collisions.
        - `scripts/refresh_community_archive_snapshot.py:1-176`: default to
          metadata-only probing; require explicit `--download`; print
          ✓/✗ metadata, caps, metrics, and next steps.
        - `scripts/verify_community_archive_snapshot.py:1-103`: add the
          mandatory human verifier with deep hash by default and optional
          Parquet metric rescan.
        - `tests/test_archive_snapshot*.py`: add 23 behavior-level tests for
          transfer, schema/quality inspection, validation, workflow, and CLI
          contracts.
        - `docs/adr/019-versioned-research-data-and-artifact-manifests.md`:
          record the accepted immutable-snapshot and future artifact-binding
          decision.
        - `docs/modules/archive.md` and `docs/index.md`: document the new module
          boundary and correct the old `INSERT OR IGNORE`/writer-lock claims.
        - `docs/EXPERIMENT_LOG.md` (EXP-013): record live probe metadata,
          bounded API results, assumptions, and the pending full-download test.
        - `docs/ROADMAP.md`: separate shipped bulk acquisition from raw archive
          refresh, topology inventory, artifact compatibility, and the
          confirmed TPOT node-alignment defect.
    - **Verification**
        - Focused TDD surface:
          `23 passed` across transfer, structural validation, acquisition
          workflow, and CLI tests.
        - Credential-free backend suite with normal clean-checkout write access:
          `1230 passed, 5 skipped, 20 warnings`.
        - Docs hygiene verifier: `9 passed, 0 failed`.
        - Live canonical HEAD:
          snapshot `20260725T045122Z-4123f74b1a43`, 901,456,905 bytes,
          Last-Modified `2026-07-25T04:51:22+00:00`, ETag
          `"b07a2925eca027be751c5814fe3ddffe-54"`.
        - Probe-only output explicitly confirmed no body download and no file
          changes.
        - First full transfer: 901,456,905 bytes received; strict inspection
          rejected the string timestamp schema and wrote no manifest.
        - Refined full-file scan: 8,318,250 rows, 34,684 accounts, source maximum
          2026-07-25T04:15:29Z, Snowflake maximum
          2026-07-25T04:15:29.758Z, 108 >1-second timestamp anomalies.
        - Completed snapshot:
          `data/community_archive/snapshots/20260725T045122Z-4123f74b1a43/`;
          SHA-256
          `f40645e181976558f2e107528e9eebf90d82038881fdb886d759e973c3fd3667`;
          producer `7b405bb5b56a83d2764ffb9598ae6279efd14a6f`,
          `git_dirty=false`.
        - Independent verifier recomputed the 901,456,905-byte file hash and
          rescanned every dataset metric with zero failed checks.
        - `make verify-baseline` on the host correctly rejected Node 26 because
          the repository/CI contract is Node 22; this repeats EXP-012's known
          runtime diagnostic and is unrelated to the Python snapshot surface.
        - All new implementation and test files are below 300 lines;
          `git diff --check` passes.
    - **Residuals**
        - The first unmanifested candidate was explicitly removed and
          reacquired; only the completed immutable snapshot remains.
        - The tweet-only Parquet does not refresh following/follower topology;
          bounded raw-object inventory is separate future work.
        - Existing `store.py`/fetch CLI still have terminal-status, username
          identity, update, and presence-history limitations documented in the
          roadmap.
        - `WORKLOG.md`, `ROADMAP.md`, and `EXPERIMENT_LOG.md` remain above the
          300-line threshold; decomposition is tracked rather than mixed into
          this data-acquisition phase.

## Assumption-Testing Repository Readiness (2026-07-25)

- [2026-07-25 21:38 IST] **Recovered current main into an isolated,
  reproducible code + frozen-data baseline (Codex GPT-5)**
    - **Goal**
        - Make the repository safe to begin empirical tests of clustering,
          network discoverability, and soft group-membership assumptions without
          pulling into or repairing the backup-synchronized conflicted checkout.
    - **Hypotheses**
        - `H1` (`0.60`): current `origin/main` contains the intended source and
          most old-checkout changes are upstream copies or sync/EOL noise.
        - `H2` (`0.25`): a small set of genuine local-only code/tests needs
          preservation.
        - `H3` (`0.15`): toolchain and data-path assumptions, rather than source
          drift, block a reproducible baseline.
    - **Predicted outcome**
        - Normalized comparison finds no or very little unique local source;
          CI-equivalent code gates pass on the exact toolchain; independently
          copied data matches the immutable source at the handoff boundary and
          reports its age instead of being mistaken for current network truth.
    - **Result**
        - `H1` confirmed, `H2` rejected, `H3` confirmed. Across 749 relevant
          paths, 746 match current main after CRLF normalization; the only
          mismatch is a superseded historical `AGENTS.md`; two old-only files
          were intentionally deleted upstream. Genuine local-only
          source/docs/tests: **0**.
        - Python 3.12 failed to install `pandas==2.1.0`; exact CI Python 3.11.15
          installed all 55 requirements. Node 26 caused 43 coupled
          `localStorage` test failures; checksum-verified Node 22.23.1 passed all
          729 graph-explorer tests.
        - The frozen data copy is byte-identical and structurally valid but
          stale: newest tweet 2026-03-22, spectral snapshot 2026-02-26,
          propagation 2026-04-10.
    - **Confidence**
        - `0.99` that the clean checkout loses no unique code/docs/tests.
        - `0.96` that the copied artifacts are a sound frozen control baseline.
        - `0.35` that the baseline represents the current Community Archive or
          current social graph; a refresh/manifest phase is still required.
    - **Fallback plan**
        - Keep the old checkout immutable and recover any disputed policy from
          Git history. If later data verification diverges, discard only the
          ignored working copies and recreate them from the source; continue
          method work on deterministic fixtures until refresh semantics are
          approved.
    - **Changes (files + why)**
        - `tpot-analyzer/.python-version:1` and `.nvmrc:1`: pin the local
          interpreter majors to CI's Python 3.11 and Node 22.
        - `tpot-analyzer/.github/workflows/test.yml:41-48`: replace the
          untracked-production-artifact cluster gate with two granularities over
          the committed deterministic medium fixture.
        - `tpot-analyzer/Makefile:8-41`: add `verify-baseline` and a distinct
          credential-free `make test-ci` target while preserving the historical
          unfiltered `make test` contract.
        - `tpot-analyzer/scripts/verify_clusters.py:1-103`: use a sparse
          production-safe synthetic adjacency and temporary label database,
          print explicit failure metrics/next steps, and return non-zero on
          exceptions or failed checks.
        - `tpot-analyzer/scripts/verify_assumption_baseline.py:1-85`: add the
          human-facing, read-only baseline CLI with strict certification-option
          validation.
        - `tpot-analyzer/scripts/_assumption_baseline_checks.py:1-116`: isolate
          Git, runtime, lock-hash, status, and reporting checks.
        - `tpot-analyzer/scripts/_assumption_baseline_data.py:1-240`: isolate
          source/working inode-size-hash parity, source/working WAL quiescence,
          immutable SQLite schema/count/integrity checks, Snowflake-based
          freshness, and bound artifact metadata.
        - `tpot-analyzer/tests/test_verify_assumption_baseline.py:1-69`: cover
          invalid hash certification, required snapshot sidecars, and
          descriptive empty-archive failure.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:7-100,155-205,234-238,274-279`:
          align onboarding with CI, use `npm ci`, remove the nonexistent Ruff
          contract, replace the unused `shadow.db` copy advice, and document
          immutable-source data certification.
        - `tpot-analyzer/docs/EXPERIMENT_LOG.md:5-95`: record EXP-012, including
          rejected runtime assumptions, hashes, test outcomes, and the
          Snowflake-date lesson.
        - `tpot-analyzer/docs/ROADMAP.md:5,85-95,153-178,418-432`: record the
          shipped readiness work and future dependency-security, refresh,
          unified-data-path, artifact-manifest, and documentation-decomposition
          work.
    - **Operational data handoff (gitignored)**
        - Clean code checkout:
          `/Volumes/AirBackup/home/Documents/Ongoing Local/Project 2 - Map TPOT - clean-main`
          on `codex/community-archive-readiness`, based on `7cfb45f`.
        - Old checkout was not pulled, reset, or edited. It remains the recovery
          and immutable-data source.
        - APFS copy-on-write files were created only for `archive_tweets.db`,
          `cache.db`, active full/TPOT graph artifacts, adjacency caches, and
          propagation outputs. `archive_cache/` and unrelated experimental DBs
          were not copied.
        - Core handoff hashes:
          - archive DB:
            `c99b23fc83e1d01e64962124385674324a163ab6ccfee2a36d59cb995b894cd4`
          - cache DB:
            `4e04289dd6d86f7166f8cdfadb03443e6925f6b90b710393fc93a648baf8a552`
          - spectral:
            `05306f30c329bc7461c770228db77b39ac34144b0919e62070567e55e3796b8e`
          - propagation:
            `1d12f3371205260d7808d1b01c6ecd66cb3cdb7013420cb9a591993d2082a830`
    - **Verification**
        - `make verify-baseline` under Node 22.23.1 → pass (runtime, docs,
          dependency contract, API contracts, cluster granularities 25/40);
          Node 26 now fails explicitly.
        - Deep data certification → `56 passed, 0 failed`; both SQLite
          `quick_check` results `ok`; all eight required source/working hash
          pairs match, have distinct inodes, and source/working WALs are
          quiescent.
        - Readiness verifier regressions → `3 passed`.
        - Backend `make test-ci` → `1210 passed, 5 skipped, 20 warnings`.
        - Public site → `12 files / 184 tests passed`.
        - Graph explorer, Node 22.23.1 → `30 files / 729 tests passed`.
    - **Residuals / human gates**
        - Current Node lockfiles report 23 graph-explorer vulnerabilities
          (2 critical) and 4 high-severity public-site vulnerabilities. No
          automatic audit fix was applied; upgrades need a reviewed dependency
          change.
        - The data is suitable as a frozen control, not a current-state result.
          Snapshot-aware Community Archive refresh semantics and a cross-artifact
          manifest remain an architectural human gate.
        - `docs/WORKLOG.md`, `docs/ROADMAP.md`, and `docs/EXPERIMENT_LOG.md`
          exceed 300 LOC. This phase made narrow mandated append-only updates;
          decomposition remains explicitly tracked in the roadmap.

## Monolith-Split Sweep (2026-05-25)

- [2026-05-25] **Five monoliths split across 5 commits, all pushed (Claude Opus 4.7)**
    - **Goal**
        - Clear every file from `docs/TECH_DEBT_SCAN_2026-03-24.md`'s "Size Hotspots" list. The pattern, established once and repeated: extract method clusters into private mixin/helper modules under a sibling `_internals/` package, keep the original file as a thin coordinator with re-exports for back-compat so test imports keep working.
    - **Commits (oldest to newest, all in `origin/main` at `7a6b393`)**
        - `68b5c56` `refactor(shadow): extract 9 pure parsers from SeleniumWorker (-252 LOC)` — `@staticmethod` parsers (`handle_from_href`, `clean_bio_text`, `parse_compact_count`, `parse_profile_schema_payload`, etc.) → `src/shadow/selenium_parsing.py`. Class keeps one-line `staticmethod()` wrappers so the ~100 `SeleniumWorker._method(...)` call sites in tests/scripts work unchanged.
        - `a548088` `refactor(shadow): split SeleniumWorker into coordinator + 4 behavior mixins` — `selenium_worker.py` 2,198 → **102 LOC**. Four mixins under `src/shadow/selenium_internals/`: `_driver_mixin` (lifecycle/login), `_list_capture_mixin` (fetch_*/scroll), `_profile_mixin` (overview/status detection), `_counters_mixin` (anchor walking). Two tests needed patch-path updates (`patch('src.shadow.selenium_worker.WebDriverWait')` → mixin path) because `from X import Y` makes a local binding that re-exports can't shadow.
        - `7967243` `refactor(scripts): split export_public_site.py into orchestrator + 3 helpers` — 1,285 → **388 LOC**. Helpers under `scripts/_export_helpers/`: `_community_extractors`, `_tweet_evidence`, `_slug_registry`.
        - `89d074a` `refactor(scripts): split active_learning.py into orchestrator + 4 helpers` — 1,066 → **415 LOC**. Helpers under `scripts/_active_learning_helpers/`: `_account_selection`, `_labeling`, `_reporting`, `_measurement`.
        - `7a6b393` `refactor(shadow): split HybridShadowEnricher into coordinator + 5 mixins` — `enricher.py` 2,449 → **953 LOC**. Five mixins under `src/shadow/_enricher_internals/`: `_observability_mixin`, `_freshness_mixin`, `_refresh_actions_mixin`, `_record_builders_mixin`, `_capture_helpers_mixin`. The 750 LOC `enrich()` method stays in the coordinator — its intertwined signal handling, pause menus, and per-seed state don't decompose cleanly without an orchestrator-level rewrite.
    - **Pattern conventions (codified, reusable)**
        - Coordinator imports each mixin and inherits in declaration order (MRO matters when methods are overridden; in practice nothing is).
        - Mixins use `from __future__ import annotations` so cross-mixin type hints (e.g. `seed: SeedAccount`) don't require importing the dataclass back from the coordinator (would be circular).
        - Mixins do **NOT** define `__init__`. State lives on the coordinator. Each mixin documents its required-state assumptions at the top.
        - Cross-mixin calls go via `self.method(...)` so Python's MRO resolves them at runtime — mixins never import each other.
        - All Selenium/dataclass re-exports stay in the coordinator for back-compat with `from src.shadow.X import Y` test imports.
        - Logger channel stays as `src.shadow.X` (explicit `LOGGER = logging.getLogger("src.shadow.X")` in each mixin) so log-grep tests don't notice the move.
        - One Windows gotcha: from `src.shadow._enricher_internals._X`, the right relative path to `src.data.shadow_store` is `...data.shadow_store` (three dots up to `src`), not `..data` (which would hit nonexistent `src.shadow.data`).
    - **Verification**
        - selenium + shadow suites: `219 passed, 2 skipped` per refactor (same before/after).
        - `test_export_public_site.py` + `test_pipeline_e2e.py`: `48 passed`.
        - `test_active_learning.py` + related: `52 passed`.
        - Total: 319 tests across the touched surface, zero behavior change.
    - **Confidence** — `0.95` (mechanical file moves with rich test coverage as the safety net)
    - **Residuals**
        - `enricher.py` is still 953 LOC — `enrich()` alone is ~750. Above the 800 monolith threshold but a 61% reduction. Decomposing `enrich()` is a method-level refactor (extracting skip-gates block, status-marker block, refresh+persist block) — separate from this file split, deferred.
        - `_freshness_mixin.py` (423 LOC) and `_list_capture_mixin.py` (884 LOC) are the next-largest files. The latter is driven by `_collect_user_list` being ~370 LOC by itself.
        - Dead-code finding inside `_make_discovery_records` (now in `_record_builders_mixin.py`): `pure_followers = followers_usernames - followers_you_follow_usernames` is computed and never used. Loop iterates ALL `followers`. Looks like intended filter that got dropped. Not investigated, not a regression introduced by this refactor.
        - The back-compat re-export pattern (staticmethod wrappers + module re-exports) defers a "migrate tests to new import paths" cleanup. That cleanup is LOC-neutral and can be done at leisure.

## SSRF Hardening — Tweet Enrichment Fetches (2026-05-21)

- [2026-05-21] **SSRF guard for tweet-enrichment URL fetches (Claude Opus 4.7)**
    - **Assumptions**
        - The tweet-enrichment pipeline only ever needs to fetch *public* web content — it has no legitimate reason to reach localhost, LAN, link-local, cloud-metadata, or tailnet addresses.
        - `t.co` link destinations resolved out of tweet text are attacker-controlled: anyone whose archive is ingested can plant a short link that redirects anywhere.
    - **Predicted outcome**
        - `fetch_link_content`, `resolve_tco_url`, and `download_image_base64` now refuse non-public targets (and non-public redirect hops) with `BlockedURLError`. The existing `except` blocks already turn that into a graceful "fetch failed" — no behavior change for public URLs.
    - **Confidence** — `0.9`
    - **Fallback plan**
        - If a legitimate fetch is over-blocked, narrow `_ip_is_blocked` or add an explicit allowlist parameter. DNS-rebinding TOCTOU is a known residual (documented in the module docstring) — close it with IP-pinned connections before any public deploy.
    - **Changes (files + why)**
        - `tpot-analyzer/src/api/url_guard.py` (NEW, ~150 LOC): `validate_url()` enforces an http(s) scheme allowlist and rejects any host resolving to a private/loopback/link-local/reserved/multicast address; explicitly blocks `100.64.0.0/10` (Tailscale/CGNAT, since `ipaddress.is_private` is version-inconsistent there) and unwraps IPv4-mapped IPv6. `safe_urlopen()` validates the URL and re-validates every redirect hop via `_ValidatingRedirectHandler`.
        - `tpot-analyzer/src/api/tweet_enrichment.py`: route `resolve_tco_url`, `fetch_link_content`, and `download_image_base64` through `safe_urlopen`; add a `tweet_id.isdigit()` guard to `fetch_syndication`. SSRF reachable path was `POST /interpret` (mode=rich) → `gather_labeling_context` → `resolve_tweet_links` → these fetches.
        - `tpot-analyzer/tests/test_url_guard.py` (NEW): 20 tests — scheme allowlist, blocked IP literals, hostname resolution (mocked `getaddrinfo`), redirect-hop revalidation.
    - **Verification**
        - `pytest tests/test_url_guard.py -q` → `20 passed`.
        - `pytest tests/test_golden_routes.py tests/test_golden_support_routes.py -q` → `23 passed` (enrichment consumers unaffected by the change).

## Topic Seed Repair (2026-04-15)

- [2026-04-15 14:35 ET] **Topic-seed ingestion + active-learning handoff repair (Codex GPT-5)**
    - **Assumptions**
        - The intended behavior is: `scripts/fetch_topic_seeds.py` stores topical search hits for context, stages the authors at the top of `frontier_ranking`, and leaves those authors eligible for the next account-level `scripts.active_learning --round 1` fetch.
    - **Predicted outcome**
        - Topic-seed runs no longer fail on helper-signature mismatch, advanced-search rows are parsed into the schema expected by `enriched_tweets`, and topic-seeded authors remain selectable until they have at least one non-`topic_seed` enrichment source.
    - **Confidence**
        - `0.93`
    - **Fallback plan**
        - If production usage shows topic-seed tweets should not live in `enriched_tweets` at all, move them into a dedicated staging table and keep only author/frontier state in the main DB. That is a larger schema change and should be reviewed before implementation.
    - **Changes (files + why)**
        - `tpot-analyzer/scripts/fetch_topic_seeds.py:18-159`: fix the ingestion contract by parsing raw `advanced_search` tweets with `parse_tweet`, logging search spend via the real `log_api_call(...)` signature, preserving author bios in `profiles`, and staging authors into `frontier_ranking` without relying on nonexistent raw fields.
        - `tpot-analyzer/scripts/active_learning.py:116-149`: narrow round-1 dedup so only prior account-level enrichment blocks selection; `topic_seed` rows now act as contextual preloads rather than suppressing the very handoff they are meant to trigger.
        - `tpot-analyzer/scripts/label_tweets_ensemble.py:317-470`: wire `config/community_glossary.json` into the actual prompt by rendering glossary-backed sub-community facets, canonical theme tags, theme dedup rules, and anti-pattern reminders so new AI-safety distinctions are exposed to the ensemble instead of sitting as dead config.
        - `tpot-analyzer/tests/test_active_learning.py:55-188`: add regression coverage for topic-seed-only accounts remaining eligible and mixed-source accounts still being suppressed.
        - `tpot-analyzer/tests/test_label_ensemble.py:156-192`: add prompt assertions for `black-box-safety`, `model-psychology`, `developmental-interpretability`, `theme:jailbreaks`, and `theme:corrigibility`.
        - `tpot-analyzer/tests/test_fetch_topic_seeds.py:1-106`: add focused tests for parsed topic ingestion, frontier staging, enrichment-log writes, and malformed raw-search rows.
        - `tpot-analyzer/scripts/verify_topic_seed_ingestion.py:1-99`: add a human-friendly verifier that prints ✓/✗ checks, counts, sample staged accounts, and next steps for the topic-seed handoff.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/pytest -q tests/test_active_learning.py tests/test_label_ensemble.py tests/test_fetch_topic_seeds.py` → `48 passed`.
        - `cd tpot-analyzer && .venv/bin/python scripts/verify_topic_seed_ingestion.py --db-path tests/does-not-exist.db` → expected failure path with explicit next-step guidance (`database: not found ...`).

## Doc Audit & Remediation (2026-03-19)

- [2026-03-19] **Full-codebase doc audit (expansion:doc-audit skill)**
    - **Findings**: 10 issues (0 P0, 4 P1, 5 P2, 1 P3)
    - Key P1s: ADR-010 title says "ADR 009", camelCase violations across communities/branches/preview APIs, golden API has 5 endpoints beyond ADR-010 spec with no backend tests, communities module had no canonical module doc
    - P2s: broken ADR links in graph.md, proof hash stale, ROADMAP missing shadow/ decomposition plans
    - **Human review**: Caught 10 hard errors in initial audit report — subagent hallucinated endpoints, missed WORKLOG entries, claimed zero test coverage where tests exist. Feedback memory saved to prevent recurrence.

- [2026-03-19] **Remediation — doc fixes + test backfill**
    - **Changes**
        - `docs/adr/010-labeling-dashboard-and-llm-eval-harness.md`: Fixed title "ADR 009" → "ADR 010"
        - `docs/modules/graph.md:53-54`: Fixed broken ADR links (006/007 filename mismatch)
        - `docs/proofs/split-determinism.md`: Updated code hash `bb8bf98` → `3bfe1da`, last verified → 2026-03-19
        - `docs/ROADMAP.md`: Added decomposition plans for enricher.py (2449 LOC), selenium_worker.py (2173 LOC), shadow_store.py (1252 LOC), expansion_strategy.py (1013 LOC)
        - `docs/modules/communities.md`: **NEW** — canonical module doc covering store (2-layer architecture), versioning (branch/snapshot), cluster_colors (ADR-013 contract), preview, all API endpoints
        - `docs/modules/INDEX.md`: Updated communities from "undocumented" to current, fixed golden.md date, added branches.py reference
        - `tests/test_golden_support_routes.py`: **NEW** — 17 integration tests covering profile (4), replies (5), engagement (5), interpret/models (3). Found retweets table schema limitation (PK = tweet_id prevents multi-retweeter lookup).
    - **Test results**: 17 new tests passing, 6 existing golden route tests still passing

## Tech Debt Sweep (2026-03-12)

- [2026-03-12] **Phase F: Pattern unification — camelCase bridge, SQLite migration, test alignment**
    - **Changes**
        - `src/api/routes/accounts.py`: Removed snake_case backward-compat aliases (`display_name`, `num_followers`, `is_shadow`) — API now returns only camelCase.
        - `graph-explorer/src/accountsApi.js`: Removed 3-way snake_case→camelCase fallback mapping.
        - `graph-explorer/src/accountsApi.test.js`: Updated fixture and removed `preserves camelCase over snake_case` test.
        - `tests/test_api_autocomplete.py`: Updated all assertions to camelCase field names.
        - `src/api/services/signal_feedback_store.py`: Migrated from in-memory list to SQLite-backed store with WAL mode. Constructor accepts `db_path` for test isolation.
        - `tests/test_signal_feedback_store.py`: All tests use `tmp_path` fixture. Added persistence round-trip and context JSON serialization tests.
        - `tests/test_analysis_routes.py`: Fixture passes `tmp_path` to SignalFeedbackStore.
        - `src/api/services/cache_manager.py`, `src/graph/signal_events.py`: Docstring clarifications (in-memory vs SQLite).
        - `tests/test_api.py`, `tests/test_cluster_colors.py`, `tests/test_discovery_endpoint_matrix.py`: Aligned with flat error format, 422 status for NO_VALID_SEEDS, ADR-013 field renames.
    - **Commits**: `34aa342`, `1559455`, `5cd38f7`
    - **Test results**: 793 passed, 2 skipped, 0 failed (Python); 63 new frontend tests (Phase F.2)

- [2026-03-12] **Phase F.2: Frontend test coverage for untested pure-logic modules**
    - **Changes**
        - `graph-explorer/src/clusterGeometry.test.js`: 28 tests covering clamp, toNumber, computeBaseCut, center, procrustesAlign, alignLayout.
        - `graph-explorer/src/tweetText.test.jsx`: 19 tests covering decodeHtmlEntities, renderTweetText, avatarColor, formatTweetDate, formatShortDate.
        - `graph-explorer/src/graphTransform.test.js`: 12 tests covering buildGraphView (null input, structural fallback, seed inclusion, shadow filtering, mutual-only, node properties, tpotness scoring, stats, case-insensitive seed resolution, bridge diagnostics).
    - **Observations**
        - `ClusterView.utils.js` is an exact duplicate of `clusterGeometry.js` (minus `alignLayout`). Consolidation opportunity.
        - Procrustes alignment has inherent numerical imprecision for trivial/degenerate inputs (~0.2 RMS for identical point sets). Tests verify behavioral properties (rmsAfter < rmsBefore) rather than exact zeros.

- [2026-03-12] **Phases B–E: Security hardening, test coverage, response contract, documentation**
    - **Commits**: `adb3509` (security), `2a48f26` (65 route tests), `6cbb792` (error contract), `e8f60fb` (docs)
    - **Security fixes**: Debug mode gated by env var, CORS restricted to allowlist, path traversal prevention in firehose, auth on extension write endpoints.
    - **API contract**: Flattened error responses from nested `{error: {code, message}}` to `{error: string, code: string}`. NO_VALID_SEEDS now returns 422.
    - **New test files**: `tests/test_discovery_routes.py` (22), `tests/test_graph_routes.py` (17), `tests/test_analysis_routes.py` (26).
    - **Docs**: `docs/reference/TUNING_PARAMETERS.md`, `docs/index.md` updated.

## Phase 4.0: Tweet Classification + Content-Aware Clustering

- [2026-03-06 04:56 UTC] **ADR-013 accuracy pass: align accepted contract with actual repo state (Codex GPT-5)**
    - **Assumptions**
        - The color-contract math is already accepted at the product level, so this pass should tighten documentation truthfulness without changing behavior.
    - **Predicted outcome**
        - `docs/adr/013-probabilistic-cluster-color-contract.md` no longer overstates current implementation status, no longer references nonexistent artifacts as if present, and matches the shipped backend/frontend color pipeline.
    - **Confidence**
        - `0.95`
    - **Fallback plan**
        - If the team wants a stricter “implemented only” ADR style, downgrade ADR-013 from `Accepted` to `Proposed` and move the deployment notes into a companion rollout doc instead of keeping them inline.
    - **Changes (files + why)**
        - `tpot-analyzer/docs/adr/013-probabilistic-cluster-color-contract.md:3-7`: keep the accepted decision, but add implementation-status language and widen scope so the GraphExplorer color-boundary rule is no longer out of scope.
        - `tpot-analyzer/docs/adr/013-probabilistic-cluster-color-contract.md:13`: fix the old-formula wording so `argmax(...)` is not incorrectly described as a weight.
        - `tpot-analyzer/docs/adr/013-probabilistic-cluster-color-contract.md:23`: clarify that ADR-013 is a rendering contract, not a commitment to one upstream membership engine.
        - `tpot-analyzer/docs/adr/013-probabilistic-cluster-color-contract.md:33-75`: tighten metric descriptions and add a current-implementation note so the doc matches the existing unweighted matched-member aggregation in `src/communities/cluster_colors.py`.
        - `tpot-analyzer/docs/adr/013-probabilistic-cluster-color-contract.md:131-151`: document the current API/rollout truth, including that `concentration` is backend-internal, the dedicated verifier is still pending, and the human approval gate happened on 2026-03-06.
        - `tpot-analyzer/docs/adr/013-probabilistic-cluster-color-contract.md:167-168`: replace the nonexistent `scripts/build_fingerprints.py` reference with a truthful reference to the planned ADR-011 fingerprint pipeline.
    - **Verification**
        - Manual consistency check against `tpot-analyzer/src/communities/cluster_colors.py`, `tpot-analyzer/src/api/cluster_routes.py`, `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx`, and `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx`.
        - No automated tests run; this was a documentation-only correction.

- [2026-02-25 16:06 UTC] **Second pass: eliminate remaining React hook dependency warnings (Codex GPT-5)**
    - **Assumptions**
        - The remaining lint warnings are stale-dependency declarations (not behavioral bugs), so explicit dependency alignment should be behavior-preserving.
    - **Predicted outcome**
        - `npm run lint` becomes fully warning-free; `ClusterCanvas`/`ClusterView` tests remain green.
    - **Confidence**
        - `0.80`
    - **Fallback plan**
        - If dependency expansion caused regressions, revert to ref-backed reads for volatile values and isolate render-effect dependencies by extracting stable selectors.
    - **Changes (files + why)**
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:253`: include `minZoomProp`/`maxZoomProp` in focus-camera effect dependencies.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:1373`: include full render-effect inputs (`canExpandNode`, `centeredNodeId`, `highlightedMemberAccountId`, palette fields, `zoomMode`) to remove stale closure risk.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:1633`: include `onSelectionChange` and `selectedSet` in hover/selection callback dependencies.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:2067`: include `logHybridZoom`, zoom bounds, and `zoomMode` in wheel-handler effect dependencies.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:71`: derive stable `expandedList`, `collapsedList`, `expandedCount`, and `focusLeafValue` for fetch effect.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:168` and `:266`: replace direct `expanded.size` reads with `expandedCount` to match declared dependencies.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:300`: align fetch-effect dependency list with the derived values used to build the request payload.
    - **Verification**
        - `cd tpot-analyzer/graph-explorer && npm run lint` → clean (`0 warnings`, `0 errors`).
        - `cd tpot-analyzer/graph-explorer && npx vitest run --silent=true src/ClusterCanvas.test.jsx src/ClusterView.integration.test.jsx src/ClusterView.test.jsx` → `53 passed`.

- [2026-02-25 15:54 UTC] **Frontend lint-gate stabilization: Vitest globals + targeted dead-code cleanup (Codex GPT-5)**
    - **Hypothesis**
        - Current `npm run lint` failures are dominated by config drift (test globals missing) and stale locals from refactors; a narrow cleanup should restore lint as a reliable quality gate without changing runtime behavior.
    - **Changes (files + why)**
        - `tpot-analyzer/graph-explorer/eslint.config.js:7`: ignore generated artifacts (`coverage`, `playwright-report`, `test-results`) and add test-file globals (`browser + node + vitest`) so test suites lint under the right environment contract.
        - `tpot-analyzer/graph-explorer/src/clusterCanvasConfig.js:1` (NEW): extract `ZOOM_CONFIG` from component file to satisfy `react-refresh/only-export-components`.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:3,133`: import shared `ZOOM_CONFIG` and use optional catch binding to remove unused error symbol.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.test.jsx:262,458`: drop unused `rerender` binding and import zoom defaults from `clusterCanvasConfig`.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.memoryleak.test.jsx:42`: remove unused `getInternalSizes` helper.
        - `tpot-analyzer/graph-explorer/src/ClusterView.integration.test.jsx:32,404`: remove unused mock param and unused post-call count variable.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:800`: remove unused `collapsingCluster` assignment in semantic-collapse path.
        - `tpot-analyzer/graph-explorer/src/ClusterView.test.jsx:1`: remove unused imports (`afterEach`, `act`).
        - `tpot-analyzer/graph-explorer/src/Discovery.jsx:6,74,110`: remove unused `normalizeHandle`/`queryState` and wire `setSelectedAutocompleteIndex` from seed-input hook.
        - `tpot-analyzer/graph-explorer/src/hooks/useSeedInput.js:118`: export `setSelectedAutocompleteIndex` so `Discovery` can control hover index.
        - `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx:77`: remove unused `graphSettings` destructure.
        - `tpot-analyzer/graph-explorer/src/accountsApi.test.js:1`: remove unused `afterEach` import.
        - `tpot-analyzer/graph-explorer/src/data.js.test.js:382`: remove unused cache-key temp vars.
        - `tpot-analyzer/graph-explorer/src/hooks/useModelSettings.test.js:2`: remove unused `waitFor` import.
        - `tpot-analyzer/graph-explorer/src/hooks/useRecommendations.js:31,113`: remove dead query-advance branch + unused cached ego state setters; keep behavior on subgraph mode unchanged.
        - `tpot-analyzer/graph-explorer/src/hooks/useRecommendations.test.js:147,300,348,760`: align destructuring with actual assertions (fix undefined/unused `result` variables).
        - `tpot-analyzer/graph-explorer/src/hooks/useAccountManager.test.js:829` and `tpot-analyzer/graph-explorer/src/hooks/useSeedInput.test.js:635`: replace `global` with `globalThis` for lint-safe timer spies.
    - **Verification**
        - `cd tpot-analyzer/graph-explorer && npm run lint` → passes with `0 errors` (`5` existing `react-hooks/exhaustive-deps` warnings remain in `ClusterCanvas.jsx` and `ClusterView.jsx`).
        - `cd tpot-analyzer/graph-explorer && npx vitest run src/ClusterCanvas.memoryleak.test.jsx src/ClusterCanvas.test.jsx src/ClusterView.integration.test.jsx src/ClusterView.test.jsx src/accountsApi.test.js src/data.js.test.js src/hooks/useModelSettings.test.js src/hooks/useRecommendations.test.js src/hooks/useAccountManager.test.js src/hooks/useSeedInput.test.js` → `10 files, 358 tests passed`.

- [2026-02-25 13:19 UTC] **Post-review hardening: interpret endpoint guardrails + labeling UI contract fixes (Codex GPT-5)**
    - **Hypothesis**
        - Four regressions identified in review can be fixed with narrow changes: undeclared YAML dependency, open-ended interpret endpoint access/model override, metrics field mismatch in labeling UI, and slider normalization drift causing intermittent 400s on label submit.
    - **Changes (files + why)**
        - `tpot-analyzer/requirements.txt:2`: add `PyYAML==6.0.2` so `src/api/routes/golden.py` imports are reproducible in fresh environments.
        - `tpot-analyzer/src/api/routes/golden.py:22`: add interpret access constants/env contracts (`GOLDEN_INTERPRET_ALLOWED_MODELS`, `GOLDEN_INTERPRET_ALLOW_REMOTE`).
        - `tpot-analyzer/src/api/routes/golden.py:63`: add allowlist + loopback checks (`_allowed_interpret_models`, `_is_loopback_request`, `_enforce_interpret_access`) to prevent arbitrary remote model spend by default.
        - `tpot-analyzer/src/api/routes/golden.py:355`: validate `threadContext` type and return explicit 400 when malformed.
        - `tpot-analyzer/src/api/routes/golden.py:410`: map access denials to HTTP 403 with descriptive error.
        - `tpot-analyzer/graph-explorer/src/Labeling.jsx:17`: replace per-field float rounding with integer-thousandths normalization, guaranteeing distributions sum to 1.0 in backend-compatible precision.
        - `tpot-analyzer/graph-explorer/src/Labeling.jsx:260`: fix metrics binding to `labeledCount` and show `labeled/total` progress.
        - `tpot-analyzer/graph-explorer/src/labelingApi.js:32`: remove unused `lucidity` argument from `submitLabel` API helper.
        - `tpot-analyzer/tests/test_golden_routes.py:207`: add `/api/golden/interpret` tests for remote deny-by-default, model allowlist rejection, and successful loopback flow with mocked OpenRouter response.
        - `tpot-analyzer/docs/index.md:47`: include ADR 010/011 in latest ADR index list to avoid documentation drift.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/pytest -q tests/test_golden_routes.py tests/test_api_autocomplete.py` → `18 passed`.
        - `cd tpot-analyzer/graph-explorer && npm run build` → successful production build.
        - `cd tpot-analyzer/graph-explorer && npx eslint src/Labeling.jsx src/labelingApi.js` → passes for touched frontend files.

- [2026-02-25 14:10 UTC] **MVP A backend curation loop scaffold (Codex GPT-5)**
    - **Hypothesis**
        - We need a normalized, persistent tweet-label/prediction schema and API layer before dashboard work; this should unlock fixed splits, queue ranking, and Brier evaluation with deterministic behavior.
    - **Changes (files + why)**
        - `tpot-analyzer/src/data/golden/constants.py:1` (NEW): define simulacrum axis constants, split/status enums, and queue weighting contract.
        - `tpot-analyzer/src/data/golden/schema.py:1` (NEW): add Option-B normalized schema + helper math/validation utilities.
        - `tpot-analyzer/src/data/golden/base.py:1` (NEW): add split bootstrap, candidate retrieval with context-cache hydration, and single-reviewer label upsert history.
        - `tpot-analyzer/src/data/golden/predictions.py:1` (NEW): add prediction ingest, disagreement/entropy queue scoring, and queue retrieval.
        - `tpot-analyzer/src/data/golden/evals.py:1` (NEW): add Brier evaluation run storage and metrics summary assembly.
        - `tpot-analyzer/src/data/golden/store.py:1` (NEW): compose focused mixins into `GoldenStore`.
        - `tpot-analyzer/src/data/golden_store.py:1`: compatibility re-export shim for existing import ergonomics.
        - `tpot-analyzer/src/api/routes/golden.py:1` (NEW): add `/api/golden/candidates|labels|queue|predictions/run|eval/run|metrics` endpoints.
        - `tpot-analyzer/src/api/server.py:24` and `tpot-analyzer/src/api/server.py:116`: register `golden_bp` in app factory startup.
        - `tpot-analyzer/tests/test_golden_routes.py:1` (NEW): route-level regression tests for split bootstrap, label state changes, queue disagreement, and eval pass criteria.
        - `tpot-analyzer/scripts/verify_mvp_a.py:1` (NEW): human-friendly ✓/✗ verification script for end-to-end MVP A backend flow.
        - `tpot-analyzer/docs/adr/009-golden-curation-schema-and-active-learning-loop.md:1` (NEW): capture schema/contract decision and constraints.
        - `tpot-analyzer/docs/index.md:1`: update docs index review date + add ADR 009/008 entries.
        - `tpot-analyzer/docs/ROADMAP.md:32`: mark MVP A backend loop item completed under Phase 4 LLM Classification.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m py_compile src/data/golden/constants.py src/data/golden/schema.py src/data/golden/base.py src/data/golden/predictions.py src/data/golden/evals.py src/data/golden/store.py src/data/golden_store.py src/api/routes/golden.py scripts/verify_mvp_a.py tests/test_golden_routes.py` → passed.
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_golden_routes.py -q` → `3 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_mvp_a --help` → CLI usage renders.

- [2026-02-25] **Architecture pivot: tweet-level LLM classification as account fingerprinting (Claude Sonnet 4.6)**
    - **Context**
        - Identified that graph-structure-only clustering cannot capture TPOT's vibe/aesthetic-based community boundaries. TPOT membership is defined by epistemic style (l1/l2/l3 simulacrum axis) and social function, not follow patterns alone. PageRank as a discovery signal is anti-correlated with TPOT membership (TPOT valorizes obscurity).
    - **Decisions (see ADR 008)**
        - Adopt two-layer architecture: (1) content-aware embedding via tweet classification (universal, runs once), (2) per-user semantic labeling via exemplar annotation (configurable, per-user).
        - Use LLM few-shot classification (OpenRouter, frontier model) with a human-curated golden dataset (`taxonomy.yaml`) to classify each tweet on three orthogonal axes: epistemic/simulacrum (l1/l2/l3), functional/social (aggression, dialectics, etc.), topic (meditation, alignment, etc.).
        - Treat liked tweets as a separate passive-engagement signal, distinct from posted tweets.
        - Active learning loop: golden dataset grows via human arbitration of high-entropy "scissor tweets"; Brier score tracks calibration per axis per model.
        - 334 anchor accounts serve as embedding scaffold for the broader follow/following graph.
    - **Data pipeline built**
        - `src/archive/fetcher.py`: streams community archive JSON per account from Supabase blob storage; atomic temp→rename cache; exponential backoff retry (4 attempts, 2/4/8/16s).
        - `src/archive/store.py`: parses tweets + likes + note-tweets into `data/archive_tweets.db`; skips retweets; INSERT OR IGNORE for safe re-runs.
        - `scripts/fetch_archive_data.py`: parallel download (N workers) + serial DB write; resume-safe (skips `ok`/`not_found` in fetch_log, retries `error`).
        - `scripts/verify_archive_vs_cache.py`: data quality comparison between archive and scraped cache.db.
    - **Status**: archive fetch in progress (316 accounts, ~halfway). Retry pass queued after first run completes (uses fixed streaming fetcher).
    - **Next**
        - Run verify_archive_vs_cache.py once fetch completes
        - Build golden dataset (collaborative: human labels tweets, we craft examples per category)
        - Build LLM eval harness + Brier score script
        - Build classification pipeline with budget controls
        - Recompute account fingerprints + clustering

## Phase 1.0: Setup & Infrastructure
- [2025-10-14] Initial setup, `codebase_investigator` analysis.
- [2025-10-14] Established `AGENTS.md` and `docs/ROADMAP.md`.
- [2025-12-08] **Architectural Refactoring (Gemini 3 Pro)**
    - **Hierarchy Decomposition**: Split monolithic `src/graph/hierarchy.py` (701 LOC) into a modular package:
        - `models.py`: Dataclasses for clusters/edges.
        - `traversal.py`: Tree navigation logic.
        - `layout.py`: PCA and edge connectivity math.
        - `builder.py`: Main orchestration logic.
    - **API Refactoring**: Refactored `server.py` (God Object, 1119 LOC) into:
        - `src/api/services/`: Dependency-injected `AnalysisManager` and `CacheManager` to replace global state.
        - `src/api/routes/`: Functional slices (Blueprints) for `core`, `graph`, `analysis`, `discovery`, `accounts`.
        - `src/api/server.py`: A lightweight Application Factory pattern (~100 LOC).
    - **Verification**: `verify_setup.py` passed.
- [2025-12-12] **Phase 1.1 (WIP): Account search → teleport → tag single accounts**
    - **Backend (teleport plumbing)**
        - `tpot-analyzer/src/api/cluster_routes.py:296` Parse `focus_leaf` query param and include it in the cache key (`_make_cache_key`) so `/api/clusters` and `/members` stay consistent.
        - `tpot-analyzer/src/graph/hierarchy/builder.py:44` Add `focus_leaf_id` parameter to `build_hierarchical_view` and apply it before greedy expansions.
        - `tpot-analyzer/src/graph/hierarchy/focus.py:1` Add deterministic “reveal leaf by splitting along the path” helper (`reveal_leaf_in_visible_set`) to guarantee a target leaf becomes visible when budget allows.
    - **Backend (search + tagging)**
        - `tpot-analyzer/src/api/routes/accounts.py:69` Add `GET /api/accounts/search?q=` using snapshot metadata for handle/name prefix search (autocomplete semantics).
        - `tpot-analyzer/src/api/routes/accounts.py:103` Add tag CRUD endpoints scoped by `ego`:
            - `GET /api/accounts/<id>/tags`
            - `POST /api/accounts/<id>/tags` with `{tag, polarity: in|not_in}`
            - `DELETE /api/accounts/<id>/tags/<tag>`
            - `GET /api/tags` for autocomplete.
        - `tpot-analyzer/src/data/account_tags.py:1` Introduce SQLite-backed `AccountTagStore` persisted at `tpot-analyzer/data/account_tags.db`.
        - `tpot-analyzer/src/api/routes/accounts.py:200` Add `GET /api/accounts/<id>/teleport_plan` which selects a base cut `n` that guarantees revealing the target leaf within `budget` (returns `focus_leaf` to use in `/api/clusters`).
    - **Frontend (wiring)**
        - `tpot-analyzer/graph-explorer/src/data.js:703` Add `focus_leaf` param propagation to `fetchClusterView` and `fetchClusterMembers`; fix timing propagation so Stage logs can show per-attempt timings.
        - `tpot-analyzer/graph-explorer/src/AccountSearch.jsx:1` Add search dropdown UI that calls `/api/accounts/search` and triggers teleport.
        - `tpot-analyzer/graph-explorer/src/AccountTagPanel.jsx:1` Add “IN / NOT IN” single-account tagging UI backed by the new account tag endpoints.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:220` Add teleport flow: clear state → apply `teleport_plan` (`visibleTarget` + `focusLeaf`) → auto-explode leaf → center camera on the member node; integrate `AccountTagPanel` in the side panel (`ClusterView.jsx:1115`).
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:98` Add member-node hit testing + highlight/centering hooks so teleport can visually focus the selected account.
    - **Repo hygiene**
        - `.gitignore` Add `tpot-analyzer/data/account_tags.db*` to keep local tag DB/WAL out of git.
    - **Verification**
        - `tpot-analyzer/scripts/verify_search_teleport_tagging.py:1` Add a human-friendly verification script that exercises `/api/clusters`, `/api/accounts/search`, `teleport_plan`, and tag CRUD with ✓/✗ output.
- [2025-12-13] **TDD backfill: regression tests for teleport + tagging**
    - **Backend unit/integration tests**
        - `tpot-analyzer/tests/test_hierarchy_focus_leaf.py:1` Covers deterministic leaf reveal (`reveal_leaf_in_visible_set`) including budget exhaustion behavior.
        - `tpot-analyzer/tests/test_account_tags_store.py:1` Covers `AccountTagStore` CRUD and tag normalization (case-insensitive keys).
        - `tpot-analyzer/tests/test_accounts_search_teleport_tags.py:1` Covers `/api/accounts/search`, `/api/accounts/<id>/teleport_plan`, and tag endpoints using Flask’s test client (no network).
    - **Frontend component tests (Vitest)**
        - `tpot-analyzer/graph-explorer/src/AccountSearch.test.jsx:1` Covers debounce + selection → `onPick`.
        - `tpot-analyzer/graph-explorer/src/AccountTagPanel.test.jsx:1` Covers tag load + add/remove flows with mocked API calls.
- [2025-12-13] **Phase 2.0 (WIP): On-demand cluster tag summary + heuristic suggested label**
    - **Goal / UX**
        - Compute tag summary only when a cluster is selected (keeps `/api/clusters` payload small).
        - Suggested label heuristic uses `score = inCount - notInCount` and picks the top tag with `score > 0`.
    - **Backend**
        - `tpot-analyzer/src/data/account_tags.py:110` Add `AccountTagStore.list_tags_for_accounts(...)` with chunking to avoid SQLite variable limits.
        - `tpot-analyzer/src/api/cluster_routes.py:582` Add `GET /api/clusters/<cluster_id>/tag_summary` returning `tagCounts` + `suggestedLabel` (uses cached view when available).
    - **Frontend**
        - `tpot-analyzer/graph-explorer/src/data.js:876` Add `fetchClusterTagSummary(...)`.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:525` Fetch tag summary on cluster select + after tag edits; render Tag summary panel and “Apply suggested label”.
    - **Tests + Verification**
        - `tpot-analyzer/tests/test_cluster_tag_summary.py:1` Covers tag summary counts + `ego` requirement.
        - `tpot-analyzer/scripts/verify_search_teleport_tagging.py:317` Extend verification to hit `/tag_summary` and confirm member-tag appears at the cluster level.
- [2025-12-16] **Stabilization: make test suite green + tighten contracts**
    - **Autocomplete/search semantics**
        - `tpot-analyzer/src/api/routes/accounts.py:1` Keep `/api/accounts/search` prefix-only (autocomplete semantics); remove dead `_rank_search_hit`.
        - `tpot-analyzer/tests/test_api_autocomplete.py:1` Align fixtures with documented expectations (5 `eigen*` accounts).
    - **Enricher testability + observability**
        - `tpot-analyzer/src/shadow/enricher.py:1` Fail fast if `policy` isn’t an `EnrichmentPolicy`; add warning logs when scrape-history lookup fails but proceed “fail-open”.
        - `tpot-analyzer/tests/conftest.py:1` Return a real `EnrichmentPolicy` fixture (no `Mock()` truthiness surprises).
        - `tpot-analyzer/tests/test_account_status_tracking.py:1` Use real `EnrichmentPolicy` in HybridShadowEnricher tests.
    - **Result**
        - `cd tpot-analyzer && .venv/bin/python -m pytest -q` → `307 passed, 7 skipped` (green).
    - **Dev tooling**
        - `tpot-analyzer/graph-explorer/package.json:1` Add `test:e2e:mock` (auto-starts Vite) and `test:e2e:mock:no-server` for reusing an already-running dev server.
        - `tpot-analyzer/scripts/run_e2e.sh:1` Add a repo-level Playwright runner for mock/full/ui/debug modes.
        - `tpot-analyzer/scripts/verify_browser_binaries.py:1` Add a browser-binary/cache verification script; docs in `tpot-analyzer/docs/diagnostics/BROWSER_BINARIES.md`.
- [2025-12-16] **E2E: lock in Phase 1 loop (mocked)**
    - **UI deep-link correctness**
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:213` Gate URL-sync effect on `urlParsed` so StrictMode mount doesn’t overwrite initial URL params before parsing (fixes flaky deep-link behavior in tests and manual reloads).
    - **Mocked E2E coverage (Playwright)**
        - `tpot-analyzer/graph-explorer/e2e/teleport_tagging_mock.spec.ts:1` Add “search → teleport → tag → tag summary → apply suggested label” regression test with fully mocked backend.
        - `tpot-analyzer/graph-explorer/e2e/cluster_mock.spec.ts:1` Stabilize cluster-view E2E by clicking nodes deterministically via canvas test helpers; add real API-failure assertion (`HTTP 500`).
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:225` Expose `window.__CLUSTER_CANVAS_TEST__` helpers in dev mode only (Playwright uses these for stable node selection).
    - **Runner updates**
        - `tpot-analyzer/graph-explorer/package.json:1` Update mock runner scripts to execute all `e2e/*mock*.spec.ts` tests.
        - `tpot-analyzer/scripts/run_e2e.sh:1` Update mock runner to execute all `e2e/*mock*.spec.ts` tests.
    - **Verification**
        - `cd tpot-analyzer/graph-explorer && npm run test:e2e:mock` (9 passed)
        - `cd tpot-analyzer/graph-explorer && npx vitest run` (7 passed)
- [2025-12-16] **UI polish: force-morph expand/collapse transitions**
    - **Goal**: remove “teleporting” feel when the cluster layout changes by using a short-lived D3 force simulation to morph nodes toward their new positions.
    - **Implementation**
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:384` Replace linear “move-to-target” tweening with a force-directed morph (`forceX/forceY` to target + `forceCollide` + `forceManyBody`) and snap to exact targets at the end for deterministic focus/teleport behavior.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:832` Keep exploded member dots visually attached to their parent cluster during morphs by translating them by the parent’s display delta.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:185` E2E helper `window.__CLUSTER_CANVAS_TEST__` returns *displayed* positions (settled/morphed), keeping Playwright clicks stable while nodes move.
    - **Verification**
        - `cd tpot-analyzer/graph-explorer && npm run test:e2e:mock` (9 passed)
        - `cd tpot-analyzer/graph-explorer && npx vitest run` (7 passed)
        - `cd tpot-analyzer && .venv/bin/python -m pytest -q` (307 passed, 7 skipped)
- [2025-12-17] **Observability: request-id correlation + disk-first logs**
    - **Goal**: eliminate “paste logs into chat” by making request timings + correlation easy to inspect via `logs/api.log` and `logs/frontend.log`.
    - **Backend**
        - `tpot-analyzer/src/api/request_context.py:1` Add ContextVar-backed request id (`req_id`) + `RequestIdFilter` for log record injection.
        - `tpot-analyzer/src/api/server.py:57` Add `before_request`/`after_request` hooks:
            - Generate/accept `X-Request-ID` (or `reqId` query) and echo it in the response header.
            - Emit access logs with `dur_ms` per request (skip `/api/log` to `DEBUG` to avoid spam).
        - `tpot-analyzer/src/api/server.py:136` Make `api.log` location stable via `TPOT_LOG_DIR` (defaults to `tpot-analyzer/logs` regardless of CWD); keep file handler at `DEBUG` and include `req=<id>` in the formatter for grepability.
        - `tpot-analyzer/src/api/log_routes.py:1` Write frontend log events to `${TPOT_LOG_DIR}/frontend.log` and include `req_id` in each JSONL entry.
    - **Dev scripts**
        - `tpot-analyzer/scripts/start_dev.sh:7` Default `API_LOG_LEVEL=DEBUG`, `CLUSTER_LOG_LEVEL=DEBUG`, `TPOT_LOG_DIR=$PROJECT_ROOT/logs`; route Vite stdout to `logs/vite.log` so `logs/frontend.log` is reserved for POST `/api/log`.
        - `tpot-analyzer/StartGraphExplorer.command:17` Ensure `TPOT_LOG_DIR` is set for the backend launch path.
    - **Verification & tooling**
        - `tpot-analyzer/scripts/verify_api_observability.py:1` Add a ✓/✗ script that checks `/api/health` + `X-Request-ID` + `api.log` correlation + `/api/log` → `frontend.log`.
        - `tpot-analyzer/scripts/tail_cluster_logs.py:1` Add a tail/filter helper (`--clusters`, `--req <id>`) for `api.log` and `frontend.log`.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest -q` (309 passed, 9 skipped)
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_api_observability` (requires backend running)
- [2025-12-17] **Repo hygiene: canonical docs + E2E naming**
    - **Docs canonicalization**
        - Repo root: replace `docs/` with a symlink to `tpot-analyzer/docs/` (keep a single canonical doc tree).
        - Repo root: remove legacy `graph-explorer/` folder (keep only `tpot-analyzer/graph-explorer/`).
    - **E2E consistency (Playwright)**
        - `tpot-analyzer/graph-explorer/e2e/cluster_real.spec.ts:1` Rename from `cluster.spec.ts`; update backend startup instructions to `python -m scripts.start_api_server`.
        - `tpot-analyzer/graph-explorer/playwright.config.ts:1` Update backend-start comment to match `scripts.start_api_server`.
        - `tpot-analyzer/scripts/run_e2e.sh:1` Update full-backend runner to execute `cluster_real.spec.ts`.
        - `tpot-analyzer/graph-explorer/package.json:1` Add `test:e2e:real` convenience script.
        - `tpot-analyzer/docs/TEST_AUDIT.md:1` Update E2E table to reference `cluster_real.spec.ts`.
        - `tpot-analyzer/CODEX_TASK_E2E_TESTS.md:1` Update “Current State” to reference `cluster_real.spec.ts`.
    - **Test suite consolidation**
        - `tpot-analyzer/tests/test_seed_profile_counts.py:1` Move root test into analyzer suite; remove sys.path hacks.
        - `tpot-analyzer/tests/test_shadow_store_migration.py:1` Move root test into analyzer suite; add `TPOT_LEGACY_DB_PATH` override + `@pytest.mark.integration`.
    - **Browser-binary docs**
        - `tpot-analyzer/docs/diagnostics/BROWSER_BINARIES.md:1` Document Playwright system browser usage + `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` for restricted-network installs.
        - `tpot-analyzer/docs/FEATURES_INTENT.md:1` Align “Disk-friendly E2E” note with system-browser approach.
    - **Verification**
        - `cd tpot-analyzer && python3 -m pytest -q tests/test_seed_profile_counts.py tests/test_shadow_store_migration.py` → `3 passed, 1 xfailed`
- [2025-12-17] **Bugfix: /api/seeds 500 + GraphExplorer crash**
    - **Root cause**
        - `tpot-analyzer/src/api/routes/accounts.py:329` was returning a Python `set` (`load_seed_candidates()` result) through `jsonify`, causing `TypeError: Object of type set is not JSON serializable` and repeated `GET /api/seeds 500` in the UI.
        - `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx:1216` rendered `graphStats.totalNodes`, which could become an array/object when `/api/graph-data` returns `directed_nodes` as a node list → React “Objects are not valid as a React child”.
    - **Fix**
        - `tpot-analyzer/src/api/routes/accounts.py:329` now returns the canonical seed/settings state (`get_seed_state()`), and `POST /api/seeds` supports both settings updates and seed list save/activate.
        - `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx:415` normalizes `data.graph.nodes` arrays into `{[id]: node}` maps and coerces `directed_nodes`/`directed_edges`/`undirected_edges` into counts for safe rendering.
        - `tpot-analyzer/graph-explorer/src/data.js:313` logs numeric counts instead of dumping arrays.
    - **Tests & verification**
        - `tpot-analyzer/tests/test_api_seeds_endpoint.py:1` adds unit tests for `/api/seeds` GET/POST.
        - `tpot-analyzer/graph-explorer/src/GraphExplorer.test.jsx:1` adds a regression test ensuring GraphExplorer renders summary counts when backend returns `directed_nodes` arrays.
        - `tpot-analyzer/scripts/verify_graph_explorer_boot.py:1` adds a ✓/✗ boot check script for `/api/seeds` and `/api/graph-data`.
    - **Note**
        - `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx` is >300 LOC (monolith); keep future changes minimal and plan a thin-slice decomposition.
- [2025-12-22] **Hybrid zoom diagnostics: scroll-to-expand instrumentation**
    - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx:106,1417,1431,1484,1532` Add opt-in HybridZoom debug logging (`?hz_log=1` or `localStorage.hybridZoomLog=1`) capturing wheel inputs, modifier-zoom path, zoom-mode transitions, and centered-node screen diagnostics for hypothesis falsification.
    - `tpot-analyzer/scripts/verify_hybrid_zoom_logging.py:1` Add a ✓/✗ verification script that scans `logs/frontend.log` for HybridZoom diagnostics and summarizes last payloads.
    - `tpot-analyzer/docs/ROADMAP.md:48` Track follow-up to decompose `ClusterCanvas.jsx` into smaller components.
- [2025-12-26] **Self-evaluating expansion with strategy scoring and caching**
    - **Goal / Design**
        - Replace deterministic expansion heuristics with a "self-evaluating" system that tries all applicable strategies and scores their outputs
        - Weights are on **evaluation signals** (size entropy, collapse ratio, fragmentation, edge separation, tag coherence), NOT on strategy selection
        - Enables user-tunable weights to define what "good structure" means
        - Precomputation + caching delivers instant expansion clicks
    - **Backend (expansion scoring)**
        - `tpot-analyzer/src/graph/hierarchy/expansion_scoring.py:1` (NEW, 465 LOC) Structure-aware scoring:
            - `compute_structure_score()` - evaluates expansion outputs on 5 weighted signals
            - `StructureScoreWeights` - user-tunable weights (default equal)
            - `StructureScoreBreakdown` - detailed component scores + human-readable reason
            - `compute_size_entropy()`, `compute_collapse_ratio()`, `compute_fragmentation_ratio()`, `compute_edge_separation_fast()`, `compute_tag_coherence()` - individual signal computations
            - `ScoredStrategy` and `rank_strategies()` for ranking strategies by score
        - `tpot-analyzer/src/graph/hierarchy/expansion_strategy.py:600` Added:
            - `execute_louvain_local()` - local Louvain community detection on induced subgraph
            - `evaluate_all_strategies()` - runs all applicable strategies and scores results
            - `get_best_expansion()` - convenience wrapper returning top-ranked strategy
    - **Backend (expansion caching)**
        - `tpot-analyzer/src/graph/hierarchy/expansion_cache.py:1` (NEW, 277 LOC) Caching infrastructure:
            - `ExpansionCache` - LRU cache with configurable TTL-based expiry
            - `CachedExpansion` - stores ranked strategies with metadata (compute time, member count)
            - `ExpansionPrecomputer` - background thread for ahead-of-time computation
            - `compute_and_cache_expansion()` - on-demand compute + cache
            - `trigger_precompute_for_visible_clusters()` - queue visible clusters for background precompute
        - `tpot-analyzer/src/graph/hierarchy/__init__.py` - exports all new symbols
    - **Tests**
        - `tpot-analyzer/tests/test_expansion_scoring.py:1` (NEW) 23 tests for scoring components
        - `tpot-analyzer/tests/test_expansion_strategy.py:407` Added 10 tests for `evaluate_all_strategies()`
        - `tpot-analyzer/tests/test_expansion_cache.py:1` (NEW) 21 tests for cache infrastructure
    - **Dependencies**
        - Added `python-louvain` package for local community detection
    - **Builder integration**
    - `tpot-analyzer/src/graph/hierarchy/builder.py:197` Replaced `should_use_local_expansion()` with `compute_and_cache_expansion()` for clusters >= 10 members
    - Added `local_expansion_strategies` dict to track which strategy was used for each expansion
    - Virtual clusters now include `expansion_strategy` field for UI display (e.g., "louvain", "core_periphery", "tag_split")
    - Falls back to dendrogram expansion if scored expansion produces single cluster

- [2025-12-30] **Test coverage hardening (goodhart audit + steelman plan) — WIP**
    - **Pre-flight review**
        - Read: `tpot-analyzer/docs/TEST_AUDIT.md`, `tpot-analyzer/docs/tasks/fix-goodharted-tests.md`, `tpot-analyzer/docs/TESTING_METHODOLOGY.md`, `tpot-analyzer/docs/ROADMAP.md`, `tpot-analyzer/docs/index.md`.
        - Hypotheses:
            - H1: Logic reimplementation in tests (e.g., ClusterView utilities, skip-coverage logic) allows behavior regressions to pass.
            - H2: Mock-call assertions in enricher orchestration tests hide missing side effects (upserts/metrics).
            - H3: Cache-internal assertions in cluster route tests bypass response contracts and miss payload regressions.
            - H4: Production-data dependencies and skip markers reduce determinism and inflate green counts.
            - H5: Oversized UI modules suppress granular tests; modularity will improve coverage focus.
    - **Completed changes (line numbers)**
        - `tpot-analyzer/scripts/verify_test_inventory.py:1`: add goodhart inventory script with ✓/✗ output + samples.
        - `tpot-analyzer/scripts/verify_backend_intent.py:1`: add backend verification script for fixtures + helper checks.
        - `tpot-analyzer/tests/fixtures/create_test_cache_db.py:1`: deterministic cache.db builder for API tests.
        - `tpot-analyzer/tests/fixtures/__init__.py:1`: mark fixtures as a package for imports.
        - `tpot-analyzer/tests/conftest.py:243`: add `temp_snapshot_dir` fixture wiring SNAPSHOT_DIR/CACHE_DB_PATH.
        - `tpot-analyzer/tests/test_api.py:11`: use deterministic cache fixture + stronger payload assertions.
        - `tpot-analyzer/src/shadow/enricher.py:1168` and `tpot-analyzer/src/shadow/enricher.py:2371`: use + expose `_compute_skip_coverage_percent`.
        - `tpot-analyzer/tests/test_shadow_enricher_utils.py:743`: assert skip coverage via helper (no reimplementation).
        - `tpot-analyzer/tests/test_cluster_routes.py:362`: assert cache hit returns identical payload; label tests use real store.
        - `tpot-analyzer/docs/ROADMAP.md:14`: capture pending test-hardening gaps (shadow enricher + fixture data).
        - `tpot-analyzer/tests/helpers/recording_shadow_store.py:1`: add recording store to assert enrichment side effects without mock-call checks.
        - `tpot-analyzer/tests/helpers/__init__.py:1`: add helper package for test utilities.
        - `tpot-analyzer/tests/test_shadow_enricher_orchestration.py:22`: switch orchestration tests to recording store + persisted outcome assertions.
        - `tpot-analyzer/tests/test_shadow_enricher_orchestration.py:443`: align delta refresh test with list-specific policy (only following refreshes).
        - `tpot-analyzer/src/graph/builder.py:76`: default archive node provenance for graph payloads.
    - **Remaining planned changes**
        - `tpot-analyzer/graph-explorer/src/ClusterView.test.jsx`: remove reimplementation tests, replace with user-flow assertions.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.memoryleak.test.jsx`: make leak checks deterministic via test hooks.
        - `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx`, `tpot-analyzer/graph-explorer/src/ClusterView.jsx`, `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx`: decompose into <300 LOC modules.
        - `tpot-analyzer/docs/index.md`: update doc index for new ADR/scripts once created.
        - `tpot-analyzer/docs/adr/006-testability-refactor.md` (NEW): record decisions on testability and modularization.
    - **Verification**
        - `cd tpot-analyzer && python3 -m pytest tests/test_shadow_enricher_orchestration.py -q` → ERROR `ModuleNotFoundError: No module named 'sqlalchemy'`.
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_shadow_enricher_orchestration.py tests/test_shadow_enricher_utils.py::TestZeroCoverageEdgeCase tests/test_cluster_routes.py::TestClusterLabelEndpoints tests/test_api.py -q` → `28 passed, 1 warning` (LibreSSL warning).

- [2026-02-09 11:26 UTC] **Bugfix: Discovery crash from hook initialization order (Codex GPT-5)**
    - **Hypothesis**
        - `Discovery` crashes because `useAccountManager` references `fireChange` in a dependency array before `fireChange` is initialized, triggering a Temporal Dead Zone `ReferenceError` during render.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/graph-explorer/src/hooks/useAccountManager.js:26`: move `fireChange` declaration before first use so render-time dependency evaluation cannot read an uninitialized `const`.
        - `tpot-analyzer/graph-explorer/src/hooks/useAccountManager.js:27`: update effect dependency to `[onAccountChange]` so callback-ref sync tracks the real input prop, not the internal notifier.
        - `tpot-analyzer/graph-explorer/src/hooks/useAccountManager.js:66`: change `markAccountPending` dependencies from `onAccountChange` to `fireChange` to match the closure and avoid stale/misleading deps.
    - **Verification**
        - `cd tpot-analyzer/graph-explorer && npm run build` → success (Vite production build completed; existing non-blocking chunk-size/import warnings remain).

- [2026-02-09 11:54 UTC] **Bugfix: `/api/subgraph/discover` 500 from route/signature drift (Codex GPT-5)**
    - **Hypothesis**
        - Discovery route refactor drifted from `src.api.discovery` contracts: `validate_request` tuple output was not unpacked and `discover_subgraph` was invoked without required `graph`/`pagerank_scores`, producing deterministic HTTP 500.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/src/api/routes/discovery.py:22`: add `_load_graph_result()` to restore route-side graph loading (in-memory snapshot -> snapshot loader -> `cache.db` fallback) so discovery has a directed graph input.
        - `tpot-analyzer/src/api/routes/discovery.py:45`: add `_resolve_seed_handles()` to resolve frontend username seeds to graph node ids before discovery scoring.
        - `tpot-analyzer/src/api/routes/discovery.py:71`: fix request validation flow by unpacking `(parsed_request, errors)` and returning structured 400 validation responses.
        - `tpot-analyzer/src/api/routes/discovery.py:108`: compute PageRank and call `discover_subgraph(directed_graph, parsed_request, pagerank_scores)` with the required signature to remove the route-level `TypeError`.
        - `tpot-analyzer/tests/test_api.py:199`: add regression test covering username-seed discovery success path (`POST /api/subgraph/discover` returns ranked payload).
        - `tpot-analyzer/tests/test_api.py:235`: add regression test covering invalid discovery payload path (400 with validation details instead of 500).
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_api.py -q` → `9 passed`.

- [2026-02-09 17:24 UTC] **Docs hygiene cleanup pass (Codex GPT-5)**
    - **Hypothesis**
        - Active docs still had stale references to retired scripts/paths and a missing canonical runbook, causing onboarding drift and broken local commands.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/docs/guides/TEST_MODE.md:5`: remove literal legacy script path from active docs while preserving migration guidance.
        - `tpot-analyzer/docs/WORKLOG.md:261`: update stale future-task path from `docs/BACKEND_IMPLEMENTATION.md` to `docs/reference/BACKEND_IMPLEMENTATION.md`.
        - `tpot-analyzer/docs/WORKLOG.md:249`: add this timestamped cleanup entry to preserve doc-hygiene rationale and verification trace.
    - **Verification**
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `6/6` checks passing.

- [2026-02-09 17:45 UTC] **Docs hygiene cleanup pass #2: historical docs modernization (Codex GPT-5)**
    - **Hypothesis**
        - Historical docs still contained runnable stale commands/scripts (`create_test_fixtures.py`, `start_test_backend.sh`, `run_all_tests.sh`, `scripts/api_server.py`) that could mislead operators despite canonical docs being fixed.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/docs/tasks/E2E_TESTS.md:36`: add modernization note with current runnable fixture/bootstrap/backend commands.
        - `tpot-analyzer/docs/tasks/E2E_TESTS.md:76`: mark legacy task-script filenames as historical/superseded and map to current implementations.
        - `tpot-analyzer/docs/tasks/E2E_TESTS.md:339`: replace stale fixture/backend verification commands with `create_test_cache_db` bootstrap + `scripts.start_api_server` workflow.
        - `tpot-analyzer/docs/archive/BUGFIXES.md:5`: add historical context banner clarifying current backend entrypoint.
        - `tpot-analyzer/docs/archive/BUGFIXES.md:119`: update backend checklist command to `.venv/bin/python -m scripts.start_api_server`.
        - `tpot-analyzer/docs/index.md:58`: add explicit historical-note bullets for `docs/tasks/E2E_TESTS.md` and `docs/archive/BUGFIXES.md`.
    - **Verification**
        - `cd tpot-analyzer && rg -n "python scripts/create_test_fixtures\\.py|\\.venv/bin/python3 scripts/api_server\\.py" docs/tasks/E2E_TESTS.md docs/archive/BUGFIXES.md` → no direct stale runnable commands remain.
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `6/6` checks passing.

- [2026-02-09 17:55 UTC] **Docs hygiene cleanup pass #3: CI gate + broad historical sweep (Codex GPT-5)**
    - **Hypothesis**
        - Docs hygiene checks should run in CI, and historical-doc drift should be enforced across all `docs/tasks/*.md` and `docs/archive/*.md`, not only two specific files.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/.github/workflows/test.yml:19`: add `Verify docs hygiene` step so PRs fail when docs drift regressions are introduced.
        - `tpot-analyzer/scripts/verify_docs_hygiene.py:43`: expand historical sweep to all markdown files under `docs/tasks/` and `docs/archive/`.
        - `tpot-analyzer/scripts/verify_docs_hygiene.py:154`: add contextualization check so legacy script references are required to be marked as historical/superseded.
        - `tpot-analyzer/docs/PLAYBOOK.md:122`: add `Docs Release Checklist` with required verification and doc-index/worklog hygiene steps.
    - **Verification**
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passing.
        - `cd tpot-analyzer && rg -n "api_server\\.py|create_test_fixtures\\.py|start_test_backend\\.sh|run_all_tests\\.sh" docs/tasks docs/archive` → only contextualized historical/superseded references remain.

- [2026-02-09 18:12 UTC] **Phase A-D sprint: discovery reliability + API contracts + service tests (Codex GPT-5)**
    - **Hypothesis**
        - Discovery had edge-case contract drift (non-object JSON shape handling, unknown seed reporting, debug cache leakage), and frontend contract paths required explicit backend parity and repeatable verification tooling.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/src/api/routes/discovery.py:45`: extend seed resolver to return unresolved inputs so unknown handles can be surfaced deterministically.
        - `tpot-analyzer/src/api/routes/discovery.py:90`: fix request-shape validation to reject non-object JSON bodies instead of coercing to `{}`.
        - `tpot-analyzer/src/api/routes/discovery.py:128`: return `NO_VALID_SEEDS` with concrete `unknown_handles` when no valid seeds remain after resolution.
        - `tpot-analyzer/src/api/discovery.py:75`: add `debug` into discovery cache key to prevent debug payload leakage across requests.
        - `tpot-analyzer/tests/test_discovery_endpoint_matrix.py:42`: add discovery regression matrix for seed normalization, unknown-seed behavior, request-shape validation, caching, and pagination.
        - `tpot-analyzer/scripts/verify_discovery_endpoint.py:70`: add human-friendly discovery verifier (`✓/✗`, metrics, next steps).
        - `tpot-analyzer/scripts/restart_and_smoke_backend.sh:1`: add backend restart + discovery smoke helper for local operator workflows.
        - `tpot-analyzer/src/api/services/signal_feedback_store.py:21`: add in-memory feedback service for discovery signal feedback and quality aggregation.
        - `tpot-analyzer/src/api/server.py:106`: inject `SIGNAL_FEEDBACK_STORE` into app config for route access.
        - `tpot-analyzer/src/api/routes/analysis.py:123`: add `/api/metrics/performance` contract endpoint used by frontend API wrappers.
        - `tpot-analyzer/src/api/routes/analysis.py:171`: add `/api/signals/feedback` and `/api/signals/quality` endpoints to match Discovery UI calls.
        - `tpot-analyzer/src/api/services/cache_manager.py:48`: expose cache-size helpers for performance diagnostics endpoint.
        - `tpot-analyzer/tests/test_api_contract_routes.py:18`: add contract tests for new performance/signals endpoints.
        - `tpot-analyzer/tests/test_signal_feedback_store.py:7`: add service behavior tests for feedback aggregation math.
        - `tpot-analyzer/tests/test_cache_manager.py:7`: add service behavior tests for graph/discovery cache storage + clear semantics.
        - `tpot-analyzer/scripts/verify_api_contracts.py:75`: add frontend/backend API route parity verifier.
        - `tpot-analyzer/scripts/verify_api_services_tests.py:29`: add route/service regression verification bundle script.
        - `tpot-analyzer/.github/workflows/test.yml:22`: add API contract verification step in CI.
        - `tpot-analyzer/docs/PLAYBOOK.md:72`: document new discovery/API verification commands.
        - `tpot-analyzer/docs/ROADMAP.md:18`: mark discovery regression verifier and API contract verifier work as implemented.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_api_contract_routes.py tests/test_discovery_endpoint_matrix.py tests/test_api.py::test_subgraph_discover_endpoint_resolves_username_seed tests/test_api.py::test_subgraph_discover_endpoint_rejects_invalid_payload -q` → `14 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_cache_manager.py tests/test_signal_feedback_store.py tests/test_api_contract_routes.py tests/test_discovery_endpoint_matrix.py -q` → `18 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_api_services_tests` → regression bundle passed (18 tests).
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_api_contracts` → `Contract gaps: 0`.
    - **Constraints**
        - Local sandbox denied port binding for live backend start (`Operation not permitted`) while validating `scripts/restart_and_smoke_backend.sh`; static/syntax checks and test-client verification were used instead.

- [2026-02-09 23:17 UTC] **Recent-activity + twitterapi.io subset verifier (Codex GPT-5)**
    - **Hypothesis**
        - Given current X app gating on follows endpoints, post recency/cadence is still high-signal and available.
        - We need an external relationship-audit comparator to quantify whether local `shadow_edge` is complete, incorrect, or a strict subset for sampled accounts.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/fetch_recent_activity.py:1` (NEW): adds batched `search/recent` harvesting for selected accounts; computes `last_tweet_at`, 7d/30d volume, median/mean post gap, engagement means, and logs request/rate-limit + estimated Post:Read spend.
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:1` (NEW): adds subset audit against `twitterapi.io` followers/followings endpoints with explicit overlap/coverage/precision metrics and missing/extra samples per account.
        - `tpot-analyzer/docs/ROADMAP.md:39` records follow-up for standardizing third-party relationship-audit key wiring and adapter behavior.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python scripts/fetch_recent_activity.py --usernames adityaarpitha eigenrobot --dry-run` → query batching preview succeeded.
        - `cd tpot-analyzer && .venv/bin/python scripts/verify_shadow_subset_against_twitterapiio.py --sample-size 1` → expected key-missing diagnostic with concrete env var names.
        - `cd tpot-analyzer && .venv/bin/python - <<'PY' ... ast.parse(...) ... PY` → syntax parse passed for both new scripts.
    - **Discovered constraints**
        - `tpot-analyzer/.env` currently includes `X_BEARER_TOKEN` but no `twitterapi.io` key variable; verifier now fails loudly with remediation steps.
        - Live X tests continue to show follows endpoint enrollment gating for the current app/token.

- [2026-02-10 02:20 UTC] **twitterapi.io verifier: per-account checkpoint writes (Codex GPT-5)**
    - **Hypothesis**
        - Full seed-list audits are long-running; writing output only at the end risks losing progress visibility and partial results if interrupted.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:360`: add `_mean_coverage(...)` helper to compute running/final average coverage from current results safely.
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:377`: add `write_report(...)` helper to persist a full JSON report payload with explicit `progress` (`completed_accounts`, `total_accounts`, `is_complete`).
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:535`: write checkpoint report after each account and print `checkpoint written (n/total)` so humans can monitor in real time.
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:547`: reuse `write_report(...)` for final report write to keep checkpoint/final schema identical.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -u scripts/verify_shadow_subset_against_twitterapiio.py --api-key "$API_KEY" --usernames adityaarpitha --max-pages 1 --page-size 200 --wait-on-rate-limit --output data/outputs/twitterapiio_shadow_audit/checkpoint_smoke.json` → checkpoint message emitted and run succeeded.
        - `cd tpot-analyzer && jq '{progress, targets, total_remote_requests, average_coverage_pct}' data/outputs/twitterapiio_shadow_audit/checkpoint_smoke.json` → shows `progress.completed_accounts=1`, `is_complete=true`.

- [2026-02-10 02:24 UTC] **Decomposition: split twitterapi.io verifier into modular helpers (Codex GPT-5)**
    - **Hypothesis**
        - `scripts/verify_shadow_subset_against_twitterapiio.py` grew past maintainable size (~575 LOC), increasing review/debug overhead and violating file-size decomposition guidance.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:1`: refactor to thin orchestrator (CLI flow + human-readable progress output) while keeping flags/output behavior stable.
        - `tpot-analyzer/scripts/shadow_subset_audit/cli.py:1`: extract argument parsing + API key resolution to isolate entrypoint config concerns.
        - `tpot-analyzer/scripts/shadow_subset_audit/remote.py:1`: extract remote endpoint schema parsing, pagination, and rate-limit handling logic.
        - `tpot-analyzer/scripts/shadow_subset_audit/local_db.py:1`: extract sqlite target selection + local follower/following resolution queries.
        - `tpot-analyzer/scripts/shadow_subset_audit/reporting.py:1`: extract overlap math and JSON report/checkpoint writer.
        - `tpot-analyzer/scripts/shadow_subset_audit/constants.py:1`: centralize default paths/key env candidates/shared symbols.
        - `tpot-analyzer/scripts/shadow_subset_audit/models.py:1`: extract `RemoteResult` dataclass for typed handoff between helpers.
        - `tpot-analyzer/scripts/shadow_subset_audit/normalize.py:1`: extract username normalization helper for consistent local/remote parsing.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python scripts/verify_shadow_subset_against_twitterapiio.py --help` → usage output renders successfully with expected options.
        - `cd tpot-analyzer && .venv/bin/python scripts/verify_shadow_subset_against_twitterapiio.py --sample-size 1` → expected missing-key diagnostic preserved (`Checked env vars: ...`).
        - `cd tpot-analyzer && .venv/bin/python scripts/fetch_recent_activity.py --dry-run --usernames user_a` → dry-run query preview works after script staging.
        - `cd tpot-analyzer && .venv/bin/python scripts/verify_docs_hygiene.py` → docs hygiene verifier still passes.

- [2026-02-10 02:57 UTC] **Observability hardening: frequent checkpoints + runtime diagnostics for twitterapi.io audit (Codex GPT-5)**
    - **Hypothesis**
        - Per-account-only checkpoints hide progress/failure cause during long runs; we need request-level observability and persisted runtime state so interruptions/failures are diagnosable.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:29`: keep entrypoint thin and add robust failure/interruption checkpoint persistence in `main()` while delegating audit loop logic.
        - `tpot-analyzer/scripts/shadow_subset_audit/runner.py:19`: extract main account/relation loop and trigger periodic + boundary checkpoints during in-flight remote fetches.
        - `tpot-analyzer/scripts/shadow_subset_audit/console.py:61`: centralize checkpoint writes so each write includes progress + runtime metadata and emits explicit checkpoint reason.
        - `tpot-analyzer/scripts/shadow_subset_audit/observability.py:42`: add `AuditRuntime` state model (status, current account/relation, remote request counters, failure reason, recent event history) plus logger wiring.
        - `tpot-analyzer/scripts/shadow_subset_audit/remote.py:103`: add structured remote events (`request_start`, `response`, `request_exception`, `rate_limit_wait`, `page_complete`, `relation_*`) via callback for live checkpoint triggers and diagnostics.
        - `tpot-analyzer/scripts/shadow_subset_audit/reporting.py:47`: add optional `runtime` payload in report JSON so checkpoint files preserve run-state observability.
        - `tpot-analyzer/scripts/shadow_subset_audit/cli.py:52`: add runtime observability flags (`--checkpoint-every-requests`, `--checkpoint-min-seconds`, `--max-event-history`, `--log-level`, `--log-file`).
        - `tpot-analyzer/scripts/shadow_subset_audit/constants.py:14`: include `API_KEY` in env fallback candidates to match current local `.env` key naming.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python - <<'PY' ... ast.parse(...) ... PY` → syntax parse passed for updated/new audit modules.
        - `cd tpot-analyzer && set -a && source .env >/dev/null 2>&1 && .venv/bin/python scripts/verify_shadow_subset_against_twitterapiio.py --usernames adityaarpitha --max-pages 1 --page-size 50 --sample-output-count 3 --wait-on-rate-limit --checkpoint-every-requests 1 --checkpoint-min-seconds 1 --max-event-history 20 --output data/outputs/twitterapiio_shadow_audit/checkpoint_observability_smoke.json` → emitted multiple in-flight checkpoints and wrote runtime metadata + `.log` file.
        - `cd tpot-analyzer && jq '.runtime | keys' data/outputs/twitterapiio_shadow_audit/checkpoint_observability_smoke.json` → runtime observability fields present (`status`, request counters, checkpoint counters, recent events, failure/termination fields).
    - **Constraints**
        - Sandbox DNS cannot resolve `api.twitterapi.io` in this session, so smoke verification confirmed observability behavior on request exceptions rather than successful remote payload fetches.

- [2026-02-10 03:39 UTC] **Resume support: avoid redundant twitterapi.io calls after interruption (Codex GPT-5)**
    - **Hypothesis**
        - Interrupted audits currently restart from account 1 and re-fetch already completed accounts; loading prior output and skipping completed usernames will reduce wasted API spend.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/shadow_subset_audit/cli.py:82`: add `--resume-from-output` flag to opt into resumable execution.
        - `tpot-analyzer/scripts/shadow_subset_audit/resume.py:50` (NEW): add robust resume-state loader that parses prior output JSON, filters rows to current target set, de-duplicates usernames, and derives carried-forward request totals from saved per-account remote metadata.
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:72`: load resume state when requested, pre-seed `results` + `total_remote_requests`, and skip completed usernames before remote calls.
        - `tpot-analyzer/scripts/verify_shadow_subset_against_twitterapiio.py:98`: add `resume_noop_complete` path when all targets are already complete, writing a final checkpoint without issuing new API requests.
        - `tpot-analyzer/scripts/shadow_subset_audit/runner.py:19`: accept `total_targets`, `completed_offset`, and `starting_total_remote_requests` so progress/index/checkpoint math remains correct across resumed runs.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python - <<'PY' ... ast.parse(...) ... PY` → syntax parse passed for updated files (`verify_shadow_subset_against_twitterapiio.py`, `runner.py`, `resume.py`, `cli.py`).
        - `cd tpot-analyzer && set -a && source .env >/dev/null 2>&1 && .venv/bin/python scripts/verify_shadow_subset_against_twitterapiio.py --usernames adityaarpitha --resume-from-output --output data/outputs/twitterapiio_shadow_audit/checkpoint_smoke.json --max-pages 1 --page-size 20 --timeout-seconds 10` → resume no-op path triggered (`remaining=0`, checkpoint reason `resume_noop_complete`).
        - `cd tpot-analyzer && set -a && source .env >/dev/null 2>&1 && .venv/bin/python scripts/verify_shadow_subset_against_twitterapiio.py --usernames adityaarpitha eigenrobot --resume-from-output --output data/outputs/twitterapiio_shadow_audit/checkpoint_smoke.json --max-pages 1 --page-size 20 --timeout-seconds 10` → skipped pre-completed `adityaarpitha`; resumed at `[2/2] @eigenrobot` and preserved carried-forward request count.

- [2026-02-10 05:15 UTC] **ADR draft: shared tagging + anchor-conditioned TPOT membership (Codex GPT-5)**
    - **Hypothesis**
        - Current local-only tagging is sufficient for single-user exploration but cannot support collaborative active learning or Chrome-extension labeling workflows.
        - A shared backend and explicit membership formulation are required before implementation can proceed safely.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/docs/adr/006-shared-tagging-and-tpot-membership.md:1`: add a proposed ADR defining the two-surface architecture (graph navigation + feed labeling), shared tag storage decision, anchor-conditioned TPOT probability model, migration outline, and blocking questions.
        - `tpot-analyzer/docs/index.md:6`: update last-reviewed date to keep doc-index freshness explicit.
        - `tpot-analyzer/docs/index.md:45`: add direct link to ADR 006 under Architecture and Specs for discoverability.
        - `tpot-analyzer/docs/ROADMAP.md:33`: add feature backlog items for anchor-conditioned TPOT scoring and uncertainty-driven active learning.
        - `tpot-analyzer/docs/ROADMAP.md:57`: add infrastructure backlog items for shared tag storage migration and Chrome-extension integration.
        - `tpot-analyzer/docs/WORKLOG.md:396`: add this timestamped entry for ADR intent and traceability.
    - **Verification**
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passing.

- [2026-02-10 05:30 UTC] **Phase 1 implementation: extension feed ingestion + account exposure summaries (Codex GPT-5)**
    - **Hypothesis**
        - Capturing in-feed tweet impressions gives stronger semantic signal than follow edges alone for "who is this account?" modeling.
        - A thin ingestion + summary layer can ship safely now and feed later TPOT membership scoring iterations.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/src/data/feed_signals.py:1` (NEW): add SQLite store for extension event ingest with idempotent event keys, validation, raw payload retention, and tweet rollup upserts.
        - `tpot-analyzer/src/data/feed_signals_queries.py:1` (NEW): extract summary/top-exposure query + keyword extraction helpers to keep `feed_signals.py` under 300 LOC and preserve modularity.
        - `tpot-analyzer/src/api/routes/extension.py:1` (NEW): add `/api/extension/feed_events`, `/api/extension/accounts/<id>/summary`, and `/api/extension/exposure/top` endpoints with scope validation (`ego`, `workspace_id`) and explicit error handling.
        - `tpot-analyzer/src/api/server.py:26`: register `extension_bp` so extension APIs are available in app factory startup paths.
        - `tpot-analyzer/tests/test_feed_signals_store.py:1` (NEW): add store-level tests for dedupe, rollup counts, keyword extraction, and invalid day windows.
        - `tpot-analyzer/tests/test_extension_routes.py:1` (NEW): add route-level tests for validation, ingest roundtrip, account summary, and top exposure listing.
        - `tpot-analyzer/scripts/verify_extension_feed_ingest.py:1` (NEW): add human-friendly ✓/✗ verifier for extension ingestion + summary endpoints.
        - `tpot-analyzer/docs/reference/DATABASE_SCHEMA.md:363`: document `feed_events` and `feed_tweet_rollup` schemas and intent.
        - `tpot-analyzer/docs/ROADMAP.md:37`: capture follow-up for embedding + recency/ranking-bias normalization on extension-captured content.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_feed_signals_store.py tests/test_extension_routes.py tests/test_api_contract_routes.py -q` → `7 passed`.
    - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_extension_feed_ingest --help` → CLI usage renders.
    - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passing.

- [2026-02-10 06:17 UTC] **Phase 1.1 implementation: open-mode policy controls + continuous firehose + tag-scope purge (Codex GPT-5)**
    - **Hypothesis**
        - We can safely keep localhost ingestion in open mode while still making privacy boundaries explicit via allowlist toggles and tag-scoped purge.
        - Continuous append-only firehose mirroring gives Indra's Net-compatible raw telemetry without blocking existing summary APIs.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/src/data/feed_scope_policy.py:101` (NEW): add scoped policy table/store with defaults (`open`, `infinite`, `continuous`) plus allowlist/firehose toggles.
        - `tpot-analyzer/src/data/feed_firehose.py:14` (NEW): add append-only NDJSON firehose writer for continuous raw event mirroring.
        - `tpot-analyzer/src/data/feed_signals_admin.py:49` (NEW): add admin queries for raw event paging, inserted-key fetch, and scoped deletion.
        - `tpot-analyzer/src/data/feed_signals.py:148`: extend ingest to optionally return inserted event keys for downstream firehose selection.
        - `tpot-analyzer/src/data/account_tags.py:110`: add positive-tag account-id lookup helpers for tag-based allowlist and purge.
        - `tpot-analyzer/src/api/routes/extension.py:35`: add `/api/extension/settings`, `/feed_events/raw`, `/feed_events/purge_by_tag`, and ingest policy/firehose orchestration.
        - `tpot-analyzer/src/api/routes/extension_runtime.py:26` (NEW): extract extension route singleton dependency wiring to keep route module <300 LOC.
        - `tpot-analyzer/src/api/routes/extension_utils.py:13` (NEW): extract shared request validation + ingest auth helpers.
        - `tpot-analyzer/src/api/routes/extension_read_routes.py:14` (NEW): extract summary/top read routes to preserve modularity.
        - `tpot-analyzer/tests/test_extension_routes.py:40`: add route coverage for settings updates, firehose filtering, raw-event reads, tag-scope purge, and guarded mode auth.
        - `tpot-analyzer/tests/test_feed_scope_policy_store.py:9` (NEW): add policy-store behavior/validation tests.
        - `tpot-analyzer/tests/test_feed_signals_admin_store.py:10` (NEW): add admin-store raw/purge tests.
        - `tpot-analyzer/tests/test_feed_signals_store.py:9`: assert inserted-event-key collection during ingest.
        - `tpot-analyzer/tests/test_account_tags_store.py:9`: assert new tag-to-account lookup helpers.
        - `tpot-analyzer/scripts/verify_extension_feed_ingest.py:95`: extend verifier to check settings API, raw-event API, firehose output, and tag-scope purge.
        - `tpot-analyzer/docs/reference/DATABASE_SCHEMA.md:414`: document `feed_scope_policy` table and firehose stream path semantics.
        - `tpot-analyzer/docs/ROADMAP.md:65`: add follow-up items for firehose relay worker and storage/privacy-boundary verification.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_extension_routes.py tests/test_feed_signals_store.py tests/test_feed_signals_admin_store.py tests/test_feed_scope_policy_store.py tests/test_account_tags_store.py tests/test_api_contract_routes.py -q` → `17 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_extension_feed_ingest --help` → CLI usage renders.
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passing.

- [2026-02-10 07:05 UTC] **Phase 1.2 implementation: spectator firehose relay worker (Codex GPT-5)**
    - **Hypothesis**
        - Spectator-mode raw streams (X, YouTube shorts, Instagram, etc.) should remain outside main prayer-detection DB and be relayed via a checkpointed firehose worker.
        - A byte-offset checkpoint + retry/backoff transport is sufficient to keep relay durable under local restarts and endpoint hiccups.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/relay_firehose_to_indra.py:1` (NEW): add thin CLI for continuous/once relay execution with batching, retry, and participant filtering controls.
        - `tpot-analyzer/scripts/firehose_relay/models.py:1` (NEW): add typed models for records/read results/send results/checkpoint state.
        - `tpot-analyzer/scripts/firehose_relay/state.py:1` (NEW): add atomic checkpoint load/save helpers for `relay_checkpoint.json`.
        - `tpot-analyzer/scripts/firehose_relay/reader.py:1` (NEW): add incremental NDJSON reader with truncation/rotation handling + parse-error accounting.
        - `tpot-analyzer/scripts/firehose_relay/transport.py:1` (NEW): add HTTP POST transport with explicit retry/backoff behavior.
        - `tpot-analyzer/scripts/firehose_relay/worker.py:20` (NEW): add relay loop that skips participant events by default, forwards spectator batches, tracks lag, and persists checkpoint metrics.
        - `tpot-analyzer/scripts/verify_firehose_relay.py:1` (NEW): add human-friendly ✓/✗ verifier with local mock endpoint and concrete forwarding metrics.
        - `tpot-analyzer/tests/test_firehose_relay_worker.py:8` (NEW): add relay tests for spectator-only forwarding and checkpoint resume semantics.
        - `tpot-analyzer/docs/ROADMAP.md:65`: mark firehose relay worker item complete and record implementation artifacts.
        - `tpot-analyzer/docs/reference/DATABASE_SCHEMA.md:450`: document relay checkpoint file contract and metrics fields.
        - `tpot-analyzer/docs/PLAYBOOK.md:84`: document relay verification/run commands for operations.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_firehose_relay_worker.py tests/test_extension_routes.py tests/test_feed_scope_policy_store.py tests/test_feed_signals_admin_store.py tests/test_feed_signals_store.py tests/test_account_tags_store.py tests/test_api_contract_routes.py -q` → `19 passed`.
        - `cd tpot-analyzer && .venv/bin/python scripts/verify_firehose_relay.py` → all checks passed (`events_forwarded_total=2`, `events_skipped_participant_total=1`).
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passing.

## Upcoming Tasks
1.  **Unit Test Backfill**: The refactor moved code, but existing tests in `test_api.py` are integration tests dependent on a live DB. We need unit tests for the new `services/` and `routes/` that mock the managers.
2.  **Documentation Update**: `docs/reference/BACKEND_IMPLEMENTATION.md` needs to be updated to reflect the new modular architecture.
3.  **Frontend Alignment**: Ensure `graph-explorer` API calls match the new route structure (URLs remained mostly the same, but need verification).

- [2026-02-10 15:15 UTC] **Relay default endpoint alignment: localhost firehose ingest (Codex GPT-5)**
    - **Hypothesis**
        - Relay ergonomics improve if the CLI defaults to the now-live Indra endpoint (`http://localhost:7777/api/firehose/ingest`) instead of requiring a mandatory flag/env setup each run.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/relay_firehose_to_indra.py:21`: add `DEFAULT_INDRA_FIREHOSE_ENDPOINT` constant and `_default_endpoint_url()` helper.
        - `tpot-analyzer/scripts/relay_firehose_to_indra.py:43`: switch `--endpoint-url` default to `_default_endpoint_url()` so unset/blank env falls back to localhost ingest path.
        - `tpot-analyzer/tests/test_relay_firehose_cli.py:1` (NEW): add unit tests for default endpoint, env override, and blank-env fallback behavior.
        - `tpot-analyzer/docs/PLAYBOOK.md:96`: update operator command to use no-flag default relay run; keep explicit override example for non-default endpoints.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_relay_firehose_cli.py tests/test_firehose_relay_worker.py -q` → `5 passed` (plus existing LibreSSL urllib3 warning).

- [2026-02-17 19:00 UTC] **Phase 0/1 foundation: observation-aware adjacency controls + diagnostics (Codex GPT-5)**
    - **Hypothesis**
        - The current clustering path treats unobserved edges as absent edges; introducing an optional observation-aware IPW adjacency path (behind settings flags) should improve math fidelity under incomplete graph coverage while preserving safe default behavior.
    - **Changes (files + why)**
        - `tpot-analyzer/src/graph/observation_model.py:1` (NEW): add observation completeness + inverse-probability weighting helpers and stats summarization.
        - `tpot-analyzer/src/api/cluster_routes.py:1`: wire optional adjacency build path (`obs_weighting=off|ipw`), maintain legacy cache compatibility, and include observation metadata in cluster responses.
        - `tpot-analyzer/src/graph/seeds.py:1`: add graph settings schema flags (`hierarchy_engine`, `membership_engine`, `obs_weighting`, `obs_p_min`, `obs_completeness_floor`) with value clamping/validation.
        - `tpot-analyzer/config/graph_settings.json:1`: add matching default settings entries so behavior is explicit and operator-tunable.
        - `tpot-analyzer/src/graph/__init__.py:1`: export observation helpers for shared graph-module usage.
        - `tpot-analyzer/tests/test_observation_model.py:1` (NEW): test completeness math, IPW weighting behavior, clipping, and summary output.
        - `tpot-analyzer/tests/test_graph_settings_flags.py:1` (NEW): test settings defaults/sanitization for new graph math flags.
        - `tpot-analyzer/scripts/verify_phase0_baseline.py:1` (NEW): add baseline verifier with explicit ✓/✗ checks and next-step guidance.
        - `tpot-analyzer/scripts/verify_observation_weighting.py:1` (NEW): add observation/IPW verifier with metrics reporting.
        - `tpot-analyzer/docs/adr/007-observation-aware-clustering-membership.md:1` (NEW): record decision and rollout plan for observation-aware math and membership evolution.
        - `tpot-analyzer/docs/index.md:1`: link ADR 007 and refresh docs index metadata.
        - `tpot-analyzer/docs/ROADMAP.md:1`: track partial-observability benchmarking and uncertainty follow-ups.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_observation_model.py tests/test_graph_settings_flags.py tests/test_api_seeds_endpoint.py tests/test_cluster_routes.py -q` → `41 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_phase0_baseline` → all checks passed.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_observation_weighting --mode off` → passed.
    - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_observation_weighting --mode ipw --p-min 0.01 --completeness-floor 0.01` → passed (`nodes=95303`, `edges=322621`, `mean_completeness=0.6907`, `clipped_pairs=63268`).

- [2026-02-17 19:07 UTC] **Phase 1.1 implementation: GRF membership endpoint + anchor aggregation (Codex GPT-5)**
    - **Hypothesis**
        - We can ship a principled TPOT membership path now by solving a GRF/harmonic labeling system from ego-scoped account-tag anchors, while keeping existing hierarchy rendering unchanged.
    - **Changes (files + why)**
        - `tpot-analyzer/src/graph/membership_grf.py:1` (NEW): add sparse GRF solver (`compute_grf_membership`) with regularized Laplacian solve, uncertainty outputs, and convergence metadata.
        - `tpot-analyzer/src/data/account_tags.py:171`: add `list_anchor_polarities(ego=...)` to aggregate per-account anchor polarity by sign of net tags.
        - `tpot-analyzer/src/api/cluster_routes.py:149`: add membership helpers (engine gate, anchor resolution, anchor digest, coverage estimate).
        - `tpot-analyzer/src/api/cluster_routes.py:846`: add `GET /api/clusters/accounts/<account_id>/membership` endpoint returning probability, CI, uncertainty/evidence, anchor counts, and solver metadata (cache-backed).
        - `tpot-analyzer/src/graph/__init__.py:31`: export GRF module symbols.
        - `tpot-analyzer/tests/test_membership_grf.py:1` (NEW): solver behavior tests (balanced chain, connectivity bias, missing-anchor validation).
        - `tpot-analyzer/tests/test_cluster_membership_endpoint.py:1` (NEW): route contract tests for disabled engine, missing anchors, and cache-hit behavior.
        - `tpot-analyzer/tests/test_account_tags_store.py:44`: extend store tests for anchor-polarity aggregation.
        - `tpot-analyzer/scripts/verify_membership_grf.py:1` (NEW): add human-friendly phase verifier with ✓/✗ checks + metrics + next steps.
        - `tpot-analyzer/docs/ROADMAP.md:30`: record shipped GRF endpoint and add calibration/UI integration follow-ups.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_membership_grf.py tests/test_cluster_membership_endpoint.py tests/test_account_tags_store.py -q` → `8 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_cluster_routes.py tests/test_api_seeds_endpoint.py tests/test_observation_model.py tests/test_graph_settings_flags.py tests/test_membership_grf.py tests/test_cluster_membership_endpoint.py -q` → `47 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_membership_grf` → all checks passed.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_phase0_baseline && .venv/bin/python -m scripts.verify_observation_weighting --mode off` → all checks passed.

- [2026-02-18 07:20 UTC] **Phase 1.2 implementation: ClusterView membership panel wiring (Codex GPT-5)**
    - **Hypothesis**
        - Showing account-level GRF membership in the existing right sidebar (selected account section) will add actionable TPOT context without changing cluster navigation behavior.
    - **Changes (files + why)**
        - `tpot-analyzer/graph-explorer/src/data.js:620`: add `fetchAccountMembership(...)` API helper for `GET /api/clusters/accounts/<id>/membership?ego=...` with explicit error propagation.
        - `tpot-analyzer/graph-explorer/src/AccountMembershipPanel.jsx:1` (NEW): add focused presentational panel for probability, CI, uncertainty, coverage, anchor counts, and high-uncertainty warning.
        - `tpot-analyzer/graph-explorer/src/ClusterDetailsSidebar.jsx:9`: render membership panel in selected-account block and thread loading/error/membership props.
        - `tpot-analyzer/graph-explorer/src/ClusterView.jsx:450`: add `loadMembership` flow, abort handling, selected-account membership effect, and refresh on tag changes.
        - `tpot-analyzer/graph-explorer/src/ClusterView.test.jsx:161`: update `./data` mock to include `fetchAccountMembership`.
        - `tpot-analyzer/graph-explorer/src/ClusterView.integration.test.jsx:651`: add end-to-end UI test for member-click → membership fetch → panel render.
        - `tpot-analyzer/graph-explorer/src/AccountMembershipPanel.test.jsx:1` (NEW): add component tests for guidance/loading/data render states.
        - `tpot-analyzer/scripts/verify_membership_ui.py:1` (NEW): add human-friendly verification script for frontend membership wiring and artifact presence.
        - `tpot-analyzer/docs/ROADMAP.md:44`: mark membership-panel integration complete and add decomposition follow-up for `ClusterView.jsx`/`data.js`.
    - **Verification**
        - `cd tpot-analyzer/graph-explorer && npx vitest run src/AccountMembershipPanel.test.jsx src/ClusterView.test.jsx src/ClusterView.integration.test.jsx` → `41 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_membership_ui` → `12/12` checks passed.

- [2026-02-18 09:30 UTC] **Phase 1 remediation kickoff: fetcher resource cleanup + real-DB test isolation (Codex GPT-5)**
    - **Hypotheses**
        - `CachedDataFetcher.close()` leaks SQLite handles because SQLAlchemy engine pools are never disposed.
        - A subset of tests reads shared `data/cache.db` by default, introducing environment-coupled flakiness (`disk I/O error`) during full-suite execution.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/src/data/fetcher.py:64`: update `close()` to always dispose the SQLAlchemy engine/pool and clear owned HTTP client references; this releases SQLite file descriptors deterministically.
        - `tpot-analyzer/tests/test_shadow_coverage.py:13`: add `_require_real_cache_db()` opt-in gate (`TPOT_RUN_REAL_DB_TESTS`) for shared-db coverage tests.
        - `tpot-analyzer/tests/test_shadow_coverage.py:108`: gate `test_low_coverage_detection()` on explicit shared-db opt-in.
        - `tpot-analyzer/tests/test_shadow_coverage.py:146`: gate `test_archive_vs_shadow_coverage()` on explicit shared-db opt-in.
        - `tpot-analyzer/tests/test_shadow_coverage.py:203`: gate `test_coverage_script_runs()` on explicit shared-db opt-in.
        - `tpot-analyzer/tests/test_shadow_enricher_utils.py:26`: add `REAL_DB_REQUIRED` skip marker for integration classes that depend on shared `data/cache.db`.
        - `tpot-analyzer/tests/test_shadow_enricher_utils.py:666`: apply real-db opt-in marker to account-ID migration integration class.
        - `tpot-analyzer/tests/test_shadow_enricher_utils.py:782`: apply real-db opt-in marker to multi-run freshness integration class.
        - `tpot-analyzer/scripts/verify_test_isolation.py:1` (NEW): add human-friendly verifier with ✓/✗ checks for fetcher-handle release, default skip behavior, optional real-db smoke test, and explicit next-step guidance.
        - `tpot-analyzer/docs/ROADMAP.md:18`: add follow-up for a dedicated opt-in shared-db regression lane to keep `TPOT_RUN_REAL_DB_TESTS` coverage visible outside default suites.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_shadow_coverage.py tests/test_shadow_enricher_utils.py -q` → `33 passed, 6 skipped`.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_test_isolation` → all checks passed (`max_handles=0`, expected skip count matched, opt-in smoke test passed).
        - `cd tpot-analyzer && .venv/bin/python -m pytest -q --maxfail=20` → `543 passed, 12 skipped, 3 xfailed`.

- [2026-02-18 09:45 UTC] **Phase 2 remediation: discovery BFS depth progression fix (Codex GPT-5)**
    - **Hypothesis**
        - Discovery depth expansion is capped at one hop because BFS frontier state is computed after mutating the visited-node set, causing `current_layer` to become empty before hop 2.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/src/api/discovery.py:245`: compute `next_frontier` before updating `subgraph_nodes`, break early on empty frontier, and carry frontier forward correctly so `depth>1` traverses as intended.
        - `tpot-analyzer/tests/test_discovery_logic.py:1` (NEW): add unit regressions that verify two-hop inclusion and strict depth boundary behavior on a deterministic in-memory graph.
        - `tpot-analyzer/scripts/verify_discovery_depth.py:1` (NEW): add phase verification script with explicit ✓/✗ checks, metrics, and next-step guidance for discovery traversal.
        - `tpot-analyzer/docs/ROADMAP.md:27`: add follow-up item to harden expansion-test dependency handling for missing `python-louvain` (`community`) in local/CI environments.
    - **Verification**
        - `cd tpot-analyzer && python3 -m pytest tests/test_discovery_logic.py tests/test_discovery_endpoint_matrix.py tests/test_api.py -q` → `20 passed`.
        - `cd tpot-analyzer && python3 -m scripts.verify_discovery_depth` → all checks passed (`checks_passed=3/3`).
        - `cd tpot-analyzer && python3 -m pytest -q --maxfail=20` → discovery tests passed; full run reported unrelated existing failures from missing optional dependency (`ModuleNotFoundError: community`) in expansion modules (`tests/test_expansion_cache.py`, `tests/test_expansion_strategy.py`).

- [2026-02-18 10:42 UTC] **Engineering guardrails doc: empirical bug patterns → enforceable invariants (Codex GPT-5)**
    - **Hypothesis**
        - Capturing recent failures as architecture guardrails (symptom, generator, invariant, guardrail, migration policy) will reduce repeat regressions and make future agent work more consistent under high-velocity iteration.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/docs/reference/ENGINEERING_GUARDRAILS.md:1` (NEW): add canonical guardrails document with traced entries for discovery BFS frontier collapse, fetcher resource lifecycle leak, real-DB test coupling, and optional dependency drift (`community`/python-louvain).
        - `tpot-analyzer/docs/index.md:6`: update doc index review date.
        - `tpot-analyzer/docs/index.md:25`: add `Engineering Guardrails` to canonical operational docs for discoverability.
    - **Verification**
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passed.

- [2026-02-21 09:45 UTC] **Phase 2 remediation follow-up: strict Louvain dependency contract (Codex GPT-5)**
    - **Hypothesis**
        - Expansion strategy failures (`ModuleNotFoundError: community`) are caused by undeclared dependency contract drift; pinning `python-louvain` in canonical requirements and adding an explicit verifier will make environments reproducible.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/requirements.txt:8`: add `python-louvain==0.16` to make the Louvain backend an explicit required dependency for environments created from project requirements.
        - `tpot-analyzer/scripts/verify_louvain_dependency_contract.py:1` (NEW): add human-friendly verifier with ✓/✗ checks for requirements pin presence and import/execute behavior of `community_louvain.best_partition`.
        - `tpot-analyzer/docs/ROADMAP.md:26`: mark Louvain dependency-contract hardening item complete with implementation reference.
        - `tpot-analyzer/docs/reference/ENGINEERING_GUARDRAILS.md:142`: update optional dependency drift guardrail to reference concrete pin + verifier artifacts.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_louvain_dependency_contract` → all checks passed (`checks_passed=2/2`).
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_expansion_strategy.py::TestExecuteLouvainLocal::test_finds_communities -q` → `1 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_expansion_strategy.py tests/test_expansion_cache.py -q` → `45 passed`.
        - `cd tpot-analyzer && .venv/bin/python -m pytest -q --maxfail=20` → `545 passed, 12 skipped, 3 xfailed`.
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passed.

- [2026-02-22 04:28 UTC] **Developer-experience hardening: venv-enforced local test entrypoints + CI contract gate (Codex GPT-5)**
    - **Hypothesis**
        - Preexisting interpreter drift (`python3` vs `.venv/bin/python`) and implicit CI path assumptions make dependency failures hard to diagnose; codifying local and CI execution contracts will keep test signals reliable.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/Makefile:1` (NEW): add canonical local test/verification targets with `.venv/bin/python` default (`verify-louvain-contract`, `test-smoke`, `test`) and explicit missing-venv diagnostics.
        - `tpot-analyzer/.github/workflows/test.yml:15`: add project-directory resolver (`.` vs `tpot-analyzer`) to make workflow commands path-stable across checkout layouts.
        - `tpot-analyzer/.github/workflows/test.yml:29`: add `Verify Louvain dependency contract` step before test execution.
        - `tpot-analyzer/.github/workflows/test.yml:48`: run pytest via `python -m pytest` to enforce interpreter consistency in CI.
        - `tpot-analyzer/scripts/verify_test_runner_contract.py:1` (NEW): add human-friendly ✓/✗ contract verifier for Makefile venv defaults and CI Louvain/pre-pytest guard wiring.
        - `tpot-analyzer/docs/PLAYBOOK.md:66`: document new local contract/entrypoint commands (`make verify-louvain-contract`, `make test-smoke`, `verify_test_runner_contract`).
        - `tpot-analyzer/docs/guides/QUICKSTART.md:177`: update quick command reference to `make test`.
        - `tpot-analyzer/README.md:267`: add canonical `make`-based test entrypoints to Testing section.
        - `tpot-analyzer/docs/ROADMAP.md:100`: mark `make` target standardization item complete.
    - **Verification**
        - `cd tpot-analyzer && python3 -m scripts.verify_test_runner_contract` → all checks passed (`checks_passed=8/8`).
        - `cd tpot-analyzer && make verify-louvain-contract` → all checks passed (`checks_passed=2/2`).
        - `cd tpot-analyzer && make test-smoke` → `7 passed`.
        - `cd tpot-analyzer && make test` → `545 passed, 12 skipped, 3 xfailed`.
        - `cd tpot-analyzer && python3 -m scripts.verify_docs_hygiene` → `9/9` checks passed.

- [2026-02-25 22:28 IST] **Merge-in: test-coverage-hardening branch integration (Codex GPT-5)**
    - **Context**
        - Preserved and integrated work from `test-coverage-hardening` (WIP checkpoint `bbfcae8`) into `main`, then resolved merge conflicts while preserving newer mainline ClusterView architecture.
    - **Imported test-hardening payload**
        - Frontend tests hardened to avoid call-count coupling:
            - `tpot-analyzer/graph-explorer/src/AccountSearch.test.jsx`
            - `tpot-analyzer/graph-explorer/src/AccountTagPanel.test.jsx`
            - `tpot-analyzer/graph-explorer/src/ClusterCanvas.memoryleak.test.jsx`
            - `tpot-analyzer/graph-explorer/src/ClusterCanvas.test.jsx`
            - `tpot-analyzer/graph-explorer/src/ClusterView.integration.test.jsx`
        - Backend test hardening:
            - `tpot-analyzer/tests/test_api.py`
            - `tpot-analyzer/tests/test_hierarchy_builder.py`
            - `tpot-analyzer/tests/test_list_scraping.py`
            - `tpot-analyzer/tests/test_shadow_archive_consistency.py`
            - `tpot-analyzer/tests/test_shadow_coverage.py`
            - `tpot-analyzer/tests/test_shadow_enricher_orchestration.py`
            - `tpot-analyzer/tests/test_shadow_enricher_utils.py`
            - `tpot-analyzer/tests/test_x_api_client.py`
    - **Regression repairs applied during integration**
        - `tpot-analyzer/tests/test_shadow_coverage.py:246`:
            - switched subprocess invocation to explicit script path + project-root `cwd` for deterministic execution.
        - `tpot-analyzer/tests/test_shadow_enricher_utils.py:572` and `tpot-analyzer/tests/test_shadow_enricher_utils.py:636`:
            - added no-op `set_pause_callback`/`set_shutdown_callback` to fake Selenium workers to satisfy `HybridShadowEnricher` constructor contract.
    - **Verification**
        - `cd /Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT-wt-test-coverage && /Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/.venv/bin/pytest -q tpot-analyzer/tests/test_api.py tpot-analyzer/tests/test_hierarchy_builder.py tpot-analyzer/tests/test_list_scraping.py tpot-analyzer/tests/test_shadow_archive_consistency.py tpot-analyzer/tests/test_shadow_coverage.py tpot-analyzer/tests/test_shadow_enricher_orchestration.py tpot-analyzer/tests/test_shadow_enricher_utils.py tpot-analyzer/tests/test_x_api_client.py` → `108 passed, 1 warning`.
        - `cd /Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT-wt-test-coverage && /Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/.venv/bin/python tpot-analyzer/scripts/verify_test_inventory.py` → skip markers/call-count/reimplementation markers resolved; internal-state assertions and >300 LOC debt remain (tracked in ROADMAP).

- [2026-03-05 11:13 IST] **Onboarding docs dry-run remediation: broken links + runnable commands (Codex GPT-5)**
    - **Hypothesis**
        - New contributors are blocked by dead README links and a few stale quickstart commands; updating docs to only existing paths and validated CLI invocations should make first-run onboarding reproducible.
    - **Changes (line numbers + why)**
        - `../README.md:5`: remove missing `grok-probe` project link so root docs no longer point to a non-existent directory.
        - `../README.md:12`: clarify that this checkout currently includes `tpot-analyzer` as the active project entrypoint.
        - `tpot-analyzer/README.md:285`: point coverage baseline reference to existing historical file (`docs/archive/test-coverage-baseline.md`).
        - `tpot-analyzer/README.md:294`: point testing-principles reference to canonical guide (`docs/TESTING_METHODOLOGY.md`).
        - `tpot-analyzer/README.md:382`: update center-user fix link to `docs/archive/CENTER_USER_FIX.md` (live path).
        - `tpot-analyzer/README.md:383`: update bugfix log link to `docs/archive/BUGFIXES.md` (live path).
        - `tpot-analyzer/README.md:384`: update test-mode link to `docs/guides/TEST_MODE.md` (live path).
        - `tpot-analyzer/docs/guides/QUICKSTART.md:27`: replace placeholder clone URL with neutral `<your-repo-url>` template.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:91`: switch cookie setup command to module form (`python -m scripts.setup_cookies`).
        - `tpot-analyzer/docs/guides/QUICKSTART.md:94`: replace invalid `--max-seeds` flag with valid `--max-scrolls`.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:105`: switch spectral build command to module form (`python -m scripts.build_spectral`) to avoid `ModuleNotFoundError: src`.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:178`: switch rebuild command to module form (`python -m scripts.refresh_graph_snapshot`) for consistency with package entrypoints.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:206`: switch troubleshooting spectral command to module form (`python -m scripts.build_spectral`).
        - `tpot-analyzer/graph-explorer/README.md:8`: align Python prerequisite with project docs (`Python 3.9+`) to remove version mismatch.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_docs_hygiene` → `9/9` checks passing.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.build_spectral --help` → CLI usage renders (module entrypoint valid).
        - `cd tpot-analyzer && .venv/bin/python -m scripts.enrich_shadow_graph --help | rg "max-scrolls|--center"` → expected flags present.
        - `cd /Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT && python3 <link-check snippet>` over onboarding docs (`README.md`, `tpot-analyzer/README.md`, `docs/index.md`, `docs/guides/QUICKSTART.md`, `docs/PLAYBOOK.md`, `graph-explorer/README.md`) → `NO_BROKEN_LINKS`.

- [2026-03-05 14:40 IST] **Dev onboarding stabilization: optional NetworKit + baseline snapshot path (Codex GPT-5)**
    - **Hypothesis**
        - First-run onboarding failures are caused by (a) mandatory NetworKit build in base dependencies and (b) quickstart using spectral build as baseline despite missing snapshot preconditions.
        - Moving NetworKit to an explicit optional dependency file and using `refresh_graph_snapshot` as the default quickstart path should make baseline setup reproducible on clean machines.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/requirements.txt:1`: remove `networkit==11.0` from base install contract so `pip install -r requirements.txt` no longer requires native NetworKit build toolchain.
        - `tpot-analyzer/requirements-performance.txt:1` (NEW): add optional performance dependency manifest with `networkit==11.0` and explicit install intent for post-onboarding acceleration.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:38`: add optional performance-install note (`requirements-performance.txt`) after baseline dependency install.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:102`: switch Step 4 baseline from `python -m scripts.build_spectral` to `python -m scripts.refresh_graph_snapshot`.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:120`: mark spectral generation as "Advanced (optional)" instead of baseline onboarding requirement.
        - `tpot-analyzer/docs/guides/QUICKSTART.md:216`: update "No graph data" troubleshooting command to `python -m scripts.refresh_graph_snapshot`.
        - `tpot-analyzer/scripts/verify_dev_onboarding.py:1` (NEW): add phase verifier with explicit ✓/✗ checks for dependency contract and quickstart onboarding command invariants.
        - `tpot-analyzer/docs/PLAYBOOK.md:71`: add `python3 -m scripts.verify_dev_onboarding` to canonical verification command set.
        - `tpot-analyzer/docs/ROADMAP.md:261`: add follow-up item for explicit offline/local-only snapshot mode to prevent unexpected Supabase refresh during onboarding.
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_dev_onboarding` → `6/6` checks passing.
        - `cd tpot-analyzer && .venv/bin/python -m scripts.verify_docs_hygiene` → `9/9` checks passing.
        - `tmpdir=$(mktemp -d /tmp/tpot-req-smoke.XXXXXX) && cd "$tmpdir" && python3 -m venv .venv && .venv/bin/pip install -r /Users/aditya/Documents/Ongoing\ Local/Project\ 2\ -\ Map\ TPOT/tpot-analyzer/requirements.txt` → base requirements install completed successfully (no NetworKit compile failure).
        - `cd tpot-analyzer && .venv/bin/python -m scripts.refresh_graph_snapshot --output-dir /tmp/tpot-onboard-check-data --frontend-output /tmp/tpot-onboard-check-analysis.json` → snapshot refresh completed and emitted expected artifacts.

- [2026-03-26 23:56 PDT] **Archive-only active learning: local tweet content without paid Twitter fetches (Codex GPT-5)**
    - **Hypothesis**
        - Archive-backed accounts should be labelable from local tweet text alone, with the LLM capturing what they talk about while `--archive-only` prevents all twitterapi.io fetch paths.
    - **Investigation loop**
        - Attempt 1/3:
            - hypothesis: the new archive-only path is ready for the full 240-account archive-safe handle set.
            - test: `cd tpot-analyzer && .venv/bin/python3 -m scripts.active_learning --round 1 --archive-only --archive-limit 20 --accounts-file /tmp/tpot_archive_active_learning_handles.txt`
            - result: rejected — every account failed on `sqlite3.OperationalError: no such column: like_count`; real `tweets` schema uses `favorite_count` and lacks `reply_count`.
        - Attempt 2/3:
            - refined_hypothesis: adapting `load_archive_tweets()` to the real archive schema is sufficient.
            - test: smoke run on `0xosprey` + `33asr` with `--archive-only --archive-limit 5`.
            - result: partially confirmed — archive rows loaded and LLM labeling started, but reply tweets still leaked one paid `thread_context` API call before archive-only finished.
        - Attempt 3/3:
            - final_hypothesis: archive-only must gate both tweet fetches and reply/thread enrichment; after that, frontier-ranked archive accounts can be labeled with zero additional twitterapi.io spend.
            - test: probe run on `5matthewdub`, then full active-learning tranche on `uh_cess`, `vyakart`, `vorathep112` via `--archive-only --archive-limit 5`.
            - result: confirmed — no new `enrichment_log` spend, `reply_fetch_rows` stayed `0`, `thread_context_cache` stayed `310`, and the three frontier accounts all completed with LLM-derived content labels.
    - **Changes (line numbers + why)**
        - `tpot-analyzer/scripts/fetch_tweets_for_account.py:274-387`: make `load_archive_tweets()` adapt to real archive schemas (`favorite_count` vs `like_count`, optional `reply_to_username`) and preserve archive-only insertion into `enriched_tweets`.
        - `tpot-analyzer/scripts/active_learning.py:415-559`: gate reply-thread context with `allow_paid_api`; archive-only now uses cached thread context only and skips API fetch on cache miss.
        - `tpot-analyzer/scripts/active_learning.py:563-715`: preserve archive-only contract through `run_round_1()` by skipping budget enforcement and passing `allow_paid_api=False` into tweet labeling.
        - `tpot-analyzer/src/archive/thread_fetcher.py:51-81`: add `allow_api` parameter so cache misses can degrade gracefully instead of silently calling twitterapi.io.
        - `tpot-analyzer/tests/test_fetch_tweets.py:124-217`: add regression coverage for both synthetic and real archive `tweets` schemas and confirm archive-only mode skips paid tweet fetches.
        - `tpot-analyzer/tests/test_active_learning.py:201-314`: add coverage for archive-only budget bypass and archive-only disabling of paid context enrichment during `run_round_1()`.
    - **Runtime outcome**
        - Full active-learning frontier intersected with locally archived accounts yielded only 3 not-yet-enriched accounts (`uh_cess`, `vyakart`, `vorathep112`). The larger 240-handle archive-safe set is a bulk archive sweep, not an uncertainty-ranked tranche.
        - `uh_cess` triaged ambiguous from content (`LLM-Whisperers`, `highbies`, `Collective-Intelligence` split).
        - `vyakart` triaged ambiguous from content (`Tech-Intellectuals`, `Collective-Intelligence`, `Core-TPOT` split).
        - `vorathep112` triaged ambiguous from content (`highbies`, `Quiet-Creatives`, `Relational-Explorers` split).
    - **Verification**
        - `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_fetch_tweets.py tests/test_active_learning.py -q` → `35 passed`.
        - Baseline metrics before fixes: `spent=5.05`, `reply_fetch_rows=0`, `archive_enriched_rows=0`, `thread_cache_rows=310`.
        - Post-fix probe (`5matthewdub`): completed with `triage=high`, no `Fetching thread context` log lines, and no change to `spent` or `thread_cache_rows`.
        - Post-frontier run metrics: `spent=5.05`, `reply_fetch_rows=0`, `thread_cache_rows=310`, `archive_enriched_rows=30`, `archive_enriched_accounts=6`, `label_sets_active_learning=1527`, `tweet_tags_llm_bits=4045`.
        - `cd tpot-analyzer && .venv/bin/python3 -m scripts.verify_active_learning` → enrichment/labeling checks pass; existing verifier still reports budget over prior cap (`$5.05 > $5.00`) and false `0/1527` model coverage because only `llm_ensemble` consensus rows are persisted.

- [2026-04-09 15:13 UTC] **Public-site Blob data delivery + Vercel recovery attempt (Codex GPT-5)**
    - **Assumptions**
        - `find-my-ingroup` remains the canonical Vercel project and should serve `amiingroup.vercel.app`.
        - The frontend should read generated export JSON through stable site-owned routes instead of relying on gitignored static assets being present in every deployment.
        - The least risky implementation is: upload `data.json` and `search.json` to fixed Blob pathnames, then proxy them through lightweight serverless routes.
    - **Predicted outcome**
        - Blob-backed `/api/data` and `/api/search` should let the frontend load current exports even when `public/data.json` and `public/search.json` are gitignored.
        - Local build and tests should pass without touching the large export pipeline logic.
        - Vercel deployment should succeed once the root-directory recursion is neutralized; if not, the blocker is project-level deploy behavior rather than app code.
    - **Confidence**
        - `0.82`
    - **Fallback plan**
        - If Vercel CLI continues to recurse `tpot-analyzer/public-site`, ship the code through the Git integration path and keep Blob upload as a separate post-export step.
        - If the API proxy approach proves fragile, fall back to build-time public blob URLs and resolve them from config instead of proxy routes.
    - **Changes (files + why)**
        - `tpot-analyzer/public-site/src/dataEndpoints.js:1-10`: add a single source of truth for `DATA_JSON_ENDPOINT`, `SEARCH_JSON_ENDPOINT`, and strict JSON fetch error handling.
        - `tpot-analyzer/public-site/src/App.jsx:13,145-159,199-211,281-288`: switch homepage and handle-lookup loading from `/data.json` + `/search.json` to `/api/data` + `/api/search`, and surface a visible data-load failure instead of silent blank loading.
        - `tpot-analyzer/public-site/src/SearchBar.jsx:1-30`: route search-index loading through the new shared endpoint helper so the search box reads Blob-backed data the same way as the main app.
        - `tpot-analyzer/public-site/api/_blobSiteData.js:1-79`: add shared Blob read/proxy logic with descriptive config/not-found/runtime errors for `data` and `search`.
        - `tpot-analyzer/public-site/api/data.js:1-5` and `tpot-analyzer/public-site/api/search.js:1-5`: expose stable site-owned JSON routes that proxy the fixed Blob pathnames.
        - `tpot-analyzer/public-site/scripts/upload-public-site-data.mjs:1-64`: add a repeatable uploader that reads `BLOB_READ_WRITE_TOKEN` from `.env.local` when necessary and overwrites `public-site/data.json` + `public-site/search.json` in Blob.
        - `tpot-analyzer/scripts/verify_public_site_blob.py:1-154`: add the required human-friendly verification script with ✓/✗ output, byte counts, local/remote parity checks, and next-step guidance.
        - `tpot-analyzer/public-site/src/dataEndpoints.test.js:1-35` and `tpot-analyzer/public-site/src/SearchBar.test.jsx:13-21,162-169`: add/repair frontend tests so fetch mocks match real `Response` semantics and cover the new endpoint helper.
    - **Investigation summary**
        - Attempt 1/3:
            - hypothesis: `amiingroup.vercel.app` was still pointed at a stale or missing deployment.
            - test: re-point alias to healthy deployment `dpl_6x1WqhjQCf6Ysx6fHLEvTzrZK8zH` and probe `/api/generate-card`.
            - result: confirmed — alias recovered and backend returned the expected `400 validation_error`.
        - Attempt 2/3:
            - refined_hypothesis: missing runtime data, not missing API credentials, is what still blocks the frontend.
            - test: probe `amiingroup.vercel.app/data.json` and `amiingroup.vercel.app/search.json`; inspect app fetch code.
            - result: confirmed — both endpoints were `404` and the frontend hardcoded those paths.
        - Attempt 3/3:
            - final_hypothesis: Blob upload plus proxy routes will solve data delivery, but Vercel CLI deploy may still be blocked by project root-directory recursion.
            - test: upload both JSON files to Blob, build locally, try direct deploy, root deploy, and prebuilt deploy.
            - result: partially confirmed — Blob uploads succeeded, local build/tests succeeded, but CLI deploy paths still failed on project root-directory recursion.
    - **Verification**
        - `cd tpot-analyzer/public-site && npm test -- --run src/dataEndpoints.test.js src/SearchBar.test.jsx src/App.test.jsx` → `43 passed`.
        - `cd tpot-analyzer/public-site && npm run build` → successful Vite production build.
        - `cd tpot-analyzer && .venv/bin/python -m pytest tests/test_export_public_site.py -q` → `40 passed`.
        - `cd tpot-analyzer/public-site && node scripts/upload-public-site-data.mjs` → uploaded:
          `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/data.json`
          and
          `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/search.json`
        - `curl -sI https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/data.json` and `.../search.json` → both `HTTP/2 200`.
        - `cd /Users/aditya/Documents/Ongoing\ Local/Project\ 2\ -\ Map\ TPOT && tpot-analyzer/.venv/bin/python tpot-analyzer/scripts/verify_public_site_blob.py --base-url https://amiingroup.vercel.app` → local checks pass; remote `/api/data` and `/api/search` still `404`, correctly identifying deploy as the remaining blocker.
    - **Operational outcome**
        - Cleaned stray local Vercel state, restored `amiingroup.vercel.app` to the healthy `find-my-ingroup` deployment, and deleted accidental `dist` / `output` Vercel projects.
        - Blob data is live and current.
        - App code for Blob-backed routes is ready locally, but not yet deployed because Vercel CLI keeps re-applying `tpot-analyzer/public-site` during deploy resolution.

- [2026-04-09 15:44 UTC] **Card-generation timeout/logging hardening (Codex GPT-5)**
    - **Assumptions**
        - The `500 generation_timeout` failure now comes from our own `AbortController` cutoff, not from missing credentials or a missing route.
        - OpenRouter image generation latency is variable enough that the previous fixed `8000ms` limit is too aggressive.
    - **Predicted outcome**
        - Raising the app-level timeout and setting Vercel `maxDuration` for the function should reduce false timeouts.
        - Request-stage logs should make it obvious whether a failing request reached OpenRouter, how long the upstream call took, and whether the failure happened before or after upstream response parsing.
    - **Confidence**
        - `0.94`
    - **Fallback plan**
        - If longer synchronous timeouts still fail in production, move card generation to an async job/poll flow instead of stretching a single request further.
    - **Changes (files + why)**
        - `tpot-analyzer/public-site/api/generate-card.js:73-170,272-304`: replace the hardcoded `8000ms` timeout with configurable `CARD_GENERATION_TIMEOUT_MS` (default `45000ms`) and add structured logs for request receipt, cache hit, prompt assembly, OpenRouter request start/finish, payload parse, Blob upload, success, timeout, and unexpected errors.
        - `tpot-analyzer/public-site/vercel.json:2-6`: set `functions.api/generate-card.js.maxDuration = 60` so Vercel’s function ceiling matches the longer synchronous generation window.
    - **Verification**
        - `cd tpot-analyzer/public-site && node -e "require('./api/generate-card.js'); console.log('generate-card-loaded')"` → module loads successfully.
        - `cd tpot-analyzer/public-site && npm run build` → successful Vite production build after adding `functions.maxDuration`.

- [2026-07-30 14:40 IST] **Raw-first retrieval Slice 0: quarantine legacy membership claims (Codex GPT-5)**
    - **Hypothesis**
        - Adjacent caveats, decimal score formatting, and honest producer names can preserve the legacy map as a baseline without presenting mixed `weight` values as calibrated community-membership probabilities.
        - Predicted outcome: no primary internal, public, download, tweet-share, or OpenGraph surface emits a bare membership-like percentage.
        - Confidence: `0.90`.
        - Fallback: hide legacy numeric values entirely if any context-free probability affordance remains.
    - **RED diagnostic**
        - Focused public contracts produced 11 expected failures among 62 tests before implementation: cards, evidence, community page, tweet share, and OpenGraph metadata all reproduced the old percentage/belonging language.
        - The graph pure-function contract initially had no implementation module. A separate first run exposed worktree dependency-resolution friction; `--configLoader runner` allowed the existing clean-clone dependencies to be reused without writing into their read-only cache.
    - **Changes (files + why)**
        - `graph-explorer/src/legacyCommunitySemantics.js:1-14` and `LegacyMapNotice.jsx:1-25`: centralize decimal formatting, exact source labels, and the adjacent legacy-map caveat; a visual pass increased light-theme contrast.
        - `graph-explorer/src/Communities.jsx:22-23,113-150,374`: rename `Weight` to `Legacy score`, remove rendered percentages, preserve actual producer names, and show the always-visible caveat.
        - `graph-explorer/src/AccountDeepDive.jsx:14-15,22,94,122,262-338`: rename the editor, use the API's native `0..1` scale, preserve source names, and keep the caveat beside editable legacy scores.
        - `public-site/src/legacyCommunitySemantics.js:1-20` and `LegacyMapNotice.jsx:1-25`: define public decimal/caveat semantics and normalize mixed-scale values to bounded, explicitly within-card relative geometry.
        - `public-site/src/CommunityCard.jsx:3-89,127-235`: render decimal legacy scores, use relative bar lengths instead of `weight * 100`, and carry the caveat in fallback, AI-image, and fullscreen branches.
        - `public-site/src/EvidenceSummary.jsx:38-40,123`: label the highest placement as an uncalibrated decimal legacy affinity while retaining the separately named historical heuristic metadata.
        - `public-site/src/CommunityPage.jsx:4-5,59,119-177`: replace “weight” and prototypical-member claims with legacy-score/exploratory-example language and an adjacent caveat.
        - `public-site/src/App.jsx:327-336` and `CardGallery.jsx:103-213`: replace homepage belonging copy and keep the caveat beside cached art in both gallery and fullscreen contexts.
        - `public-site/src/styles.css:566-624`: reserve viewport height for the fullscreen caveat and bound the notice beside short-viewport art.
        - `public-site/src/EvidenceSummary.jsx:31-157`: remove the hidden `weight * 100 >= 5` bridge/community-count inference, report only legacy row count/order, and describe supporting accounts as legacy-labeled rather than members.
        - `public-site/src/shareText.js:1-14` and `public-site/api/og.js:41-53`: share ranked names without numbers, explicitly deny membership-probability meaning, and avoid the contradictory “Find your ingroup” call to action.
        - `public-site/src/CardDownload.jsx:1-228`, `cardDownloadAi.js:1-118`, and `cardCanvas.js:1-58`: cap exports at three ranked scores plus an omission count, reserve a tested caveat/footer area, normalize visible bars within-card, and decompose AI canvas rendering so the React component remains below 300 LOC.
        - `public-site/src/legacyCardPrompt.js:1-72`, `GenerateCard.jsx:14,263`, `public-site/api/_legacyCardPrompt.js:1-108`, and `api/generate-card.js:12,143-149`: replace score percentages, score thresholds, and “community membership” art direction with top-three rank-only exploratory motifs and explicit methodological constraints.
        - Focused semantics tests updated/added across `graph-explorer/src/legacyCommunitySemantics.test.js`, `AccountDeepDive.legacyScores.test.jsx`, `Communities.truthfulness.test.jsx`, and public card, gallery, homepage, prompt, evidence, community-page, share, download-layout, and OpenGraph contracts.
        - `scripts/verify_legacy_community_truthfulness.py:1-299`: add the required human-readable verifier with ✓/✗ checks over 18 production surfaces plus 31 executable adversarial contracts.
    - **Verification**
        - The first focused RED tranche produced 11 expected public failures across 62 tests. Independent review then held the commit after finding unbounded bar geometry, clipped 15-score exports, membership language in both generated-card prompts, and context-free fullscreen art.
        - The second RED tranche reproduced `7333%` geometry from score `73.3335`, 4/4 prompt failures, missing fullscreen notices, and unconstrained export rows.
        - `cd graph-explorer && npx vitest run src --configLoader runner` → `746/746` passed; the suite retains pre-existing verbose canvas logs and React `act(...)` warnings.
        - `cd public-site && npm test` → `211/211` passed.
        - `cd graph-explorer && npm run build -- --configLoader runner` and `cd public-site && npm run build` → both production builds succeeded. The graph build retains its pre-existing large-chunk/dynamic-import warnings.
        - `python3 scripts/verify_legacy_community_truthfulness.py` → 18 production surfaces, 52 required markers, 31 forbidden patterns, and 31 executable contracts checked; all passed.
        - In-app browser visual pass at the isolated worktree dev server → caveat is adjacent to the table, “Legacy score” is visible, and the light-theme warning is readable after the contrast adjustment. The API was deliberately left unconfigured, so the preview showed no real rows and did not open or migrate the production database.
    - **Scope and debt**
        - No Community Gold schema/module was added, no data changed, no paid API was called, and nothing was deployed.
        - The mounted `Communities.jsx` (661 LOC) and `AccountDeepDive.jsx` (540 LOC) remain pre-existing monolith debt already tracked in `docs/ROADMAP.md`; this slice only added imports/labels/notices and did not attempt a mixed refactor.
        - `public-site/src/CommunityCard.test.jsx` remains inherited 325-LOC debt after changing the old percentage assertion; its fixture-preserving split is tracked separately in `docs/ROADMAP.md`.
        - Prompt extraction reduced `GenerateCard.jsx` from 407 to 345 LOC and `api/generate-card.js` from 460 to 353 LOC, but both remain inherited decomposition debt; the client remainder is now explicitly tracked alongside the existing server item.
