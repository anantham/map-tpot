# ADR030: Deterministic historical source-row consolidation

Date:18 October2026. Status: approved local-consolidation contract.
Related:ADR025,ADR028. No new schema,service or identity semantics.

## Issue and decision

Root-neighborhood batches are useful for exploration but are not a systematic
way to consolidate all saved historical follows. Add an explicit alias-row mode
to the existing copied importer/CLI, ordered by the source table's composite key
(source_id,target_id,direction), bounded to10000 rows with an explicit offset.

The row domain contains rows with at least one shadow: endpoint, excluding
self-loops. Report excluded self-loop count and total domain separately from
the selected window. Unknown/malformed selected directions,identities,times or
metadata refuse the copied transaction. Existing source-channel exclusions remain.
Only literal captured independent profile fields are projected; no numeric
identity is inferred from a matching handle. Preserve arrow orientation for
inbound and outbound rows. No source fetching or current-follow claim.

Report selected/qualified rows and net new observations separately. Repeated
projection is idempotent; a no-new-observation batch must not be adopted as a new
graph. Existing raw stores,tags,all prior graph rows and rollback remain intact.
An offset describes this exact saved-source state, not an external crawl cursor;
the existing copied-batch source-identity guards bind the operation to that state.

## Consumer and limits

Historical search already reads imported bios and outgoing1–2-hop paths. Accounts
with imported incident edges but no selected-root scope may open a partial
neighborhood: explicitly unknown total saved neighborhood coverage, never an
invented complete list or an empty not_imported result. Old selected-root scopes
retain their original source snapshots and counts. Numeric-only discovery and
current account evidence remain separate. No membership/competence inference.

Independent source/synthetic review,source-row comparisons,repeat/FK/retention
checks and actual Review evidence opening precede private adoption. First window
is offset0/limit10000, then continue at the reported nextOffset. Subsequent windows
reuse reviewed code and source contracts rather than adding another substrate.
