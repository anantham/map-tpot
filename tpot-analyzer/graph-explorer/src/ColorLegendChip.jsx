import { useState, useEffect, useRef } from 'react'

/**
 * Floating "Colored by" chip that lives inside the canvas container at
 * bottom-right. Replaces the always-on community-legend bar.
 *
 * Two goals:
 *   1. Make the color story explicit — "blob colors are dominant community"
 *      isn't obvious by default; the chip names it.
 *   2. Reclaim canvas vertical space — the previous legend bar took ~30px
 *      always; the chip is ~28px and only expands on click.
 *
 * Closed: a single pill saying "Colored by community".
 * Open: pill expands upward to show the 16 community dots + names.
 *
 * Outside-click and Escape both close it. Position is absolute so the
 * parent must be `position: relative` (the canvas container already is).
 */
export default function ColorLegendChip({ communities }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Outside click closes the popover
  useEffect(() => {
    if (!open) return
    const handle = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [open])

  // Escape closes (only when open)
  useEffect(() => {
    if (!open) return
    const handle = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setOpen(false)
      }
    }
    document.addEventListener('keydown', handle)
    return () => document.removeEventListener('keydown', handle)
  }, [open])

  if (!communities || communities.length === 0) return null

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        bottom: 12,
        right: 12,
        zIndex: 5,
      }}
    >
      {open && (
        <div
          role="region"
          aria-label="Community legend"
          style={{
            position: 'absolute',
            bottom: 32,
            right: 0,
            background: 'var(--panel, #fff)',
            border: '1px solid var(--panel-border, #cbd5e1)',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            padding: 10,
            maxHeight: 320,
            overflowY: 'auto',
            minWidth: 200,
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted, #475569)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>
            Communities ({communities.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {communities.map(c => (
              <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <span style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: c.color,
                  border: '1px solid rgba(0,0,0,0.15)',
                  flexShrink: 0,
                }} />
                <span style={{ color: 'var(--text)' }}>{c.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-label="Toggle community legend"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 10px',
          background: 'var(--panel, #fff)',
          border: '1px solid var(--panel-border, #cbd5e1)',
          borderRadius: 16,
          fontSize: 11,
          color: 'var(--text-muted, #475569)',
          cursor: 'pointer',
          boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
        }}
        title="Each blob's color reflects its dominant community. Click for the full legend."
      >
        {/* Mini swatch row — first 4 communities so the chip itself
            hints at the color story even when closed */}
        <span style={{ display: 'flex', gap: 2 }}>
          {communities.slice(0, 4).map(c => (
            <span
              key={c.id}
              style={{
                display: 'inline-block',
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: c.color,
              }}
            />
          ))}
        </span>
        <span>Colored by community</span>
        <span style={{ fontSize: 10, opacity: 0.7 }}>{open ? '▾' : '▴'}</span>
      </button>
    </div>
  )
}
