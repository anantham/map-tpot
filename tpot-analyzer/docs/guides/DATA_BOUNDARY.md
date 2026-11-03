# Code to share, data to keep local

Release boundary, 19 October 2026. This is a practical handoff guide, not a
privacy certification or a license to republish another source's data.

## What belongs in Git

Code, synthetic tests, configuration without credentials, methodology and
sanitized aggregate findings can be reviewed for sharing. The private Review
workspace, public legacy map and repository are different deliverables.

Runtime `data/` is ignored by default, regardless of filename or format. Only
three exact paths are allowed in the index. Root-level `Related data/` archives
are also ignored and must have no tracked entries:

- `data/.gitkeep` and `data/fixtures/.gitkeep`: empty directory markers.
- `data/manifests/twitterapiio_price_card_20260730.json`: public, historical price
  configuration used by synthetic acquisition tests. It is not a current quote
  or authority to spend. Paid plans must separately verify current pricing.

Keep new synthetic test fixtures under `tests/fixtures/`, with their invented
origin clear. Do not use real profiles or curator judgments as convenient tests.
An allowlisted filename is not proof that its contents are safe; review changes.

Never stage contact trackers, raw profiles/posts/pages, account mappings,
curator labels, reviewer notes, private event research, browser/session data,
SQLite files, model output or live secrets. A public website does not make a
joined personal dossier appropriate to publish.

## Files already tracked need a separate step

An ignore rule does not untrack existing files. This integration stops tracking
14 legacy account-derived, annotation and evaluation artifacts. All originals
remain in their local locations, with a checked private rollback copy. No raw
database, curator tag store or source capture is deleted or rewritten.

A follow-up index check also stopped tracking one older research ZIP outside
`data/`. Its original local path and a hash-checked private copy are retained.
The same verifier now checks both data directories; ignoring a folder cannot
hide an already-tracked file from this check. Old Git history remains unchanged.

The retained local taxonomy contains real-post examples, not invented public
configuration. The classifier and legacy interpretation surface still use that
local input where present. A fresh clone does not contain it. Prompt-format
tests instead use invented examples; this is not a replacement research taxonomy.

Historical graph lenses and frozen-control evaluation also need a complete
authorized local bundle, including its matching manifest, calibration, holdouts
and graph files. A fresh clone is intentionally not a private-data backup and
cannot reproduce historical measurements without those inputs. Do not fill gaps
with guessed IDs or silently load a different bundle. Restore only your own
authorized source data and preserve its identity and source-use restrictions.

## What this does not erase

Old Git commits can still contain files removed from the current tree. Some
legacy data was already present on `main` before this integration. Neither
`.gitignore` nor an untracking commit purges that history or changes remote
copies, forks and clones. No history rewrite or force push is performed here.

Do not describe this checkout cleanup as historical data removal. Any future
history-removal operation needs an explicit scope, coordinated backup/recovery
plan and separate authority. Treat credentials found in history as an incident,
not merely an ignore-rule problem.

## Checks before a handoff

### Local main is not the same as a public release

The authoritative integration checkout is `Project 2 - Map TPOT - clean-main`.
The original dirty checkout and preservation refs are recovery material, not
competing destinations for new work. Do not merge a preservation snapshot merely
to make every branch appear merged: it can restore superseded code or data.

At the October 19 handoff audit, accepted local `main` was `a91f615`, 100 commits
ahead of independently checked GitHub main `6f03044`. Two additional tested
patches, saved-reference tag discovery (`e49344a`) and unknown-handle support
(`2992f92`), still required independent review and combined integration checks.
These discovery patches are now combined and tested on isolated candidate
`3e0f649`. Its October 19 evening independent code-only review found no blockers,
but the subsequent required combined check timed out twice; integration is held,
not waived. The older source-only security
[PR 11](https://github.com/anantham/map-tpot/pull/11) is also unmerged and needs a
compatibility pass against this newer code, not a blind merge of both security
variants. The prepared Archive dataset remains inactive. See the dated [roadmap](../ROADMAP.md) for
subsequent status; neither these hashes nor a successful merge prove deployment.

Current-data ignore rules do not make the existing history safe to publish.
Retain all source/tag/rollback copies and inspect the exact outgoing history
before any separately authorized push. Private working-log suffixes and scratch
scripts are not automatically part of a documentation handoff.

### Run the existing checks

From `tpot-analyzer/`:

```sh
python3 scripts/verify_shareable_checkout.py
python3 scripts/verify_docs_hygiene.py
git diff --cached --stat
git diff --cached --check
```

The data verifier reads index paths and ignore rules, not private data contents.
It catches accidentally tracked data even when the path matches `.gitignore`.
It is also in CI. Its success is not a secret/content scan, a backup check,
confirmation of remote state or permission to publish.

Inspect the exact commit and documentation before pushing. Old working logs can
contain personal details even when no dataset file is staged. Stage owned paths
or inspected hunks; do not use `git add .` on this research workspace. Keep local,
committed, integrated, pushed and publicly served status separate.

## Reproduce without the owner's personal dataset

The synthetic test suite exercises search, source paths, corrections and
privacy refusals without shipping the real graph. Isolate persistence and lease
roots before importing the app; never run ad-hoc migration or verification
commands against someone else's live tag database. Refer to the existing
[testing methodology](../TESTING_METHODOLOGY.md) and
[test-mode guide](TEST_MODE.md) for the fixture workflows.

To run real discovery, supply your own permitted local evidence and the matching
configuration. Source availability, retention and withdrawal rules still apply.
Keep private sources separate from derived, rebuildable indexes. Back up raw
evidence and curator corrections privately; local rollback copies on the same
disk are not off-device backup. No paid fetch, outreach, deployment or public
snapshot is implied by cloning or merging this repository.

Start with the [methods and lessons](DISCOVERY_METHODS.md), then the
[integration roadmap](../plans/2026-10-14-map-tpot-data-integration-roadmap.md).
