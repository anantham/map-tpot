# Ego Network Optimization Plan

## Problem
- Current `/api/graph-data` takes 4-16 seconds to serialize all 70,838 nodes
- User just wants to see their immediate network + top recommendations
- No need to load entire graph upfront

## Solution: Lightweight Ego Network Endpoint

### New Endpoint: `/api/ego-network`

**Request:**
```json
{
  "username": "your_twitter_handle",
  "depth": 2,  // How many hops out
  "top_recommendations": 20  // How many recommendations to include
}
```

**Response:**
```json
{
  "ego": {
    "username": "...",
    "display_name": "...",
    // Full profile data
  },
  "network": {
    "nodes": {
      // Only nodes in ego network (your follows + their follows up to depth)
      // Plus top 20 recommendations
    },
    "edges": [
      // Only edges between these nodes
    ]
  },
  "recommendations": [
    // Top 20 scored recommendations with explanations
  ],
  "stats": {
    "total_nodes": 150,  // Much smaller!
    "your_following": 100,
    "recommendations": 20,
    "load_time_ms": 250  // Much faster!
  }
}
```

### Benefits
1. **Fast initial load** - Only serialize ~150-500 nodes instead of 70K
2. **Progressive enhancement** - Can lazy-load more as user explores
3. **Clear distinction** - Your account is the "ego" node
4. **Immediate value** - See your network + recommendations right away

### Implementation Steps
1. Add `/api/ego-network` endpoint
2. Extract k-hop subgraph around ego node
3. Run discovery algorithm for top recommendations
4. Serialize only the relevant subset
5. Update Discovery.jsx to use this endpoint first
6. Add "Load Full Graph" button if user wants more

### Estimated Performance
- Current: 4-16 seconds for full graph
- New: 200-500ms for ego network
- **30-80x faster!**
