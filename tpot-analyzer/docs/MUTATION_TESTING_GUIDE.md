# Mutation Testing Guide

**What is Mutation Testing?**

Mutation testing evaluates test quality by introducing bugs (mutations) into your code and checking if tests catch them. If a test suite passes despite broken code, those tests provide false security.

**Key Metrics:**
- **Line Coverage:** What code was executed (current: 92%)
- **Mutation Score:** What code was verified (target: 85%+)

---

## Quick Start

### 1. Install Dependencies

```bash
cd tpot-analyzer
pip install -r requirements.txt
```

This installs:
- `mutmut==2.4.4` - Mutation testing framework
- `hypothesis==6.92.1` - Property-based testing (Phase 2)

### 2. Run Mutation Testing on a Module

```bash
# Test a single module
mutmut run --paths-to-mutate=src/config.py

# Test multiple modules
mutmut run --paths-to-mutate=src/api/cache.py,src/graph/metrics.py

# Test entire src/ directory (WARNING: slow, 1-2 hours)
mutmut run
```

### 3. View Results

```bash
# Show summary
mutmut results

# Show detailed results
mutmut show

# Generate HTML report
mutmut html
open mutmut-results.html
```

---

## Understanding Results

### Output Example:

```
Mutations: 47
Killed: 38 (80.9%)      ← Tests caught the bug ✅
Survived: 7 (14.9%)     ← Tests didn't catch the bug ❌
Timeout: 2 (4.3%)       ← Mutation caused infinite loop ⚠️

Mutation Score: 80.9%
```

### What Each Status Means:

| Status | Meaning | Test Quality |
|--------|---------|--------------|
| **Killed** | Test failed when code was broken | ✅ Good - test is effective |
| **Survived** | Test passed despite broken code | ❌ Bad - test has gaps |
| **Timeout** | Mutation caused infinite loop | ⚠️ Acceptable - detected abnormal behavior |
| **Suspicious** | Test behaved unexpectedly | 🔍 Investigate |

### Mutation Score Formula:

```
Mutation Score = (Killed + Timeout) / Total Mutations
```

**Target:** 85%+ mutation score

---

## Analyzing Survived Mutations

Survived mutations indicate test gaps. Example:

```bash
# Show survived mutation #5
mutmut show 5
```

**Output:**
```python
# Original code (src/graph/metrics.py:23)
if alpha < 0 or alpha > 1:
    raise ValueError("Alpha must be in [0, 1]")

# Mutated code
if alpha < 0 or alpha >= 1:  # Changed > to >=
    raise ValueError("Alpha must be in [0, 1]")

# Status: SURVIVED
# Tests still passed!
```

**Fix:** Add test for boundary value:
```python
def test_pagerank_alpha_boundary():
    """Alpha=1.0 should be valid (boundary test)."""
    graph = nx.DiGraph([("a", "b")])
    pr = compute_personalized_pagerank(graph, ["a"], alpha=1.0)
    assert sum(pr.values()) == pytest.approx(1.0)
```

---

## Common Mutation Types

Mutmut applies these mutations:

| Type | Example | Catches |
|------|---------|---------|
| **Number** | `0` → `1` | Magic numbers, off-by-one |
| **Comparison** | `>` → `>=` | Boundary conditions |
| **Boolean** | `True` → `False` | Logic errors |
| **String** | `"x"` → `"XX"` | String handling |
| **Arithmetic** | `+` → `-` | Calculation errors |
| **Assignment** | `x = 5` → `x = 6` | Value errors |

---

## Running Mutation Tests Efficiently

### Strategy 1: Test Changed Files Only

```bash
# Get changed files in current branch
CHANGED=$(git diff --name-only origin/main...HEAD | grep "^src/" | tr '\n' ',')

# Run mutation testing on changed files only
mutmut run --paths-to-mutate="$CHANGED"
```

### Strategy 2: Use Coverage Data

```bash
# First, generate coverage data
pytest tests/ --cov=src --cov-report=

# Then run mutation testing (only mutates covered lines)
mutmut run --use-coverage
```

This skips mutations on uncovered code (speeds up 2-3x).

### Strategy 3: Parallel Execution

```bash
# Run on 4 CPU cores
mutmut run --paths-to-mutate=src/ --runner="pytest -x -q" --processes=4
```

**Time Estimates:**
- Single module (100 lines): ~5-10 minutes
- Core modules (500 lines): ~30-60 minutes
- Full codebase: ~2-4 hours (without coverage filter)

---

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/mutation-testing.yml
name: Mutation Testing

on:
  pull_request:
    paths:
      - 'src/**'
      - 'tests/**'

jobs:
  mutation-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Need full history for diff

      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd tpot-analyzer
          pip install -r requirements.txt

      - name: Run mutation tests on changed files
        run: |
          cd tpot-analyzer

          # Get changed Python files
          CHANGED=$(git diff --name-only origin/main...HEAD | grep "^src/.*\.py$" | tr '\n' ',')

          if [ -z "$CHANGED" ]; then
            echo "No Python source files changed"
            exit 0
          fi

          # Run mutation testing
          mutmut run --paths-to-mutate="$CHANGED" --CI

      - name: Check mutation score threshold
        run: |
          cd tpot-analyzer

          # Extract mutation score
          SCORE=$(mutmut results | grep -oP 'Mutation score: \K[0-9.]+')

          echo "Mutation score: $SCORE%"

          # Fail if below 80%
          if (( $(echo "$SCORE < 80" | bc -l) )); then
            echo "❌ Mutation score below 80% threshold"
            exit 1
          fi

          echo "✅ Mutation score meets threshold"

      - name: Generate report
        if: failure()
        run: |
          cd tpot-analyzer
          mutmut html

      - name: Upload report
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: mutation-report
          path: tpot-analyzer/mutmut-results.html
```

---

## Baseline Measurement (Phase 1, Task 1.2)

### Running Full Baseline

```bash
cd tpot-analyzer

# Generate coverage data first
pytest tests/ --cov=src --cov-report=

# Run mutation testing on each module
mutmut run --paths-to-mutate=src/config.py
mutmut results > results/config_baseline.txt

mutmut run --paths-to-mutate=src/logging_utils.py
mutmut results > results/logging_baseline.txt

mutmut run --paths-to-mutate=src/api/cache.py
mutmut results > results/cache_baseline.txt

# ... repeat for all modules
```

### Expected Baseline Results

Based on code analysis:

| Module | Mutations | Est. Killed | Est. Score | Priority |
|--------|-----------|-------------|------------|----------|
| `src/config.py` | ~40 | ~15 (38%) | **LOW** | 🔴 High |
| `src/logging_utils.py` | ~50 | ~20 (40%) | **LOW** | 🔴 High |
| `src/api/cache.py` | ~80 | ~60 (75%) | **GOOD** | 🟢 Low |
| `src/api/server.py` | ~120 | ~65 (54%) | **MEDIUM** | 🟡 Medium |
| `src/graph/metrics.py` | ~60 | ~50 (83%) | **GOOD** | 🟢 Low |
| `src/graph/builder.py` | ~90 | ~60 (67%) | **MEDIUM** | 🟡 Medium |
| `src/data/fetcher.py` | ~100 | ~70 (70%) | **MEDIUM** | 🟡 Medium |

**Overall Estimated Score:** 55-65%

---

## Improving Mutation Score

### Step 1: Identify Survived Mutations

```bash
# Show all survived mutations
mutmut show --survived

# Show specific mutation
mutmut show 5
```

### Step 2: Analyze Why It Survived

Common reasons:

1. **No test for that code path**
   ```python
   # Survived: Changed 'if x > 0' to 'if x >= 0'
   # Reason: No test with x=0
   ```
   **Fix:** Add boundary value test

2. **Test uses same calculation as code (mirror)**
   ```python
   # Code: return a + b
   # Test: assert add(2,3) == 2 + 3  # Same calculation!
   ```
   **Fix:** Use hardcoded expected value

3. **Test too generic**
   ```python
   # Test: assert result is not None
   # Survived: Any mutation that returns non-None
   ```
   **Fix:** Assert specific expected value

### Step 3: Write Test to Kill Mutation

```python
# Example: Kill mutation "alpha > 1" → "alpha >= 1"
def test_pagerank_alpha_equals_one_valid():
    """Alpha=1.0 should be valid (teleportation disabled)."""
    graph = nx.DiGraph([("a", "b"), ("b", "c")])
    pr = compute_personalized_pagerank(graph, ["a"], alpha=1.0)

    # Should not raise
    assert sum(pr.values()) == pytest.approx(1.0)
    assert pr["a"] > 0  # Seed should have score
```

### Step 4: Re-run Mutation Testing

```bash
# Run mutation testing again
mutmut run --paths-to-mutate=src/graph/metrics.py

# Check if mutation is now killed
mutmut results
```

---

## Troubleshooting

### Issue: Mutation testing is very slow

**Solutions:**
1. Use `--use-coverage` to skip uncovered code
2. Use `--processes=4` for parallel execution
3. Test specific modules instead of entire codebase
4. Use `--CI` flag to skip interactive prompts

### Issue: All mutations timeout

**Cause:** Mutation created infinite loop (common with `while` loops)

**Solution:**
```bash
# Increase timeout (default: 10s)
mutmut run --timeout-multiplier=2.0
```

### Issue: Tests are flaky under mutation

**Cause:** Tests depend on timing, randomness, or external state

**Solution:**
- Use deterministic seeds for random generators
- Mock time-dependent code
- Isolate tests (proper setup/teardown)

### Issue: Can't reproduce survived mutation locally

```bash
# Apply specific mutation
mutmut apply 5

# Run tests manually
pytest tests/test_graph_metrics.py -v

# Revert mutation
git checkout src/graph/metrics.py
```

---

## Best Practices

### DO:
✅ Run mutation testing before merging PRs
✅ Focus on critical modules first (core algorithms)
✅ Use coverage to speed up mutation testing
✅ Write property-based tests (kill many mutations at once)
✅ Target 85%+ mutation score on new code

### DON'T:
❌ Don't mutate test files
❌ Don't mutate generated code
❌ Don't mutate logging/print statements
❌ Don't aim for 100% mutation score (diminishing returns)
❌ Don't run full mutation testing on every commit (too slow)

---

## Resources

- **Mutmut Docs:** https://mutmut.readthedocs.io/
- **Mutation Testing Intro:** https://en.wikipedia.org/wiki/Mutation_testing
- **Property-Based Testing:** https://hypothesis.readthedocs.io/
- **This Project's Baseline:** `docs/MUTATION_TESTING_BASELINE.md`

---

## Phase 1 Checklist

- [x] Mutation testing infrastructure set up
- [ ] Baseline measurement complete (Task 1.2)
- [ ] Tests categorized (Task 1.3)
- [ ] Nokkukuthi tests deleted (Task 1.4)
- [ ] Mirror tests fixed (Task 1.5)
- [ ] Target: 75-80% mutation score after Phase 1

**Next:** Run `mutmut run` on each module and document results.
