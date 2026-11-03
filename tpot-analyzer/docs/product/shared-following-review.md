# Optional shared-following comparison in Review

Prepared 23-24 October 2026. This is an experimental retrieval view, not a
membership model, a new default, an identity merge or a data acquisition.

## User journey

Open an account's working tag, expand graph recovery and explicitly choose
Compare shared following. A separate table compares stable-ID follows,
historical handle targets and both together for the same current tag.
The existing seven-channel method/direction controls retain their defaults.

Hide each IN label in turn, leave its edges available and rank it from the
other IN accounts. All INs remain in denominators; fewer than three means
insufficient examples, not zero recovery. Report outgoing coverage, shared-
target reachability and conservative/possible tied top-25 counts. These ranges
are not confidence intervals. This on-demand view is not a frozen study.

Select one evidence view for the unreviewed queue. This queue uses all current
INs, not held-out folds. Current INs are excluded by the ranker; current OUTs
remain in evaluation/exposure but are hidden from the queue, not penalized.
Other tags and other curators do not supply seeds. Editing a tag refreshes the
view; late responses from prior tags/views are ignored, and cancellation/retry
remain visible without writing a judgment.

## Why a candidate appears

The pattern is seed -> shared follow target <- candidate, not a directed chain
from seed to candidate. Each target contributes
`1 / observed_seed_following / observed_target_followers` to the candidate.
One deterministic target per supporting seed is shown, at most three paths;
these are representative witnesses, not all score contributions.

Each path retains both original arrows, source snapshots/fields and capture
dates. Naive historical times remain timezone-unspecified. Historical targets
say identity unresolved and do not link to an assumed present-day account.
Candidate actions use the independently admitted exact numeric account ID and
existing dossier/tag editor. No handle means the action stays unavailable.

## Sources and implementation boundary

Reuse the fixed scorer and source reader from the offline experiment. Move
their responsibilities into pure graph arithmetic and stdlib-only historical
feature loading so both CLIs and the authenticated reader use one implementation.
The HTTP adapter only composes qualified sources, target-scoped tags and DTOs.
No new persistence, schema, inference service or provider is introduced.

Historical sources must have independent numeric profiles and pass the existing
saved metadata's severe flagged/protected/unavailable exclusions. Original
shadow row hashes, pointers, arrows, channels and time bases must reconcile.
Missing metadata is distinct from an excluded source. Alias-source edges cannot
become candidates, and numeric/handle target namespaces remain separate even
when they could describe one person. Malformed sources refuse; absent/unqualified
features are unknown coverage, not proof of no relationships. No network fallback.

Partial captures, handle reuse, duplicate stable/alias representations and
non-simultaneous observations limit interpretation. No competence, affiliation,
membership probability, independence or prospective usefulness claim follows.

## Acceptance and preservation

Source-shaped synthetic HTTP tests cover exact IDs, all denominators, source
witnesses, auth, invalid filters, missing/corrupt sources, protection, OUT queue
behavior and fresh tags. UI tests cover explanations, candidate actions,
cancellation/retry and stale requests. Existing research CLI tests, focused
channel verifier and combined Research Notes acceptance remain required.

Independent code/synthetic-only review and a disposable real UI/API browser
journey precede private serving. Preserve source stores, tag events, contact
decisions, active data binding and rollback. Real-data acceptance must not invent
a human tag or confirmation. No paid fetching, outreach or push is authorized.
