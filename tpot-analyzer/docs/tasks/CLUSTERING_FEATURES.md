# CODEX TASK: Clustering Math Integration & Advanced Features

**Created**: 2024-12-17  
**Priority**: High  
**Estimated Effort**: 8-12 hours  
**Dependencies**: `src/graph/hierarchy/math_foundations.py` (already implemented)

---

## Context

We've refactored the clustering math to be more principled:

1. **Information-Theoretic Budget** - Based on Miller's Law (human working memory ~7±2 items)
2. **MDL-Based Expansion** - Minimum Description Length principle for split decisions  
3. **Stress-Minimizing Layout** - SMACOF algorithm preserves cluster distances better than PCA

The backend (`src/graph/hierarchy/builder.py`) now supports these via new parameters:
- `budget_preference: float` (0.0=overview, 1.0=detail) 
- `use_mdl_expansion: bool` (default True)
- `use_stress_layout: bool` (default True)

**This task covers**: Frontend integration, soft membership, active learning infrastructure, and documentation.

---

## Task 1: Frontend Budget Slider

### 1.1 Add Budget Preference to ClusterView State

**File**: `graph-explorer/src/ClusterView.jsx`

Add state for budget preference:

```javascript
// Near other state declarations
const [budgetPreference, setBudgetPreference] = useState(0.5);
```

### 1.2 Create Budget Slider Component

**File**: `graph-explorer/src/components/BudgetSlider.jsx` (new file)

```javascript
import React from 'react';

/**
 * Budget preference slider based on information theory.
 * 
 * The budget determines how many clusters to show simultaneously.
 * Based on Miller's Law: humans can process ~7±2 chunks of information.
 * 
 * 0.0 = Overview mode (fewer, larger clusters)
 * 0.5 = Balanced (default)
 * 1.0 = Detail mode (more, smaller clusters)
 */
export function BudgetSlider({ value, onChange, disabled = false }) {
  const labels = {
    0: 'Overview',
    0.5: 'Balanced', 
    1: 'Detail'
  };
  
  // Compute approximate cluster count for display
  // Formula mirrors backend: base ~22, range 11-44
  const estimatedClusters = Math.round(11 + 33 * value);
  
  return (
    <div className="budget-slider">
      <label className="budget-slider__label">
        Visual Density
        <span className="budget-slider__estimate">
          (~{estimatedClusters} clusters)
        </span>
      </label>
      <div className="budget-slider__track-container">
        <input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          disabled={disabled}
          className="budget-slider__input"
        />
        <div className="budget-slider__labels">
          <span>Overview</span>
          <span>Balanced</span>
          <span>Detail</span>
        </div>
      </div>
      <p className="budget-slider__help">
        Based on cognitive load research. Lower = see big picture, Higher = see fine detail.
      </p>
    </div>
  );
}

export default BudgetSlider;
```

### 1.3 Add Styles

**File**: `graph-explorer/src/components/BudgetSlider.css` (new file)

```css
.budget-slider {
  padding: 12px 16px;
  background: var(--surface-secondary, #f5f5f5);
  border-radius: 8px;
  margin-bottom: 16px;
}

.budget-slider__label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
  margin-bottom: 8px;
}

.budget-slider__estimate {
  font-weight: 400;
  color: var(--text-secondary, #666);
  font-size: 0.9em;
}

.budget-slider__track-container {
  position: relative;
}

.budget-slider__input {
  width: 100%;
  height: 8px;
  -webkit-appearance: none;
  background: linear-gradient(to right, 
    var(--color-primary-light, #b3d4fc) 0%, 
    var(--color-primary, #4a90d9) 50%,
    var(--color-primary-dark, #2d5a8a) 100%
  );
  border-radius: 4px;
  outline: none;
}

.budget-slider__input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  background: white;
  border: 2px solid var(--color-primary, #4a90d9);
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.budget-slider__labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.75em;
  color: var(--text-secondary, #888);
  margin-top: 4px;
}

.budget-slider__help {
  font-size: 0.8em;
  color: var(--text-tertiary, #999);
  margin-top: 8px;
  margin-bottom: 0;
}
```

### 1.4 Integrate into ClusterView

**File**: `graph-explorer/src/ClusterView.jsx`

Add import and usage:

```javascript
import { BudgetSlider } from './components/BudgetSlider';
import './components/BudgetSlider.css';

// In the sidebar/controls area:
<BudgetSlider
  value={budgetPreference}
  onChange={(val) => {
    setBudgetPreference(val);
    // Trigger refetch with new preference
    fetchClusters({ budgetPreference: val });
  }}
  disabled={loading}
/>
```

### 1.5 Update API Call

**File**: `graph-explorer/src/ClusterView.jsx`

Update the fetch function to include budget_preference:

```javascript
const fetchClusters = async (options = {}) => {
  const params = new URLSearchParams({
    n: options.n || 15,
    budget_preference: options.budgetPreference ?? budgetPreference,
    // ... other params
  });
  
  const response = await fetch(`/api/clusters?${params}`);
  // ...
};
```

### 1.6 Update Backend Route

**File**: `src/api/cluster_routes.py`

Add budget_preference parameter:

```python
@bp.route('/clusters')
def get_clusters():
    # ... existing code ...
    
    budget_preference = request.args.get('budget_preference', 0.5, type=float)
    budget_preference = max(0.0, min(1.0, budget_preference))  # Clamp to [0, 1]
    
    # Pass to build_hierarchical_view
    view_data = build_hierarchical_view(
        # ... existing params ...
        budget_preference=budget_preference,
        use_mdl_expansion=True,
        use_stress_layout=True,
    )
```

### Verification

```bash
# Backend test
curl "http://localhost:5000/api/clusters?budget_preference=0.2" | jq '.meta.budget'
curl "http://localhost:5000/api/clusters?budget_preference=0.8" | jq '.meta.budget'
# Should show different budget values

# Frontend test
# Open ClusterView, adjust slider, verify cluster count changes
```

---

## Task 2: Soft Membership Display

Soft membership allows nodes to belong to multiple clusters with different probabilities, based on distance in spectral embedding space.

### 2.1 Backend: Compute Soft Memberships

**File**: `src/graph/hierarchy/soft_membership.py` (new file)

```python
"""Soft cluster membership via spectral embedding distances."""
from __future__ import annotations

import numpy as np
from typing import Dict, List, Tuple, Optional
from scipy.spatial.distance import cdist


def compute_soft_memberships(
    node_embeddings: np.ndarray,  # (n_nodes, n_dims)
    cluster_centroids: np.ndarray,  # (n_clusters, n_dims)
    cluster_ids: List[str],
    temperature: float = 1.0,
) -> Dict[int, List[Tuple[str, float]]]:
    """Compute soft membership probabilities for each node.
    
    Uses softmax over negative distances to cluster centroids.
    Temperature controls sharpness: lower = more decisive, higher = more spread.
    
    Args:
        node_embeddings: Node positions in spectral space
        cluster_centroids: Cluster centroid positions
        cluster_ids: String IDs for each cluster
        temperature: Softmax temperature (default 1.0)
    
    Returns:
        Dict mapping node_index -> list of (cluster_id, probability) tuples
        Only includes clusters with probability > 0.05
    """
    # Compute distances from each node to each centroid
    distances = cdist(node_embeddings, cluster_centroids, metric='euclidean')
    
    # Convert to similarities via softmax
    # Negative distance = higher similarity
    logits = -distances / temperature
    
    # Softmax per row
    exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
    probabilities = exp_logits / exp_logits.sum(axis=1, keepdims=True)
    
    # Build result dict, filtering low-probability memberships
    result = {}
    threshold = 0.05
    
    for node_idx in range(len(node_embeddings)):
        memberships = []
        for cluster_idx, prob in enumerate(probabilities[node_idx]):
            if prob >= threshold:
                memberships.append((cluster_ids[cluster_idx], float(prob)))
        
        # Sort by probability descending
        memberships.sort(key=lambda x: x[1], reverse=True)
        result[node_idx] = memberships
    
    return result


def get_boundary_nodes(
    soft_memberships: Dict[int, List[Tuple[str, float]]],
    entropy_threshold: float = 0.8,
) -> List[int]:
    """Find nodes that sit on cluster boundaries (high membership entropy).
    
    Boundary nodes have significant probability mass in multiple clusters,
    making them interesting for exploration and potential misclassification review.
    
    Args:
        soft_memberships: Output from compute_soft_memberships
        entropy_threshold: Normalized entropy threshold (0-1) for "boundary" status
    
    Returns:
        List of node indices with high membership entropy
    """
    boundary_nodes = []
    
    for node_idx, memberships in soft_memberships.items():
        if len(memberships) <= 1:
            continue
        
        probs = np.array([p for _, p in memberships])
        
        # Compute normalized entropy
        entropy = -np.sum(probs * np.log(probs + 1e-10))
        max_entropy = np.log(len(probs))  # Uniform distribution
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
        
        if normalized_entropy >= entropy_threshold:
            boundary_nodes.append(node_idx)
    
    return boundary_nodes


def format_membership_for_api(
    soft_memberships: Dict[int, List[Tuple[str, float]]],
    node_ids: np.ndarray,
    top_k: int = 3,
) -> Dict[str, List[Dict]]:
    """Format soft memberships for API response.
    
    Args:
        soft_memberships: Output from compute_soft_memberships
        node_ids: Array of node ID strings
        top_k: Maximum memberships to return per node
    
    Returns:
        Dict mapping node_id -> list of {cluster_id, probability}
    """
    result = {}
    for node_idx, memberships in soft_memberships.items():
        node_id = str(node_ids[node_idx])
        result[node_id] = [
            {"cluster_id": cid, "probability": round(prob, 3)}
            for cid, prob in memberships[:top_k]
        ]
    return result
```

### 2.2 Add Soft Membership to API Response

**File**: `src/api/cluster_routes.py`

```python
from src.graph.hierarchy.soft_membership import (
    compute_soft_memberships,
    get_boundary_nodes,
    format_membership_for_api,
)

@bp.route('/clusters')
def get_clusters():
    # ... existing code ...
    
    # Optionally include soft memberships
    include_soft = request.args.get('include_soft_membership', 'false').lower() == 'true'
    
    response_data = {
        "clusters": [...],
        "edges": [...],
        "positions": {...},
        "meta": {...},
    }
    
    if include_soft:
        # Get embeddings and centroids from cache/computation
        soft_memberships = compute_soft_memberships(
            node_embeddings=spectral_result.embedding,
            cluster_centroids=np.stack([c.centroid for c in view_data.clusters]),
            cluster_ids=[c.id for c in view_data.clusters],
            temperature=1.0,
        )
        
        boundary_nodes = get_boundary_nodes(soft_memberships)
        
        response_data["soft_memberships"] = format_membership_for_api(
            soft_memberships, 
            spectral_result.node_ids,
            top_k=3,
        )
        response_data["boundary_node_ids"] = [
            str(spectral_result.node_ids[i]) for i in boundary_nodes
        ]
    
    return jsonify(response_data)
```

### 2.3 Frontend: Display Boundary Indicator

**File**: `graph-explorer/src/ClusterCanvas.jsx`

Add visual indicator for boundary nodes (nodes near cluster edges):

```javascript
// When rendering a node that's in boundary_node_ids
const isBoundary = boundaryNodeIds?.includes(nodeId);

// Add a subtle glow or different border for boundary nodes
const nodeStyle = {
  ...baseStyle,
  boxShadow: isBoundary ? '0 0 8px rgba(255, 165, 0, 0.6)' : 'none',
  borderStyle: isBoundary ? 'dashed' : 'solid',
};
```

### 2.4 Frontend: Membership Tooltip

When hovering over a node, show its cluster memberships:

```javascript
// In tooltip component
{softMemberships[hoveredNodeId] && (
  <div className="membership-breakdown">
    <h4>Cluster Membership</h4>
    {softMemberships[hoveredNodeId].map(({ cluster_id, probability }) => (
      <div key={cluster_id} className="membership-bar">
        <span className="cluster-name">{clusterLabels[cluster_id]}</span>
        <div className="probability-bar" style={{ width: `${probability * 100}%` }} />
        <span className="probability-value">{(probability * 100).toFixed(0)}%</span>
      </div>
    ))}
  </div>
)}
```

### Verification

```bash
# Test soft membership API
curl "http://localhost:5000/api/clusters?include_soft_membership=true" | jq '.boundary_node_ids | length'
# Should return some boundary nodes

# Test specific node membership
curl "http://localhost:5000/api/clusters?include_soft_membership=true" | jq '.soft_memberships | to_entries | .[0]'
# Should show node with multiple cluster probabilities
```

---

## Task 3: Active Learning Infrastructure

Active learning allows users to provide feedback that improves clustering over time.

### 3.1 User Feedback Schema

**File**: `src/db/schema_feedback.sql` (new file)

```sql
-- User feedback on cluster assignments
CREATE TABLE IF NOT EXISTS cluster_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- What kind of feedback
    feedback_type TEXT NOT NULL,  -- 'merge', 'split', 'move_node', 'label'
    
    -- Context
    node_id TEXT,                 -- For move_node feedback
    source_cluster_id TEXT,       -- Original cluster
    target_cluster_id TEXT,       -- Destination cluster (for move/merge)
    
    -- User's reasoning (optional)
    reason TEXT,
    
    -- Confidence in feedback (0-1)
    confidence REAL DEFAULT 1.0,
    
    -- Has this been incorporated into model?
    applied BOOLEAN DEFAULT FALSE,
    applied_at TIMESTAMP
);

-- Index for finding unapplied feedback
CREATE INDEX IF NOT EXISTS idx_feedback_unapplied 
ON cluster_feedback(applied, created_at);

-- Cluster labels (user-provided names)
CREATE TABLE IF NOT EXISTS cluster_labels (
    cluster_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 Feedback API

**File**: `src/api/feedback_routes.py` (new file)

```python
"""API routes for cluster feedback and active learning."""
from flask import Blueprint, request, jsonify
import sqlite3
from datetime import datetime

bp = Blueprint('feedback', __name__, url_prefix='/api/feedback')


def get_db():
    """Get database connection."""
    # Use your existing db connection pattern
    from src.db.connection import get_connection
    return get_connection()


@bp.route('/submit', methods=['POST'])
def submit_feedback():
    """Submit user feedback on clustering.
    
    Request body:
    {
        "feedback_type": "move_node" | "merge" | "split" | "label",
        "node_id": "optional - for move_node",
        "source_cluster_id": "d_123",
        "target_cluster_id": "d_456 - for move/merge",
        "reason": "optional explanation",
        "confidence": 0.9
    }
    """
    data = request.json
    
    required = ['feedback_type', 'source_cluster_id']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    feedback_type = data['feedback_type']
    valid_types = ['move_node', 'merge', 'split', 'label']
    if feedback_type not in valid_types:
        return jsonify({"error": f"Invalid feedback_type. Must be one of: {valid_types}"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO cluster_feedback 
        (feedback_type, node_id, source_cluster_id, target_cluster_id, reason, confidence)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        feedback_type,
        data.get('node_id'),
        data['source_cluster_id'],
        data.get('target_cluster_id'),
        data.get('reason'),
        data.get('confidence', 1.0),
    ))
    
    conn.commit()
    feedback_id = cursor.lastrowid
    
    return jsonify({
        "success": True,
        "feedback_id": feedback_id,
        "message": "Feedback recorded. It will be incorporated in the next model update."
    })


@bp.route('/pending', methods=['GET'])
def get_pending_feedback():
    """Get all feedback that hasn't been applied yet."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, feedback_type, node_id, source_cluster_id, target_cluster_id, 
               reason, confidence, created_at
        FROM cluster_feedback
        WHERE applied = FALSE
        ORDER BY created_at DESC
    """)
    
    rows = cursor.fetchall()
    feedback = [
        {
            "id": row[0],
            "feedback_type": row[1],
            "node_id": row[2],
            "source_cluster_id": row[3],
            "target_cluster_id": row[4],
            "reason": row[5],
            "confidence": row[6],
            "created_at": row[7],
        }
        for row in rows
    ]
    
    return jsonify({"pending_feedback": feedback, "count": len(feedback)})


@bp.route('/label', methods=['POST'])
def set_cluster_label():
    """Set or update a cluster's user-defined label.
    
    Request body:
    {
        "cluster_id": "d_123",
        "label": "Jhana Bros"
    }
    """
    data = request.json
    
    if not data.get('cluster_id') or not data.get('label'):
        return jsonify({"error": "cluster_id and label are required"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO cluster_labels (cluster_id, label, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cluster_id) DO UPDATE SET
            label = excluded.label,
            updated_at = excluded.updated_at
    """, (data['cluster_id'], data['label'], datetime.utcnow().isoformat()))
    
    conn.commit()
    
    return jsonify({"success": True, "cluster_id": data['cluster_id'], "label": data['label']})


@bp.route('/labels', methods=['GET'])
def get_all_labels():
    """Get all user-defined cluster labels."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT cluster_id, label FROM cluster_labels")
    rows = cursor.fetchall()
    
    labels = {row[0]: row[1] for row in rows}
    return jsonify({"labels": labels})
```

### 3.3 Register Blueprint

**File**: `src/api/server.py`

```python
from src.api.feedback_routes import bp as feedback_bp

app.register_blueprint(feedback_bp)
```

### 3.4 Frontend: Feedback UI

**File**: `graph-explorer/src/components/ClusterFeedback.jsx` (new file)

```javascript
import React, { useState } from 'react';

/**
 * Feedback panel for cluster corrections.
 * Appears when user right-clicks a cluster or selects "Give Feedback".
 */
export function ClusterFeedback({ 
  clusterId, 
  clusterLabel,
  allClusters,
  onClose,
  onSubmit 
}) {
  const [feedbackType, setFeedbackType] = useState('label');
  const [newLabel, setNewLabel] = useState(clusterLabel || '');
  const [targetCluster, setTargetCluster] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    
    const payload = {
      feedback_type: feedbackType,
      source_cluster_id: clusterId,
      reason: reason || undefined,
    };
    
    if (feedbackType === 'label') {
      // Use separate label endpoint
      await fetch('/api/feedback/label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cluster_id: clusterId, label: newLabel }),
      });
    } else {
      if (feedbackType === 'merge' && targetCluster) {
        payload.target_cluster_id = targetCluster;
      }
      
      await fetch('/api/feedback/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }
    
    setSubmitting(false);
    onSubmit?.();
    onClose();
  };

  return (
    <div className="cluster-feedback-panel">
      <h3>Improve Clustering</h3>
      <p className="feedback-cluster-name">Cluster: {clusterLabel || clusterId}</p>
      
      <div className="feedback-type-selector">
        <label>
          <input
            type="radio"
            value="label"
            checked={feedbackType === 'label'}
            onChange={(e) => setFeedbackType(e.target.value)}
          />
          Rename this cluster
        </label>
        <label>
          <input
            type="radio"
            value="merge"
            checked={feedbackType === 'merge'}
            onChange={(e) => setFeedbackType(e.target.value)}
          />
          Merge with another cluster
        </label>
        <label>
          <input
            type="radio"
            value="split"
            checked={feedbackType === 'split'}
            onChange={(e) => setFeedbackType(e.target.value)}
          />
          This cluster should be split
        </label>
      </div>
      
      {feedbackType === 'label' && (
        <input
          type="text"
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
          placeholder="Enter cluster name..."
          className="feedback-input"
        />
      )}
      
      {feedbackType === 'merge' && (
        <select 
          value={targetCluster} 
          onChange={(e) => setTargetCluster(e.target.value)}
          className="feedback-select"
        >
          <option value="">Select cluster to merge with...</option>
          {allClusters
            .filter(c => c.id !== clusterId)
            .map(c => (
              <option key={c.id} value={c.id}>{c.label || c.id}</option>
            ))}
        </select>
      )}
      
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Why? (optional but helpful)"
        className="feedback-reason"
        rows={2}
      />
      
      <div className="feedback-actions">
        <button onClick={onClose} disabled={submitting}>Cancel</button>
        <button onClick={handleSubmit} disabled={submitting} className="primary">
          {submitting ? 'Submitting...' : 'Submit Feedback'}
        </button>
      </div>
    </div>
  );
}
```

### Verification

```bash
# Test feedback submission
curl -X POST http://localhost:5000/api/feedback/submit \
  -H "Content-Type: application/json" \
  -d '{"feedback_type": "merge", "source_cluster_id": "d_100", "target_cluster_id": "d_101", "reason": "Same community"}'

# Test label setting
curl -X POST http://localhost:5000/api/feedback/label \
  -H "Content-Type: application/json" \
  -d '{"cluster_id": "d_100", "label": "Jhana Bros"}'

# Get pending feedback
curl http://localhost:5000/api/feedback/pending
```

---

## Task 4: Incorporate Feedback into Clustering

### 4.1 Constraint-Based Clustering

**File**: `src/graph/hierarchy/constrained_clustering.py` (new file)

```python
"""Apply user feedback as constraints during clustering."""
from __future__ import annotations

import numpy as np
from typing import Dict, List, Set, Tuple
from scipy.cluster.hierarchy import linkage, fcluster


def apply_must_link_constraints(
    embedding: np.ndarray,
    must_link_pairs: List[Tuple[int, int]],
    strength: float = 0.5,
) -> np.ndarray:
    """Modify embedding to pull must-link nodes closer.
    
    Used when user says "these should be in the same cluster".
    
    Args:
        embedding: (n_nodes, n_dims) spectral embedding
        must_link_pairs: List of (node_i, node_j) that should be together
        strength: How much to pull them together (0-1)
    
    Returns:
        Modified embedding with must-link pairs closer
    """
    modified = embedding.copy()
    
    for i, j in must_link_pairs:
        # Move both nodes toward their midpoint
        midpoint = (modified[i] + modified[j]) / 2
        modified[i] = modified[i] * (1 - strength) + midpoint * strength
        modified[j] = modified[j] * (1 - strength) + midpoint * strength
    
    return modified


def apply_cannot_link_constraints(
    embedding: np.ndarray,
    cannot_link_pairs: List[Tuple[int, int]],
    strength: float = 0.5,
) -> np.ndarray:
    """Modify embedding to push cannot-link nodes apart.
    
    Used when user says "these should NOT be in the same cluster".
    
    Args:
        embedding: (n_nodes, n_dims) spectral embedding
        cannot_link_pairs: List of (node_i, node_j) that should be separate
        strength: How much to push them apart (0-1)
    
    Returns:
        Modified embedding with cannot-link pairs further apart
    """
    modified = embedding.copy()
    
    for i, j in cannot_link_pairs:
        # Push nodes away from each other
        direction = modified[i] - modified[j]
        norm = np.linalg.norm(direction)
        if norm > 1e-10:
            direction = direction / norm
            # Push both nodes in opposite directions
            modified[i] = modified[i] + direction * strength
            modified[j] = modified[j] - direction * strength
    
    return modified


def feedback_to_constraints(
    pending_feedback: List[Dict],
    node_id_to_idx: Dict[str, int],
    cluster_to_nodes: Dict[str, Set[int]],
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Convert user feedback to must-link and cannot-link constraints.
    
    Args:
        pending_feedback: List of feedback records from database
        node_id_to_idx: Mapping from node_id to embedding index
        cluster_to_nodes: Mapping from cluster_id to set of node indices
    
    Returns:
        (must_link_pairs, cannot_link_pairs)
    """
    must_link = []
    cannot_link = []
    
    for fb in pending_feedback:
        fb_type = fb['feedback_type']
        
        if fb_type == 'merge':
            # All nodes in source and target should be linked
            source_nodes = cluster_to_nodes.get(fb['source_cluster_id'], set())
            target_nodes = cluster_to_nodes.get(fb['target_cluster_id'], set())
            
            # Create must-link between representative nodes
            if source_nodes and target_nodes:
                # Link centroids (or first nodes) as representatives
                src_rep = next(iter(source_nodes))
                tgt_rep = next(iter(target_nodes))
                must_link.append((src_rep, tgt_rep))
        
        elif fb_type == 'split':
            # This is harder - we don't know how to split
            # Mark as "needs manual review" or use boundary detection
            pass
        
        elif fb_type == 'move_node':
            # Node should not be with source, should be with target
            node_idx = node_id_to_idx.get(fb['node_id'])
            if node_idx is not None:
                # Cannot-link with source cluster members
                source_nodes = cluster_to_nodes.get(fb['source_cluster_id'], set())
                for src_node in source_nodes:
                    if src_node != node_idx:
                        cannot_link.append((node_idx, src_node))
                
                # Must-link with target cluster
                target_nodes = cluster_to_nodes.get(fb['target_cluster_id'], set())
                if target_nodes:
                    tgt_rep = next(iter(target_nodes))
                    must_link.append((node_idx, tgt_rep))
    
    return must_link, cannot_link
```

### 4.2 Batch Feedback Application Script

**File**: `scripts/apply_feedback.py` (new file)

```python
#!/usr/bin/env python3
"""Apply pending user feedback to update clustering.

Run periodically (e.g., nightly) or manually after collecting feedback.

Usage:
    python scripts/apply_feedback.py [--dry-run]
"""
import argparse
import logging
from pathlib import Path

import numpy as np

from src.db.connection import get_connection
from src.graph.spectral import load_spectral_result, save_spectral_result
from src.graph.hierarchy.constrained_clustering import (
    apply_must_link_constraints,
    apply_cannot_link_constraints,
    feedback_to_constraints,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Apply user feedback to clustering")
    parser.add_argument('--dry-run', action='store_true', help="Show what would change without applying")
    parser.add_argument('--spectral-path', type=Path, default=Path('data/spectral'), help="Path to spectral data")
    args = parser.parse_args()
    
    # Load pending feedback
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, feedback_type, node_id, source_cluster_id, target_cluster_id, confidence
        FROM cluster_feedback
        WHERE applied = FALSE
        ORDER BY created_at
    """)
    
    feedback_rows = cursor.fetchall()
    if not feedback_rows:
        logger.info("No pending feedback to apply")
        return
    
    logger.info(f"Found {len(feedback_rows)} pending feedback items")
    
    pending_feedback = [
        {
            'id': row[0],
            'feedback_type': row[1],
            'node_id': row[2],
            'source_cluster_id': row[3],
            'target_cluster_id': row[4],
            'confidence': row[5],
        }
        for row in feedback_rows
    ]
    
    # Load current spectral result
    spectral_result = load_spectral_result(args.spectral_path / 'current')
    
    # Build mappings
    node_id_to_idx = {nid: i for i, nid in enumerate(spectral_result.node_ids)}
    
    # TODO: Load current cluster assignments to build cluster_to_nodes
    # This requires loading the hierarchical view state
    cluster_to_nodes = {}  # Placeholder
    
    # Convert feedback to constraints
    must_link, cannot_link = feedback_to_constraints(
        pending_feedback, node_id_to_idx, cluster_to_nodes
    )
    
    logger.info(f"Generated {len(must_link)} must-link and {len(cannot_link)} cannot-link constraints")
    
    if args.dry_run:
        logger.info("Dry run - not applying changes")
        return
    
    # Apply constraints to embedding
    modified_embedding = spectral_result.embedding.copy()
    
    if must_link:
        modified_embedding = apply_must_link_constraints(modified_embedding, must_link)
    
    if cannot_link:
        modified_embedding = apply_cannot_link_constraints(modified_embedding, cannot_link)
    
    # Save modified result
    # Note: This creates a new version, preserving the original
    spectral_result.embedding = modified_embedding
    save_spectral_result(spectral_result, args.spectral_path / 'current_constrained')
    
    # Mark feedback as applied
    feedback_ids = [fb['id'] for fb in pending_feedback]
    cursor.executemany(
        "UPDATE cluster_feedback SET applied = TRUE, applied_at = CURRENT_TIMESTAMP WHERE id = ?",
        [(fid,) for fid in feedback_ids]
    )
    conn.commit()
    
    logger.info(f"Applied {len(feedback_ids)} feedback items")


if __name__ == '__main__':
    main()
```

---

## Task 5: Documentation

### 5.1 Create Math Documentation

**File**: `docs/CLUSTERING_MATH.md` (new file)

```markdown
# Hierarchical Clustering: Mathematical Foundations

This document explains the mathematical principles behind TPOT Analyzer's clustering system.

## Overview

The clustering pipeline has four main stages:

1. **Spectral Embedding** - Map graph structure to continuous space
2. **Hierarchical Clustering** - Build dendrogram of nested clusters  
3. **Visual Budget** - Determine how many clusters to show
4. **Interactive Expansion** - Let users drill down with MDL guidance

---

## 1. Spectral Embedding

### Why Spectral?

Spectral methods find structure by analyzing the graph Laplacian's eigenspectrum.
Key insight: **eigenvectors encode community structure**.

### The Normalized Laplacian

Given adjacency matrix A:

```
L_sym = I - D^{-1/2} A D^{-1/2}
```

Where D is the degree matrix.

Properties:
- Eigenvalues in [0, 2]
- First eigenvector is trivial (constant)
- Subsequent eigenvectors reveal cluster structure

### Embedding Construction

1. Compute k smallest eigenvectors of L_sym (excluding trivial)
2. Row-normalize to unit length (points on hypersphere)
3. Result: each node has k-dimensional coordinate

**Why row-normalize?** Puts all nodes on unit sphere, making cosine distance meaningful.

### References
- von Luxburg, U. (2007). "A Tutorial on Spectral Clustering"

---

## 2. Hierarchical Clustering (Ward's Method)

We use Ward's agglomerative clustering on the spectral embedding.

### Ward's Criterion

At each step, merge the pair of clusters that minimizes increase in total within-cluster variance:

```
Δ(A,B) = (n_A * n_B)/(n_A + n_B) * ||μ_A - μ_B||²
```

### Why Ward?
- Produces balanced trees (unlike single/complete linkage)
- Minimizes variance = clusters are "tight"
- Works well with spectral embeddings

### Dendrogram Structure

The linkage matrix encodes the merge history:
- Row i: clusters merged at step i
- Columns: [left_child, right_child, distance, size]

---

## 3. Information-Theoretic Budget

### The Problem

How many clusters should we show? Too few = no insight. Too many = cognitive overload.

### Miller's Law

Humans can hold ~7±2 "chunks" in working memory (Miller, 1956).

For complex visual items with spatial layout, we estimate:
- Base capacity: ~6 items (2.5 bits)
- Spatial bonus: ~3x more with 2D layout (1.5 bits)
- Total: ~22-24 items baseline

### Formula

```python
base_capacity = 2^(MILLER_BITS + SPATIAL_BONUS)  # ~24
adjusted = base_capacity / cluster_entropy        # Simpler clusters = show more
user_scaled = adjusted * (0.5 + 1.5 * preference) # User slider
size_factor = 1 + 0.1 * log10(n_nodes / 100)     # Larger graphs get slightly more
```

### User Adjustment

The `budget_preference` slider maps [0, 1] to:
- 0.0: Overview mode (~11 clusters)
- 0.5: Balanced (~22 clusters)  
- 1.0: Detail mode (~44 clusters)

---

## 4. MDL-Based Expansion

### The Problem

When user clicks "expand", how many children to show?

Old approach: arbitrary `size^0.4` heuristic.
New approach: **Minimum Description Length** (Rissanen, 1978).

### MDL Principle

The best model is the one that **compresses the data most**.

Description Length = bits to encode model + bits to encode data given model

### For Clustering

```
DL(cluster) = DL(centroid) + DL(member deviations from centroid)
```

- Centroid cost: ~0.5 bits per dimension (on unit sphere)
- Deviation cost: `0.5 * log2(2πe * variance)` bits per dimension per member

### Expansion Decision

Split cluster C into children C1, C2 if:

```
DL(C1) + DL(C2) + split_cost < DL(C)
```

Where `split_cost = complexity_penalty * log2(n_children)`.

### Intuition

- High-variance cluster → children likely tighter → SPLIT
- Low-variance cluster → children similar to parent → DON'T SPLIT
- Automatically adapts to local structure

---

## 5. Stress-Minimizing Layout

### The Problem

Given cluster centroids in 30D, how to place them in 2D?

Old approach: PCA (preserves variance).
New approach: MDS (preserves distances).

### Why MDS > PCA?

PCA maximizes variance along principal axes. But for clustering visualization,
we care about **relative distances**: similar clusters should be close.

### Stress Function

```
stress = sqrt(Σ(d_high - d_low)² / Σ d_high²)
```

Where d_high = distances in spectral space, d_low = distances in 2D layout.

### SMACOF Algorithm

Iteratively minimizes stress via majorization:
1. Compute current 2D distances
2. Apply Guttman transform (closed-form improvement)
3. Repeat until convergence

### Result

Layout where spectral neighbors are visual neighbors.

---

## References

1. Miller, G. A. (1956). "The Magical Number Seven, Plus or Minus Two"
2. von Luxburg, U. (2007). "A Tutorial on Spectral Clustering"
3. Ward, J. H. (1963). "Hierarchical Grouping to Optimize an Objective Function"
4. Rissanen, J. (1978). "Modeling by Shortest Data Description"
5. Kruskal, J. B. (1964). "Multidimensional Scaling"
6. de Leeuw, J. (1977). "Applications of Convex Analysis to Multidimensional Scaling"
```

### 5.2 Update README

**File**: `README.md` - Add section:

```markdown
## Clustering Mathematics

TPOT Analyzer uses principled mathematical approaches for clustering:

- **Spectral Embedding**: Normalized Laplacian eigenvectors
- **Information-Theoretic Budget**: Based on Miller's Law (human cognitive limits)
- **MDL-Based Expansion**: Minimum Description Length for split decisions
- **Stress-Minimizing Layout**: SMACOF algorithm for 2D positioning

See [docs/CLUSTERING_MATH.md](docs/CLUSTERING_MATH.md) for details.
```

---

## Task 6: Tests for New Features

### 6.1 Soft Membership Tests

**File**: `tests/test_soft_membership.py` (new file)

```python
"""Tests for soft cluster membership."""
import numpy as np
import pytest

from src.graph.hierarchy.soft_membership import (
    compute_soft_memberships,
    get_boundary_nodes,
    format_membership_for_api,
)


class TestSoftMembership:
    
    def test_node_at_centroid_has_high_primary_membership(self):
        """Node exactly at a centroid should have ~100% membership there."""
        centroids = np.array([[0, 0], [10, 0], [0, 10]])
        node_embeddings = np.array([[0, 0]])  # Exactly at first centroid
        
        memberships = compute_soft_memberships(
            node_embeddings, centroids, ['c0', 'c1', 'c2']
        )
        
        primary = memberships[0][0]
        assert primary[0] == 'c0'
        assert primary[1] > 0.9
    
    def test_node_between_clusters_has_split_membership(self):
        """Node equidistant from two centroids should have ~50/50 split."""
        centroids = np.array([[0, 0], [10, 0]])
        node_embeddings = np.array([[5, 0]])  # Midpoint
        
        memberships = compute_soft_memberships(
            node_embeddings, centroids, ['c0', 'c1']
        )
        
        probs = [p for _, p in memberships[0]]
        assert abs(probs[0] - probs[1]) < 0.1  # Should be roughly equal


class TestBoundaryNodes:
    
    def test_finds_high_entropy_nodes(self):
        """Nodes with split membership should be flagged as boundary."""
        soft_memberships = {
            0: [('c0', 0.9), ('c1', 0.1)],  # Clear assignment
            1: [('c0', 0.5), ('c1', 0.5)],  # Boundary
            2: [('c0', 0.45), ('c1', 0.35), ('c2', 0.2)],  # Also boundary
        }
        
        boundary = get_boundary_nodes(soft_memberships, entropy_threshold=0.7)
        
        assert 0 not in boundary  # Clear assignment
        assert 1 in boundary  # 50/50 split
        assert 2 in boundary  # Split across 3
```

### 6.2 Constrained Clustering Tests

**File**: `tests/test_constrained_clustering.py` (new file)

```python
"""Tests for feedback-based clustering constraints."""
import numpy as np
import pytest

from src.graph.hierarchy.constrained_clustering import (
    apply_must_link_constraints,
    apply_cannot_link_constraints,
)


class TestMustLinkConstraints:
    
    def test_pulls_nodes_closer(self):
        """Must-link constraint should reduce distance between nodes."""
        embedding = np.array([[0, 0], [10, 0], [5, 5]])
        
        dist_before = np.linalg.norm(embedding[0] - embedding[1])
        
        modified = apply_must_link_constraints(
            embedding, must_link_pairs=[(0, 1)], strength=0.5
        )
        
        dist_after = np.linalg.norm(modified[0] - modified[1])
        
        assert dist_after < dist_before


class TestCannotLinkConstraints:
    
    def test_pushes_nodes_apart(self):
        """Cannot-link constraint should increase distance between nodes."""
        embedding = np.array([[0, 0], [1, 0], [5, 5]])
        
        dist_before = np.linalg.norm(embedding[0] - embedding[1])
        
        modified = apply_cannot_link_constraints(
            embedding, cannot_link_pairs=[(0, 1)], strength=0.5
        )
        
        dist_after = np.linalg.norm(modified[0] - modified[1])
        
        assert dist_after > dist_before
```

---

## Verification Checklist

- [ ] Budget slider appears in ClusterView
- [ ] Moving slider changes cluster count
- [ ] API accepts `budget_preference` parameter
- [ ] Soft memberships included when requested
- [ ] Boundary nodes highlighted in UI
- [ ] Feedback submission works
- [ ] Feedback shows in pending list
- [ ] Labels persist across sessions
- [ ] All new tests pass
- [ ] Documentation renders correctly

---

## Notes for Reviewer

1. **Performance**: Soft membership computation is O(n_nodes * n_clusters). May need caching for large graphs.

2. **Constraint strength**: The 0.5 default for must-link/cannot-link is arbitrary. May need tuning.

3. **MDL complexity penalty**: Currently 1.0. Higher values = fewer splits. May need user control.

4. **Temperature for soft membership**: Currently 1.0. Lower = sharper boundaries. May want to expose.

5. **Feedback incorporation**: Currently manual script. Consider automated nightly job.
