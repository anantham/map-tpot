import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor, act } from '@testing-library/react'
import ClusterCanvas from './ClusterCanvas'

describe('ClusterCanvas High-Value Tests', () => {
  // Setup data
  const initialNodes = [
    { id: 'node1', x: 0, y: 0, radius: 20, color: 'red' }, // Center node
    { id: 'node2', x: 100, y: 100, radius: 20, color: 'blue' } // Offset node
  ]

  const defaultProps = {
    nodes: initialNodes,
    edges: [],
    width: 500,
    height: 500,
    onSelect: vi.fn(),
    onSelectionChange: vi.fn(),
    selectionMode: false
  }
  
  // Global mock cleanup
  const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect
  
  beforeEach(() => {
    // Mock getBoundingClientRect globally for JSDOM
    Element.prototype.getBoundingClientRect = vi.fn(() => ({
      width: 500, height: 500, top: 0, left: 0, bottom: 500, right: 500, x: 0, y: 0, toJSON: () => {}
    }))

    // Mock clientWidth/Height for JSDOM (needed for canvas sizing)
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 500 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 500 })
  })

  afterEach(() => {
    Element.prototype.getBoundingClientRect = originalGetBoundingClientRect
    // Reset clientWidth/Height
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 0 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 0 })
    vi.clearAllMocks()
  })
  
  const waitForSettle = async () => {
     // Wait for effects and animation frames to flush
     await act(async () => {
       await new Promise(r => setTimeout(r, 50))
     })
  }

  it('detects a click on a centered node (Hit Detection)', async () => {
    const singleNodeProps = { ...defaultProps, nodes: [{ id: 'center', x: 100, y: 100, radius: 20 }] }
    const { container } = render(<ClusterCanvas {...singleNodeProps} />)
    
    await waitForSettle()
    
    // Auto-fit should align (100,100) to Center (250,250).
    const canvas = container.querySelector('canvas')
    fireEvent.click(canvas, { clientX: 250, clientY: 250 })

    await waitFor(() => {
      expect(defaultProps.onSelect).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'center' })
      )
    })
  })

  it('respects Event Priority: Selection Mode prevents Panning', async () => {
    const onSelectionChange = vi.fn()
    // Need a node to hit for selection change to fire
    const nodes = [{ id: 'target', x: 100, y: 100, radius: 20 }]
    
    const { container } = render(
      <ClusterCanvas 
        {...defaultProps} 
        nodes={nodes}
        selectionMode={true} 
        onSelectionChange={onSelectionChange} 
      />
    )
    
    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Drag across the center (200,200 to 300,300) to encompass the node at 250,250
    fireEvent.mouseDown(canvas, { clientX: 200, clientY: 200 })
    fireEvent.mouseMove(canvas, { clientX: 300, clientY: 300 })
    fireEvent.mouseUp(canvas, { clientX: 300, clientY: 300 })

    expect(onSelectionChange).toHaveBeenCalled()
  })

  it('respects Event Priority: Normal Mode triggers Pan (no selection)', async () => {
    const onSelectionChange = vi.fn()
    const nodes = [{ id: 'target', x: 100, y: 100, radius: 20 }]

    const { container } = render(
      <ClusterCanvas 
        {...defaultProps} 
        nodes={nodes}
        selectionMode={false} 
        onSelectionChange={onSelectionChange} 
      />
    )
    
    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Drag across center
    fireEvent.mouseDown(canvas, { clientX: 200, clientY: 200 })
    fireEvent.mouseMove(canvas, { clientX: 300, clientY: 300 })
    fireEvent.mouseUp(canvas, { clientX: 300, clientY: 300 })

    expect(onSelectionChange).not.toHaveBeenCalled()
  })

  it('handles background clicks', async () => {
    const onSelect = vi.fn()
    const singleNodeProps = { 
      ...defaultProps, 
      nodes: [{ id: 'center', x: 100, y: 100, radius: 20 }],
      onSelect 
    }
    
    const { container } = render(<ClusterCanvas {...singleNodeProps} />)
    
    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Click far away from center (at 0,0) - node is at 250,250
    fireEvent.click(canvas, { clientX: 10, clientY: 10 })

    expect(onSelect).toHaveBeenCalledWith(null)
  })
  
  it('correctly interprets coordinates after Zoom (Wheel)', async () => {
     const onSelect = vi.fn()
     const singleNodeProps = { 
       ...defaultProps, 
       nodes: [{ id: 'center', x: 0, y: 0, radius: 20 }],
       onSelect
     }
     
     const { container } = render(<ClusterCanvas {...singleNodeProps} />)
     await waitForSettle()
     const canvas = container.querySelector('canvas')
     
     // 1. Initial State: Node is at 250, 250.
     fireEvent.click(canvas, { clientX: 250, clientY: 250 })
     expect(onSelect).toHaveBeenCalledTimes(1)
     onSelect.mockClear()
     
     // 2. Zoom In (Wheel Up) at Center
     fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
     await waitForSettle()
     
     // 3. Click again at center - should still hit
     fireEvent.click(canvas, { clientX: 250, clientY: 250 })
     expect(onSelect).toHaveBeenCalledTimes(1)
     onSelect.mockClear()
     
     // 4. Pan to the right (move camera Left, so node moves Right)
     // Drag from 250 to 300
     fireEvent.mouseDown(canvas, { clientX: 250, clientY: 250 })
     fireEvent.mouseMove(canvas, { clientX: 300, clientY: 250 }) // Move 50px right
     fireEvent.mouseUp(canvas, { clientX: 300, clientY: 250 })
     
     // Click at OLD location (250, 250) - Should Miss (Background Click)
     fireEvent.click(canvas, { clientX: 250, clientY: 250 })
     expect(onSelect).toHaveBeenCalledWith(null)
     onSelect.mockClear()
     
     // Click at NEW location (300, 250) - Should Hit
     fireEvent.click(canvas, { clientX: 300, clientY: 250 })
     expect(onSelect).toHaveBeenCalledTimes(1)
  })
})