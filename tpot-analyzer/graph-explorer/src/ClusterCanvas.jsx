import { useEffect, useRef, useState, useMemo, useCallback } from 'react'

const clamp = (val, min, max) => Math.min(max, Math.max(min, val))

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

export default function ClusterCanvas({ nodes, edges, onSelect, onGranularityChange }) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const [transform, setTransform] = useState({ scale: 1, offset: { x: 0, y: 0 } })
  const dragRef = useRef(null)
  const [hoveredNode, setHoveredNode] = useState(null)
  const transformRef = useRef(transform)
  
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

  // Memoize spread calculation
  const processedNodes = useMemo(() => spreadNodes(nodes), [nodes])

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

  // Draw canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const { width, height } = canvas
    ctx.clearRect(0, 0, width, height)

    const index = Object.fromEntries(processedNodes.map(n => [n.id, n]))
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

      const baseOpacity = 0.15 + Math.min(0.35, Math.log1p(edge.weight) * 0.05)
      ctx.strokeStyle = `rgba(100, 140, 200, ${baseOpacity})`
      ctx.lineWidth = 0.5 + Math.min(2, Math.log1p(edge.weight) * 0.3)
      ctx.beginPath()
      ctx.moveTo(p1.x, p1.y)
      ctx.quadraticCurveTo(cx, cy, p2.x, p2.y)
      ctx.stroke()
    })

    // Draw nodes
    processedNodes.forEach(node => {
      const p = toScreen(node)
      const isHovered = hoveredNode === node.id
      
      ctx.beginPath()
      const radius = node.radius * (isHovered ? 1.1 : 1)
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
      
      const gradient = ctx.createRadialGradient(p.x - radius * 0.3, p.y - radius * 0.3, 0, p.x, p.y, radius)
      if (node.containsEgo) {
        gradient.addColorStop(0, '#a78bfa')
        gradient.addColorStop(1, '#7c3aed')
      } else {
        gradient.addColorStop(0, '#64748b')
        gradient.addColorStop(1, '#334155')
      }
      ctx.fillStyle = gradient
      ctx.fill()
      
      ctx.strokeStyle = isHovered ? '#3b82f6' : '#e2e8f0'
      ctx.lineWidth = isHovered ? 3 : 1.5
      ctx.stroke()
    })

    // Draw labels
    ctx.font = '11px Inter, system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    
    processedNodes.forEach(node => {
      const p = toScreen(node)
      const labelY = p.y + node.radius + 4
      
      const maxLen = 24
      let label = node.label || node.id
      if (label.length > maxLen) {
        label = label.slice(0, maxLen - 1) + '…'
      }
      
      // Text shadow
      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'
      ctx.fillText(label, p.x + 1, labelY + 1)
      ctx.fillText(label, p.x - 1, labelY - 1)
      ctx.fillText(label, p.x + 1, labelY - 1)
      ctx.fillText(label, p.x - 1, labelY + 1)
      
      ctx.fillStyle = '#1e293b'
      ctx.fillText(label, p.x, labelY)
      
      ctx.font = '9px Inter, system-ui, sans-serif'
      ctx.fillStyle = '#64748b'
      ctx.fillText(`(${node.size})`, p.x, labelY + 13)
      ctx.font = '11px Inter, system-ui, sans-serif'
    })
  }, [processedNodes, edges, transform, hoveredNode])

  const hitTest = useCallback((x, y) => {
    const t = transformRef.current
    return processedNodes.find(node => {
      const sx = node.x * t.scale + t.offset.x
      const sy = node.y * t.scale + t.offset.y
      return Math.hypot(sx - x, sy - y) <= node.radius + 8
    })
  }, [processedNodes])

  const handleClick = useCallback((evt) => {
    if (!canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const x = evt.clientX - rect.left
    const y = evt.clientY - rect.top
    const hit = hitTest(x, y)
    onSelect?.(hit || null)
  }, [hitTest, onSelect])

  const handleMouseMove = useCallback((evt) => {
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
    const hit = hitTest(x, y)
    setHoveredNode(prev => {
      const next = hit?.id || null
      return prev === next ? prev : next
    })
  }, [hitTest])

  const handleMouseDown = useCallback((evt) => {
    dragRef.current = { x: evt.clientX, y: evt.clientY, transform: transformRef.current }
  }, [])
  
  const handleMouseUp = useCallback(() => {
    dragRef.current = null
  }, [])

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
          cursor: hoveredNode ? 'pointer' : (dragRef.current ? 'grabbing' : 'grab') 
        }} 
      />
      {!processedNodes.length && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#475569' }}>
          Loading clusters...
        </div>
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
        Scroll: split/merge clusters | Ctrl+Scroll: zoom | Drag: pan
      </div>
    </div>
  )
}
