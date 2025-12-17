# Holdout Validation Plan for Tag-Based Clustering

## Overview

This plan creates a validation framework to test whether intuitive community clusters emerge from sparse tagging. The core idea: if I tag 5 accounts as "AI Safety", does label propagation correctly identify other AI Safety accounts I *didn't* tag?

## Phase 1: Create Ground Truth Holdout Sets

### 1.1 Define Intuitive Clusters

First, identify 4-6 clusters you can recognize intuitively. Suggested starting set:

| Cluster Name | Description | Seed Handles (examples) |
|-------------|-------------|------------------------|
| AI Safety | x-risk, alignment researchers, MIRI/Anthropic/OpenAI safety | @AISafetyMemes, @TurnTrout, @ESYudkowsky |
| Rationality | LessWrong, ACX, rationalist-adjacent | @slatestarcodex, @ESYudkowsky, @nosilverv |
| Postrat/Tpot Core | Vibes, memetics, Twitter meta | @paborito, @eigenrobot, @visakanv |
| Tech/Startup | Founders, VCs, tech commentary | Varies |
| Gender Wars | Culture war, dating discourse | Varies |
| Effective Altruism | EA orgs, cause prioritization | @GiveWell, @80aborito |

### 1.2 Build Per-Cluster Holdout

For each cluster, identify accounts in two groups:

**Training Set (Will Tag)**
- 3-5 accounts you're VERY confident about
- These will be used to "seed" the cluster

**Holdout Set (Won't Tag - Validation)**
- 5-10 accounts you're confident about
- These will be used to measure if propagation works
- Never tag these during experiments!

**Format (JSON):**
```json
{
  "clusters": {
    "ai_safety": {
      "training": ["username1", "username2", "username3"],
      "holdout": ["username4", "username5", "username6", "username7", "username8"]
    },
    "rationality": {
      "training": ["..."],
      "holdout": ["..."]
    }
  }
}
```

### 1.3 File Location
Save as: `data/holdout_clusters.json`

---

## Phase 2: Search & Tag Infrastructure (Minimal)

Before testing propagation, we need basic ability to:
1. Search for accounts by handle
2. Tag them
3. Store tags persistently

### 2.1 Backend: Tag Storage

Add a `tags` table to `clusters.db`:

```sql
CREATE TABLE IF NOT EXISTS account_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_holdout BOOLEAN DEFAULT FALSE,
    UNIQUE(account_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_account_tags_tag ON account_tags(tag);
CREATE INDEX IF NOT EXISTS idx_account_tags_account ON account_tags(account_id);
```

### 2.2 Backend: API Endpoints

**Search accounts:**
```
GET /api/accounts/search?q=<handle>&limit=20
```
Returns: `[{id, username, display_name, followers_count}]`

**Add tag:**
```
POST /api/accounts/{id}/tags
Body: {tag: "ai_safety", confidence: 1.0}
```

**Get tags:**
```
GET /api/accounts/{id}/tags
GET /api/tags/{tag}/accounts  (all accounts with this tag)
```

### 2.3 Frontend: Minimal CLI First

Skip the UI initially. Use a Python script to:
1. Load holdout_clusters.json
2. For training accounts: resolve handles → account_ids, add tags
3. Leave holdout accounts untagged

---

## Phase 3: Label Propagation (Simplest Version)

### 3.1 Algorithm: Semi-Supervised Label Spreading

Use sklearn's `LabelSpreading` on the spectral embedding space:

```python
from sklearn.semi_supervised import LabelSpreading

# Prepare labels: -1 for unlabeled, 0+ for tagged clusters
y = np.full(n_nodes, -1)
for i, node_id in enumerate(node_ids):
    if node_id in tagged_accounts["ai_safety"]:
        y[i] = 0
    elif node_id in tagged_accounts["rationality"]:
        y[i] = 1
    # etc.

# Fit on spectral embedding
model = LabelSpreading(kernel='rbf', alpha=0.2)
model.fit(embedding, y)

# Get soft probabilities for ALL nodes
probabilities = model.label_distributions_
```

### 3.2 Graph-Based Alternative

Use the actual adjacency matrix instead of embedding distances:

```python
from sklearn.semi_supervised import LabelSpreading

# Build affinity from adjacency (normalized)
model = LabelSpreading(kernel='precomputed', alpha=0.2)
model.fit(normalized_adjacency, y)
```

### 3.3 Output

For each node, we get a probability vector over clusters. This becomes our "soft membership".

---

## Phase 4: Validation Metrics

### 4.1 Holdout Accuracy

For holdout accounts in cluster C:
- Get their predicted probability for cluster C
- Compute metrics:

```python
def evaluate_holdout(cluster_name, holdout_ids, probabilities, cluster_idx):
    holdout_probs = [probabilities[node_to_idx[id]][cluster_idx] for id in holdout_ids]
    
    return {
        "mean_prob": np.mean(holdout_probs),
        "min_prob": np.min(holdout_probs),
        "top_cluster_accuracy": sum(
            np.argmax(probabilities[node_to_idx[id]]) == cluster_idx 
            for id in holdout_ids
        ) / len(holdout_ids)
    }
```

### 4.2 Success Criteria

**Good result:** Holdout accounts for cluster C have:
- Mean probability > 0.5 for cluster C
- Top-cluster accuracy > 60% (their highest prob is the correct cluster)

**Excellent result:**
- Mean probability > 0.7
- Top-cluster accuracy > 80%

### 4.3 Confusion Analysis

For each holdout account, show:
- True cluster
- Top-3 predicted clusters with probabilities
- Identify systematic confusions (e.g., AI Safety ↔ Rationality)

---

## Phase 5: Implementation Roadmap

### Week 1: Holdout Setup
1. [ ] Create `holdout_clusters.json` with 4-5 clusters
2. [ ] Add `account_tags` table to clusters.db
3. [ ] Write script to resolve handles → account_ids
4. [ ] Verify all holdout accounts exist in the graph

### Week 2: Basic Propagation
1. [ ] Implement label spreading on spectral embedding
2. [ ] Tag training accounts (from holdout file)
3. [ ] Run propagation
4. [ ] Compute holdout metrics

### Week 3: Iteration
1. [ ] Analyze confusion patterns
2. [ ] Try graph-based propagation (adjacency kernel)
3. [ ] Experiment with different alpha values
4. [ ] Add more training accounts if needed

---

## File Structure

```
tpot-analyzer/
├── data/
│   ├── holdout_clusters.json    # Ground truth
│   ├── clusters.db              # Existing + new tags table
│   └── validation_results/      # New directory
│       ├── run_001.json
│       └── run_002.json
├── scripts/
│   ├── setup_holdout.py         # Load JSON, create tags
│   ├── run_propagation.py       # Execute label spreading
│   └── evaluate_holdout.py      # Compute metrics
└── docs/
    └── HOLDOUT_VALIDATION_PLAN.md  # This file
```

---

## Quick Start Commands

```bash
# 1. Edit holdout file (manually populate)
vim data/holdout_clusters.json

# 2. Setup tags from training accounts
python scripts/setup_holdout.py --mode train

# 3. Run propagation
python scripts/run_propagation.py --output data/validation_results/run_001.json

# 4. Evaluate
python scripts/evaluate_holdout.py data/validation_results/run_001.json
```

---

## Notes on Edge Cases

1. **Handle → ID resolution failures**: Some handles may not be in the graph. Log and skip.

2. **Overlapping clusters**: Some accounts genuinely belong to multiple clusters (e.g., AI Safety AND Rationality). Consider:
   - Multi-label evaluation (does probability for BOTH correct clusters exceed threshold?)
   - Or explicitly mark these as "boundary" nodes, excluded from strict accuracy

3. **Sparse training**: With only 3-5 training samples per cluster, propagation may be weak. If results are poor, first try increasing training set before changing algorithm.

4. **Graph structure vs embedding**: If embedding-based propagation fails but you believe structure should work, try graph-based kernel. They capture different signals.
