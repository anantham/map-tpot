# Graph Explorer Interaction Enhancements

**Date:** 2025-11-08
**Status:** Approved
**Implementation Strategy:** Quick wins (3-4 hours)

## Context

The Graph Explorer currently uses react-force-graph-2d and performs well at the current scale (50-500 nodes). Users need richer interaction capabilities without migrating to a different visualization library. This design focuses on immediate UX improvements while deferring advanced features for post-validation.

## Requirements

### Must-Have (This Phase)
- Node dragging capability
- Zoom-responsive node sizing (nodes get smaller as you zoom in)
- Right-click context menu with basic actions

### Deferred (Post-Validation)
- Node pinning (freeze nodes permanently)
- Custom node shapes (circles vs. squares)
- Edge labels
- Edge color customization
- Visual indicators for frozen/pinned state

## Constraints

- Frontend-only changes (maintain current Flask API)
- No new npm dependencies
- Must preserve existing data pipeline
- Changes isolated to GraphExplorer.jsx

## Design

### Feature 1: Node Dragging

**Implementation:** One-line change
```javascript
// GraphExplorer.jsx:894
enableNodeDrag={true}  // Change from false
```

**Behavior:** react-force-graph-2d's built-in drag temporarily pins nodes during drag, then releases them back to physics simulation.

### Feature 2: Zoom-Responsive Node Sizing

**Problem:** Currently `nodeRelSize={6}` creates fixed-size nodes. Labels already scale with zoom (line 937), but nodes don't.

**Solution:** Replace default node rendering with custom `nodeCanvasObject` that scales inversely with zoom:

```javascript
nodeCanvasObject={(node, ctx, globalScale) => {
  // Calculate zoom-responsive radius
  const radius = 6 / Math.sqrt(globalScale);

  // Get color from extracted helper
  const color = getNodeColor(node);

  // Draw circle
  ctx.beginPath();
  ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();

  // Draw label (existing logic)
  const label = node.display_name || node.username || node.id;
  const fontSize = 12 / globalScale;
  ctx.font = `${fontSize}px sans-serif`;
  ctx.fillStyle = "rgba(248, 250, 252, 0.92)";
  ctx.fillText(label, node.x + radius + 2, node.y + fontSize / 2);
}}
```

**Note:** `Math.sqrt()` damping prevents nodes from becoming too small at high zoom levels.

### Feature 3: Right-Click Context Menu

**State Addition:**
```javascript
const [contextMenu, setContextMenu] = useState(null);
// Shape: { node: NodeObject, x: number, y: number } | null
```

**Event Handler:**
```javascript
onNodeRightClick={(node, event) => {
  event.preventDefault();
  setContextMenu({ node, x: event.clientX, y: event.clientY });
}}
```

**Menu Component:**
```jsx
{contextMenu && (
  <div
    style={{
      position: 'fixed',
      left: contextMenu.x,
      top: contextMenu.y,
      background: 'white',
      border: '1px solid #ccc',
      borderRadius: '4px',
      padding: '8px',
      zIndex: 1000,
      boxShadow: '0 2px 8px rgba(0,0,0,0.15)'
    }}
    onMouseLeave={() => setContextMenu(null)}
  >
    <button onClick={() => {
      navigator.clipboard.writeText(contextMenu.node.username || contextMenu.node.id);
      setContextMenu(null);
    }}>
      Copy @{contextMenu.node.username || contextMenu.node.id}
    </button>
    <button onClick={() => {
      const username = contextMenu.node.username || contextMenu.node.id;
      window.open(`https://twitter.com/${username}`, '_blank');
      setContextMenu(null);
    }}>
      Open on Twitter
    </button>
  </div>
)}
```

## Integration Points

### Extract Node Color Logic

Current `nodeColor` prop (lines 895-901) needs extraction into a helper function for reuse:

```javascript
const getNodeColor = (node) => {
  if (node.id === selectedNodeId) return COLORS.selectedNode;
  if (selectedNeighbors.has(node.id)) return COLORS.neighborNode;
  if (node.isSeed) return COLORS.seedNode;
  if (node.shadow) return COLORS.shadowNode;
  return COLORS.baseNode;
};
```

### Canvas Object Mode

Set `nodeCanvasObjectMode={() => "replace"}` to ensure custom rendering fully replaces default.

### Context Menu Dismissal

Add global click handler to close menu on outside clicks:
```javascript
useEffect(() => {
  if (!contextMenu) return;

  const handleClick = () => setContextMenu(null);
  const handleEscape = (e) => {
    if (e.key === 'Escape') setContextMenu(null);
  };

  document.addEventListener('click', handleClick);
  document.addEventListener('keydown', handleEscape);

  return () => {
    document.removeEventListener('click', handleClick);
    document.removeEventListener('keydown', handleEscape);
  };
}, [contextMenu]);
```

## Edge Cases

1. **Missing username**: Menu falls back to `node.id` for shadow nodes without usernames
2. **Context menu positioning**: Uses fixed positioning at click coordinates
3. **Drag during layout**: Physics simulation continues during drag (handled by library)
4. **Multiple context menus**: Only one menu open at a time (state holds single menu)

## Testing Plan

1. **Node Dragging**
   - Drag seed, shadow, and regular nodes
   - Verify nodes respond to physics after release
   - Test during active layout simulation

2. **Zoom Scaling**
   - Zoom in/out with mouse wheel
   - Verify nodes shrink/grow smoothly
   - Confirm labels and nodes scale proportionally

3. **Context Menu**
   - Right-click nodes with usernames
   - Right-click shadow nodes (may lack username)
   - Verify menu dismisses on click outside
   - Verify menu dismisses on ESC key
   - Test "Copy username" action
   - Test "Open on Twitter" action

## Non-Goals (Explicitly Deferred)

These features are valuable but deferred until quick wins are validated:
- Permanent node pinning with visual indicators
- Node shape customization (square, diamond, etc.)
- Edge label rendering
- Per-edge color customization
- Keyboard shortcuts for interactions

## Future Migration Path

This design enhances the current react-force-graph-2d stack. If performance degrades at scale (>10k nodes), the architectural analysis recommends:
- **Primary:** Cytoscape.js with WebGL renderer
- **Alternative:** Sigma.js v3 with Graphology

Current enhancements remain low-risk and can be migrated to either library with similar patterns.

## Estimated Effort

- Feature implementation: 2-3 hours
- Testing and polish: 1 hour
- **Total: 3-4 hours**

## Success Criteria

- Users can drag nodes and manually position them
- Nodes scale inversely with zoom (less visual clutter when zoomed in)
- Right-click menu provides quick access to copy username and open Twitter profile
- No performance regression on current 50-500 node graphs
