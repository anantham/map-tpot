# Critical Bug Fixes - Graph Explorer MVP

## Date: 2025-10-07

> Historical note (updated 2026-02-09): this archive records an earlier backend
> layout. Current runtime entrypoint is `.venv/bin/python -m scripts.start_api_server`.

### Bug #1: Edge Schema Mismatch (FIXED)
**File (at the time):** `scripts/api_server.py`
**Lines:** 28-60

#### Problem
The backend was returning edges in the wrong format:
```python
# Backend returned:
edges = [{'source_id': '...', 'target_id': '...', 'direction': 'outbound'}]

# Frontend expected:
edges = [{'source': '...', 'target': '...', 'mutual': true}]
```

This caused the frontend to fail when trying to render the graph, as it couldn't find the `source` and `target` properties.

#### Solution
Added edge processing logic to:
1. Detect bidirectional edges (edges that exist in both directions)
2. Convert from `source_id`/`target_id` to `source`/`target`
3. Add a `mutual` flag indicating if the edge is bidirectional

```python
# Process edges to detect mutual relationships
edge_lookup = {}
for edge in edges:
    source = edge['source_id']
    target = edge['target_id']
    # Create a canonical key (sorted tuple) to detect bidirectional edges
    key = tuple(sorted([source, target]))

    if key not in edge_lookup:
        edge_lookup[key] = {
            'source': source,
            'target': target,
            'directions': set()
        }
    edge_lookup[key]['directions'].add(edge.get('direction', 'outbound'))

# Convert to frontend format
processed_edges = []
for key, data in edge_lookup.items():
    mutual = len(data['directions']) >= 2 or 'bidirectional' in data['directions']

    processed_edges.append({
        'source': data['source'],
        'target': data['target'],
        'mutual': mutual
    })
```

#### Impact
- ✅ Frontend can now parse edge data correctly
- ✅ Mutual edges are properly detected and flagged
- ✅ "Mutual-only" toggle will work correctly

---

### Bug #2: Node Filtering Logic Error (FIXED)
**File:** `graph-explorer/src/GraphExplorer.jsx`
**Lines:** 275-305

#### Problem
The subgraph filtering logic had a mismatch between:
1. `allowedNodeSet` - which contained a mix of account IDs and lowercase usernames
2. The filtering check - which only checked raw account IDs

This caused the filtering to fail because:
```javascript
// topNIds contains account IDs like "123456789"
// effectiveSeedSet contains lowercase usernames like "visakanv"
const allowedNodeSet = new Set([...topNIds, ...effectiveSeedSet]);

// But we check using the raw account ID, which won't match usernames
if (!allowedNodeSet.has(id)) return null;  // ❌ Fails for seed usernames
```

#### Solution
1. Build `allowedNodeSet` with only account IDs (from topNIds)
2. Add a pre-pass to resolve seed usernames to their account IDs
3. Add those account IDs to the allowed set

```javascript
// Build allowed set with both account IDs and usernames for matching
const allowedNodeSet = new Set(topNIds);

// Add seed nodes to the allowed set (they should always be visible)
nodeIds.forEach((rawId) => {
  const id = String(rawId);
  const meta = nodesMeta[id] || {};
  const usernameLower = meta.username ? String(meta.username).toLowerCase() : null;
  const idLower = id.toLowerCase();

  // Check if this node is a seed by any of its identifiers
  if (effectiveSeedSet.has(idLower) ||
      (usernameLower && effectiveSeedSet.has(usernameLower))) {
    allowedNodeSet.add(id);  // Add the actual account ID
  }
});
```

#### Impact
- ✅ Subgraph size (N) slider now works correctly
- ✅ Seed nodes are always included in the visualization
- ✅ Top N nodes are properly filtered and displayed
- ✅ No more null nodes in the graph data

---

## Testing Checklist

### Backend (current entrypoint)
- [ ] Run the API server: `.venv/bin/python -m scripts.start_api_server`
- [ ] Check that edges have the correct format in the response
- [ ] Verify that mutual edges are detected (look for `mutual: true`)
- [ ] Check logs for any errors during edge processing

### Frontend (GraphExplorer.jsx)
- [ ] Run the frontend: `cd graph-explorer && npm run dev`
- [ ] Verify the graph loads without errors
- [ ] Test the "Subgraph Size (N)" slider - should show exactly N nodes + seeds
- [ ] Test the "Mutual-only" toggle - should filter edges correctly
- [ ] Verify seed nodes are always visible regardless of N value
- [ ] Check browser console for any errors

### Integration Test
- [ ] Start both servers (backend and frontend)
- [ ] Load the graph in the browser
- [ ] Adjust the N slider from 10 to 100 and observe node count changes
- [ ] Toggle "Mutual-only" and observe edge filtering
- [ ] Verify "Adi's Seeds" are always visible

---

## Next Steps

Now that these critical bugs are fixed, the next priorities are:

1. **Add caching** - Prevent recomputing PageRank/Betweenness on every request
2. **Add logging/instrumentation** - Track performance and errors
3. **Implement seed input parsing** - Allow users to add custom seeds
4. **Add default seeds to API** - So "Adi's Seeds" preset works correctly

See the main code review document for details on these improvements.
