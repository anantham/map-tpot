import { useEffect, useRef, useState, useMemo, useCallback } from 'react'

const clamp = (val, min, max) => Math.min(max, Math.max(min, val))

// Easing function for smooth animations
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)

// Force-based repulsion to spread overlapping nodes
const spreadNodes = (inputNodes) => {
  if (!inputNodes.length) return inputNodes
  
  const positioned = inputNodes.map(n => ({
    ...n,
    px: n.x,
    py: n.y,
  }))
  
  const iterations = 50
  const minDistance = 60
  
  for (let iter = 0; iter < iterations; iter++) {
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const a = positioned[i]
        const b = positioned[j]
        
        const dx = b.px - a.px
        const dy = b.py - a.py
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.1
        
        const minDist = Math.max(minDistance, a.radius + b.radius + 20)
        
        if (dist < minDist) {
          const force = (minDist - dist) / dist * 0.5
          const fx = dx * force
          const fy = dy * force
          
          a.px -= fx
          a.py -= fy
          b.px += fx
          b.py += fy
        }
      }
    }
  }
  
  return positioned.map(n => ({
    ...n,
    x: n.px,
    y: n.py,
  }))
}

export default function ClusterCanvas({ 
  nodes, 
  edges, 
  onSelect, 
  onGranularityChange,
  selectionMode = false,
  selectedIds = new Set(),
  onSelectionChange,
  highlightedIds = [],
  pendingClusterId = null,
}) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const [transform, setTransform] = useState({ scale: 1, offset: { x: 0, y: 0 } })
  const dragRef = useRef(null)
  const [hoveredNode, setHoveredNode] = useState(null)
  const [hoveredEdge, setHoveredEdge] = useState(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const [selectionBox, setSelectionBox] = useState(null)
  const selectionDragRef = useRef(null)
  const transformRef = useRef(transform)
  const selectedSet = useMemo(() => {
    if (selectedIds instanceof Set) return selectedIds
    return new Set(selectedIds || [])
  }, [selectedIds])
  const highlightedSet = useMemo(() => new Set(highlightedIds || []), [highlightedIds])
  
  // Animation state - use a single render trigger instead of complex objects in deps
  const prevNodesRef = useRef([])
  const animationRef = useRef(null)
  const transitionRef = useRef({ entering: new Set(), exiting: new Set(), exitingNodes: [] })
  const [renderTrigger, setRenderTrigger] = useState(0) // Simple number to trigger re-renders
  const animProgressRef = useRef(1)
  const pulsePhaseRef = useRef(0)
  const pulseAnimationRef = useRef(null)
  
  // Keep transform ref in sync
  useEffect(() => {
    transformRef.current = transform
  }, [transform])

  // Resize canvas to container
  useEffect(() => {
    const resize = () => {
      if (!containerRef.current || !canvasRef.current) return
      const { clientWidth, clientHeight } = containerRef.current
      canvasRef.current.width = clientWidth
      canvasRef.current.height = clientHeight
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])

  // Pulse animation for pending cluster
  useEffect(() => {
    if (!pendingClusterId) {
      pulsePhaseRef.current = 0
      if (pulseAnimationRef.current) {
        cancelAnimationFrame(pulseAnimationRef.current)
        pulseAnimationRef.current = null
      }
      return
    }
    
    const startTime = performance.now()
    const animate = (now) => {
      const elapsed = (now - startTime) / 1000 // seconds
      pulsePhaseRef.current = elapsed * 2 * Math.PI // Complete cycle per second
      setRenderTrigger(t => t + 1) // Trigger re-render
      pulseAnimationRef.current = requestAnimationFrame(animate)
    }
    pulseAnimationRef.current = requestAnimationFrame(animate)
    
    return () => {
      if (pulseAnimationRef.current) {
        cancelAnimationFrame(pulseAnimationRef.current)
      }
    }
  }, [pendingClusterId])

  // Memoize spread calculation
  const processedNodes = useMemo(() => spreadNodes(nodes), [nodes])

  // Detect node transitions and start animation
  useEffect(() => {
    const prevIds = new Set(prevNodesRef.current.map(n => n.id))
    const currIds = new Set(processedNodes.map(n => n.id))
    
    const entering = new Set([...currIds].filter(id => !prevIds.has(id)))
    const exiting = new Set([...prevIds].filter(id => !currIds.has(id)))
    
    // Only animate if there are changes
    if (entering.size > 0 || exiting.size > 0) {
      transitionRef.current = { 
        entering, 
        exiting, 
        exitingNodes: prevNodesRef.current.filter(n => !currIds.has(n.id)) 
      }
      animProgressRef.current = 0
      
      // Cancel any existing animation
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
      
      const startTime = performance.now()
      const duration = 300 // ms
      
      const animate = (now) => {
        const elapsed = now - startTime
        const progress = Math.min(1, elapsed / duration)
        animProgressRef.current = easeOutCubic(progress)
        setRenderTrigger(t => t + 1) // Trigger re-render
        
        if (progress < 1) {
          animationRef.current = requestAnimationFrame(animate)
        } else {
          // Animation complete - clear transition state
          transitionRef.current = { entering: new Set(), exiting: new Set(), exitingNodes: [] }
          animationRef.current = null
        }
      }
      
      animationRef.current = requestAnimationFrame(animate)
    }
    
    // Store current nodes for next comparison
    prevNodesRef.current = processedNodes
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [processedNodes])

  // Auto-fit transform when processedNodes change
  useEffect(() => {
    if (!processedNodes.length || !containerRef.current) return
    const xs = processedNodes.map(n => n.x)
    const ys = processedNodes.map(n => n.y)
    const bbox = {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    }
    const width = containerRef.current.clientWidth || 800
    const height = containerRef.current.clientHeight || 600
    const pad = 120
    const dx = Math.max(bbox.maxX - bbox.minX, 1)
    const dy = Math.max(bbox.maxY - bbox.minY, 1)
    const scale = 0.85 * Math.min((width - pad) / dx, (height - pad) / dy)
    const offset = {
      x: width / 2 - ((bbox.minX + bbox.maxX) / 2) * scale,
      y: height / 2 - ((bbox.minY + bbox.maxY) / 2) * scale,
    }
    setTransform({ scale, offset })
  }, [processedNodes])

  // Draw canvas - use renderTrigger for animation updates
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const { width, height } = canvas
    ctx.clearRect(0, 0, width, height)

    // Get current animation state from refs
    const transitionState = transitionRef.current
    const animationProgress = animProgressRef.current
    const pulsePhase = pulsePhaseRef.current

    // Combine current nodes with exiting nodes for animation
    const allNodes = [...processedNodes, ...(transitionState.exitingNodes || [])]
    const index = Object.fromEntries(allNodes.map(n => [n.id, n]))
    const toScreen = (p) => ({
      x: p.x * transform.scale + transform.offset.x,
      y: p.y * transform.scale + transform.offset.y,
    })

    // Draw edges
    edges.forEach(edge => {
      const source = index[edge.source]
      const target = index[edge.target]
      if (!source || !target) return
      const p1 = toScreen(source)
      const p2 = toScreen(target)
      
      const mx = (p1.x + p2.x) / 2
      const my = (p1.y + p2.y) / 2
      const dx = p2.x - p1.x
      const dy = p2.y - p1.y
      const len = Math.hypot(dx, dy) || 1
      const normX = -dy / len
      const normY = dx / len
      const curve = Math.min(30, len * 0.15)
      const cx = mx + normX * curve
      const cy = my + normY * curve
      const op = edge.opacity ?? Math.min(1, Math.max(0.05, (edge.connectivity || 0.1)))
      
      // Check if this edge is hovered
      const isHovered = hoveredEdge && 
        hoveredEdge.source === edge.source && 
        hoveredEdge.target === edge.target
      
      if (isHovered) {
        // Highlight hovered edge
        ctx.strokeStyle = 'rgba(59, 130, 246, 0.9)'  // Blue
        ctx.lineWidth = 3
      } else {
        const baseOpacity = 0.1 + Math.min(0.4, op)
        ctx.strokeStyle = `rgba(100, 140, 200, ${baseOpacity})`
        ctx.lineWidth = 0.5 + Math.min(2, Math.log1p(edge.rawCount || 1) * 0.2)
      }
      
      ctx.beginPath()
      ctx.moveTo(p1.x, p1.y)
      ctx.quadraticCurveTo(cx, cy, p2.x, p2.y)
      ctx.stroke()
    })

    // Draw nodes (including exiting ones during animation)
    allNodes.forEach(node => {
      const p = toScreen(node)
      const isHovered = hoveredNode === node.id
      const isSelected = selectedSet.has(node.id)
      const isHighlighted = highlightedSet.has(node.id)
      const isEntering = transitionState.entering.has(node.id)
      const isExiting = transitionState.exiting.has(node.id)
      const isPending = node.id === pendingClusterId
      
      // Calculate animation modifiers
      let animScale = 1
      let animOpacity = 1
      if (isEntering) {
        animScale = 0.5 + animationProgress * 0.5  // Scale from 50% to 100%
        animOpacity = animationProgress  // Fade in
      } else if (isExiting) {
        animScale = 1 - animationProgress * 0.5  // Scale from 100% to 50%
        animOpacity = 1 - animationProgress  // Fade out
      }
      
      // Pulse effect for pending cluster
      let pulseScale = 1
      let pulseGlow = 0
      if (isPending) {
        pulseScale = 1 + Math.sin(pulsePhase) * 0.1  // Scale 90% to 110%
        pulseGlow = (Math.sin(pulsePhase) + 1) / 2  // 0 to 1
      }
      
      ctx.globalAlpha = animOpacity
      
      ctx.beginPath()
      const baseRadius = node.radius * (isHovered ? 1.1 : 1) * (isSelected ? 1.08 : 1) * (isHighlighted ? 1.05 : 1)
      const radius = baseRadius * animScale * pulseScale
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
      
      // Draw glow for pending cluster
      if (isPending && pulseGlow > 0) {
        ctx.save()
        ctx.shadowColor = 'rgba(14, 165, 233, 0.6)'
        ctx.shadowBlur = 15 + pulseGlow * 15
        ctx.fillStyle = 'rgba(14, 165, 233, 0.3)'
        ctx.fill()
        ctx.restore()
      }
      
      const gradient = ctx.createRadialGradient(p.x - radius * 0.3, p.y - radius * 0.3, 0, p.x, p.y, radius)
      if (node.containsEgo) {
        gradient.addColorStop(0, '#a78bfa')
        gradient.addColorStop(1, '#7c3aed')
      } else if (isHighlighted) {
        // Orange/amber for collapse preview siblings
        gradient.addColorStop(0, '#fbbf24')
        gradient.addColorStop(1, '#d97706')
      } else if (isPending) {
        // Cyan/blue for pending expansion
        gradient.addColorStop(0, '#67e8f9')
        gradient.addColorStop(1, '#0ea5e9')
      } else if (isEntering) {
        // Green tint for newly appearing nodes
        gradient.addColorStop(0, '#86efac')
        gradient.addColorStop(1, '#22c55e')
      } else {
        gradient.addColorStop(0, '#64748b')
        gradient.addColorStop(1, '#334155')
      }
      ctx.fillStyle = gradient
      ctx.fill()
      
      ctx.strokeStyle = isPending ? '#0ea5e9' : (isHighlighted ? '#f59e0b' : (isSelected ? '#0ea5e9' : (isHovered ? '#3b82f6' : '#e2e8f0')))
      ctx.lineWidth = isPending ? 4 : (isHighlighted ? 4 : (isSelected ? 3.5 : (isHovered ? 3 : 1.5)))
      ctx.stroke()
      
      ctx.globalAlpha = 1  // Reset alpha
    })

    // Draw labels (including exiting ones during animation)
    ctx.font = '11px Inter, system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    
    allNodes.forEach(node => {
      const p = toScreen(node)
      const isEntering = transitionState.entering.has(node.id)
      const isExiting = transitionState.exiting.has(node.id)
      
      // Apply animation to labels
      let animOpacity = 1
      let animScale = 1
      if (isEntering) {
        animOpacity = animationProgress
        animScale = 0.5 + animationProgress * 0.5
      } else if (isExiting) {
        animOpacity = 1 - animationProgress
        animScale = 1 - animationProgress * 0.5
      }
      
      const labelY = p.y + (node.radius * animScale) + 4
      
      const maxLen = 24
      let label = node.label || node.id
      if (label.length > maxLen) {
        label = label.slice(0, maxLen - 1) + '…'
      }
      
      // Text shadow
      ctx.fillStyle = `rgba(255, 255, 255, ${0.9 * animOpacity})`
      ctx.fillText(label, p.x + 1, labelY + 1)
      ctx.fillText(label, p.x - 1, labelY - 1)
      ctx.fillText(label, p.x + 1, labelY - 1)
      ctx.fillText(label, p.x - 1, labelY + 1)
      
      ctx.fillStyle = `rgba(30, 41, 59, ${animOpacity})`
      ctx.fillText(label, p.x, labelY)
      
      ctx.font = '9px Inter, system-ui, sans-serif'
      ctx.fillStyle = `rgba(100, 116, 139, ${animOpacity})`
      ctx.fillText(`(${node.size})`, p.x, labelY + 13)
      ctx.font = '11px Inter, system-ui, sans-serif'
    })
  }, [processedNodes, edges, transform, hoveredNode, hoveredEdge, selectedSet, highlightedSet, pendingClusterId, renderTrigger])

  const hitTest = useCallback((x, y) => {
    const t = transformRef.current
    return processedNodes.find(node => {
      const sx = node.x * t.scale + t.offset.x
      const sy = node.y * t.scale + t.offset.y
      return Math.hypot(sx - x, sy - y) <= node.radius + 8
    })
  }, [processedNodes])

  // Hit test for edges - check distance to curved edge path
  const edgeHitTest = useCallback((x, y) => {
    const t = transformRef.current
    const index = Object.fromEntries(processedNodes.map(n => [n.id, n]))
    const toScreen = (p) => ({
      x: p.x * t.scale + t.offset.x,
      y: p.y * t.scale + t.offset.y,
    })
    
    const threshold = 8 // pixels from edge
    
    for (const edge of edges) {
      const source = index[edge.source]
      const target = index[edge.target]
      if (!source || !target) continue
      
      const p1 = toScreen(source)
      const p2 = toScreen(target)
      
      // Calculate control point for quadratic curve
      const mx = (p1.x + p2.x) / 2
      const my = (p1.y + p2.y) / 2
      const dx = p2.x - p1.x
      const dy = p2.y - p1.y
      const len = Math.hypot(dx, dy) || 1
      const normX = -dy / len
      const normY = dx / len
      const curve = Math.min(30, len * 0.15)
      const cx = mx + normX * curve
      const cy = my + normY * curve
      
      // Sample points along the curve and check distance
      for (let t = 0; t <= 1; t += 0.05) {
        const invT = 1 - t
        const px = invT * invT * p1.x + 2 * invT * t * cx + t * t * p2.x
        const py = invT * invT * p1.y + 2 * invT * t * cy + t * t * p2.y
        if (Math.hypot(px - x, py - y) < threshold) {
          return edge
        }
      }
    }
    return null
  }, [processedNodes, edges])

  const handleClick = useCallback((evt) => {
    if (!canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const x = evt.clientX - rect.left
    const y = evt.clientY - rect.top
    const hit = hitTest(x, y)
    if (selectionMode && hit) {
      const next = new Set(selectedSet)
      if (next.has(hit.id)) {
        next.delete(hit.id)
      } else {
        next.add(hit.id)
      }
      onSelectionChange?.(next)
    }
    onSelect?.(hit || null)
  }, [hitTest, onSelect, onSelectionChange, selectedSet, selectionMode])

  const handleMouseMove = useCallback((evt) => {
    if (selectionDragRef.current) {
      const rect = canvasRef.current.getBoundingClientRect()
      const x = evt.clientX - rect.left
      const y = evt.clientY - rect.top
      setSelectionBox(box => ({
        ...(box || selectionDragRef.current),
        x2: x,
        y2: y,
      }))
      // Live preview of selection while dragging
      const { x1, y1 } = selectionDragRef.current
      const minX = Math.min(x1, x)
      const maxX = Math.max(x1, x)
      const minY = Math.min(y1, y)
      const maxY = Math.max(y1, y)
      const hits = processedNodes
        .filter(node => {
          const sx = node.x * transformRef.current.scale + transformRef.current.offset.x
          const sy = node.y * transformRef.current.scale + transformRef.current.offset.y
          return sx >= minX && sx <= maxX && sy >= minY && sy <= maxY
        })
        .map(n => n.id)
      if (hits.length && onSelectionChange) {
        const next = new Set(selectedSet)
        hits.forEach(id => next.add(id))
        onSelectionChange(next)
      }
      return
    }
    
    if (dragRef.current) {
      const dx = evt.clientX - dragRef.current.x
      const dy = evt.clientY - dragRef.current.y
      setTransform({
        scale: dragRef.current.transform.scale,
        offset: {
          x: dragRef.current.transform.offset.x + dx,
          y: dragRef.current.transform.offset.y + dy,
        },
      })
      return
    }
    
    if (!canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const x = evt.clientX - rect.left
    const y = evt.clientY - rect.top
    
    setMousePos({ x: evt.clientX, y: evt.clientY })
    
    // Check node hover first (nodes on top of edges)
    const hitNode = hitTest(x, y)
    setHoveredNode(prev => {
      const next = hitNode?.id || null
      return prev === next ? prev : next
    })
    
    // Check edge hover if no node is hovered
    if (!hitNode) {
      const hitEdge = edgeHitTest(x, y)
      setHoveredEdge(hitEdge)
    } else {
      setHoveredEdge(null)
    }
  }, [hitTest, edgeHitTest])

  const handleMouseDown = useCallback((evt) => {
    if (selectionMode && evt.button === 0) {
      const rect = canvasRef.current.getBoundingClientRect()
      const x = evt.clientX - rect.left
      const y = evt.clientY - rect.top
      selectionDragRef.current = { x1: x, y1: y, x2: x, y2: y }
      setSelectionBox({ x1: x, y1: y, x2: x, y2: y })
      return
    }
    dragRef.current = { x: evt.clientX, y: evt.clientY, transform: transformRef.current }
  }, [selectionMode])
  
  const handleMouseUp = useCallback(() => {
    if (selectionDragRef.current) {
      const { x1, y1, x2, y2 } = selectionDragRef.current
      const minX = Math.min(x1, x2)
      const maxX = Math.max(x1, x2)
      const minY = Math.min(y1, y2)
      const maxY = Math.max(y1, y2)
      const hits = processedNodes
        .filter(node => {
          const sx = node.x * transformRef.current.scale + transformRef.current.offset.x
          const sy = node.y * transformRef.current.scale + transformRef.current.offset.y
          return sx >= minX && sx <= maxX && sy >= minY && sy <= maxY
        })
        .map(n => n.id)
      if (hits.length) {
        const next = new Set(selectedSet)
        hits.forEach(id => next.add(id))
        onSelectionChange?.(next)
      }
      setSelectionBox(null)
      selectionDragRef.current = null
    }
    dragRef.current = null
  }, [processedNodes, onSelectionChange, selectedSet])

  // Native wheel handler to prevent passive event issues
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    
    const handleWheel = (evt) => {
      evt.preventDefault()
      evt.stopPropagation()
      
      if (evt.metaKey || evt.ctrlKey) {
        // Geometric zoom
        const factor = evt.deltaY > 0 ? 0.9 : 1.1
        const newScale = clamp(transformRef.current.scale * factor, 0.1, 10)
        setTransform(t => ({
          scale: newScale,
          offset: t.offset,
        }))
      } else {
        // Semantic zoom: change granularity
        const step = evt.deltaY > 0 ? 3 : -3
        onGranularityChange?.(step)
      }
    }
    
    container.addEventListener('wheel', handleWheel, { passive: false })
    return () => container.removeEventListener('wheel', handleWheel)
  }, [onGranularityChange])

  return (
    <div
      ref={containerRef}
      style={{ flex: 1, position: 'relative', background: '#f8fafc' }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onClick={handleClick}
    >
      <canvas 
        ref={canvasRef} 
        style={{ 
          width: '100%', 
          height: '100%', 
          cursor: selectionMode ? 'crosshair' : (hoveredNode ? 'pointer' : (dragRef.current ? 'grabbing' : 'grab')) 
        }} 
      />
      {!processedNodes.length && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#475569' }}>
          Loading clusters...
        </div>
      )}
      {selectionBox && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(selectionBox.x1, selectionBox.x2),
            top: Math.min(selectionBox.y1, selectionBox.y2),
            width: Math.abs(selectionBox.x2 - selectionBox.x1),
            height: Math.abs(selectionBox.y2 - selectionBox.y1),
            border: '1px solid #0ea5e9',
            background: 'rgba(14, 165, 233, 0.08)',
            pointerEvents: 'none',
          }}
        />
      )}
      <div style={{ 
        position: 'absolute', 
        bottom: 12, 
        left: 12, 
        background: 'rgba(255,255,255,0.9)', 
        padding: '8px 12px', 
        borderRadius: 6,
        fontSize: 11,
        color: '#475569'
      }}>
        {selectionMode 
          ? 'Selection mode: drag to box-select clusters for collapse. Click toggles selection.'
          : 'Scroll: split/merge clusters | Ctrl+Scroll: zoom | Drag: pan'}
      </div>
      {/* Edge tooltip */}
      {hoveredEdge && (
        <div style={{
          position: 'fixed',
          left: mousePos.x + 12,
          top: mousePos.y + 12,
          background: 'rgba(30, 41, 59, 0.95)',
          color: '#f8fafc',
          padding: '8px 12px',
          borderRadius: 6,
          fontSize: 12,
          fontFamily: 'Inter, system-ui, sans-serif',
          pointerEvents: 'none',
          zIndex: 1000,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          maxWidth: 200,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {hoveredEdge.rawCount} edge{hoveredEdge.rawCount !== 1 ? 's' : ''}
          </div>
          <div style={{ color: '#94a3b8', fontSize: 11 }}>
            Connectivity: {(hoveredEdge.connectivity || 0).toFixed(3)}
          </div>
        </div>
      )}
    </div>
  )
}
