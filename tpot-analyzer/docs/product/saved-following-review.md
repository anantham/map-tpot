# Reviewing a saved following list

Status, 21 October 2026: captured-list browsing is reviewed, merged as `21a48b2`
and browser-accepted in private Review. The latest configured capture is the
default for its owner; historical browsing remains explicitly selectable.

Review lets a curator browse the most recent configured following capture or
the historical Archive list and open an account in the existing evidence and
tag editor. This avoids pasting accounts one at a time. A dated capture is not
proof of the live following list.

## Review an account

Set your curator identity, then choose **Browse saved following**. Search the
list by name, handle, account ID or existing tag. Filter accounts with tags,
without tags or with unavailable tag information. IN and NOT IN remain separate
judgments; a missing tag is not a negative judgment.

**Most recent saved list** uses the configured, count-reconciled provider capture
for this exact curator. The capture interval appears above the list. Select
**Historical Archive list** to use the older snapshot instead. The choices are
not unioned: historical-only accounts do not silently enter the captured list.
Protected or otherwise unqualified profiles are not exposed from the raw capture;
their IDs remain in the list, and only already-admitted profile locators can
supply a handle. ID-only rows remain visible with an explicit explanation.

Choose **Review** to open the account by its exact numeric ID and saved handle.
The existing dossier performs its identity check before editing is allowed.
A row without a usable saved handle remains visible but cannot open a dossier.
Only the selected account is added to the browser-local queue. Existing notes,
Takes and tag history are preserved.

## Source boundaries

The historical read-only roster uses `cache.db` tables `archive_following` and `account`.
Handles and display names are historical locators, not fresh profile checks.
Already-consolidated profiles in the relationship sidecar supply additional
locators by exact account ID, with their capture date and snapshot reference
shown in row details. Unchecked published Archive profile observations remain
hidden under the existing source gate. This list performs no network requests.
If the optional sidecar is unavailable, the list reports that coverage gap and
retains the historical account-table locators rather than inventing profiles.
Upload and import dates are preserved as metadata, not follow-start dates.
These rows do not enter graph ranking or bypass its source-admission rules.

Working tags come from the curator's existing `account_tags.db`, joined by exact
account ID. An unavailable tag store stays unknown rather than appearing empty.
Tag owner namespaces are not merged by case; the UI uses its normalized curator
identity and joins only that exact stored owner. After opening an account, live
tag changes update its list row by account ID, never by a historical handle.
If the tag read fails, that row becomes unknown rather than restoring old tags.
Switching curator clears the old view and cancels its request. The endpoint is
curator-authenticated, does not fetch remote data, and never initializes stores.

## Verification

From `tpot-analyzer`, run `python scripts/verify_following_review.py` for synthetic
reader, route and browser-component checks with disposable persistence roots.
Run `scripts/verify_research_notes_inbox.py` for the existing combined acceptance.
Keep live tag and source stores out of synthetic tests.

## Filling profile gaps from a current provider capture

A following endpoint can return both directed relationship observations and
profile objects. Reuse those objects before purchasing separate profile reads.
Request the maximum documented page size, retain every original page, and bind
each observation to its receipt timestamp and original `/followings/N` pointer.
Reconcile exact numeric IDs, not display names or counts alone. A terminal page
and stable before/after profile count support snapshot coverage, not atomic proof
of every relationship. Differences from an old export do not reveal follow or
unfollow dates, reasons, beliefs or membership.

`scripts/verify_current_following_capture.py` consumes this project's saved
`receipt.json`/`roster.json` format. It makes no paid calls and never activates
the result. Supply explicit app, capture, graph, archive, cache, tags and new
output paths through its `--help` interface. It reuses the existing public-profile
qualifier, source writer and copied-graph transaction. Original graph rows and
raw page bytes survive; repeat import and SQLite integrity are checked.

Protected, privacy-unknown, unavailable, identity-conflicting and previously
flagged rows stay excluded from the new profile/follow projection. Their absence
is a policy/coverage gap, not proof of no person or interest. Existing historical
observations are preserved, not relabelled as current. Blank observed bios are
not automatically a reason to buy the same profile again. Profile website fields
are retained links, not verified owned sites or alternative contact routes.

The historical Review roster does not automatically become the new current
list. A copied profile graph can improve its exact-ID locators independently;
current-roster presentation and graph adoption remain explicit delivery steps.
Run `pytest -q tests/test_current_following_capture.py` for invented public,
protected, flagged, large-ID, malformed-capture and source/tag-retention controls.

## Connecting a retained capture to the browser

Set the private API's `MAP_TPOT_FOLLOWING_CAPTURE` to the retained capture directory
containing `receipt.json` and `roster.json`, then reload the owned runtime. No raw
capture is committed, copied into a frontend asset or passed to an external model.
The route reads only captured IDs and observation metadata, checks exact curator
identity, unique IDs, terminal completion, matching before/after counts and a
timezone-aware capture interval, and joins the existing curator-scoped tags.
Raw bios, email fields and billing metadata do not enter the roster response.
These checks validate local schema consistency, not cryptographic provenance or
atomic completeness. Profile/follow admission into graph ranking is unchanged.

Without configuration, or for a different curator, the historical source remains
the default. An invalid configured capture for its owner returns an explicit error;
it does not silently display the old or an empty list. Historical selection still
works. All reads are local and read-only. Run `scripts/verify_following_review.py`
for both sources, authenticated refusal, exact-ID tags and synthetic editor
add/retract checks; `tests/test_following_capture_roster.py` covers the capture
reader and route. Keep real tag stores out of those tests.

Pricing checked 21 October 2026: the provider uses page-size-dependent following
prices, not the old flat per-profile rate. See its [rate card](https://twitterapi.io/pricing)
and [following endpoint contract](https://docs.twitterapi.io/api-reference/endpoint/get_user_followings).
Reserve conservatively before each request. An immediate unchanged account
balance is not proof of zero settled cost; distinguish estimated price, reserved
budget and account-wide balance movement. Never retry an ambiguous paid call
just because billing or result completeness is uncertain.
