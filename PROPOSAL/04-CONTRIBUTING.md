# Contributing to map-tpot

Thank you for your interest in contributing! This guide will help you get started.

---

## Code of Conduct

Be respectful, constructive, and collaborative. We're building tools for community understanding — let's model good community behavior.

---

## How to Contribute

### Reporting Bugs

1. **Search existing issues** to avoid duplicates
2. **Create a new issue** with:
   - Clear title describing the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, browser)
   - Relevant logs or screenshots

### Suggesting Features

1. **Open a discussion** or issue describing:
   - The problem you're trying to solve
   - Your proposed solution
   - Alternative approaches considered
   - Impact on existing functionality

### Submitting Code

1. **Fork the repository**
2. **Create a feature branch:**
   ```bash
   git checkout -b feat/your-feature-name
   # or: git checkout -b fix/bug-description
   ```
3. **Make your changes** following our style guide
4. **Write/update tests** for your changes
5. **Run the test suite:**
   ```bash
   cd tpot-analyzer
   pytest tests/ -v
   ```
6. **Commit with clear messages** (see format below)
7. **Push and create a Pull Request**

---

## Development Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- Git

### Backend (tpot-analyzer)

```bash
cd tpot-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify setup
python3 scripts/verify_setup.py
```

### Frontend (graph-explorer)

```bash
cd tpot-analyzer/graph-explorer
npm install
npm run lint  # Check for issues
npm run dev   # Start dev server
```

---

## Code Style

### Python

- **Formatter:** We don't enforce a specific formatter, but consistent style is expected
- **Type hints:** Use them for public APIs
- **Docstrings:** Required for public functions and classes
- **Max line length:** 100 characters preferred
- **Imports:** Standard library → third-party → local, alphabetized within groups

Example:
```python
from dataclasses import dataclass
from typing import Optional

import networkx as nx
import pandas as pd

from src.data.fetcher import CachedDataFetcher


def compute_pagerank(
    graph: nx.DiGraph,
    seeds: list[str],
    alpha: float = 0.85,
) -> dict[str, float]:
    """Compute personalized PageRank with given seed accounts.

    Args:
        graph: Directed graph with account IDs as nodes.
        seeds: Account IDs to use as personalization vector.
        alpha: Damping factor (default 0.85).

    Returns:
        Dictionary mapping account IDs to PageRank scores.
    """
    ...
```

### JavaScript/React

- **ESLint:** Run `npm run lint` before committing
- **Prettier:** Consistent formatting
- **Functional components:** Preferred over class components
- **Hooks:** Use React hooks for state management

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description

Longer explanation if needed.

Context: Why this change was made
Changes: What was changed
Impact: What this enables or fixes
Tests: What tests were added/modified
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(api): add ego-network endpoint for faster initial load

Context: Full graph loading takes 4-16 seconds
Changes: Added /api/ego-network endpoint that returns k-hop subgraph
Impact: Initial load reduced to 200-500ms
Tests: Added test_ego_network_endpoint to test_api.py
```

```
fix(enricher): handle Unicode apostrophes in deleted account detection

Context: Twitter uses U+2019 (') instead of U+0027 (')
Changes: Added normalization before string matching
Impact: Deleted accounts now correctly detected
Tests: Added test case with fancy apostrophe
```

---

## Testing Guidelines

### Philosophy

From [AGENTS.md](../AGENTS.md#test_design_principles):

- **Test behavior, not implementation** — Tests should survive refactoring
- **Verify observable outcomes** — Check database state, not mock calls
- **Use realistic fixtures** — Complete objects, not minimal stubs

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only (fast)
pytest tests/ -v -m unit

# With coverage
pytest --cov=src --cov-report=term-missing tests/

# Specific file
pytest tests/test_api.py -v
```

### Writing Tests

```python
# Good: Tests public API, verifies side effects
def test_enrich_persists_edges(mock_store, mock_worker):
    """Enrichment should persist discovered edges to database."""
    enricher = HybridShadowEnricher(store=mock_store, worker=mock_worker)
    result = enricher.enrich([seed_account])

    # Verify observable outcome
    edges = mock_store.get_edges(seed_account.account_id)
    assert len(edges) == 100
    assert all(e.source_id == seed_account.account_id for e in edges)


# Bad: Tests internal implementation
def test_should_skip_seed_returns_true():
    """Tests private method — will break on refactoring."""
    enricher = HybridShadowEnricher(...)
    result = enricher._should_skip_seed(seed)  # ❌ Private method
    assert result is True
```

---

## Pull Request Process

1. **Create PR** against `main` branch
2. **Fill out template** with:
   - Summary of changes
   - Related issues
   - Testing performed
   - Screenshots (for UI changes)
3. **Wait for review** — maintainers will provide feedback
4. **Address feedback** — push additional commits
5. **Merge** — maintainer will merge when approved

### PR Checklist

- [ ] Tests pass locally
- [ ] Linting passes (`npm run lint` for frontend)
- [ ] Documentation updated if needed
- [ ] Commit messages follow convention
- [ ] No secrets or credentials included
- [ ] WORKLOG.md updated for significant changes

---

## Documentation

### When to Update Docs

- **New feature:** Add usage instructions
- **API change:** Update endpoint documentation
- **Bug fix:** Consider adding troubleshooting entry
- **Architecture change:** Create or update ADR

### ADR Process

For significant architectural decisions:

1. Create `docs/adr/NNN-title.md`
2. Use template from [AGENTS.md](../AGENTS.md)
3. Status: `Proposed`
4. Get review and feedback
5. Update status to `Accepted` when merged

---

## Getting Help

- **Questions:** Open a GitHub Discussion
- **Bugs:** Open an Issue
- **Security:** See [SECURITY.md](SECURITY.md)

---

## Recognition

Contributors will be acknowledged in:
- Pull request comments
- Release notes (for significant contributions)
- README acknowledgments section (for major features)

---

*Thank you for helping make map-tpot better!*
