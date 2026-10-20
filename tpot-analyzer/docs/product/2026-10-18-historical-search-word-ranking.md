# Historical search: visible word-match tiers

## User journey

Search a topic, optionally within one or two captured outgoing hops. Whole-word
support appears before matches found only inside longer text. Keep partial-name
lookup and show why a partial candidate was retained. Source dates, historical
identity limits and graph arrows remain inspectable.

## Decision and tradeoffs

Reuse the existing `evidence_text` boundary: Unicode alphanumeric characters
bound words; underscores, hyphens and punctuation separate them. Simple ASCII
letter plurals are accepted. This is a lexical convention, not multilingual word
segmentation, semantic relevance, competence or membership confidence.

Do not filter partial matches from the corpus or invent a continuous confidence
score. Order all-word hits first, then captured shortest-hop distance, then
handle. Within the returned window, put partial-only hits in a named disclosure;
open it by default when no whole-word hits are shown. Truncation and counts stay
explicit.

Each historical row may report `ranking.matchKind`,
`ranking.wholeWordFields` and `ranking.partialTerms`. Existing matched fields,
bio/source metadata and network path remain unchanged. Summary match counts cover
the complete qualifying set, not just the returned window. Older responses
without these fields remain neutral; never label them newly validated word
support.

## Bounds and known limitations

The historical candidate set remains the literal all-fragments intersection. No
source, tag, ontology, identity, graph schema or other search-mode policy changes.
No fetching or outreach. Native details controls preserve keyboard access.

Compounds such as `opensource` may remain partial for a multiword query such as
`open source`, even when semantically relevant. Keep such results available;
the grouping is not a good/bad lead judgment. Compound/synonym handling and
navigation beyond the returned window are separate product decisions.
