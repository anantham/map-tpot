# Project Conventions

<!--
Last verified: 2026-02-27
Code hash: 7ba43d1
-->

## Naming

| Domain | Convention | Example | Anti-example |
|--------|-----------|---------|-------------|
| Python functions | snake_case | `split_for_tweet` | `splitForTweet` |
| Python classes | PascalCase | `GoldenStore` | `golden_store` |
| API response keys | camelCase | `splitCounts`, `tweetId` | `split_counts`, `tweet_id` |
| Database columns | snake_case | `tweet_id`, `is_active` | `tweetId`, `isActive` |
| React components | PascalCase | `ClusterView`, `Labeling` | `clusterView` |
| CSS classes | kebab-case | `node-label` | `nodeLabel` |
| Constants | UPPER_SNAKE | `AXIS_SIMULACRUM` | `axisSimulacrum` |
| Config env vars | UPPER_SNAKE | `OPENROUTER_API_KEY` | `openrouterApiKey` |

**Known violation:** API response keys are camelCase (frontend convention) while DB columns are snake_case. Conversion happens in `_rows_to_candidates()` and route handlers.

## Error Handling

| Context | Pattern | Example |
|---------|---------|---------|
| API routes | Return JSON `{"error": "<msg>"}` with HTTP status | `return jsonify({"error": str(exc)}), 400` |
| Store methods | Raise `ValueError` for bad input | `raise ValueError("axis required")` |
| Store methods | Raise `RuntimeError` for missing prerequisites | `raise RuntimeError("tweets table not found")` |
| Scripts | `logger.error()` + `sys.exit(1)` | See `scripts/classify_tweets.py` |
| Silent degradation | Log warning, return empty/default | `_load_context()` returns `[]` if table missing |

## Data Formats

| Data | Format | Why |
|------|--------|-----|
| Tweet IDs | String (not int) | Twitter IDs exceed JS `Number.MAX_SAFE_INTEGER` |
| Timestamps | ISO 8601 UTC in DB, display-local in UI | Unambiguous, sortable |
| Probabilities | Dict `{"l1": 0.x, "l2": 0.x, "l3": 0.x, "l4": 0.x}` summing to 1.0 | Validated by `validate_distribution()` with ±0.001 tolerance |
| Splits | String enum: `"train"`, `"dev"`, `"test"` | Deterministic via SHA256 hash bucketing |

## File Organization

| Rule | Threshold | Action |
|------|-----------|--------|
| Max file size | ~300 LOC | Split by domain/concern |
| Test files | Mirror source structure | `tests/test_<module>.py` |
| Scripts | `scripts/` directory | Executable, CLI-driven |
| No orphaned root files | — | Ask user where it belongs |

## Patterns

| Pattern | Where used | Example |
|---------|-----------|---------|
| Blueprint + store | API routes | `golden_bp` + `GoldenStore` |
| Singleton store | DB access | `_golden_store` with lazy `_get_golden_store()` |
| Mixin composition | Store decomposition | `BaseGoldenStore + PredictionMixin + EvaluationMixin → GoldenStore` |
| Deterministic hashing | Split assignment | `SHA256(tweet_id)[:8] % 100` |
| Active-flag versioning | Label history | `is_active=1` with `supersedes_label_set_id` |
| NOT EXISTS over LEFT JOIN | Fast unlabeled queries | `_list_unlabeled_fast()` in `base.py` |
| Loopback-only endpoints | LLM API calls | `/interpret` checks `request.remote_addr` |
