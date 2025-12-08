import { useEffect, useRef, useState, useMemo, useCallback } from 'react'

const clamp = (val, min, max) => Math.min(max, Math.max(min, val))

// Easing functions for smooth animations
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)
const easeInOutQuad = (t) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2

// Spring physics with damping for natural bounce effect
const easeOutElastic = (t) => {
  const c4 = (2 * Math.PI) / 3
  return t === 0 ? 0 : t === 1 ? 1 : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1
}

// Smooth spring for entering nodes (gentle bounce)
const easeOutBack = (t) => {
  const c1 = 1.70158
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

// Find the "parent" position for expand/collapse animations
// For collapse: find the cluster that will remain after collapse
// For expand: use the cluster that's being expanded
const findParentPosition = (nodeId, allNodes, edges) => {
  // Try to find a connected cluster as parent
  const connectedEdges = edges.filter(e => e.source === nodeId || e.target === nodeId)
  if (connectedEdges.length > 0) {
    const connectedId = connectedEdges[0].source === nodeId ? connectedEdges[0].target : connectedEdges[0].source
    const parent = allNodes.find(n => n.id === connectedId)
    if (parent) return { x: parent.x, y: parent.y }
  }

  // Fallback: use center of all nodes
  if (allNodes.length > 0) {
    const centerX = allNodes.reduce((sum, n) => sum + n.x, 0) / allNodes.length
    const centerY = allNodes.reduce((sum, n) => sum + n.y, 0) / allNodes.length
    return { x: centerX, y: centerY }
  }

  return { x: 0, y: 0 }
}

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
  memberNodes = [],
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
  const [hoveredMember, setHoveredMember] = useState(null)
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
  const transitionRef = useRef({
    entering: new Set(),
    exiting: new Set(),
    exitingNodes: [],
    parentPositions: new Map(), // Map of node.id -> {x, y} for collapse/expand origins
    nodeVelocities: new Map(), // Map of node.id -> {vx, vy} for smooth physics
    moving: new Map(),
  })
  const [renderTrigger, setRenderTrigger] = useState(0) // Simple number to trigger re-renders
  const animProgressRef = useRef(1)
  const pulsePhaseRef = useRef(0)
  const pulseAnimationRef = useRef(null)
  const overlapRatioRef = useRef(1)
  const hasAutofitRef = useRef(false)
  
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
    const prevMap = new Map(prevNodesRef.current.map(n => [n.id, n]))
    const currMap = new Map(processedNodes.map(n => [n.id, n]))
    const prevIds = new Set(prevMap.keys())
    const currIds = new Set(currMap.keys())

    const overlap = [...currIds].filter(id => prevIds.has(id)).length
    overlapRatioRef.current = currIds.size ? overlap / currIds.size : 1

    const entering = new Set([...currIds].filter(id => !prevIds.has(id)))
    const exiting = new Set([...prevIds].filter(id => !currIds.has(id)))

    const moving = new Map()
    currMap.forEach((node, id) => {
      const prevNode = prevMap.get(id)
      if (prevNode) {
        const dx = node.x - prevNode.x
        const dy = node.y - prevNode.y
        if (Math.hypot(dx, dy) > 1e-3) {
          moving.set(id, { from: { x: prevNode.x, y: prevNode.y }, to: { x: node.x, y: node.y } })
        }
      }
    })

    const getAvgPosition = (ids, sourceMap) => {
      const pts = ids.map(cid => sourceMap.get(cid)).filter(Boolean)
      if (!pts.length) return null
      const x = pts.reduce((s, p) => s + p.x, 0) / pts.length
      const y = pts.reduce((s, p) => s + p.y, 0) / pts.length
      return { x, y }
    }

    // Only animate if there are changes
    if (entering.size > 0 || exiting.size > 0 || moving.size > 0) {
      const parentPositions = new Map()
      const nodeVelocities = new Map()

      const seedEntering = (id) => {
        const node = currMap.get(id)
        if (!node) return null
        if (node.parentId && prevMap.has(node.parentId)) return prevMap.get(node.parentId)
        if (node.childrenIds && node.childrenIds.length) {
          const fromChildren = getAvgPosition(node.childrenIds, prevMap)
          if (fromChildren) return fromChildren
        }
        if (node.parentId && currMap.has(node.parentId)) return currMap.get(node.parentId)
        return findParentPosition(id, processedNodes, edges)
      }

      const seedExiting = (id) => {
        const node = prevMap.get(id)
        if (!node) return null
        if (node.parentId && currMap.has(node.parentId)) return currMap.get(node.parentId)
        if (node.childrenIds && node.childrenIds.length) {
          const toChildren = getAvgPosition(node.childrenIds, currMap)
          if (toChildren) return toChildren
        }
        return findParentPosition(id, processedNodes, edges)
      }

      entering.forEach(id => {
        const parentPos = seedEntering(id)
        if (parentPos) parentPositions.set(id, parentPos)
        nodeVelocities.set(id, { vx: 0, vy: 0 }) // Start with zero velocity
      })

      exiting.forEach(id => {
        const parentPos = seedExiting(id)
        if (parentPos) parentPositions.set(id, parentPos)
        nodeVelocities.set(id, { vx: 0, vy: 0 })
      })

      transitionRef.current = {
        entering,
        exiting,
        exitingNodes: prevNodesRef.current.filter(n => !currIds.has(n.id)),
        parentPositions,
        nodeVelocities,
        moving,
      }
      animProgressRef.current = 0

      // Cancel any existing animation
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }

      const startTime = performance.now()
      const duration = moving.size > 0 && entering.size === 0 && exiting.size === 0 ? 500 : 700 // ms

      const animate = (now) => {
        const elapsed = now - startTime
        const progress = Math.min(1, elapsed / duration)

        if (entering.size > 0 && exiting.size === 0) {
          animProgressRef.current = easeOutBack(progress)
        } else if (exiting.size > 0 && entering.size === 0) {
          animProgressRef.current = easeInOutQuad(progress)
        } else {
          animProgressRef.current = easeOutCubic(progress)
        }

        setRenderTrigger(t => t + 1) // Trigger re-render

        if (progress < 1) {
          animationRef.current = requestAnimationFrame(animate)
        } else {
          transitionRef.current = {
            entering: new Set(),
            exiting: new Set(),
            exitingNodes: [],
            parentPositions: new Map(),
            nodeVelocities: new Map(),
            moving: new Map(),
          }
          animationRef.current = null
        }
      }

      animationRef.current = requestAnimationFrame(animate)
    }

    prevNodesRef.current = processedNodes

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [processedNodes, edges])

  // Auto-fit transform when processedNodes change (first load or big mismatch)
  useEffect(() => {
    if (!processedNodes.length || !containerRef.current) return
    const shouldFit = !hasAutofitRef.current || overlapRatioRef.current < 0.25
    if (!shouldFit) return

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
    hasAutofitRef.current = true
  }, [processedNodes])

  // Draw canvas - use renderTrigger for animation updates
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const renderStart = performance.now()
    const ctx = canvas.getContext('2d')
    const { width, height } = canvas
    ctx.clearRect(0, 0, width, height)

    // Get current animation state from refs
    const transitionState = transitionRef.current
    const movingState = transitionState.moving || new Map()
    const animationProgress = animProgressRef.current
    const pulsePhase = pulsePhaseRef.current

    // Combine current nodes with exiting nodes for animation
    const allNodes = [...processedNodes, ...(transitionState.exitingNodes || [])]
    const index = Object.fromEntries(allNodes.map(n => [n.id, n]))
    const toScreen = (p) => ({
      x: p.x * transform.scale + transform.offset.x,
      y: p.y * transform.scale + transform.offset.y,
    })

    const positionFor = (node) => {
      if (!node) return null
      const isEntering = transitionState.entering.has(node.id)
      const isExiting = transitionState.exiting.has(node.id)
      const isMoving = movingState.has(node.id)
      let nx = node.x
      let ny = node.y
      const parentPos = transitionState.parentPositions.get(node.id)
      if (isEntering && parentPos) {
        nx = parentPos.x + (node.x - parentPos.x) * animationProgress
        ny = parentPos.y + (node.y - parentPos.y) * animationProgress
      } else if (isExiting && parentPos) {
        nx = node.x + (parentPos.x - node.x) * animationProgress
        ny = node.y + (parentPos.y - node.y) * animationProgress
      } else if (isMoving) {
        const move = movingState.get(node.id)
        nx = move.from.x + (move.to.x - move.from.x) * animationProgress
        ny = move.from.y + (move.to.y - move.from.y) * animationProgress
      }
      return { x: nx, y: ny }
    }

    // Draw edges
    edges.forEach(edge => {
      const source = index[edge.source]
      const target = index[edge.target]
      if (!source || !target) return
      const sp = positionFor(source)
      const tp = positionFor(target)
      if (!sp || !tp) return
      const p1 = toScreen(sp)
      const p2 = toScreen(tp)
      
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
      const isHovered = hoveredNode === node.id
      const isSelected = selectedSet.has(node.id)
      const isHighlighted = highlightedSet.has(node.id)
      const isEntering = transitionState.entering.has(node.id)
      const isExiting = transitionState.exiting.has(node.id)
      const isMoving = movingState.has(node.id)
      const isPending = node.id === pendingClusterId

      // Calculate interpolated position for smooth animations
      let nodeX = node.x
      let nodeY = node.y

      if (isEntering || isExiting) {
        const parentPos = transitionState.parentPositions.get(node.id)
        if (parentPos) {
          if (isEntering) {
            // Entering: interpolate FROM parent TO final position (birth animation)
            nodeX = parentPos.x + (node.x - parentPos.x) * animationProgress
            nodeY = parentPos.y + (node.y - parentPos.y) * animationProgress
          } else if (isExiting) {
            // Exiting: interpolate FROM current TO parent position (collapse animation)
          nodeX = node.x + (parentPos.x - node.x) * animationProgress
          nodeY = node.y + (parentPos.y - node.y) * animationProgress
        }
      } else if (isMoving) {
        const move = movingState.get(node.id)
        nodeX = move.from.x + (move.to.x - move.from.x) * animationProgress
        nodeY = move.from.y + (move.to.y - move.from.y) * animationProgress
      }
      }

      const p = toScreen({ x: nodeX, y: nodeY })

      // Calculate animation modifiers
      let animScale = 1
      let animOpacity = 1
      if (isEntering) {
        // Birth animation: start small and grow
        animScale = 0.2 + animationProgress * 0.8  // Scale from 20% to 100%
        animOpacity = Math.min(1, animationProgress * 1.5)  // Fade in faster
      } else if (isExiting) {
        // Collapse animation: shrink as it moves toward parent
        animScale = 1 - animationProgress * 0.8  // Scale from 100% to 20%
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

    // Draw member nodes (exploded leaves)
    memberNodes.forEach(m => {
      const p = toScreen({ x: m.x, y: m.y })
      const isHovered = hoveredMember && hoveredMember.id === m.id
      const radius = (m.radius || 4) * transform.scale * 0.9
      ctx.beginPath()
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
      ctx.fillStyle = isHovered ? 'rgba(59,130,246,0.9)' : 'rgba(148,163,184,0.9)'
      ctx.fill()
      if (isHovered && m.username) {
        ctx.font = '10px Inter, system-ui, sans-serif'
        ctx.fillStyle = '#0f172a'
        ctx.fillText(m.username, p.x + 6, p.y - 6)
      }
    })

    // Draw labels (including exiting ones during animation)
    ctx.font = '11px Inter, system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    
    allNodes.forEach(node => {
      const isEntering = transitionState.entering.has(node.id)
      const isExiting = transitionState.exiting.has(node.id)
      const isMoving = movingState.has(node.id)
      let lx = node.x
      let ly = node.y
      if (isEntering || isExiting) {
        const parentPos = transitionState.parentPositions.get(node.id)
        if (parentPos) {
          if (isEntering) {
            lx = parentPos.x + (node.x - parentPos.x) * animationProgress
            ly = parentPos.y + (node.y - parentPos.y) * animationProgress
          } else {
            lx = node.x + (parentPos.x - node.x) * animationProgress
            ly = node.y + (parentPos.y - node.y) * animationProgress
          }
        }
      } else if (isMoving) {
        const move = movingState.get(node.id)
        lx = move.from.x + (move.to.x - move.from.x) * animationProgress
        ly = move.from.y + (move.to.y - move.from.y) * animationProgress
      }

      const p = toScreen({ x: lx, y: ly })
      
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

    // Log render performance
    const renderEnd = performance.now()
    const renderTime = Math.round(renderEnd - renderStart)
    if (renderTime > 16) { // Only log if slower than 60fps (16ms)
      console.warn(`[ClusterCanvas] ⚠️  Slow render: ${renderTime}ms (nodes: ${processedNodes.length}, edges: ${edges.length})`)
    } else if (transitionState.entering.size > 0 || transitionState.exiting.size > 0) {
      console.log(`[ClusterCanvas] 🎬 Animation frame: ${renderTime}ms (progress: ${Math.round(animationProgress * 100)}%)`)
    }
  }, [processedNodes, edges, memberNodes, transform, hoveredNode, hoveredEdge, hoveredMember, selectedSet, highlightedSet, pendingClusterId, renderTrigger])

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
    
    // Check member hover if no cluster node hovered
    let hitMember = null
    if (!hitNode && memberNodes.length) {
      const inv = transformRef.current
      for (let i = memberNodes.length - 1; i >= 0; i--) {
        const m = memberNodes[i]
        const sx = m.x * inv.scale + inv.offset.x
        const sy = m.y * inv.scale + inv.offset.y
        const dist = Math.hypot(sx - x, sy - y)
        const r = (m.radius || 4) * inv.scale + 4
        if (dist <= r) {
          hitMember = m
          break
        }
      }
    }
    setHoveredMember(hitMember)
    
    // Check edge hover if no node/member is hovered
    if (!hitNode && !hitMember) {
      const hitEdge = edgeHitTest(x, y)
      setHoveredEdge(hitEdge)
    } else {
      setHoveredEdge(null)
    }
  }, [hitTest, edgeHitTest, memberNodes])

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
    setHoveredMember(null)
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
          cursor: selectionMode ? 'crosshair' : ((hoveredNode || hoveredMember) ? 'pointer' : (dragRef.current ? 'grabbing' : 'grab')) 
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
      {hoveredMember && (
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
          maxWidth: 220,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {hoveredMember.displayName || hoveredMember.username || hoveredMember.id}
          </div>
          {hoveredMember.username && (
            <div style={{ color: '#94a3b8', fontSize: 11 }}>
              @{hoveredMember.username}
            </div>
          )}
          {hoveredMember.numFollowers != null && (
            <div style={{ color: '#94a3b8', fontSize: 11 }}>
              Followers: {hoveredMember.numFollowers}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
