# Phase 1 Community Correctness

Last reviewed: 2026-03-26

## Goal

Bootstrap a trustworthy `community correctness` benchmark before changing the
ontology, running multiscale sweeps, or introducing typed-graph structure.

Phase 1 does four things:

1. Curates a small, reviewable pilot slate.
2. Uses `x-ai/grok-4.20-multi-agent-beta` as an external X-native auditor.
3. Records human judgments in the existing `account_community_gold_*` tables.
4. Reuses the current evaluator instead of inventing a parallel benchmark path.

## Scope

- `36` review items total.
- `12` `core` items: high-confidence current-map members.
- `12` `boundary` items: likely split / merge pressure cases.
- `12` `hard_negative` items: plausible confounders that should likely be `out`.

This is intentionally a pilot, not a full ontology-wide adjudication pass.

## Output Artifacts

- `data/evals/phase1_membership_audit_accounts.json`
- `data/evals/phase1_membership_audit_review_sheet.csv`
- `data/outputs/phase1_membership_audit/membership_audit_results.jsonl`
- `data/outputs/phase1_membership_audit/hard_negative_suggestions.json`

## Review Contract

The human review sheet is community-specific, not ontology-global.

Each row asks:

- For `@account`, relative to `target_community_short_name`, is the judgment:
  - `in`
  - `out`
  - `abstain`

Interpretation:

- `in`: strong enough that this row can count as a positive for the target community.
- `out`: strong enough that this row can count as a negative for the target community.
- `abstain`: too ambiguous, bridge-like, or underdetermined to score.

The Phase 1 importer writes only the target-community judgment for each row.
It does not expand one review into ontology-wide `out` labels.

## Grok Usage

Grok is an external auditor, not ground truth.

Use it for:

- public-legibility checks
- broad-scene mapping into the ontology
- surfacing disagreements that deserve human review

Do not treat Grok agreement as equivalent to truth.

## Local Context Rules

The runner packages:

- account handle
- bio
- up to `N` local sample posts from `tweets`
- fallback posts from `enriched_tweets`

If neither source exists, the manifest marks `missing_local_posts=true`. This is
expected for many famous-adjacent hard negatives.

## Workflow

1. Prepare or refresh the pilot slate:

```bash
cd tpot-analyzer
.venv/bin/python scripts/run_phase1_membership_audit.py --prepare-only
```

2. Preview prompts without spending:

```bash
cd tpot-analyzer
.venv/bin/python scripts/run_phase1_membership_audit.py --dry-run --limit 2
```

3. Run the Grok membership audit:

```bash
cd tpot-analyzer
.venv/bin/python scripts/run_phase1_membership_audit.py --mode membership
```

4. Optionally ask Grok for more hard-negative suggestions:

```bash
cd tpot-analyzer
.venv/bin/python scripts/run_phase1_membership_audit.py --mode hard-negatives
```

5. Fill `human_judgment`, `human_confidence`, and `human_note` in the CSV.

6. Import the reviewed labels:

```bash
cd tpot-analyzer
.venv/bin/python scripts/import_phase1_gold_labels.py --reviewer human_phase1
```

7. Verify readiness or post-import status:

```bash
cd tpot-analyzer
.venv/bin/python scripts/verify_phase1_community_audit.py
```

## Verification Semantics

Before human review is imported, the verifier should still pass the substrate
checks:

- docs exist
- prompt templates exist
- manifest exists
- review sheet exists
- bucket counts are correct

After labels are imported, it should additionally surface:

- active label counts
- per-community judgment breakdown
- whether the evaluator can score any communities yet

## Known Limitations

- Many hard negatives only have local bios, not local tweets.
- The pilot does not cover every community equally.
- Imported labels are target-community judgments, not full ontology-wide gold.
- Grok is not an independent oracle; it is a useful external memory / scene model.

