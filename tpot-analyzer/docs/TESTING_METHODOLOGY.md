# Testing Methodology

Living document capturing how we test, why, and lessons learned from human feedback.

## Philosophy

1. **Tests are signal, not checkbox** - A passing test suite means nothing if it doesn't catch real bugs
2. **Human taste is irreplaceable** - Automated tests verify correctness; humans verify "feels right"
3. **Every manual bug finding becomes automated** - Reproducible bugs graduate to E2E tests
4. **Document the "why"** - Future AI/devs should understand test structure rationale

## Test Pyramid

| Layer | Framework | What It Catches | What It Misses |
|-------|-----------|-----------------|----------------|
| **Unit** (pytest/vitest) | Fast, isolated | Logic errors, API contracts, edge cases | Integration, timing, UX |
| **E2E** (Playwright) | User flows | Regressions, integration bugs | Subjective feel, visual polish |
| **Manual** (Human) | Exploration | UX jank, math incorrectness, edge cases, taste | - |

### Current Coverage

**Backend (pytest):** 321 tests collected
- Account status tracking, tags, search, teleport
- Cluster hierarchy, layout, members
- Shadow store, enrichment, seeds
- API endpoints, serialization

**Frontend (vitest):** 8 tests
- ClusterCanvas hit detection, zoom, selection modes
- AccountSearch debounce
- AccountTagPanel CRUD
- GraphExplorer rendering

**E2E (Playwright):** 4 spec files
- `cluster_mock.spec.ts` - Cluster expand/collapse with mocked backend
- `cluster_real.spec.ts` - Full integration with real backend
- `teleport_tagging_mock.spec.ts` - Search → teleport → tag flow
- `hybrid-zoom.spec.ts` - Semantic zoom (NEW, untracked)

## Manual Testing Gaps → Automated Coverage Mapping

When human finds issue X, we add test Y.

| Date | Human Finding | Root Cause | Test Added | Category |
|------|---------------|------------|------------|----------|
| - | - | - | - | - |

## Lessons Learned

Hard-won knowledge from bugs that slipped through.

### Lesson: Mock truthiness can hide bugs
- **Discovered:** 2025-12-16
- **Symptom:** Tests passed but `if policy:` was always True because Mock() is truthy
- **Fix:** Use real `EnrichmentPolicy` objects in fixtures, not `Mock()`
- **Test:** `conftest.py` now returns real policy; `test_account_status_tracking.py` updated

### Lesson: URL state can race with React StrictMode
- **Discovered:** 2025-12-16
- **Symptom:** Deep links lost parameters on page load
- **Fix:** Gate URL-sync effect on `urlParsed` flag
- **Test:** E2E deep-link tests in `cluster_mock.spec.ts`

### Lesson: JSON serialization of Python sets fails silently in dev
- **Discovered:** 2025-12-17
- **Symptom:** `/api/seeds` returned 500, frontend crashed
- **Fix:** Return list instead of set; added `test_api_seeds_endpoint.py`
- **Test:** Unit test verifies JSON serializable response

## Current Gaps (What Human Testing Catches)

Things automated tests cannot reliably verify:

1. **Animation smoothness** - Force-morph transitions, staggered entry timing
2. **Visual layout** - Node overlap, label readability, color contrast
3. **Interaction feel** - Drag responsiveness, zoom inertia, click precision
4. **Math correctness** - Are cluster positions sensible? Do sizes reflect reality?
5. **Edge cases** - Unusual data shapes, empty states, boundary conditions
6. **Cross-browser** - Safari quirks, mobile touch events

## Manual Testing Protocol

After each feature, AI provides:
1. **What's new** - Features to exercise
2. **What to look for** - Specific behaviors, potential issues
3. **Known limitations** - What automated tests don't cover

Human reports issues conversationally. AI:
1. Extracts root cause
2. Adds to "Lessons Learned" if novel
3. Creates E2E test for reproducible bugs
4. Updates this doc

---

## Appendix: Running Tests

```bash
# Backend
cd tpot-analyzer
.venv/bin/python3 -m pytest tests/ -q

# Frontend unit
cd tpot-analyzer/graph-explorer
npx vitest run

# E2E (mock backend)
cd tpot-analyzer/graph-explorer
npm run test:e2e:mock

# E2E (real backend - start backend first)
cd tpot-analyzer
python -m scripts.start_api_server  # terminal 1
cd graph-explorer && npm run test:e2e:real  # terminal 2
```
