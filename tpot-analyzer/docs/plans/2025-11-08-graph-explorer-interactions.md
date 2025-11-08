# Graph Explorer Interaction Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add node dragging, zoom-responsive node sizing, and right-click context menu to Graph Explorer.

**Architecture:** Enhance existing react-force-graph-2d component with built-in drag support, custom canvas rendering for zoom-responsive nodes, and React state-based context menu system.

**Tech Stack:** React 19, react-force-graph-2d, HTML5 Canvas API

---

## Task 1: Enable Node Dragging

**Files:**
- Modify: `graph-explorer/src/GraphExplorer.jsx:894`

**Step 1: Enable drag in ForceGraph2D component**

Change line 894 from:
```javascript
enableNodeDrag={false}
```

To:
```javascript
enableNodeDrag={true}
```

**Step 2: Test drag functionality**

Manual test:
1. Start dev server: `cd graph-explorer && npm run dev`
2. Open browser to `http://localhost:5173`
3. Click on Discovery tab, then Graph Explorer tab
4. Click and drag any node
5. Expected: Node follows cursor, can be repositioned
6. Release mouse, verify node either stays or drifts based on physics

**Step 3: Commit**

```bash
git add graph-explorer/src/GraphExplorer.jsx
git commit -m "feat(graph): Enable node dragging in Graph Explorer"
```

---

## Task 2: Extract Node Color Helper Function

**Files:**
- Modify: `graph-explorer/src/GraphExplorer.jsx:895-901`

**Step 1: Extract color logic into helper function**

Current code at lines 895-901:
```javascript
nodeColor={(node) => {
  if (node.id === selectedNodeId) return COLORS.selectedNode;
  if (selectedNeighbors.has(node.id)) return COLORS.neighborNode;
  if (node.isSeed) return COLORS.seedNode;
  if (node.shadow) return COLORS.shadowNode;
  return COLORS.baseNode;
}}
```

Add new helper function after line 500 (after `selectedNeighbors` definition):
```javascript
const getNodeColor = useCallback((node) => {
  if (node.id === selectedNodeId) return COLORS.selectedNode;
  if (selectedNeighbors.has(node.id)) return COLORS.neighborNode;
  if (node.isSeed) return COLORS.seedNode;
  if (node.shadow) return COLORS.shadowNode;
  return COLORS.baseNode;
}, [selectedNodeId, selectedNeighbors]);
```

**Step 2: Update nodeColor prop to use helper**

Change lines 895-901 to:
```javascript
nodeColor={getNodeColor}
```

**Step 3: Test color rendering still works**

Manual test:
1. Refresh Graph Explorer
2. Click on a node - verify it turns pink (selectedNode color)
3. Hover top accounts list - verify neighbors turn teal
4. Verify seed nodes are yellow, shadow nodes are slate gray

**Step 4: Commit**

```bash
git add graph-explorer/src/GraphExplorer.jsx
git commit -m "refactor(graph): Extract node color logic into helper function"
```

---

## Task 3: Implement Zoom-Responsive Node Sizing

**Files:**
- Modify: `graph-explorer/src/GraphExplorer.jsx:893,934-941`

**Step 1: Remove fixed nodeRelSize prop**

Delete line 893:
```javascript
nodeRelSize={6}
```

**Step 2: Update nodeCanvasObjectMode**

Change line 934 from:
```javascript
nodeCanvasObjectMode={() => "after"}
```

To:
```javascript
nodeCanvasObjectMode={() => "replace"}
```

**Step 3: Replace nodeCanvasObject with combined node+label rendering**

Replace lines 935-941:
```javascript
nodeCanvasObject={(node, ctx, globalScale) => {
  const label = node.display_name || node.username || node.id;
  const fontSize = 12 / globalScale;
  ctx.font = `${fontSize}px sans-serif`;
  ctx.fillStyle = "rgba(248, 250, 252, 0.92)";
  ctx.fillText(label, node.x + 8, node.y + fontSize / 2);
}}
```

With:
```javascript
nodeCanvasObject={(node, ctx, globalScale) => {
  // Calculate zoom-responsive radius
  const baseRadius = 6;
  const radius = baseRadius / Math.sqrt(globalScale);

  // Get node color
  const color = getNodeColor(node);

  // Draw circle
  ctx.beginPath();
  ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();

  // Optional: Add border for selected nodes
  if (node.id === selectedNodeId) {
    ctx.strokeStyle = COLORS.selectedNode;
    ctx.lineWidth = 2 / globalScale;
    ctx.stroke();
  }

  // Draw label
  const label = node.display_name || node.username || node.id;
  const fontSize = 12 / globalScale;
  ctx.font = `${fontSize}px sans-serif`;
  ctx.fillStyle = "rgba(248, 250, 252, 0.92)";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(label, node.x + radius + 2, node.y);
}}
```

**Step 4: Test zoom-responsive sizing**

Manual test:
1. Refresh Graph Explorer
2. Use mouse wheel to zoom in
3. Expected: Nodes visually shrink as you zoom in
4. Zoom out
5. Expected: Nodes grow larger
6. Verify labels also scale appropriately
7. Verify node colors still work (selected, neighbors, seeds, shadows)

**Step 5: Commit**

```bash
git add graph-explorer/src/GraphExplorer.jsx
git commit -m "feat(graph): Add zoom-responsive node sizing"
```

---

## Task 4: Add Context Menu State and Handlers

**Files:**
- Modify: `graph-explorer/src/GraphExplorer.jsx:96,942-945`

**Step 1: Add context menu state**

Add after line 99 (after `subgraphSize` state):
```javascript
const [contextMenu, setContextMenu] = useState(null);
```

**Step 2: Add right-click handler to ForceGraph2D**

Add after line 944 (after `onNodeClick`):
```javascript
onNodeRightClick={(node, event) => {
  event.preventDefault();
  setContextMenu({
    node,
    x: event.clientX,
    y: event.clientY
  });
}}
```

**Step 3: Test right-click triggers state update**

Manual test:
1. Add temporary debug: `console.log('Context menu:', contextMenu);` after state definition
2. Refresh Graph Explorer
3. Right-click on a node
4. Expected: Console shows context menu object with node, x, y
5. Remove console.log

**Step 4: Commit**

```bash
git add graph-explorer/src/GraphExplorer.jsx
git commit -m "feat(graph): Add context menu state and right-click handler"
```

---

## Task 5: Add Context Menu Dismissal Logic

**Files:**
- Modify: `graph-explorer/src/GraphExplorer.jsx` (after context menu state)

**Step 1: Add useEffect for global dismissal handlers**

Add after the context menu state definition (around line 100):
```javascript
// Dismiss context menu on outside click or ESC key
useEffect(() => {
  if (!contextMenu) return;

  const handleClick = () => setContextMenu(null);
  const handleEscape = (e) => {
    if (e.key === 'Escape') setContextMenu(null);
  };

  // Small delay to prevent immediate dismissal from the right-click event
  const timeoutId = setTimeout(() => {
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleEscape);
  }, 100);

  return () => {
    clearTimeout(timeoutId);
    document.removeEventListener('click', handleClick);
    document.removeEventListener('keydown', handleEscape);
  };
}, [contextMenu]);
```

**Step 2: Test dismissal behavior**

Manual test:
1. Refresh Graph Explorer
2. Right-click node to open menu
3. Click elsewhere - verify menu closes
4. Right-click again
5. Press ESC - verify menu closes

**Step 3: Commit**

```bash
git add graph-explorer/src/GraphExplorer.jsx
git commit -m "feat(graph): Add context menu dismissal on click and ESC"
```

---

## Task 6: Render Context Menu UI Component

**Files:**
- Modify: `graph-explorer/src/GraphExplorer.jsx:947` (after closing `</div>` for graph-container)
- Modify: `graph-explorer/src/App.css` (for menu styling)

**Step 1: Add context menu JSX**

Add before the final closing `</div>` of the layout container (around line 947, after graph-container closing div):

```jsx
{contextMenu && (
  <div
    className="context-menu"
    style={{
      position: 'fixed',
      left: contextMenu.x,
      top: contextMenu.y,
      zIndex: 1000
    }}
    onClick={(e) => e.stopPropagation()}
  >
    <button
      className="context-menu-item"
      onClick={() => {
        const username = contextMenu.node.username || contextMenu.node.id;
        navigator.clipboard.writeText(username);
        setContextMenu(null);
      }}
    >
      Copy @{contextMenu.node.username || contextMenu.node.id}
    </button>
    <button
      className="context-menu-item"
      onClick={() => {
        const username = contextMenu.node.username || contextMenu.node.id;
        window.open(`https://twitter.com/${username}`, '_blank');
        setContextMenu(null);
      }}
    >
      Open on Twitter
    </button>
  </div>
)}
```

**Step 2: Add context menu styles**

Add to `graph-explorer/src/App.css` at the end:

```css
.context-menu {
  background: #1e293b;
  border: 1px solid #475569;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  padding: 4px;
  min-width: 180px;
}

.context-menu-item {
  display: block;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: #e2e8f0;
  text-align: left;
  cursor: pointer;
  font-size: 14px;
  border-radius: 4px;
  transition: background 0.15s;
}

.context-menu-item:hover {
  background: #334155;
}

.context-menu-item:active {
  background: #475569;
}
```

**Step 3: Test full context menu functionality**

Manual test:
1. Refresh Graph Explorer
2. Right-click on a node with username
3. Expected: Menu appears at cursor position with dark theme
4. Hover menu items - verify hover effect
5. Click "Copy @username" - verify clipboard contains username
6. Right-click another node
7. Click "Open on Twitter" - verify new tab opens to correct profile
8. Right-click shadow node (may not have username) - verify fallback to ID works

**Step 4: Commit**

```bash
git add graph-explorer/src/GraphExplorer.jsx graph-explorer/src/App.css
git commit -m "feat(graph): Add context menu UI with copy and open actions"
```

---

## Task 7: Final Integration Testing

**Files:**
- No code changes

**Step 1: Comprehensive manual test**

Test all three features together:

1. **Node Dragging:**
   - Drag multiple node types (seed, shadow, regular)
   - Verify drag works during active physics simulation
   - Verify nodes can be repositioned

2. **Zoom Sizing:**
   - Zoom in/out with mouse wheel
   - Verify nodes shrink when zooming in
   - Verify nodes grow when zooming out
   - Verify colors remain correct at all zoom levels
   - Verify labels scale proportionally

3. **Context Menu:**
   - Right-click various nodes
   - Test copy username action
   - Test open Twitter action
   - Verify menu dismisses on outside click
   - Verify menu dismisses on ESC key
   - Verify menu doesn't interfere with node selection

4. **Integration:**
   - Drag a node, then right-click it
   - Right-click a node, dismiss menu, then select it normally
   - Zoom while context menu is open
   - Verify no console errors

**Step 2: Document any issues found**

If issues found, create separate commits to fix them.

**Step 3: Final commit (if needed)**

```bash
git add .
git commit -m "fix(graph): Address integration issues from testing"
```

---

## Success Criteria

- ✅ Nodes can be dragged and repositioned
- ✅ Nodes scale inversely with zoom level
- ✅ Right-click opens context menu at cursor
- ✅ Context menu has "Copy username" and "Open Twitter" actions
- ✅ Context menu dismisses on outside click and ESC
- ✅ No performance regression on 50-500 node graphs
- ✅ All existing features still work (selection, colors, physics)

## Notes for Engineer

**react-force-graph-2d Canvas Rendering:**
- The library uses HTML5 Canvas API for rendering
- `nodeCanvasObject` gives you full control over node drawing
- `globalScale` parameter represents current zoom level (higher = more zoomed in)
- Using `Math.sqrt(globalScale)` for radius provides smooth damping

**Context Menu Pattern:**
- Uses React state + event listeners for dismissal
- `stopPropagation` on menu prevents immediate dismissal
- 100ms timeout prevents right-click event from triggering dismissal

**Testing Context:**
- This is UI/interaction work, so manual testing is primary approach
- Focus on user experience and edge cases
- Test with different node types (seed, shadow, regular)
