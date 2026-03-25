# Tech Debt Surface Scan — 2026-03-24

Scan performed after sessions 8-10 (rapid development: active learning pipeline, 5 Chrome audit fixes, independent mode propagation, About page rewrite, 130 frontend tests, public site deploy).

---

## Executive Summary

| Dimension | Issues | Critical | High |
|-----------|--------|----------|------|
| Pattern Conflicts | 5 | 2 | 3 |
| Band-Aid Fixes | 3 systemic | 1 | 2 |
| Test Coverage Gaps | 23 untested scripts | — | 5,600 LOC at risk |
| Security | 4 | 1 | 2 |
| Documentation Gaps | 5 major | 2 | 3 |

---

## Dimension 1: Pattern Conflicts

### 1.1 Community ID Triple-Format

**The single most damaging pattern conflict.** Three identifier systems coexist:

- **UUID strings** (`0a924ce4-...`): `community.id`, `community_account.community_id`, routes, `src/` layer
- **short_name strings** (`LLM-Whisperers`): `account_community_bits.community_id`, labeling pipeline
- **community_name strings** (`LLM Whisperers` with spaces): Legacy, still in `propagate_community_labels.py`

**Damage this session:** `insert_seeds.py` inserted short_names into `community_account` (expects UUIDs). Propagation crashed: `KeyError: 'LLM-Whisperers'`. Fixed with `short_to_uuid` lookup — a band-aid.

**Locations:**
- `scripts/rollup_bits.py:170` — builds `lower_to_id` mapping on every call
- `scripts/insert_seeds.py:37-42` — reads short_name from bits table, resolves to UUID
- `scripts/label_tweets_ensemble.py:46-62` — `VALID_SHORT_NAMES` uses short_names
- `scripts/migrate_community_short_names.py` — migration script confirms known problem
- `src/api/routes/community_gold.py:93` — accepts BOTH `communityId` and `community_id`

**Fix:** Standardize on UUID everywhere. Store UUID in `account_community_bits`. Keep short_name as display only.
**Effort:** Moderate

### 1.2 Naming: get_ vs fetch_ vs load_ vs extract_

~35 `load_`, ~10 `get_`, ~8 `fetch_`, ~3 `extract_` in scripts alone — interchangeable.

**Fix:** Convention: `load_` file/disk, `fetch_` network, `get_` computed, `extract_` parse/transform.
**Effort:** Low

### 1.3 Error Response Helper — Zero Callers

`src/api/responses.py` defines `error_response()` / `ok_response()`. **Zero imports.** 109 hand-rolled `jsonify({"error":...})` across 12 API files with 3 different shapes: `{error}`, `{error, code}`, `{error, detail}` (note: `detail` singular vs helper's `details` plural).

**Fix:** Mechanical migration of 109 call sites.
**Effort:** Trivial

### 1.4 Three DB Connection Patterns

- **Raw** `sqlite3.connect()`: 70+ in scripts. No guaranteed close. `cluster_soft.py:67-75` manual `.close()` unreachable on exception.
- **Context manager** `with sqlite3.connect()`: `feed_signals.py`, `signal_events.py`. Safe.
- **Injected** conn parameter: `communities/store.py`, `assemble_context.py`. Best for tests.

**Fix:** `with` minimum for scripts, injection for `src/`.
**Effort:** Moderate

### 1.5 camelCase vs snake_case in API JSON

`community_gold.py:93` accepts both. `golden.py:728` returns `accountId`. `accounts.py:170` mixes both.

**Fix:** Pick camelCase for JSON, apply consistently.
**Effort:** Moderate

---

## Dimension 2: Test Coverage Gaps

### 2.1 Core Pipeline — 5,600 LOC, Zero Tests

| LOC | Script | What it does |
|-----|--------|-------------|
| 622 | `scripts/enrich_shadow_graph.py` | Graph enrichment — follower/following lists |
| 539 | `scripts/cluster_soft.py` | NMF soft clustering — community assignments |
| 418 | `scripts/build_quote_graph.py` | Quote-tweet graph from Supabase |
| 400 | `scripts/refresh_graph_snapshot.py` | Graph snapshot rebuild |
| 377 | `scripts/build_content_vectors.py` | TF-IDF content vectors (17.5M likes) |
| 368 | `scripts/build_cofollowed_matrix.py` | Co-followed Jaccard similarity |
| 356 | `scripts/resolve_directory_handles.py` | Handle resolution |
| 342 | `scripts/fetch_tweets_for_account.py` | Tweet fetching (used by active_learning) |
| 310 | `scripts/build_mention_graph.py` | Mention graph |
| 297 | `scripts/fetch_recent_activity.py` | Activity fetching |
| 296 | `scripts/refresh_account_data.py` | Account refresh |
| 286 | `scripts/cluster_communities.py` | Community clustering |

### 2.2 Untested src/ Modules

| LOC | Module |
|-----|--------|
| 663 | `src/data/blob_importer.py` — 9GB archive ingest |
| 499 | `src/graph/signal_pipeline.py` — signal computation |
| 403 | `src/api/tweet_enrichment.py` — enrichment API |
| 384 | `src/api/labeling_context.py` — context assembly (has SQL f-strings) |
| 368 | `src/graph/signal_events.py` — event processing |

### 2.3 Independent Mode — No Tests

`--mode independent` just implemented. `tests/test_propagate_community_labels.py` covers classic only. Seed-neighbor counting, modified abstain gate untested.

### 2.4 Mock-Heavy Tests

| Ratio | File | Mocks | Asserts |
|-------|------|-------|---------|
| 3.4:1 | `tests/test_account_status_tracking.py` | 27 | 8 |
| 2.0:1 | `tests/test_relay_firehose_cli.py` | 6 | 3 |
| 1.9:1 | `tests/test_list_scraping.py` | 15 | 8 |

---

## Dimension 3: Band-Aid Fixes

### 3.1 Silent Exception Swallowing — 47 Instances

~25 in `src/`, ~22 in `scripts/`.

**Most dangerous (FIXED 2026-03-24):**

| File | Lines | Fix |
|------|-------|-----|
| `scripts/cluster_soft.py` | 76, 92, 108 | ✅ Narrowed to `sqlite3.OperationalError/DatabaseError/FileNotFoundError` + `logger.warning()` |
| `src/api/snapshot_loader.py` | 323 | ✅ Narrowed to `json.JSONDecodeError/TypeError` + `logger.warning()` |
| `src/api/discovery.py` | 92, 569 | ✅ Narrowed to `json.JSONDecodeError/ValueError/OSError/KeyError` + `logger.warning()` |
| `src/communities/confidence.py` | 72 | ✅ Narrowed to `sqlite3.OperationalError` + `logger.warning()` |
| `src/graph/seeds.py` | 42 | ✅ Narrowed to `json.JSONDecodeError/ValueError/UnicodeDecodeError` + `logger.warning()` |

**Remaining:** ~30 low-risk instances with already-specific exception types (e.g., `sqlite3.IntegrityError: pass` for duplicate inserts). These are acceptable patterns.
**Effort:** Done for critical path; remaining are low-priority.

### 3.2 Scattered str() for community_id

5+ locations wrap `str(community_id)` defensively because it sometimes arrives as non-string:
- `community_gold.py:93`, `reads.py:75`, `evals.py:35`, `export_public_site.py:259`

**Root cause:** Format not enforced at DB layer.
**Fix:** Enforce str at DB boundary, validate once.

### 3.3 Dual CI Computation

| Path | Formula | Accounts |
|------|---------|----------|
| `export_public_site.py:357-374` | 5-factor `compute_confidence()` (0.25+0.30+0.20+0.15+0.10) | Exemplar |
| `export_public_site.py:419-422` | Inline `tw * (1-nw) * (1-ent)` from `account_band` | All others |

Same `confidence` field, two completely different formulas. Consumers cannot distinguish.

**Fix:** Use 5-factor for all, or add `confidence_source` field.

---

## Dimension 4: Security

### CRITICAL

**S1: SQL Injection — `debug_single_account.py:230,242,252,260-265`** ✅ FIXED 2026-03-24

Parameterized all 8 queries with `.bindparams()`.

### HIGH

**S2: `str(exc)` in API Responses** ✅ PARTIALLY FIXED 2026-03-24

Original count: 43. Analysis revealed:
- **9 dangerous** (`RuntimeError`, `FileNotFoundError` leaking internals/paths) → ✅ FIXED: generic messages + server-side logging
- **34 safe** (`ValueError`, `PermissionError` from input validation) → kept as-is: these are controlled, user-friendly validation messages

Fixed files: `community_gold.py` (8 fixes), `extension.py` (1 fix).

**S3: `debug=True` + `host='0.0.0.0'` — `api_server.py:147`** ✅ FIXED 2026-03-24

Gated behind `FLASK_DEBUG` env var, bound to `127.0.0.1`.

### MEDIUM

**S4: Table name f-strings** — 5 locations, all hardcoded values (safe today, fragile pattern).

`refresh_graph_snapshot.py:191`, `snapshot_loader.py:105`, `resolve_directory_handles.py:193`, `blob_importer.py:303`, `verify_backend_intent.py:32`

### Clean
- No `verify=False`, no dangerous code execution, subprocess uses list-form

---

## Dimension 5: Documentation Gaps

### 5.1 archive_tweets.db — Zero Schema Docs

DATABASE_SCHEMA.md (629 lines) covers only `cache.db`. The 9GB primary DB has 20+ undocumented tables:

`enriched_tweets`, `enrichment_log`, `chrome_audit_log`, `chrome_audit_findings`, `account_community_bits`, `tweet_tags`, `tweet_label_set`, `tweet_label_prob`, `account_following`, `account_engagement_agg`, `tpot_directory_holdout`, `frontier_ranking`, `quality_candidates`, `seed_eligibility`, `community`, `community_account`, `community_branch`, `community_snapshot`, `signed_reply`, `account_band`

### 5.2 5-Factor Confidence — Code Only

`src/communities/confidence.py` — weights (0.25/0.30/0.20/0.15/0.10), 20+ sub-thresholds, 5 output levels. No ADR, no TUNING_PARAMETERS.md entry.

### 5.3 Chrome Audit Workflow — Ephemeral Notes

Exists only in session handovers. No runbook for: tweet selection, verdict meanings, finding-to-fix mapping.

### 5.4 Missing from TUNING_PARAMETERS.md

| Parameter | Value | Location |
|-----------|-------|----------|
| SPECIALIST_MIN_WEIGHT | 0.30 | `classify_bands.py:41` |
| SPECIALIST_MAX_ENTROPY | 0.70 | `classify_bands.py:42` |
| BRIDGE_MIN_WEIGHT | 0.15 | `classify_bands.py:43` |
| BRIDGE_MIN_COMMUNITIES | 2 | `classify_bands.py:44` |
| BRIDGE_MAX_NONE | 0.40 | `classify_bands.py:45` |
| FRONTIER_MIN_WEIGHT | 0.08 | `classify_bands.py:46` |
| Engagement RT weight | 0.6 | `propagate_community_labels.py:251` |
| Engagement like weight | 0.4 | `propagate_community_labels.py:252` |
| Engagement reply weight | 0.2 | `propagate_community_labels.py:253` |
| Uncertainty entropy weight | 0.7 | `propagate_community_labels.py:667` |
| Uncertainty degree weight | 0.3 | `propagate_community_labels.py:667` |

### 5.5 ADR Issues

- Duplicate `001-` prefix (two different ADRs)
- ADRs 001-005 not in `docs/index.md`
- No ADRs for: independent propagation, 5-factor confidence, four-band classification, 3-model ensemble, NMF k=16

---

## Size Hotspots (>300 LOC)

| LOC | File | Notes |
|-----|------|-------|
| 2,449 | `src/shadow/enricher.py` | On ROADMAP |
| 1,303 | `src/api/cluster_routes.py` | On ROADMAP |
| 1,068 | `scripts/propagate_community_labels.py` | Loading + propagation + eval + CLI |
| 973 | `scripts/active_learning.py` | Full pipeline |
| 962 | `scripts/export_public_site.py` | 7 extract functions |

## Duplicated Code

- `load_adjacency()` — identical in 3 scripts
- `load_accounts()` + `load_bios()` — near-identical in 2 scripts
- `ARCHIVE_DB` path constant — defined in 15+ scripts

---

## Action Sequence

### This Sprint
1. ~~Fix SQL injection `debug_single_account.py:230-265`~~ ✅ DONE
2. ~~Fix `debug=True` on `0.0.0.0` `api_server.py:147`~~ ✅ DONE
3. Standardize community_id on UUID in `account_community_bits`

### This Month
4. ~~Add `logger.warning()` to critical `except: pass`~~ ✅ DONE (5 critical files fixed; ~30 low-risk with specific types remain)
5. ~~Replace dangerous `str(exc)` in API responses~~ ✅ DONE (9 RuntimeError/FileNotFoundError fixed; 34 safe ValueError kept)
6. ~~Migrate 109 errors to `error_response()` helper~~ ✅ DONE (64 calls migrated across 12 files)
7. Document `archive_tweets.db` schema
8. Add confidence + band thresholds to TUNING_PARAMETERS.md
9. ~~Write independent mode tests~~ ✅ DONE (8 tests in TestIndependentMode)

### Backlog
10. Test top 5 untested pipeline scripts
11. ~~Standardize DB connections~~ PARTIALLY DONE (shared paths extracted, scripts use src.config)
12. ~~Extract duplicated functions + DB paths~~ ✅ DONE (src/config.py + src/data/adjacency.py)
13. Write Chrome audit runbook
14. Fix ADR numbering + index

---

*Scan by Claude Opus 4.6, 2026-03-24. Three parallel agents across 5 dimensions.*
