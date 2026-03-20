# Communities — NMF Soft Clustering, Curation & Versioning

<!--
Last verified: 2026-03-19
Code hash: 596924c
Verified by: agent
-->

## Purpose

Manages soft community assignments for network accounts using a two-layer
architecture: an immutable NMF layer (algorithmic runs) and a mutable curator
layer (human-edited canonical map). Includes branch/snapshot versioning so
curators can explore alternative ontologies without losing state.

## Module Files

| File | LOC | Responsibility |
|------|-----|----------------|
| `store.py` | 367 | SQLite persistence — Layer 1 (NMF) and Layer 2 (curator) CRUD |
| `versioning.py` | 377 | Branch/snapshot version control for Layer 2 state |
| `cluster_colors.py` | 226 | ADR-013 probabilistic color contract (5 rendering quantities) |
| `preview.py` | 185 | Rich per-account preview data for curator UI |

### API Routes

| File | LOC | Blueprint | Prefix |
|------|-----|-----------|--------|
| `routes/communities.py` | 264 | `communities_bp` | `/api/communities` |
| `routes/branches.py` | 216 | `branches_bp` | `/api/communities/branches` |

## Architecture

### Two-Layer Design (store.py)

**Layer 1 — NMF (immutable, recomputable):**
- `community_run` — One row per NMF clustering run (k, signal, threshold)
- `community_membership` — W matrix: (run_id, account_id, community_idx, weight)
- `community_definition` — H matrix top signals: (run_id, community_idx, feature_type, target, score)

**Layer 2 — Curator's map (mutable, human-editable):**
- `community` — Named communities with color, description, seeded_from_run
- `community_account` — Account assignments with weight and source (`nmf` | `human`)
- `account_note` — Curator's freeform per-account notes

**Commit contract:**
- Layer 1 bulk writers (`save_run`, `save_memberships`, `save_definitions`) commit
  internally — called from scripts expecting atomic writes.
- Layer 2 single-row writers (`upsert_community`, `upsert_community_account`,
  `upsert_account_note`) do NOT commit — callers batch and commit.
- Destructive ops (`delete_community`, `clear_seeded_communities`,
  `reseed_nmf_memberships`) commit internally for safety.

**Human override:** PK `(community_id, account_id)` ensures one assignment per pair.
`upsert_community_account(source='human')` overwrites NMF at write time.

### Versioning (versioning.py)

Branch/snapshot model for Layer 2:

- `community_branch` — Named branches, one active at a time
- `community_snapshot` — Immutable checkpoints per branch
- `community_snapshot_data` — Serialized JSON (community, assignment, note rows)

Key operations:
- `capture_snapshot()` — Freeze current Layer 2 state as JSON
- `restore_snapshot()` — Wipe Layer 2, restore from snapshot (destructive)
- `switch_branch()` — Auto-save current, restore target's latest snapshot
- `is_branch_dirty()` — Check if working state differs from latest snapshot
- `ensure_main_branch()` — Idempotent first-run setup

### Color Contract (cluster_colors.py)

Implements ADR-013's five independent rendering quantities from soft community
membership propagation:

| Quantity | Formula | Meaning |
|----------|---------|---------|
| `signal_strength` | `1 - p[none]` | How much community signal exists |
| `purity` | `top1 / sum(K)` | How concentrated in dominant community |
| `ambiguity` | `top1 - top2` | Margin between top two |
| `coverage` | `matched / total` | Fraction with propagation scores |
| `confidence` | `mean(1 - uncertainty)` | Per-member quality |
| `chroma` | `sqrt(signal * confidence * coverage) * concentration` | Final rendering value |

Data classes: `PropagationData` (loaded from `.npz`), `CommunityInfo` (per-cluster result).

### Account Preview (preview.py)

Assembles rich per-account data for the curator UI by joining archive tables
with community assignments. Returns: profile, community memberships, mutual
followers, notable followees, recent/top tweets, liked tweets, RT targets,
TPOT score, curator note.

**Note:** Response uses snake_case keys (`account_id`, `followers_you_know`,
`tpot_score`). This is a known convention violation — see tech debt below.

## API Endpoints

### Communities (`/api/communities`)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | List all communities with member counts |
| GET | `/<id>/members` | Members of a community (optional `?ego=` for "I follow" badge) |
| GET | `/account/<id>` | Which communities an account belongs to |
| PUT | `/<id>/members/<account_id>` | Manually assign account (source=human) |
| DELETE | `/<id>/members/<account_id>` | Remove account from community |
| PATCH | `/<id>` | Update community name/color/description |
| DELETE | `/<id>` | Delete community + cascade assignments |
| GET | `/account/<id>/preview` | Rich account preview (profile, tweets, follows, note) |
| PUT | `/account/<id>/note` | Save curator's freeform note |
| PUT | `/account/<id>/weights` | Update community weights for an account |

### Branches (`/api/communities/branches`)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | List branches (auto-creates 'main' on first call) |
| POST | `/` | Create new branch forked from current state |
| PATCH | `/<id>` | Rename or update branch description |
| DELETE | `/<id>` | Delete non-active branch (409 if active) |
| POST | `/<id>/switch` | Switch to branch (action: save\|discard) |
| GET | `/<id>/dirty` | Check if working state differs from snapshot |
| GET | `/<id>/snapshots` | List snapshots on branch |
| POST | `/<id>/snapshots` | Save named snapshot |
| POST | `/<id>/snapshots/<snap_id>/restore` | Restore snapshot |

## Dependencies

```
store.py ──→ versioning.py  (uses now_utc only)
         ──→ preview.py     (uses get_account_communities, get_account_note)
         ──→ routes/communities.py
         ──→ routes/branches.py

versioning.py ──→ routes/branches.py
preview.py    ──→ routes/communities.py
cluster_colors.py ──→ cluster_routes.py (loaded for cluster rendering)
```

No circular dependencies. `cluster_colors.py` is consumed by the cluster routes
module, not the community routes.

## Known Tech Debt

- **snake_case API responses:** `communities.py`, `branches.py`, and `preview.py`
  return snake_case keys (`member_count`, `base_run_id`, `account_id`, etc.)
  violating the project's camelCase convention (CONVENTIONS.md). Frontend
  (`Communities.jsx`, `AccountDeepDive.jsx`) already depends on these shapes,
  so fixing requires a coordinated migration.
- **`is_branch_dirty()` is O(n):** Loads entire snapshot data to compare. Could
  add a content hash to the snapshot table.
- **No partial restore:** `restore_snapshot()` always wipes and restores atomically.

## Design Docs

Historical design rationale in `docs/plans/`:
- `2026-02-25-communities-curation-tab.md` — Original tab design
- `2026-02-26-community-snapshots-design.md` — Versioning architecture
- `2026-02-26-community-clusteriew-design.md` — ClusterView integration

## ADR References

- [ADR-011: Content-Aware Fingerprinting and Community Visualization](../adr/011-content-aware-fingerprinting-and-community-visualization.md)
- [ADR-012: Community-Seeded Cluster Navigation](../adr/012-community-seeded-cluster-navigation.md)
- [ADR-013: Probabilistic Cluster Color Contract](../adr/013-probabilistic-cluster-color-contract.md)
