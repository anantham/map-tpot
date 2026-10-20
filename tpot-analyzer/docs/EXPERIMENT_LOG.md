# Experiments and reusable lessons

Public summary, 20 October 2026. All account examples in published guides are
invented. Historical inputs and account-level results stay private; synthetic
tests do not reproduce or validate these social findings. Different historical
panels used different source pools and cannot be combined into one benchmark.

## Seed weighting

- Question: do selective sources recover a niche better than raw shared support?
- Hypothesis: reciprocal-degree source votes reduce broad-source noise.
- Method: hide one known positive label, retain graph edges, compare fixed top-K
  recovery with raw support on the declared pool.
- Result: this weighting did not reliably beat raw support in the bounded panels.
- Lesson: a plausible information-theoretic intuition is not an empirical win;
  partial capture can also distort degree estimates.
- Next: separate coverage, popularity and prospective usefulness before tuning.

## Text and fixed fusion

- Question: does cheap authored-post TF-IDF improve known-example recovery?
- Hypothesis: content supplies the missing boundary signal.
- Method: compare text, raw graph support and a fixed fusion on the same covered
  candidates; the text recipe excludes repost-prefixed posts.
- Result: this particular text/fusion recipe did not reliably improve top-K recovery.
- Lesson: do not generalize that failure to semantic models or retweet taste.
- Next: test a new representation only with a declared target and held-out comparison.

## Typed graph hide-and-recover

- Question: can graph connections recover examples without tag-name keywords?
- Hypothesis: directed interactions can complement follows.
- Method: separate source/layer/direction; compare popularity, direct support,
  observed-degree support and a fixed bounded two-step walk.
- Result: relative performance differed across layers; there is no universal winner.
- Lesson: two-hop reach can saturate a captured cohort without sharpening a boundary.
- Next: classify misses as missing data, unreachable or low ranked; prospectively
  review new candidates before claiming discovery precision.

## Reusing saved evidence

- Question: must an absent search result trigger another fetch?
- Hypothesis: qualified existing captures can restore missing associations.
- Method: rebuild a derived view from retained source pointers, compare the fixed
  query before/after and inspect the source on the joined card.
- Result: some evidence gaps were join/import problems, not missing web content.
- Lesson: source qualification still matters; rows without admissible provenance
  cannot be promoted merely because a database contains endpoints.
- Next: inventory local coverage, stage a small batch and retain rollback identity.

## Contact classification/export

- Question: does an empty personal-email field imply no alternative route?
- Hypothesis: narrowly classified exports drop relevant organisation routes.
- Method: trace a saved clue through classification, export and final status;
  inspect the public page's intended use.
- Result: the pipeline could find an organisation inbox and still export an
  incorrect “no route” status.
- Lesson: discovery, classification, completion and delivery are separate states.
- Next: preserve contextual inboxes/forms and incomplete checks, not just name-matching emails.

## Outreach outcome denominators

- Question: can an outreach snapshot tell us which channel or wording works?
- Hypothesis: mixed cohorts and insufficient elapsed time can distort the conclusion.
- Method: distinguish drafts, history-cleared recipients, actual sends, replies,
  interest, applications and attendance by dated cohort.
- Result: operational backlog could not establish a causal winning channel/style.
- Lesson: a better-looking funnel is not evidence of causality.
- Next: prospective comparisons with fixed eligibility, elapsed time and denominators.

## Clean-publication acceptance

- Question: can methods and tested behavior be shared without unpublished research?
- Hypothesis: a final-tree port from a public base avoids private local commit ancestry.
- Method: inspect outgoing paths/content/history, test with disposable synthetic
  stores, independently review the sanitized slice and compare protected private state.
- Result: local synthetic combined acceptance, full portable test selection,
  explorer unit suite/build, changed-source lint and independent review passed.
  Whole-app legacy lint debt remains recorded; see [roadmap](ROADMAP.md).
- Lesson: ignore rules and tip redactions alone do not sanitize earlier Git commits.
- Next: publish only the exact accepted branch; keep merge/deployment separate.

## Portable test selection

- Question: can a clone run the declared credential-free Python selection?
- Hypothesis: a live-network module lacks the marker used by that selection.
- Method: run the unmodified CI selection with disposable state, inspect all
  failures and compare the failing module with the public base.
- Result: 2,469 tests passed, two skipped and three live Supabase checks failed
  at DNS/connectivity. The unchanged module had a key-dependent skip but no
  `requires_supabase` marker, so the declared exclusion did not select it out.
- Lesson: environment-based skips are not a substitute for explicit test type;
  collection-time synthetic configuration can make a network check look ready.
- Follow-up result: adding the registered marker, without changing assertions,
  produced 2,469 passed, two skipped and three deselected under the same CI
  selection. Independent source-only review found no blockers. This does not
  claim the live Supabase service was tested.
- Next: retain explicit integration selection and proper configuration for live
  connectivity checks; do not supply a live dataset to credential-free CI.

## Documentation discovery

- Question: can a new reader find current methods and setup from the root README?
- Hypothesis: the default branch still shows old docs, while publication navigation
  buries the hub and mixes current Review with the legacy map.
- Method: compare the default/publication READMEs, inspect the hub's local targets,
  and add isolated missing-route/broken-link regressions before changing navigation.
- Result: default main lacked the new links; publication's hub linked a nonexistent
  structure file, while the previous nine docs checks still passed. New navigation
  tests initially failed. After reorganization, three tests and 11 docs checks pass,
  including 74 local links across five entrypoints. A fixture using an existing
  `./docs/index.md` form also prevented an overly literal route check.
- Lesson: file existence and historical-hygiene checks do not establish a usable
  documentation entrypoint. Current guidance and archived explanations need distinct homes.
- Review: independent Gemini review found no blockers; its optional `./`
  normalization concern was falsified by the runtime and existing fixture.
- Next: verify the published follow-up; merging it to default main is a separate action.
