import { useEffect, useRef } from 'react'

/**
 * Right-side drawer that overlays the canvas rather than reflowing it.
 *
 * Why position:absolute over its parent (not a flex sibling):
 *   ClusterCanvas reads containerRef.current.clientWidth to size its <canvas>.
 *   If the drawer were a flex sibling, mounting it would shrink the canvas
 *   container and trigger a resize / re-layout of the force simulation
 *   every time the user opened the sidebar. Keeping it as an overlay means
 *   the canvas dimensions don't change — the drawer just covers part of
 *   the map. Closer to map UX (Google Maps drawers behave this way).
 *
 * Closes on:
 *   - clicking the ✕ button
 *   - pressing Escape (only when open)
 *   - calling onClose() programmatically (e.g., selecting a different cluster)
 *
 * Parent must position itself with `position: relative` (or any non-static)
 * so the drawer's absolute positioning anchors to it.
 */
export default function Drawer({
  open,
  onClose,
  width = 360,
  title = null,
  children,
}) {
  const drawerRef = useRef(null)

  // Escape closes the drawer; only when open so it doesn't intercept other
  // Escape handlers (e.g., GraphExplorer's contextMenu close).
  useEffect(() => {
    if (!open) return
    const handle = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handle)
    return () => document.removeEventListener('keydown', handle)
  }, [open, onClose])

  return (
    <div
      ref={drawerRef}
      role="dialog"
      aria-hidden={!open}
      aria-label={title || 'Details panel'}
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width,
        height: '100%',
        background: 'var(--panel, #fff)',
        borderLeft: '1px solid var(--panel-border, #e2e8f0)',
        boxShadow: open ? '0 0 20px rgba(0,0,0,0.08)' : 'none',
        // +24px buffer over `width` so a vertical scrollbar (usually ~15px
        // on Windows) doesn't leave the drawer's left edge peeking past the
        // viewport in the closed state. Empirically verified during visual
        // QA — the drawer was at x=1412..1772 in a 1423px viewport.
        transform: open ? 'translateX(0)' : `translateX(${width + 24}px)`,
        transition: 'transform 200ms ease, box-shadow 200ms ease',
        overflow: 'auto',
        zIndex: 10,
        // When closed, also disable pointer events so the canvas behind is clickable
        pointerEvents: open ? 'auto' : 'none',
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: '1px solid var(--panel-border, #e2e8f0)',
        position: 'sticky',
        top: 0,
        background: 'var(--panel, #fff)',
        zIndex: 1,
      }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)' }}>
          {title}
        </div>
        <button
          onClick={onClose}
          aria-label="Close panel"
          title="Close (Esc)"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted, #475569)',
            cursor: 'pointer',
            fontSize: 18,
            lineHeight: 1,
            padding: '4px 8px',
            borderRadius: 4,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-muted, #f1f5f9)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
        >
          ✕
        </button>
      </div>
      <div style={{ padding: 16 }}>
        {children}
      </div>
    </div>
  )
}
