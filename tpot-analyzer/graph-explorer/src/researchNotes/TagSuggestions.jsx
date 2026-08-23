import { useEffect, useId, useMemo, useRef, useState } from 'react'

import './TagSuggestions.css'

const DISMISSAL_STORAGE_KEY = 'tpot:research-notes:suggestion-dismissals:v1'

function readSessionDismissals() {
  try {
    const stored = window.sessionStorage.getItem(DISMISSAL_STORAGE_KEY)
    const parsed = stored ? JSON.parse(stored) : []
    return new Set(Array.isArray(parsed) ? parsed.filter((key) => typeof key === 'string') : [])
  } catch {
    return new Set()
  }
}

function writeSessionDismissals(dismissals) {
  try {
    window.sessionStorage.setItem(DISMISSAL_STORAGE_KEY, JSON.stringify([...dismissals]))
  } catch {
    // Dismissal is non-gold UI state; an unavailable browser store must not block review.
  }
}

function proposalPolarity(suggestion) {
  if (suggestion?.polarity === 'in') return 'in'
  if (['out', 'not_in'].includes(suggestion?.polarity)) return 'not_in'
  return null
}

function proposalQuote(suggestion) {
  return suggestion?.sourceQuote || suggestion?.quote || ''
}

function proposalKind(suggestion) {
  return suggestion?.tagKind || suggestion?.kind || 'untyped'
}

function suggestionKey(suggestion) {
  return [
    suggestion?.sourceSha256 || suggestion?.sourceHash || '',
    String(suggestion?.tag || '').trim().toLowerCase(),
    proposalPolarity(suggestion) || 'review',
    proposalKind(suggestion),
    proposalQuote(suggestion),
    suggestion?.sourceStart ?? '',
    suggestion?.sourceEnd ?? '',
  ].join(':')
}

const scopedSuggestionKey = (scope, suggestion) => (
  `${String(scope || 'default')}:${suggestionKey(suggestion)}`
)

function isAccepted(suggestion, tags) {
  const polarity = proposalPolarity(suggestion)
  const tag = String(suggestion?.tag || '').trim().toLowerCase()
  if (!polarity || !tag) return false
  const expectedPolarity = polarity === 'in' ? 1 : -1
  return tags.some((current) => (
    String(current.tag || '').trim().toLowerCase() === tag
    && current.polarity === expectedPolarity
  ))
}

export default function TagSuggestions({
  disabled = false,
  dismissalScope = 'default',
  loading = false,
  onAccept,
  suggestions = [],
  tags = [],
}) {
  const contentId = useId()
  const signature = useMemo(
    () => suggestions.map(suggestionKey).sort().join('|'),
    [suggestions],
  )
  const [dismissed, setDismissed] = useState(readSessionDismissals)
  const isDismissed = (suggestion) => (
    dismissed.has(scopedSuggestionKey(dismissalScope, suggestion))
  )
  const unresolved = suggestions.filter((suggestion) => (
    !isDismissed(suggestion) && !isAccepted(suggestion, tags)
  ))
  const dismissedCount = suggestions.filter(isDismissed).length
  const [expanded, setExpanded] = useState(unresolved.length > 0)
  const previousUnresolved = useRef(unresolved.length)

  useEffect(() => {
    setDismissed(readSessionDismissals())
  }, [dismissalScope, signature])

  useEffect(() => {
    if (unresolved.length === 0) setExpanded(false)
    if (previousUnresolved.current === 0 && unresolved.length > 0) setExpanded(true)
    previousUnresolved.current = unresolved.length
  }, [unresolved.length])

  const totalLabel = `${suggestions.length} suggestion${suggestions.length === 1 ? '' : 's'}`
  const unresolvedLabel = `${unresolved.length} suggestion${unresolved.length === 1 ? '' : 's'} to review`
  const restoreLabel = `Restore ${dismissedCount} dismissed suggestion${dismissedCount === 1 ? '' : 's'}`

  const dismiss = (suggestion) => {
    const key = scopedSuggestionKey(dismissalScope, suggestion)
    setDismissed((current) => {
      const next = new Set([...current, key])
      writeSessionDismissals(next)
      return next
    })
  }

  const restoreDismissed = () => {
    setDismissed((current) => {
      const next = new Set(current)
      suggestions.forEach((suggestion) => {
        next.delete(scopedSuggestionKey(dismissalScope, suggestion))
      })
      writeSessionDismissals(next)
      return next
    })
    setExpanded(true)
  }

  if (suggestions.length === 0) return null

  return (
    <section className="tag-suggestions" aria-labelledby="tag-suggestions-title">
      <header className="tag-suggestions-header">
        <div>
          <h3 id="tag-suggestions-title">Suggested from your Takes</h3>
          <span>{expanded ? unresolvedLabel : `${totalLabel} · collapsed`}</span>
        </div>
        <button
          type="button"
          aria-controls={contentId}
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse suggestions' : 'Expand suggestions'}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? 'Hide' : 'Show'}
        </button>
      </header>
      {dismissedCount > 0 && (
        <button
          type="button"
          className="tag-suggestion-restore"
          onClick={restoreDismissed}
        >
          {restoreLabel}
        </button>
      )}
      {expanded && <p>
        Proposed from your notes. Accepting writes a reversible judgment;
        dismissing only hides the proposal for this review session.
      </p>}
      {expanded && <div className="tag-suggestions-list" id={contentId}>
        {suggestions.map((suggestion) => {
          const tag = String(suggestion?.tag || '').trim()
          const polarity = proposalPolarity(suggestion)
          const label = polarity === 'in' ? 'IN' : polarity === 'not_in' ? 'NOT IN' : 'REVIEW'
          const key = scopedSuggestionKey(dismissalScope, suggestion)
          const accepted = isAccepted(suggestion, tags)
          if (dismissed.has(key)) return null
          return (
            <article key={key}>
              <div className="tag-suggestion-heading">
                <strong>{tag || 'Untitled proposal'}</strong>
                <span>{label} · {proposalKind(suggestion).replaceAll('_', ' ')}</span>
              </div>
              {proposalQuote(suggestion) && <blockquote>{proposalQuote(suggestion)}</blockquote>}
              <div className="tag-suggestion-actions">
                {polarity ? (
                  <button
                    type="button"
                    aria-label={`Accept ${tag} as ${label}`}
                    disabled={disabled || loading || accepted || !tag}
                    onClick={() => onAccept?.({ tag, polarity })}
                  >
                    {accepted ? 'Already tagged' : `Mark ${label}`}
                  </button>
                ) : (
                  <span className="tag-suggestion-review">No judgment proposed.</span>
                )}
                {!accepted && (
                  <button
                    type="button"
                    className="tag-suggestion-dismiss"
                    aria-label={`Dismiss ${tag} suggestion`}
                    onClick={() => dismiss(suggestion)}
                  >
                    Dismiss
                  </button>
                )}
              </div>
            </article>
          )
        })}
      </div>}
    </section>
  )
}
