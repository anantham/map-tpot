# Historical search: visible word-match tiers

Intent recorded18 October2026;implementation of the approved retrieval/ranking
direction. Owner:Codex,canonical clean-main,codex/curator-review-shell.

## User journey

Search a topic,optionally within1–2 captured outgoing hops. Whole-word support
should appear before matches found only inside longer text. Keep partial-name
lookup and show exactly why a partial candidate was retained. Source dates,
historical identity limits and graph arrows remain inspectable.

## Decision and tradeoffs

Reuse the existing evidence_text boundary definition:Unicode alphanumeric
characters bound words;underscores,hyphens and punctuation separate them. Simple
ASCII letter plurals are accepted. This is a lexical convention,not multilingual
word segmentation,semantic relevance,competence or membership confidence.

Do not filter partial matches out of the corpus. That would break useful prefix
and partial-name discovery. Do not invent a continuous confidence score either.
Instead,order all-word hits first,then captured shortest-hop distance,then handle.
Within the returned window,put partial-only hits in a named disclosure;open it by
default when no whole-word hits are shown. Truncation/counts stay explicit.

Each historical row reports ranking.matchKind,ranking.wholeWordFields and
ranking.partialTerms. Existing matchedFields,bio/source metadata and networkPath
are unchanged. Summary matchCounts covers the complete qualifying set,not just
the returned window. An older response without these fields remains neutral;
never label it as newly validated word support.

## Bounds and verification

The historical candidate set remains the literal all-fragments intersection.
No source,tag,ontology,identity,graph schema or other search-mode policy changes.
No fetching or outreach. Native details controls preserve keyboard access.

Public behavior tests first reproduce a partial text hit crowding out a whole
word hit at limit1,including a closer partial vs farther whole scoped case.
Verify punctuation/Unicode/short terms/underscores/plurals,partial-only lookup,
summary/window counts and source/auth/cancellation boundaries. Independent
code/synthetic review,combined acceptance and actual private Review inspection
precede serving. Preserve private data and the prior graph for rollback.

## Verification checkpoint

Privately served18 October2026,18:09 IST after independent code/synthetic review
and combined acceptance. The source-scoped control retains all21 candidates and
their source/path evidence,now17 whole-word and4 partial. Prefix-only lookup and
out-of-window reporting were inspected in Review. No human relevance acceptance
or calibrated fit improvement is claimed.

Known lexical limitation:opensource is a compound token and therefore partial
for the query open source,even where it is semantically relevant. Keep it available;
do not interpret the grouping as good/bad leads. Compound/synonym handling and
navigation beyond the returned window remain separate product decisions.
