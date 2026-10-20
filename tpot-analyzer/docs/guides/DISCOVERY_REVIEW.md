# Private Review workflow

Review is the source-inspection and reversible-tagging workspace. It is separate
from the legacy Communities map: old cluster percentages are not per-tag model
probabilities or a source of new human judgments.

## Try it with permitted local inputs

Follow the [Quickstart](QUICKSTART.md) and [Playbook](../PLAYBOOK.md) to install
dependencies and configure the API/explorer. The explorer's Research Notes view
is selected with `?view=research-notes`. Review endpoints require curator auth;
match browser and server token configuration without committing credentials.
Keep the service private. This branch does not configure a public deployment.

No real dataset is bundled. An empty or unconfigured source should be reported
as unavailable, not padded with sample people or silently replaced by a different
snapshot. Synthetic behavior can be checked without private inputs; see
[test mode](TEST_MODE.md) and [data boundary](DATA_BOUNDARY.md).

## The useful loop

1. Search saved profile, post, website and work evidence, or paste an account.
2. Open the exact account's dossier. Inspect the matched passage and source date;
   follow the original page/post pointer rather than trusting a generated summary.
3. Apply independent IN/NOT IN tags, add an optional tag note, or retract a choice.
   Suggestions remain proposals until confirmed. Unknown does not mean NOT IN.
4. Inspect candidates supported by the chosen tag's examples. Choose source,
   direction and ranking scope; open a witness path to see why an account appears.
5. Use graph hide-and-recover to compare fixed methods, not to invent a confidence
   percentage. Review new candidates separately from retrospective test results.

The joined contact card retains account links, cached-page clues and saved route
observations without claiming they identify one verified person or grant consent.
Private research notes and contact history should never enter a public export.

## Limits

The current search is evidence retrieval, not universal semantic understanding.
Source availability and time windows vary. A few displayed witness paths are
not an exhaustive score decomposition. Cross-platform links, work associations
and possible inboxes remain claims to investigate. See the
[method guide](DISCOVERY_METHODS.md) for evaluation and contact safeguards.
