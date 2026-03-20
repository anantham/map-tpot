# Find My Ingroup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static public site where anyone can look up their Twitter handle and see soft community membership across a curated TPOT ontology.

**Architecture:** Python export script reads SQLite + NPZ + Parquet, produces two JSON files. Standalone Vite + React app at `tpot-analyzer/public-site/` consumes them. Zero backend. Deploys to Vercel free tier.

**Tech Stack:** Python 3.9 (export), Vite 7 + React 19 (frontend), Canvas API (PNG generation)

**Spec:** `docs/superpowers/specs/2026-03-19-find-my-ingroup-design.md`

**Note:** The export script loads `.npz` files via `numpy.load()` (NumPy's own format, not pickle from untrusted sources). These are locally-generated graph analysis artifacts.

---

## File Structure

### Export Pipeline (Python)

| File | Responsibility |
|------|---------------|
| `scripts/export_public_site.py` | Main export script — reads data sources, applies abstain gate, writes JSON |
| `config/public_site.json` | Curator-specific config (contribution links, site name, curator handle) |
| `tests/test_export_public_site.py` | Unit tests for export logic (filtering, schema, abstain gate) |

### Static Frontend (React)

| File | Responsibility |
|------|---------------|
| `public-site/package.json` | Dependencies: react, react-dom, vite |
| `public-site/vite.config.js` | Vite config |
| `public-site/vercel.json` | Vercel deployment config (rewrites, headers) |
| `public-site/index.html` | HTML shell |
| `public-site/src/main.jsx` | React mount point |
| `public-site/src/App.jsx` | Top-level: loads data.json, manages search state, routes to card/prompt |
| `public-site/src/SearchBar.jsx` | Autocomplete input — lazy-loads search.json, filters handles |
| `public-site/src/CommunityCard.jsx` | Result card — community bars (color or grayscale by tier) |
| `public-site/src/CardDownload.jsx` | Canvas-to-PNG rendering + download trigger |
| `public-site/src/ContributePrompt.jsx` | "Not found" / "contribute your data" with links from meta |
| `public-site/src/styles.css` | All styles |

---

## Task 1: Export Config File

**Files:**
- Create: `config/public_site.json`

- [ ] **Step 1: Create the config file**

```json
{
  "site_name": "Find My Ingroup",
  "curator": "aditya",
  "links": {
    "curator_dm": "https://twitter.com/messages/compose?recipient_id=YOUR_TWITTER_NUMERIC_ID",
    "community_archive": "https://github.com/community-archive/community-archive",
    "repo": "https://github.com/aditya/tpot-analyzer"
  },
  "export": {
    "min_weight": 0.05,
    "abstain_threshold": 0.10,
    "output_dir": "public-site/public"
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add config/public_site.json
git commit -m "feat(public-site): add export config for public site"
```

---

## Task 2: Export Script — Core Logic

**Files:**
- Create: `scripts/export_public_site.py`
- Create: `tests/test_export_public_site.py`

- [ ] **Step 1: Write failing test for community extraction**

```python
# tests/test_export_public_site.py
import json
import sqlite3
import pytest
from pathlib import Path


def _create_test_db(db_path: Path) -> None:
    """Create a minimal archive_tweets.db with community tables."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE community (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            color TEXT NOT NULL, description TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE community_account (
            community_id TEXT NOT NULL, account_id TEXT NOT NULL,
            weight REAL NOT NULL, source TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (community_id, account_id)
        );
        INSERT INTO community VALUES ('c1', 'AI Safety', '#ff0000', 'AI alignment folks', '', '');
        INSERT INTO community VALUES ('c2', 'Philosophy', '#00ff00', 'Thinkers', '', '');
        INSERT INTO community_account VALUES ('c1', 'acct1', 0.85, 'nmf', '');
        INSERT INTO community_account VALUES ('c2', 'acct1', 0.12, 'nmf', '');
        INSERT INTO community_account VALUES ('c1', 'acct2', 0.60, 'nmf', '');
        INSERT INTO community_account VALUES ('c2', 'acct2', 0.03, 'nmf', '');
    """)
    conn.commit()
    conn.close()


class TestExtractCommunities:
    def test_extracts_communities_with_member_counts(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        _create_test_db(db_path)

        from scripts.export_public_site import extract_communities
        communities = extract_communities(db_path)

        assert len(communities) == 2
        ai = next(c for c in communities if c["name"] == "AI Safety")
        assert ai["color"] == "#ff0000"
        assert ai["member_count"] == 2

    def test_filters_memberships_below_min_weight(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        _create_test_db(db_path)

        from scripts.export_public_site import extract_classified_accounts
        accounts = extract_classified_accounts(db_path, min_weight=0.05)

        acct2 = next(a for a in accounts if a["id"] == "acct2")
        # acct2 has weight 0.03 for Philosophy — should be filtered out
        community_ids = [m["community_id"] for m in acct2["memberships"]]
        assert "c2" not in community_ids
        assert "c1" in community_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.export_public_site'`

- [ ] **Step 3: Implement extract_communities and extract_classified_accounts**

```python
# scripts/export_public_site.py
"""Export pre-computed community data as static JSON for the public site."""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _PROJECT_ROOT / "config" / "public_site.json"
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"


def load_config(config_path: Path = _DEFAULT_CONFIG) -> dict:
    """Load export configuration."""
    with open(config_path) as f:
        return json.load(f)


def extract_communities(db_path: Path) -> list[dict]:
    """Extract community metadata with member counts."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT c.id, c.name, c.color, c.description,
                  COUNT(ca.account_id) as member_count
           FROM community c
           LEFT JOIN community_account ca ON ca.community_id = c.id
           GROUP BY c.id
           ORDER BY member_count DESC"""
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "color": r["color"],
            "description": r["description"] or "",
            "member_count": r["member_count"],
        }
        for r in rows
    ]


def extract_classified_accounts(
    db_path: Path,
    min_weight: float = 0.05,
) -> list[dict]:
    """Extract accounts with direct community assignments."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    account_ids = [
        r["account_id"]
        for r in conn.execute(
            "SELECT DISTINCT account_id FROM community_account"
        ).fetchall()
    ]

    accounts = []
    for acct_id in account_ids:
        memberships = [
            {"community_id": r["community_id"], "weight": round(r["weight"], 4)}
            for r in conn.execute(
                """SELECT community_id, weight FROM community_account
                   WHERE account_id = ? AND weight >= ?
                   ORDER BY weight DESC""",
                (acct_id, min_weight),
            ).fetchall()
        ]
        if memberships:
            accounts.append({"id": acct_id, "tier": "classified", "memberships": memberships})

    conn.close()
    return accounts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py
git commit -m "feat(export): community and classified account extraction"
```

---

## Task 3: Export Script — Propagated Accounts + Abstain Gate

**Files:**
- Modify: `scripts/export_public_site.py`
- Modify: `tests/test_export_public_site.py`

- [ ] **Step 1: Write failing test for propagation loading + abstain gate**

```python
# Add to tests/test_export_public_site.py
import numpy as np

class TestExtractPropagated:
    def _make_npz(self, tmp_path, n_nodes=5, n_communities=2):
        """Create a minimal propagation NPZ."""
        memberships = np.zeros((n_nodes, n_communities + 1), dtype=np.float32)
        memberships[0] = [0.7, 0.2, 0.1]   # strong signal
        memberships[1] = [0.05, 0.04, 0.91] # weak — below abstain threshold
        memberships[2] = [0.3, 0.5, 0.2]    # moderate
        memberships[3] = [0.03, 0.02, 0.95] # all below min_weight
        memberships[4] = [0.8, 0.1, 0.1]    # classified (skip)

        npz_path = tmp_path / "community_propagation.npz"
        np.savez(
            npz_path,
            memberships=memberships,
            uncertainty=np.array([0.1, 0.9, 0.3, 0.95, 0.05], dtype=np.float32),
            abstain_mask=np.array([False, True, False, True, False]),
            labeled_mask=np.array([False, False, False, False, True]),
            node_ids=np.array(["n0", "n1", "n2", "n3", "n4"]),
            community_ids=np.array(["c1", "c2"]),
            community_names=np.array(["AI Safety", "Philosophy"]),
            community_colors=np.array(["#ff0000", "#00ff00"]),
        )
        return npz_path

    def test_excludes_abstained_nodes(self, tmp_path):
        npz_path = self._make_npz(tmp_path)
        from scripts.export_public_site import extract_propagated_handles

        handles_meta = {"n0": "user0", "n2": "user2", "n1": "user1", "n3": "user3"}
        classified_ids = {"n4"}
        result = extract_propagated_handles(
            npz_path, handles_meta, classified_ids,
            min_weight=0.05, abstain_threshold=0.10,
        )
        assert "user0" in result
        assert "user2" in result
        assert "user1" not in result  # abstain_mask=True
        assert "user3" not in result  # abstain_mask=True

    def test_excludes_classified_from_propagated(self, tmp_path):
        npz_path = self._make_npz(tmp_path)
        from scripts.export_public_site import extract_propagated_handles

        handles_meta = {"n4": "classifieduser"}
        classified_ids = {"n4"}
        result = extract_propagated_handles(
            npz_path, handles_meta, classified_ids,
            min_weight=0.05, abstain_threshold=0.10,
        )
        assert "classifieduser" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py::TestExtractPropagated -v`
Expected: FAIL — `cannot import name 'extract_propagated_handles'`

- [ ] **Step 3: Implement extract_propagated_handles**

Add to `scripts/export_public_site.py`:

```python
def extract_propagated_handles(
    npz_path: Path,
    node_id_to_username: dict[str, str],
    classified_ids: set[str],
    *,
    min_weight: float = 0.05,
    abstain_threshold: float = 0.10,
) -> dict[str, dict]:
    """Build handle->membership index from propagation NPZ.

    Excludes: classified accounts, abstained nodes, nodes without usernames,
    and nodes whose max community weight is below abstain_threshold.
    """
    data = np.load(str(npz_path), allow_pickle=False)
    memberships = data["memberships"]       # (N, K+1)
    abstain_mask = data["abstain_mask"]      # (N,) bool
    node_ids = data["node_ids"]             # (N,) str
    community_ids = data["community_ids"]   # (K,) str

    n_communities = len(community_ids)
    handles: dict[str, dict] = {}
    skipped_abstain = 0
    skipped_no_username = 0
    skipped_classified = 0

    for i, nid in enumerate(node_ids):
        nid_str = str(nid)

        if nid_str in classified_ids:
            skipped_classified += 1
            continue

        username = node_id_to_username.get(nid_str)
        if not username:
            skipped_no_username += 1
            continue

        if abstain_mask[i]:
            skipped_abstain += 1
            continue

        weights = memberships[i, :n_communities]
        max_weight = float(weights.max())

        if max_weight < abstain_threshold:
            skipped_abstain += 1
            continue

        entry_memberships = [
            {"community_id": str(community_ids[c]), "weight": round(float(weights[c]), 4)}
            for c in range(n_communities)
            if float(weights[c]) >= min_weight
        ]

        if not entry_memberships:
            skipped_abstain += 1
            continue

        handles[username.lower()] = {
            "id": nid_str,
            "tier": "propagated",
            "memberships": entry_memberships,
        }

    logger.info(
        "Propagated: %d exported, %d abstained, %d no username, %d classified (skipped)",
        len(handles), skipped_abstain, skipped_no_username, skipped_classified,
    )
    return handles
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py
git commit -m "feat(export): propagated account extraction with abstain gate"
```

---

## Task 4: Export Script — Main Entrypoint + JSON Assembly

**Files:**
- Modify: `scripts/export_public_site.py`
- Modify: `tests/test_export_public_site.py`

- [ ] **Step 1: Write failing test for full export**

```python
# Add to tests/test_export_public_site.py
import pandas as pd

class TestFullExport:
    def test_produces_data_and_search_json(self, tmp_path):
        db_path = tmp_path / "data" / "archive_tweets.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _create_test_db(db_path)

        nodes_df = pd.DataFrame({
            "node_id": ["acct1", "acct2", "acct3"],
            "username": ["alice", "bob", "charlie"],
            "display_name": ["Alice A", "Bob B", "Charlie C"],
            "num_followers": [100.0, 200.0, 50.0],
            "bio": ["hello", "world", None],
        })
        parquet_path = tmp_path / "data" / "graph_snapshot.nodes.parquet"
        nodes_df.to_parquet(parquet_path)

        config = {
            "site_name": "Test Site",
            "curator": "tester",
            "links": {"curator_dm": "https://example.com", "community_archive": "https://example.com", "repo": "https://example.com"},
            "export": {"min_weight": 0.05, "abstain_threshold": 0.10, "output_dir": str(tmp_path / "out")},
        }

        from scripts.export_public_site import run_export

        run_export(data_dir=tmp_path / "data", output_dir=tmp_path / "out", config=config)

        data_json = json.loads((tmp_path / "out" / "data.json").read_text())
        search_json = json.loads((tmp_path / "out" / "search.json").read_text())

        assert len(data_json["communities"]) == 2
        assert len(data_json["accounts"]) == 2
        assert data_json["meta"]["curator"] == "tester"
        assert "links" in data_json["meta"]

        alice = next(a for a in data_json["accounts"] if a["username"] == "alice")
        assert alice["bio"] == "hello"
        assert alice["followers"] == 100

        assert "alice" in search_json["handles"]
        assert search_json["handles"]["alice"]["tier"] == "classified"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py::TestFullExport -v`
Expected: FAIL — `cannot import name 'run_export'`

- [ ] **Step 3: Implement run_export and _enrich_classified_accounts**

Add to `scripts/export_public_site.py`:

```python
def _enrich_classified_accounts(accounts: list[dict], nodes_df: pd.DataFrame) -> list[dict]:
    """Add metadata (username, display_name, bio, followers) from parquet."""
    node_lookup = nodes_df.set_index("node_id").to_dict("index")
    enriched = []
    for acct in accounts:
        meta = node_lookup.get(acct["id"], {})
        username = meta.get("username")
        if not username or str(username) in ("nan", "None", ""):
            continue
        followers = meta.get("num_followers")
        enriched.append({
            **acct,
            "username": str(username),
            "display_name": str(meta.get("display_name") or username),
            "bio": str(meta.get("bio") or ""),
            "followers": int(followers) if followers and not np.isnan(followers) else 0,
        })
    return enriched


def run_export(
    *,
    data_dir: Path = _DEFAULT_DATA_DIR,
    output_dir: Path | None = None,
    config: dict | None = None,
) -> None:
    """Main export: read all sources, produce data.json + search.json."""
    if config is None:
        config = load_config()

    export_cfg = config.get("export", {})
    min_weight = export_cfg.get("min_weight", 0.05)
    abstain_threshold = export_cfg.get("abstain_threshold", 0.10)

    if output_dir is None:
        output_dir = _PROJECT_ROOT / export_cfg.get("output_dir", "public-site/public")
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "archive_tweets.db"
    parquet_path = data_dir / "graph_snapshot.nodes.parquet"
    npz_path = data_dir / "community_propagation.npz"

    communities = extract_communities(db_path)
    logger.info("Extracted %d communities", len(communities))

    raw_accounts = extract_classified_accounts(db_path, min_weight=min_weight)
    nodes_df = pd.read_parquet(parquet_path)
    accounts = _enrich_classified_accounts(raw_accounts, nodes_df)
    classified_ids = {a["id"] for a in accounts}
    logger.info("Extracted %d classified accounts", len(accounts))

    search_handles: dict[str, dict] = {}
    for acct in accounts:
        search_handles[acct["username"].lower()] = {"id": acct["id"], "tier": "classified"}

    if npz_path.exists():
        node_id_to_username = {
            str(k): str(v) for k, v in
            zip(nodes_df["node_id"].astype(str), nodes_df["username"].astype(str))
            if v and str(v) not in ("nan", "None", "")
        }
        propagated = extract_propagated_handles(
            npz_path, node_id_to_username, classified_ids,
            min_weight=min_weight, abstain_threshold=abstain_threshold,
        )
        search_handles.update(propagated)
    else:
        logger.warning("No community_propagation.npz found — exporting classified only")

    data_json = {
        "meta": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "curator": config.get("curator", "unknown"),
            "site_name": config.get("site_name", "Find My Ingroup"),
            "total_classified": len(accounts),
            "total_searchable": len(search_handles),
            "links": config.get("links", {}),
        },
        "communities": communities,
        "accounts": accounts,
    }

    search_json = {"handles": search_handles}

    data_out = output_dir / "data.json"
    search_out = output_dir / "search.json"
    data_out.write_text(json.dumps(data_json, ensure_ascii=False, indent=None))
    search_out.write_text(json.dumps(search_json, ensure_ascii=False, indent=None))

    logger.info(
        "Export complete: data.json=%dKB, search.json=%dKB, classified=%d, searchable=%d",
        data_out.stat().st_size // 1024, search_out.stat().st_size // 1024,
        len(accounts), len(search_handles),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = load_config()
    run_export(config=config)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tpot-analyzer && .venv/bin/python3 -m pytest tests/test_export_public_site.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run the real export against actual data**

Run: `cd tpot-analyzer && .venv/bin/python3 -m scripts.export_public_site`
Expected: prints stats — classified count, searchable count, file sizes

- [ ] **Step 6: Commit**

```bash
git add scripts/export_public_site.py tests/test_export_public_site.py
git commit -m "feat(export): full JSON export pipeline with abstain gate"
```

---

## Task 5: Public Site Scaffold

**Files:**
- Create: `public-site/package.json`, `public-site/vite.config.js`, `public-site/vercel.json`
- Create: `public-site/index.html`, `public-site/src/main.jsx`
- Create: `public-site/src/App.jsx` (placeholder), `public-site/src/styles.css`

- [ ] **Step 1: Initialize the project**

```bash
cd tpot-analyzer && mkdir -p public-site/src public-site/public
cd public-site
npm init -y
npm install react react-dom
npm install -D vite @vitejs/plugin-react
```

- [ ] **Step 2: Create vite.config.js**

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({ plugins: [react()] })
```

- [ ] **Step 3: Create vercel.json**

```json
{
  "rewrites": [
    { "source": "/((?!data\\.json|search\\.json|assets/).*)", "destination": "/index.html" }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" }
      ]
    }
  ]
}
```

- [ ] **Step 4: Create index.html, main.jsx, placeholder App.jsx, and base styles.css**

See spec for exact content. App.jsx loads `data.json` on mount and displays site name + account count.

- [ ] **Step 5: Verify dev server works**

Run: `cd tpot-analyzer/public-site && npx vite --port 5175`
Expected: opens at `http://localhost:5175`, shows site name + account count

- [ ] **Step 6: Commit**

```bash
git add public-site/
git commit -m "feat(public-site): scaffold Vite + React app"
```

---

## Task 6: Search Bar Component

**Files:**
- Create: `public-site/src/SearchBar.jsx`
- Modify: `public-site/src/App.jsx`
- Modify: `public-site/src/styles.css`

- [ ] **Step 1: Create SearchBar.jsx**

Implements: text input, strips leading `@`, trims whitespace, lowercases. Lazy-loads `search.json` on first keystroke. Shows up to 8 autocomplete suggestions matching prefix. On submit or suggestion click, calls `onResult` with the matched entry (or `{ tier: 'not_found' }`).

- [ ] **Step 2: Add search bar styles**

Input field, suggestions dropdown, submit button. Dark theme matching the site.

- [ ] **Step 3: Wire SearchBar into App.jsx**

App builds `Map<id, account>` and `Map<id, community>` from `data.json`. On result, enriches classified accounts from the account map. Renders raw JSON for now (debug).

- [ ] **Step 4: Verify in browser**

Type a handle that exists in exported data. Verify JSON result appears below search bar.

- [ ] **Step 5: Commit**

```bash
git add public-site/src/
git commit -m "feat(public-site): search bar with lazy-loaded autocomplete"
```

---

## Task 7: Community Card + Contribute Prompt

**Files:**
- Create: `public-site/src/CommunityCard.jsx`
- Create: `public-site/src/ContributePrompt.jsx`
- Modify: `public-site/src/App.jsx`
- Modify: `public-site/src/styles.css`

- [ ] **Step 1: Create CommunityCard.jsx**

Renders: header (handle, display name, bio for classified), community bars sorted by weight. Bars use community hex colors for classified tier, grayscale for propagated. Shows "based on your network position" note for propagated.

- [ ] **Step 2: Create ContributePrompt.jsx**

Three contribution paths sourced from `data.json.meta.links`. Shown below grayscale cards and instead of cards for not-found handles.

- [ ] **Step 3: Add card and contribute styles**

Dark theme cards. Color bars for classified, gray bars for propagated. Responsive layout.

- [ ] **Step 4: Wire into App.jsx**

Replace debug JSON output with CommunityCard (classified + propagated) and ContributePrompt (propagated + not_found).

- [ ] **Step 5: Verify all three tiers in browser**

Classified handle → colorful card. Propagated handle → grayscale card + contribute. Unknown handle → contribute prompt only.

- [ ] **Step 6: Commit**

```bash
git add public-site/src/
git commit -m "feat(public-site): community card with color/grayscale tiers + contribute prompt"
```

---

## Task 8: PNG Download

**Files:**
- Create: `public-site/src/CardDownload.jsx`
- Modify: `public-site/src/CommunityCard.jsx`
- Modify: `public-site/src/styles.css`

- [ ] **Step 1: Create CardDownload.jsx**

Canvas-to-PNG implementation. Draws: background, handle, display name, community bars with labels and percentages, site URL footer. Colors match on-screen card (colorful or grayscale). Downloads as `ingroup-{handle}.png`.

- [ ] **Step 2: Add download button to CommunityCard**

"Download your card" button at card bottom. Passes bar data, handle, tier to CardDownload.

- [ ] **Step 3: Verify download**

Click button → PNG downloads. Verify it matches the on-screen card visually.

- [ ] **Step 4: Commit**

```bash
git add public-site/src/
git commit -m "feat(public-site): client-side PNG card download"
```

---

## Task 9: Polish + Deploy Config

**Files:**
- Modify: `public-site/src/App.jsx` (reset button, footer)
- Modify: `public-site/src/styles.css` (responsive, mobile)
- Modify: `.gitignore`

- [ ] **Step 1: Add "search again" reset and curator footer**

- [ ] **Step 2: Add responsive styles (mobile breakpoints)**

- [ ] **Step 3: Add gitignore entries**

```
tpot-analyzer/public-site/public/data.json
tpot-analyzer/public-site/public/search.json
tpot-analyzer/public-site/node_modules/
tpot-analyzer/public-site/dist/
```

- [ ] **Step 4: Build and verify production bundle**

```bash
cd tpot-analyzer/public-site && npm run build && npx serve dist
```

- [ ] **Step 5: Commit**

```bash
git add public-site/ .gitignore
git commit -m "feat(public-site): responsive polish, deploy config"
```

---

## Task 10: End-to-End Verification

- [ ] **Step 1: Run full pipeline**

```bash
cd tpot-analyzer
.venv/bin/python3 -m scripts.export_public_site
cd public-site && npm run build && npx serve dist
```

- [ ] **Step 2: Test all three tiers**

1. Classified handle → colorful card → download PNG
2. Propagated handle → grayscale card + contribute note → download PNG
3. Nonexistent handle → contribute prompt with working links

- [ ] **Step 3: Verify JSON sizes**

```bash
ls -lh public-site/public/data.json public-site/public/search.json
```

- [ ] **Step 4: Deploy to Vercel (when ready)**

```bash
cd public-site && npx vercel
```

- [ ] **Step 5: Final commit**

```bash
git commit -m "chore(public-site): end-to-end verified, ready for deployment"
```
