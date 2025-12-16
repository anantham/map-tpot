import { useCallback, useEffect, useRef, useState } from 'react'
import { searchAccounts } from './accountsApi'

const normalizeQuery = (raw) => (raw || '').trim().replace(/^@/, '')

export default function AccountSearch({ onPick, placeholder = 'Search accounts…' }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const debounceRef = useRef(null)

  const runSearch = useCallback(async (q) => {
    const cleaned = normalizeQuery(q)
    if (!cleaned) {
      setResults([])
      setOpen(false)
      return
    }
    try {
      const items = await searchAccounts({ q: cleaned, limit: 12 })
      setResults(Array.isArray(items) ? items : [])
      setOpen(Array.isArray(items) && items.length > 0)
      setActiveIdx(-1)
    } catch {
      setResults([])
      setOpen(false)
      setActiveIdx(-1)
    }
  }, [])

  useEffect(() => () => debounceRef.current && clearTimeout(debounceRef.current), [])

  const handleChange = (e) => {
    const next = e.target.value
    setQuery(next)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => runSearch(next), 200)
  }

  const pick = (item) => {
    if (!item) return
    onPick?.(item)
    setQuery('')
    setResults([])
    setOpen(false)
    setActiveIdx(-1)
  }

  const handleKeyDown = (e) => {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((prev) => Math.min(results.length - 1, prev + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((prev) => Math.max(-1, prev - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0) pick(results[activeIdx])
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActiveIdx(-1)
    }
  }

  return (
    <div style={{ position: 'relative', minWidth: 260, flex: '1 1 260px' }}>
      <input
        value={query}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        style={{
          width: '100%',
          padding: '8px 10px',
          borderRadius: 8,
          border: '1px solid var(--panel-border)',
          background: 'var(--panel)',
          color: 'var(--text)',
        }}
      />
      {open && results.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            right: 0,
            maxHeight: 280,
            overflow: 'auto',
            border: '1px solid var(--panel-border)',
            borderRadius: 10,
            background: 'var(--panel)',
            boxShadow: '0 10px 24px rgba(0,0,0,0.12)',
            zIndex: 30,
          }}
        >
          {results.map((item, idx) => {
            const displayName = item.displayName || item.display_name
            return (
              <div
                key={item.id || `${item.username}-${idx}`}
                onMouseDown={(e) => {
                  e.preventDefault()
                  pick(item)
                }}
                onMouseEnter={() => setActiveIdx(idx)}
                style={{
                  padding: '8px 10px',
                  cursor: 'pointer',
                  background: idx === activeIdx ? 'var(--bg-muted)' : 'transparent',
                  borderBottom: idx === results.length - 1 ? 'none' : '1px solid var(--panel-border)',
                }}
              >
                <div style={{ fontWeight: 700, color: 'var(--text)' }}>
                  @{item.username || item.id}
                </div>
                {displayName && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{displayName}</div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
