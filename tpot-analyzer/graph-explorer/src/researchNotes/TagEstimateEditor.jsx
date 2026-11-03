import { useEffect, useId, useRef, useState } from 'react'

import { fetchTagEstimates, saveTagEstimate } from '../tagEstimatesApi'
import './TagEstimateEditor.css'

const defaultDraft = {
  high: 75,
  low: 25,
  point: 50,
}

const asPercent = (value) => Math.round(Number(value) * 100)

const draftFrom = (current) => current ? {
  high: asPercent(current.plausible_high),
  low: asPercent(current.plausible_low),
  point: asPercent(current.point_estimate),
} : defaultDraft

const summaryFor = (current) => current
  ? `${asPercent(current.point_estimate)}% · plausible eventual range ${asPercent(current.plausible_low)}–${asPercent(current.plausible_high)}%`
  : 'Estimate not recorded'

export default function TagEstimateEditor({
  accountId,
  disabled = false,
  ego,
  reviewSessionId,
  tag,
}) {
  const [current, setCurrent] = useState(null)
  const [draft, setDraft] = useState(defaultDraft)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const [history, setHistory] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const inputId = useId()
  const requestId = useRef(0)
  const subject = `${ego || ''}:${accountId || ''}:${tag || ''}`
  const subjectRef = useRef(subject)
  subjectRef.current = subject
  const headingId = `${inputId}-title`
  const sampleCount = current ? Math.max(history.length, 1) : 0

  useEffect(() => {
    const activeRequest = requestId.current + 1
    requestId.current = activeRequest
    setCurrent(null)
    setDraft(defaultDraft)
    setError(null)
    setExpanded(false)
    setHistory([])
    setLoaded(false)
    if (!ego || !accountId || !tag) return undefined

    fetchTagEstimates({ ego, accountId, tag })
      .then((response) => {
        if (requestId.current !== activeRequest) return
        const nextCurrent = response?.current || null
        setCurrent(nextCurrent)
        setHistory(response?.history || [])
        setDraft(draftFrom(nextCurrent))
        setLoaded(true)
      })
      .catch((nextError) => {
        if (requestId.current !== activeRequest) return
        setError(nextError.message || 'Failed to load estimate trajectory')
        setLoaded(false)
      })
    return () => {
      if (requestId.current === activeRequest) requestId.current += 1
    }
  }, [accountId, ego, tag])

  const setValue = (field, value) => {
    setDraft((prior) => ({ ...prior, [field]: Number(value) }))
  }

  const save = async () => {
    if (disabled || saving || !loaded) return
    if (!(draft.low <= draft.point && draft.point <= draft.high)) {
      setError('Plausible range must satisfy minimum ≤ estimate ≤ maximum.')
      return
    }
    const mutationSubject = subject
    setError(null)
    setSaving(true)
    try {
      const response = await saveTagEstimate({
        ego,
        accountId,
        tag,
        pointEstimate: draft.point / 100,
        plausibleLow: draft.low / 100,
        plausibleHigh: draft.high / 100,
        reviewSessionId,
      })
      if (subjectRef.current !== mutationSubject) return
      const nextCurrent = response?.current || null
      setCurrent(nextCurrent)
      setHistory(response?.history || [])
      setDraft(draftFrom(nextCurrent))
      setExpanded(false)
    } catch (nextError) {
      if (subjectRef.current === mutationSubject) {
        setError(nextError.message || 'Failed to save estimate sample')
      }
    } finally {
      if (subjectRef.current === mutationSubject) setSaving(false)
    }
  }

  const action = current ? 'Adjust' : 'Add'

  return (
    <section className="tag-estimate-editor" aria-labelledby={headingId}>
      <header>
        <div>
          <h3 id={headingId}>Membership estimate · {tag}</h3>
          <p>{loaded ? summaryFor(current) : 'Loading estimate trajectory…'}</p>
        </div>
        <button
          type="button"
          aria-expanded={expanded}
          disabled={disabled || !loaded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Hide controls' : `${action} estimate for ${tag}`}
        </button>
      </header>

      {error && <p className="tag-estimate-error" role="alert">{error}</p>}

      {expanded && (
        <div className="tag-estimate-controls">
          <p>
            The plausible eventual range is your forecast of where this estimate
            may settle after substantially more review—not model confidence.
          </p>
          <div className="tag-estimate-slider">
            <label htmlFor={`${inputId}-point`}>Current membership estimate</label>
            <output>{draft.point}%</output>
            <input
              id={`${inputId}-point`}
              type="range"
              min={draft.low}
              max={draft.high}
              value={draft.point}
              onChange={(event) => setValue('point', event.target.value)}
            />
          </div>
          <div className="tag-estimate-range">
            <div className="tag-estimate-slider">
              <label htmlFor={`${inputId}-low`}>Plausible eventual minimum</label>
              <output>{draft.low}%</output>
              <input
                id={`${inputId}-low`}
                type="range"
                min="0"
                max={draft.point}
                value={draft.low}
                onChange={(event) => setValue('low', event.target.value)}
              />
            </div>
            <div className="tag-estimate-slider">
              <label htmlFor={`${inputId}-high`}>Plausible eventual maximum</label>
              <output>{draft.high}%</output>
              <input
                id={`${inputId}-high`}
                type="range"
                min={draft.point}
                max="100"
                value={draft.high}
                onChange={(event) => setValue('high', event.target.value)}
              />
            </div>
          </div>
          <button type="button" disabled={disabled || saving} onClick={save}>
            {saving ? 'Saving sample…' : 'Save estimate sample'}
          </button>
        </div>
      )}

      {current && (
        <p className="tag-estimate-caveat">
          Latest of {sampleCount} saved {sampleCount === 1 ? 'sample' : 'samples'};
          not yet a stabilized endpoint.
        </p>
      )}
      {history.length > 0 && (
        <details className="tag-estimate-history">
          <summary>Estimate trajectory ({history.length})</summary>
          <ol>
            {history.map((event) => (
              <li key={event.event_id}>
                <strong>{summaryFor(event)}</strong>
                <span>{new Date(event.recorded_at).toLocaleString()}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  )
}
