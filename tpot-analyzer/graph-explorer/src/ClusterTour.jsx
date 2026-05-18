import { useEffect, useState, useCallback } from 'react'

/**
 * First-visit walkthrough for the cluster view.
 *
 * Three steps explaining: (1) what a blob is + click to inspect,
 * (2) scroll-to-drill, (3) granularity slider.
 *
 * Persists "seen" state in localStorage so it only fires once.
 * Parent renders the persistent "?" button via the exported ClusterTourTrigger
 * to re-open at any time.
 */

const LS_KEY = 'tpot:clusterTourSeen:v1'

const STEPS = [
  {
    title: 'Each blob is a cluster',
    body: (
      <>
        Every dot on the map is a group of accounts that follow each other tightly.
        The color shows which community they mostly belong to.
        <br /><br />
        <strong>→ Click any blob to see who's in it.</strong>
      </>
    ),
  },
  {
    title: 'Scroll on a blob to drill in',
    body: (
      <>
        Want to see the sub-clusters inside one of these groups?
        Scroll your mouse wheel <em>while hovering on a blob</em> to split it
        into its children. Scroll the other way to merge them back.
        <br /><br />
        <strong>→ Try it on any blob.</strong>
      </>
    ),
  },
  {
    title: 'Granularity slider sets overall detail',
    body: (
      <>
        The slider at the top controls how many clusters appear by default —
        slide right for more, smaller clusters; slide left for fewer, larger ones.
        <br /><br />
        Use it as your "zoom level" for the whole map.
      </>
    ),
  },
]

function readSeen() {
  if (typeof window === 'undefined') return true
  try {
    return window.localStorage.getItem(LS_KEY) === '1'
  } catch {
    return true  // private mode etc — don't pester
  }
}

function writeSeen() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(LS_KEY, '1')
  } catch {}
}

/** Hook returning {open, openTour, closeTour} so the parent can wire a "?" button. */
export function useClusterTour() {
  const [open, setOpen] = useState(false)

  // Auto-open on first visit
  useEffect(() => {
    if (!readSeen()) setOpen(true)
  }, [])

  const openTour = useCallback(() => setOpen(true), [])
  const closeTour = useCallback(() => {
    writeSeen()
    setOpen(false)
  }, [])

  return { open, openTour, closeTour }
}

export default function ClusterTour({ open, onClose }) {
  const [step, setStep] = useState(0)

  // Reset to step 0 each time the tour is re-opened
  useEffect(() => {
    if (open) setStep(0)
  }, [open])

  if (!open) return null

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Quick tour"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={onClose}  // backdrop click dismisses
    >
      <div
        onClick={(e) => e.stopPropagation()}  // clicks inside the card don't dismiss
        style={{
          background: 'var(--panel, #fff)',
          color: 'var(--text)',
          borderRadius: 12,
          maxWidth: 460,
          width: '90%',
          padding: 24,
          boxShadow: '0 12px 32px rgba(0,0,0,0.25)',
        }}
      >
        <div style={{ color: 'var(--text-muted, #475569)', fontSize: 12, marginBottom: 6 }}>
          Welcome — quick tour ({step + 1} of {STEPS.length})
        </div>
        <h2 style={{ margin: '0 0 12px 0', fontSize: 18 }}>{current.title}</h2>
        <div style={{ lineHeight: 1.55, fontSize: 14, color: 'var(--text)' }}>
          {current.body}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20, gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted, #475569)',
              cursor: 'pointer',
              padding: '8px 12px',
            }}
          >
            Skip
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            {step > 0 && (
              <button
                onClick={() => setStep(s => Math.max(0, s - 1))}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--panel-border, #cbd5e1)',
                  color: 'var(--text)',
                  cursor: 'pointer',
                  padding: '8px 16px',
                  borderRadius: 6,
                }}
              >
                ← Back
              </button>
            )}
            <button
              onClick={() => {
                if (isLast) onClose()
                else setStep(s => s + 1)
              }}
              style={{
                background: 'var(--accent, #0ea5e9)',
                border: 'none',
                color: '#fff',
                cursor: 'pointer',
                padding: '8px 16px',
                borderRadius: 6,
                fontWeight: 600,
              }}
            >
              {isLast ? 'Got it' : 'Next →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Persistent help button to re-open the tour. Floats wherever the parent puts it. */
export function ClusterTourTrigger({ onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label="Show tour"
      title="Show tour"
      style={{
        background: 'var(--panel, #fff)',
        border: '1px solid var(--panel-border, #cbd5e1)',
        color: 'var(--text)',
        width: 32,
        height: 32,
        borderRadius: '50%',
        cursor: 'pointer',
        fontSize: 14,
        fontWeight: 700,
        boxShadow: '0 2px 6px rgba(0,0,0,0.1)',
      }}
    >
      ?
    </button>
  )
}

// Exported for tests
export const _internals = { LS_KEY, STEPS, readSeen, writeSeen }
