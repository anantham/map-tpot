# Repository Cleanup Plan

**Date**: 2024-12-17  
**Current state**: Organic growth has created scattered files, duplicate data, and unclear organization  
**Goal**: Clean, professional repository structure with clear separation of concerns

---

## Overview of Issues

### Root Level (`Project 2 - Map TPOT/`)
| Item | Issue | Action |
|------|-------|--------|
| `community-archive/` | Separate project with own .git | Consider: submodule, separate repo, or archive |
| `grok-probe/` | Small utility, unclear if active | Archive or separate repo |
| `context/` | Reference files (HTML, PDF) | Move to `tpot-analyzer/docs/reference/` or .gitignore |
| `Related data/` | ZIP archive | .gitignore (don't track large archives) |
| `data/` | Duplicate of tpot-analyzer/data/ | Delete (use tpot-analyzer/data/) |
| `logs/` | Stale logs | Delete |
| `test-results/` | Stale test output | Delete |
| `node_modules/` | Unknown purpose at root | Delete |
| `.pytest_cache/` | Should be gitignored | Delete, add to .gitignore |
| `AGENTS.md` / `CLAUDE.md` | AI instruction files | Keep or move to `.claude/` |

### tpot-analyzer/ Level
| Item | Issue | Action |
|------|-------|--------|
| `BUGFIXES.md`, `CENTER_USER_FIX.md`, etc. | Loose docs | Move to `docs/archive/` |
| `CODEX_TASK_*.md` | Task documents | Move to `docs/tasks/` |
| `*.log` files | Debug artifacts | Move to logs/ or delete |
| `cache.db`, `tpot.db` at root | Duplicates of data/*.db | Delete |
| `tmpfile`, `test_list_diagnostics.py` | Stale temp files | Delete |
| `analysis_output.json`, `enrichment_summary.json` | Output artifacts | Move to `data/outputs/` |
| `blob_import_*.log` | Import logs | Move to `logs/imports/` or delete |
| `logs/` (2594 HTML files!) | Debug snapshots | Archive old, keep recent |

### tpot-analyzer/docs/ Level
| Current | Proposed |
|---------|----------|
| Flat structure with some subdirs | Organized hierarchy |

---

## Proposed Directory Structure

```
tpot-analyzer/
├── .github/                    # CI/CD workflows
├── config/                     # Runtime configuration
│   ├── enrichment_policy.json
│   └── graph_settings.json
├── data/                       # All data files
│   ├── .gitkeep
│   ├── outputs/                # Generated outputs (gitignored)
│   └── fixtures/               # Test fixtures (committed)
├── docs/
│   ├── index.md                # Documentation home
│   ├── ROADMAP.md
│   ├── adr/                    # Architecture Decision Records
│   ├── guides/                 # How-to guides
│   │   ├── QUICKSTART.md
│   │   ├── GPU_SETUP.md
│   │   ├── SCRAPE_DEBUG.md
│   │   └── TEST_MODE.md
│   ├── reference/              # API docs, schemas
│   │   ├── DATABASE_SCHEMA.md
│   │   └── ENRICHMENT_FLOW.md
│   ├── specs/                  # Technical specifications
│   ├── plans/                  # Historical planning docs
│   ├── tasks/                  # Codex/AI task documents
│   │   ├── CLUSTERING_FEATURES.md
│   │   ├── E2E_TESTS.md
│   │   └── UI_AESTHETICS.md
│   ├── archive/                # Historical/completed docs
│   │   ├── BUGFIXES.md
│   │   ├── CENTER_USER_FIX.md
│   │   └── ...
│   └── test-plans/
├── graph-explorer/             # Frontend (React/Vite)
│   ├── src/
│   ├── e2e/
│   └── ...
├── logs/                       # Runtime logs (gitignored)
│   └── .gitkeep
├── scripts/                    # CLI tools and utilities
│   ├── archive/                # Old/unused scripts
│   └── ...
├── secrets/                    # Credentials (gitignored)
├── src/                        # Python source code
│   ├── api/
│   ├── data/
│   ├── graph/
│   └── shadow/
├── tests/
│   ├── fixtures/
│   └── ...
├── .env.example
├── .gitignore
├── README.md
├── pytest.ini
└── requirements.txt
```

---

## Commit Sequence

### Phase 1: Gitignore & Delete Stale Files (Safe, No Code Changes)

#### Commit 1.1: Update .gitignore
```bash
# Add to tpot-analyzer/.gitignore:

# Logs and debug artifacts
logs/*.html
logs/snapshot_*.html
*.log
!logs/.gitkeep

# Data outputs (keep fixtures)
data/outputs/
data/*.db
data/*.pkl
data/*.parquet
data/*.npz
data/*.json
!data/.gitkeep
!data/fixtures/

# Temp files
tmpfile
*.pyc
__pycache__/
.pytest_cache/
.coverage
*.db-shm
*.db-wal

# IDE
.DS_Store
.claude/
```

**Message**: `chore: update .gitignore for logs, data artifacts, and temp files`

#### Commit 1.2: Delete root-level stale directories
```bash
cd "Project 2 - Map TPOT"
rm -rf data/                  # Duplicate of tpot-analyzer/data/
rm -rf logs/                  # Stale
rm -rf test-results/          # Stale
rm -rf node_modules/          # Unknown purpose
rm -rf .pytest_cache/         # Should be gitignored
```

**Message**: `chore: remove stale root-level directories (data, logs, test-results, node_modules)`

#### Commit 1.3: Delete stale files in tpot-analyzer/
```bash
cd tpot-analyzer
rm -f tmpfile
rm -f test_list_diagnostics.py
rm -f cache.db tpot.db         # Duplicates of data/*.db
rm -f *.log                    # diagnostics_test.log, test_diagnostics_output.log
rm -f blob_import_*.log        # Import logs
```

**Message**: `chore: remove stale temp files and duplicate databases`

---

### Phase 2: Archive HTML Snapshots (Large Cleanup)

#### Commit 2.1: Archive old HTML snapshots
```bash
cd tpot-analyzer/logs

# Create archive directory
mkdir -p archive/snapshots-2024

# Move all HTML files older than 30 days to archive
find . -name "snapshot_*.html" -mtime +30 -exec mv {} archive/snapshots-2024/ \;

# Compress the archive
tar -czvf archive/snapshots-2024.tar.gz archive/snapshots-2024/
rm -rf archive/snapshots-2024/

# Or just delete them all if not needed:
# rm -f snapshot_*.html
```

**Message**: `chore: archive old HTML debug snapshots (2500+ files)`

---

### Phase 3: Reorganize Documentation

#### Commit 3.1: Create docs directory structure
```bash
cd tpot-analyzer/docs
mkdir -p guides reference tasks archive
```

**Message**: `docs: create organized directory structure`

#### Commit 3.2: Move loose docs to appropriate locations
```bash
cd tpot-analyzer

# Move task documents
mv CODEX_TASK_CLUSTERING_FEATURES.md docs/tasks/CLUSTERING_FEATURES.md
mv CODEX_TASK_E2E_TESTS.md docs/tasks/E2E_TESTS.md
mv CODEX_TASK_UI_AESTHETICS.md docs/tasks/UI_AESTHETICS.md

# Move guides
mv QUICKSTART_BACKEND.md docs/guides/QUICKSTART.md
mv SCRAPE_DEBUG_GUIDE.md docs/guides/SCRAPE_DEBUG.md
mv TEST_MODE.md docs/guides/TEST_MODE.md

# Move to docs root
mv docs/GPU_SETUP.md docs/guides/

# Move historical/archive docs
mv BUGFIXES.md docs/archive/
mv CENTER_USER_FIX.md docs/archive/
mv CORRUPTION_DETECTION_FIX.md docs/archive/
mv EGO_NETWORK_PLAN.md docs/archive/
mv METRICS_PROPOSAL.md docs/archive/
mv PERFORMANCE_INSTRUMENTATION.md docs/archive/
```

**Message**: `docs: reorganize documentation into guides/, tasks/, archive/`

#### Commit 3.3: Move reference docs
```bash
cd tpot-analyzer/docs

# Already in docs, just reorganize
mv DATABASE_SCHEMA.md reference/
mv ENRICHMENT_FLOW.md reference/
mv BACKEND_IMPLEMENTATION.md reference/
mv BLOB_IMPORT_FAILURE_ANALYSIS.md archive/
mv HOLDOUT_VALIDATION_PLAN.md archive/
mv PERFORMANCE_OPTIMIZATIONS.md reference/
mv PERFORMANCE_PROFILING.md reference/
mv FEATURES_INTENT.md reference/
mv WORKLOG.md archive/
```

**Message**: `docs: move technical docs to reference/, historical to archive/`

---

### Phase 4: Organize Data Directory

#### Commit 4.1: Create data subdirectories
```bash
cd tpot-analyzer/data
mkdir -p outputs fixtures
touch outputs/.gitkeep
touch fixtures/.gitkeep

# Move output artifacts
mv ../analysis_output.json outputs/ 2>/dev/null || true
mv ../enrichment_summary.json outputs/ 2>/dev/null || true
```

**Message**: `data: create outputs/ and fixtures/ subdirectories`

---

### Phase 5: Consolidate Root Level

#### Commit 5.1: Move context/ to docs/reference/
```bash
cd "Project 2 - Map TPOT"
mv context/ tpot-analyzer/docs/reference/external/
# Or if too large, add to .gitignore instead
```

**Message**: `docs: move context/ reference files to docs/reference/external/`

#### Commit 5.2: Handle community-archive
**Options:**
1. Convert to git submodule
2. Move to separate repository
3. Archive and remove

```bash
# Option 3: Archive (if not actively maintained)
cd "Project 2 - Map TPOT"
tar -czvf community-archive-backup.tar.gz community-archive/
rm -rf community-archive/
# Add note to README about where it went
```

**Message**: `chore: archive community-archive (moved to separate storage)`

#### Commit 5.3: Handle grok-probe
```bash
cd "Project 2 - Map TPOT"
# If not used, archive it
mv grok-probe/ tpot-analyzer/scripts/archive/grok-probe/
# Or delete entirely
```

**Message**: `chore: archive grok-probe utility`

#### Commit 5.4: Clean up Related data/
```bash
# Add to .gitignore at root level
echo "Related data/" >> .gitignore
```

**Message**: `chore: gitignore Related data/ (large archives)`

---

### Phase 6: Test Audit Cleanup

#### Commit 6.1: Remove placeholder tests
```bash
cd tpot-analyzer/tests

# Delete placeholder test classes from test_list_scraping.py (lines 57-158)
# Keep only the actual tests (lines 1-56)
```

**Message**: `test: remove 6 placeholder tests from test_list_scraping.py`

#### Commit 6.2: Rename misleading test file
```bash
cd tpot-analyzer/tests
git mv test_shadow_enrichment_integration.py test_enricher_orchestration.py
```

**Message**: `test: rename test_shadow_enrichment_integration.py → test_enricher_orchestration.py`

*Rationale: File has 201 mocks, not integration tests*

---

### Phase 7: Final Cleanup & Documentation

#### Commit 7.1: Update root README
Update `tpot-analyzer/README.md` with:
- New directory structure
- Quick start commands
- Links to docs/

**Message**: `docs: update README with new directory structure`

#### Commit 7.2: Create docs/index.md
```markdown
# TPOT Analyzer Documentation

## Quick Start
- [Backend Quickstart](guides/QUICKSTART.md)
- [GPU Setup](guides/GPU_SETUP.md)

## Guides
- [Scrape Debugging](guides/SCRAPE_DEBUG.md)
- [Test Mode](guides/TEST_MODE.md)

## Reference
- [Database Schema](reference/DATABASE_SCHEMA.md)
- [Enrichment Flow](reference/ENRICHMENT_FLOW.md)
- [API Reference](reference/BACKEND_IMPLEMENTATION.md)

## Tasks (for Codex/AI)
- [Clustering Features](tasks/CLUSTERING_FEATURES.md)
- [E2E Tests](tasks/E2E_TESTS.md)
- [UI Aesthetics](tasks/UI_AESTHETICS.md)

## Architecture
- [ADRs](adr/)
- [Specs](specs/)
```

**Message**: `docs: create documentation index`

#### Commit 7.3: Add .gitkeep files
```bash
cd tpot-analyzer
touch logs/.gitkeep
touch data/.gitkeep
touch data/outputs/.gitkeep
touch data/fixtures/.gitkeep
touch tests/fixtures/.gitkeep
```

**Message**: `chore: add .gitkeep files for empty directories`

---

## Summary Statistics

| Metric | Before | After |
|--------|--------|-------|
| Root-level directories | 10 | 3 (community-archive decision pending) |
| tpot-analyzer loose .md files | 12 | 1 (README.md) |
| tpot-analyzer/logs HTML files | 2,594 | 0 (archived) |
| tpot-analyzer/logs total files | 2,605 | ~10 |
| Placeholder tests | 6 | 0 |
| Misleading test names | 1 | 0 |

---

## Execution Order

```bash
# Phase 1: Safe cleanup
git add -A && git commit -m "chore: update .gitignore for logs, data artifacts, and temp files"
# ... delete stale files ...
git add -A && git commit -m "chore: remove stale root-level directories"
git add -A && git commit -m "chore: remove stale temp files and duplicate databases"

# Phase 2: Archive snapshots (may take a while)
git add -A && git commit -m "chore: archive old HTML debug snapshots"

# Phase 3: Reorganize docs
git add -A && git commit -m "docs: create organized directory structure"
git add -A && git commit -m "docs: reorganize documentation into guides/, tasks/, archive/"
git add -A && git commit -m "docs: move technical docs to reference/, historical to archive/"

# Phase 4: Data organization
git add -A && git commit -m "data: create outputs/ and fixtures/ subdirectories"

# Phase 5: Root consolidation (decide on community-archive first)
git add -A && git commit -m "chore: consolidate root level"

# Phase 6: Test cleanup
git add -A && git commit -m "test: remove placeholder tests and rename misleading file"

# Phase 7: Documentation
git add -A && git commit -m "docs: update README and create index"
git add -A && git commit -m "chore: add .gitkeep files"
```

---

## Decisions Needed

1. **community-archive**: Keep as-is, submodule, or archive?
2. **grok-probe**: Keep, archive, or delete?
3. **HTML snapshots**: Archive (keep for debugging) or delete entirely?
4. **context/ reference files**: Move to docs or .gitignore?

---

## Post-Cleanup Verification

```bash
# Verify structure
tree -L 2 tpot-analyzer/ -I 'node_modules|.venv|__pycache__|.git'

# Verify tests still pass
cd tpot-analyzer && python -m pytest tests/ -v

# Verify no broken imports
python -c "from src.api import server; print('OK')"

# Check git status is clean
git status
```
