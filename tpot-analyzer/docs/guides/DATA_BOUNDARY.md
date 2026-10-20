# Share methods, keep personal evidence private

Publication boundary, 20 October 2026. This is practical release guidance, not a
privacy certification or permission to republish another source's data.

## Intended public contents

Application code, invented test fixtures, non-secret configuration, generic
architecture contracts and reusable methodology. The private Review workspace,
legacy public map, source dataset and Git branch are different deliverables.

Runtime `data/` is ignored by default. The index allows only these exact paths:

- `data/.gitkeep`
- `data/fixtures/.gitkeep`
- `data/manifests/twitterapiio_price_card_20260730.json`

The price card is public historical configuration used in synthetic tests, not
current pricing or spending authority. New invented fixtures belong under
`tests/fixtures/`. An allowlisted filename is not a content-safety guarantee.
Root-level `Related data/` research archives are also excluded.

Never stage contact trackers, raw profiles/posts/pages, identity mappings,
curator judgments, private research/logs, browser sessions, databases, model
outputs or credentials. Public source material can become sensitive when joined
into a person dossier. Keep collection, retention, access and removal policies.

## Publication branch versus private working history

The publication branch starts at the existing public base and ports reviewed
final source without merging unpublished operational history. Its four public
ledgers are curated summaries, not copies of private research diaries. Original
local history, raw stores, judgments and rollback copies remain private.

Legacy dataset paths are removed from the publication tree; this is not erasure
from existing Git history. `.gitignore` neither untracks files nor removes old
commits. No history rewrite or force push is part of this release. Previously
public commits, forks and clones may still retain legacy material. Any separate
history-removal project needs its own explicit scope and recovery plan.

## Reproduce contracts, not someone else's dataset

A clone intentionally lacks the owner's graph, private taxonomy and research
notes. Synthetic tests exercise source paths, auth/refusal, search, correction
and recovery behavior without those inputs. They do not reproduce historical
community results or validate social categories.

To run real discovery, supply your own permitted source bundle and matching
configuration. Do not fill missing provenance with guessed IDs, replace a missing
taxonomy with real examples copied into tests, or silently use a different
snapshot. Isolate every persistence/lease root before importing application code
for tests. Raw evidence and curator changes need private backups; a rollback
copy on the same disk is not an off-device backup.

From `tpot-analyzer/`, with dependencies installed:

```sh
python3 scripts/verify_shareable_checkout.py
python3 scripts/verify_docs_hygiene.py
git diff --cached --stat
git diff --cached --check
```

The shareable-checkout verifier checks tracked paths and ignore rules, not
content, secrets, history, backup integrity or remote state. Review the exact
outgoing commits too, including earlier versions of docs. Never use `git add .`
on a private research workspace. Stage explicit owned paths or inspected hunks.

Separate edited, tested, committed, merged, pushed and served states. Publishing
this code does not expose the private Review service, deploy a public dataset,
authorize fetching, send invitations or establish consent to contact anyone.
