# ADR 035: Research-cited source links are not verified identities

- Date: 2026-10-18
- Status: Approved local consolidation contract
- Extends: ADR 025

## Decision

Project explicitly supported source URLs from retained work/research records as
an account-to-web-resource citation. Its meaning is only that saved research
cited a page while associating the exact account with work. Company, team and
publication pages are allowed; they are not automatically owned profiles. Do not
create person-equivalence, employment, verified-platform-identity or contact
predicates.

Require an exact same-snapshot/card-pointer work association with matching
numeric account, work title and URL. Preserve source note, evidence pointer,
qualifications and related work pointer. Preparation dates remain literal source
text; unknown observation time stays unknown. Ignore private/unrelated drafts,
fit, outreach, availability and other fields. Never infer URL/domain equivalence
or join by name.

## Supported source shapes and qualifications

Admit only inspected, explicitly supported root scalar/list URL fields and the
specific nested evidence/source/bridge/link-metadata structures defined by the
writer. Preserve each exact scalar or list-element JSON pointer; do not rewrite
one field as another or normalize aliases. A saved source may contain multiple
supported formats; each is handled independently. Do not recursively scan for
URLs, extract prose, resolve saved references, or interpret packet locators or
author metadata as source links.

Allowlisted source qualifications retain their exact literal values and original
field pointers, including false, null and integer status values where the source
contract permits them. Witness roles distinguish citation context; root evidence
lists retain their recorded conclusion, and individual evidence entries retain
their own paraphrase and pointer. These are saved researcher statements and
limits, not verified ownership, employment, residence, current role, identity,
corroboration or confidence.

A malformed present supported field refuses the copied batch, even if another
field is valid. Unsupported sibling formats remain unprojected rather than being
treated as aliases. A source with no admitted citation does not manufacture
readiness. Preserve the source-specific policy and exact account/work anchor.

## Consumer and preservation

Show a bounded, separately labelled disclosure in exact-account Review and include
literal URL matches in the private POST lookup. Group repeated URL/context values
before presentation limits while retaining each cited pointer; repetition is not
corroboration. A shared URL never merges accounts. Citation notes do not enter
interest-search ranking. Preserve older DTO behavior when no citation import is
available.

Apply source policy to the work anchor on every read; a child citation cannot
bypass a hidden anchor. Missing projection is partial, not a complete zero.
Malformed citation evidence must not erase healthy contacts, paths or lookup
families. Use safe links without fetch/send/submit controls. Keep raw sources,
tags, prior graph, package/index and rollback intact. Reuse the existing copied
transaction, source validation and rollback; no new schema, service or
platform-neutral identity architecture is implied.
