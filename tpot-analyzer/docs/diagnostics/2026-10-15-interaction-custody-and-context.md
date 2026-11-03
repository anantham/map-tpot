# Interaction custody and Review context,15 October2026

Purpose: separate available observations from usable identities before extending
discovery. Counts below are historical local custody, not current public consent
or unique people. Existing profiles/work/contact/follow search remains independent.

## What is retained

| Source unit | Records | What can be asserted |
| --- | ---: | --- |
| Archive posts | 5,553,430 across327 source accounts | 4,317,336 parent-post refs;4,085,817 target-handle refs. This local schema has no reply-target account-ID column |
| Likes | 17,501,243 across257 source accounts | 2,291,026 join an exact stored post author;15,210,217 do not. Keep unknown authors unresolved; liked-post text is still usable evidence |
| Retweets | 774,266 across315 source accounts | 373,309 have a stored handle candidate;400,957 do not. Even a match is not verified historical/current identity |
| API typed records | 260 | 13 reply/247 retweet rows. Only2 reply/15 retweet rows have both endpoints profiled in the currently served October sidecar |
| Shadow follows | 319,066 direction-qualified rows | Not319,066 verified social relationships: aliases, duplicate captures and direction need source-aware treatment |
| Shadow profiles | 95,138 | 94,797 use handle-derived shadow IDs;72,873 have bio text. No automatic alias-to-person merge |

Derived account-pair tables also exist:408,446 engagement pairs,549,285 quote
pairs,3,822,341 mention pairs and17,362 heuristic signed-reply rows. These are
not new raw events or independent corroborations. The old engagement builder
inner-joins likes/replies to stored posts and retweets to current profile handles,
silently excluding unknowns. Do not reuse its totals as full raw graph coverage.

The new repeatable offline command is:

```sh
.venv/bin/python scripts/verify_map_interactions.py \
  --archive data/archive_tweets.db --shadow data/cache.db \
  --sidecar data/private/map-relationship-pilot-20261015/saved-follow-candidate.db \
  --output data/private/map-interaction-audit-20261015/new-inventory.json
```

It uses read-only connections, per-store read snapshots and bounded queries;
missing/expired queries are unavailable, never zero. Output is new/private and
will not overwrite an existing receipt. File stats do not prove global quiescence
or detect WAL-only changes. This report does not activate archive evidence.

## Freshness is a separate question

The [publisher's access guide](https://www.community-archive.org/llms.txt) directs
filtered applications to policy-aware REST and bulk work to consent-safe exports.
The public pointer inspected15 October names2026-10-15T07-06-19Z, not the July
package found in the previous audit. Its manifest reports10,812,754 posts across
853 authors and863 profiles,972,287,758B of tweets plus158,496B of profiles.
These are publisher metadata, not locally checksum-verified downloaded rows.
Metadata only was fetched; no Parquet import or active backfill happened here.

The manifest includes reply_to_account_id, quoted/retweeted tweet IDs, conversation
IDs and mentioned-account IDs. REST instead names reply_to_user_id. Those are
different schemas; an adapter must not guess one from the other. Manifest minimum
created_at is1998, so chronology needs validation before recency claims. Old local
custody must not bypass current eligibility/withdrawal rules or replace new data.

## A concrete consumer now

Current REST observations already retain reply/quote/conversation references.
Seventeen inspected saved observations contain324 rows,186 reply-post refs,
99 exact reply-account refs and14 quote refs; these are not unique-post counts.
The Review DTO previously discarded all four fields. It now preserves exact string
IDs/nulls and renders this-post, reply, quote and distinct conversation-root links.
No handle/author inference, new fetch, graph weighting or membership score is added.
A reference is not agreement, friendship or competence; linked context can be gone.
Private browser acceptance14:30 confirms20 this-post/13 reply/4 quote/7 root links
in one current dossier;154 backend tests/13 checks, independent review/closure,
focused lint/build and no browser errors.93/93 judgments and protected data intact.

Next: use the current source eligibility/schema contract to bring real typed post
relationships into explained search; retain unresolved person→post links instead
of dropping them. Keep each edge type separate and connect retrieved passages to
existing tags/contact evidence. This UI repair is not that full graph integration.
