# Community Map Snapshots — Design

## Goal

Version control for community curation state. Save named checkpoints, create branches to explore different ontological framings (e.g. "Kegan Stage 3" vs "By technical domain"), switch between them, and restore from any save point.

## Architecture

**Approach: Snapshot table + branch pointer** (chosen over workspace-scoped Layer 2 and diff chains).

Layer 2 tables (`community`, `community_account`, `account_note`) remain the single mutable working state. Snapshots are immutable JSON copies attached to named branches. One branch is active at a time. Switching branches wipes and restores Layer 2.

This is minimally invasive — existing CRUD code doesn't change. Snapshots are clean blobs, easy to export/share later.

## Schema

Three new tables added to `archive_tweets.db`:

```sql
CREATE TABLE IF NOT EXISTS community_branch (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    base_run_id  TEXT,
    is_active    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    -- future: author_id TEXT, visibility TEXT, published_at TEXT
    FOREIGN KEY (base_run_id) REFERENCES community_run(run_id)
);

CREATE TABLE IF NOT EXISTS community_snapshot (
    id           TEXT PRIMARY KEY,
    branch_id    TEXT NOT NULL,
    name         TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (branch_id) REFERENCES community_branch(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_snapshot_data (
    snapshot_id   TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('community', 'assignment', 'note')),
    data          TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES community_snapshot(id) ON DELETE CASCADE
);
```

Key decisions:
- `is_active` — exactly one branch has `is_active=1`. This is what Layer 2 represents.
- `kind` + JSON in snapshot_data — extensible; new per-account data = new kind value.
- `base_run_id` — tracks which NMF run a branch was built from. Allows branching from different NMF parameterizations.

## Branch Operations

### Create branch (fork from current)
1. Auto-snapshot current Layer 2 onto current branch.
2. Create new branch row.
3. Copy same snapshot onto new branch.
4. Set new branch as active.

### Switch branch
1. Check dirty state (compare working Layer 2 against latest snapshot on current branch).
2. If dirty: require user to save or discard. Do not auto-save.
3. Wipe Layer 2 tables.
4. Restore from target branch's latest snapshot.
5. Set target branch as active.

### Save snapshot
1. Serialize current Layer 2 (communities, assignments, notes) as JSON.
2. Store in `community_snapshot` + `community_snapshot_data`.
3. Attach to current active branch. Optional user-provided name.

### Restore snapshot
1. Pick any snapshot on the current branch.
2. Wipe Layer 2, restore from that snapshot.
3. Does not delete newer snapshots (can go forward again).

### Delete branch
- Cannot delete the active branch.
- CASCADE deletes snapshots and snapshot_data.

### Dirty detection
- Serialize current Layer 2 state, compare against latest snapshot's JSON.
- If no snapshot exists on branch yet, state is "clean" (creation itself snapshots).

## API Endpoints

Route group: `/api/communities/branches`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/branches` | List all branches |
| POST | `/branches` | Create branch (fork) |
| PATCH | `/branches/:id` | Rename / update description |
| DELETE | `/branches/:id` | Delete (not active) |
| GET | `/branches/:id/dirty` | Check unsaved changes |
| POST | `/branches/:id/switch` | Switch to branch (body: `{action: "save"\|"discard"}`) |
| POST | `/branches/:id/snapshots` | Save snapshot |
| GET | `/branches/:id/snapshots` | List snapshots on branch |
| POST | `/branches/:id/snapshots/:sid/restore` | Restore snapshot |

Existing `/api/communities` CRUD is unchanged — operates on active branch's live Layer 2 data.

## UI

Branch bar added between header and main layout:

```
[🔀 main ▼ | Save | Branch... | ⚠ unsaved changes]
```

- **Branch dropdown** — list all branches, click to switch. Dirty state triggers modal: "Save changes to [branch]?" → Save / Discard / Cancel.
- **Save button** — snapshot current state. Optional name prompt (default: timestamp).
- **Branch button** — fork from current state, prompt for name.
- **Dirty indicator** — "unsaved changes" badge when working state ≠ latest snapshot.
- **Snapshot history** (lower priority) — expandable list of snapshots, click to restore.

No changes to deep dive, member table, or community list.

## Bootstrapping

On first use (no branches exist), auto-create "main" branch:
- `is_active = 1`
- `base_run_id` = latest NMF run
- Snapshot current Layer 2 state

Existing users get seamless upgrade — current work becomes first snapshot on "main".

## Edge Cases

- **Empty branch:** defensively handle (restore to empty state).
- **NMF re-run:** only affects Layer 1. Active branch stays as-is. User creates new branch with new `base_run_id`.
- **Snapshot size:** ~300 accounts × 14 communities ≈ 500KB per snapshot. Fine for SQLite.
- **Concurrent writes:** single-user + SQLite WAL. Not a concern now.

## Future Phases (not built now, schema supports)

- Multi-user: `author_id`, `visibility`, `published_at` fields on branch.
- Public browsing: read-only website where others view curated ontologies.
- Diffing between branches/snapshots.
- Merging branches.
- Branch from a specific historical snapshot (currently always forks from working state).

## Related

- ADR 006: shared tagging & workspace model (proposed, not implemented)
- `src/communities/store.py`: Layer 1 (NMF) + Layer 2 (curator) persistence
- `src/api/routes/communities.py`: existing CRUD endpoints
