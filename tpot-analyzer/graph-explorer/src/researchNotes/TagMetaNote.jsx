import { useCallback, useEffect, useId, useRef, useState } from 'react'

import { fetchTagMetaNote, saveTagMetaNote } from '../accountsApi'
import {
  clearTagMetaDraft,
  readTagMetaDraft,
  writeTagMetaDraft,
} from './tagMetaDraftStorage'

const timestamp = (entry) => entry?.created_at || entry?.recordedAt || ''
const MAX_NOTE_CHARS = 10_000

export default function TagMetaNote({ disabled = false, ego, tag }) {
  const noteId = useId()
  const [current, setCurrent] = useState(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [hasLocalDraft, setHasLocalDraft] = useState(false)
  const [draftStored, setDraftStored] = useState(false)
  const [reconciled, setReconciled] = useState(false)
  const aliveRef = useRef(true)
  const requestRef = useRef(0)
  const subject = { ego, tag }
  const subjectKey = `${String(ego || '').toLowerCase()}:${String(tag || '').toLowerCase()}`
  const subjectRef = useRef(subjectKey)
  subjectRef.current = subjectKey

  const load = useCallback(async () => {
    if (!ego || !tag) return
    const requestId = requestRef.current + 1
    requestRef.current = requestId
    const localDraft = readTagMetaDraft({ ego, tag })
    if (localDraft?.note !== undefined) {
      setDraft(localDraft.note)
      setHasLocalDraft(true)
      setDraftStored(true)
    }
    setReconciled(false)
    setLoading(true)
    setError(null)
    try {
      const response = await fetchTagMetaNote({ ego, tag })
      if (requestId !== requestRef.current) return
      const nextCurrent = response?.current || null
      const savedDraft = readTagMetaDraft({ ego, tag })
      const baseline = nextCurrent?.note || ''
      const shouldRestore = savedDraft?.note !== undefined && savedDraft.note !== baseline
      if (!shouldRestore && savedDraft) clearTagMetaDraft({ ego, tag })
      setCurrent(nextCurrent)
      setHistory(response?.history || [])
      setDraft(shouldRestore ? savedDraft.note : baseline)
      setHasLocalDraft(shouldRestore)
      setDraftStored(shouldRestore)
      setReconciled(true)
    } catch (nextError) {
      if (requestId !== requestRef.current) return
      setCurrent(null)
      setHistory([])
      setReconciled(false)
      setError(nextError.message || 'Failed to load this tag note')
    } finally {
      if (requestId === requestRef.current) setLoading(false)
    }
  }, [ego, tag])

  useEffect(() => {
    aliveRef.current = true
    load()
    return () => {
      aliveRef.current = false
      requestRef.current += 1
    }
  }, [load])

  if (!ego || !tag) return null

  const unchanged = draft === (current?.note || '')
  const earlier = history.slice(0, Math.max(0, history.length - 1)).reverse()

  const save = async () => {
    if (disabled || loading || saving || unchanged || !reconciled) return
    const savingSubjectKey = subjectKey
    const noteToSave = draft
    setSaving(true)
    setError(null)
    try {
      await saveTagMetaNote({ ego, tag, note: noteToSave })
      clearTagMetaDraft(subject)
      if (aliveRef.current && subjectRef.current === savingSubjectKey) {
        setHasLocalDraft(false)
        setDraftStored(false)
        await load()
      }
    } catch (nextError) {
      if (aliveRef.current && subjectRef.current === savingSubjectKey) {
        setError(nextError.message || 'Failed to save this tag note')
      }
    } finally {
      if (aliveRef.current && subjectRef.current === savingSubjectKey) {
        setSaving(false)
      }
    }
  }

  const updateDraft = (nextDraft) => {
    setDraft(nextDraft)
    const isChanged = nextDraft !== (current?.note || '')
    setHasLocalDraft(isChanged)
    if (isChanged) setDraftStored(writeTagMetaDraft(subject, nextDraft))
    else {
      clearTagMetaDraft(subject)
      setDraftStored(false)
    }
  }

  return (
    <section className="tag-meta-note" aria-labelledby="tag-meta-note-title">
      <h3 id="tag-meta-note-title">What I currently mean by “{tag}”</h3>
      <p>
        Optional and versioned. Your reviewed examples remain more authoritative
        than this working description.
      </p>
      <label htmlFor={noteId}>
        What do you currently mean by {tag}?
      </label>
      <textarea
        id={noteId}
        disabled={disabled || loading || saving}
        maxLength={MAX_NOTE_CHARS}
        onChange={(event) => updateDraft(event.target.value)}
        placeholder="Write a note to your future self; this does not become a model rule."
        value={draft}
      />
      <div className="tag-meta-note-actions">
        <button
          type="button"
          disabled={disabled || loading || saving || unchanged || !reconciled}
          onClick={save}
        >
          {saving ? 'Saving…' : 'Save tag note'}
        </button>
        {current && (
          <span>Current version saved {timestamp(current) || 'at an unknown time'}</span>
        )}
      </div>
      <div className="tag-meta-note-status" aria-live="polite">
        {loading && <span>Loading tag note…</span>}
        {!loading && error && (
          <>
            <span>{error}</span>
            <span>Server state is not reconciled. Retry before saving.</span>
            <button type="button" disabled={saving} onClick={load}>
              Retry tag note
            </button>
          </>
        )}
        {hasLocalDraft && draftStored && (
          <span>Unsaved draft kept on this device.</span>
        )}
        {hasLocalDraft && !draftStored && (
          <span>Unsaved draft is only in this open view—save before switching.</span>
        )}
      </div>
      {earlier.length > 0 && (
        <details>
          <summary>Recent earlier meanings ({earlier.length})</summary>
          <ol>
            {earlier.map((entry) => (
              <li key={entry.note_id || `${timestamp(entry)}:${entry.note}`}>
                <span>{entry.note || '(cleared)'}</span>
                <small>{timestamp(entry)} · {(entry.source || 'unknown').replaceAll('_', ' ')}</small>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  )
}
