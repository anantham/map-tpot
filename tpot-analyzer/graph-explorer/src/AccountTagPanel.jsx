import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteAccountTag,
  fetchAccountTags,
  listDistinctTags,
  upsertAccountTag,
} from './accountsApi'
import TagSuggestions from './researchNotes/TagSuggestions'

const polarityLabel = (polarity) => (polarity === 1 ? 'IN' : polarity === -1 ? 'NOT IN' : '—')

export default function AccountTagPanel({
  ego,
  account,
  onTagChanged,
  onTagStateLoaded,
  onVocabularyLoaded,
  suggestions = [],
}) {
  const accountId = account?.id
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [vocabularyError, setVocabularyError] = useState(null)
  const [tags, setTags] = useState([])
  const [tagsLoaded, setTagsLoaded] = useState(false)
  const [events, setEvents] = useState([])
  const [availableTags, setAvailableTags] = useState([])
  const [tagDraft, setTagDraft] = useState('')
  const [polarity, setPolarity] = useState('in')
  const loadRequest = useRef(0)

  const canEdit = Boolean(ego && accountId)
  const canMutate = canEdit && tagsLoaded

  const load = useCallback(async () => {
    if (!ego || !accountId) return
    const requestId = loadRequest.current + 1
    loadRequest.current = requestId
    setLoading(true)
    setError(null)
    try {
      const res = await fetchAccountTags({ ego, accountId })
      if (requestId !== loadRequest.current) return
      const nextTags = res?.tags || []
      setTags(nextTags)
      setEvents(res?.events || [])
      setTagsLoaded(true)
      onTagStateLoaded?.(nextTags)
    } catch (err) {
      if (requestId !== loadRequest.current) return
      setError(err.message || 'Failed to load tags')
      setTags([])
      setEvents([])
      setTagsLoaded(false)
      onTagStateLoaded?.(null)
    } finally {
      if (requestId === loadRequest.current) setLoading(false)
    }
  }, [ego, accountId, onTagStateLoaded])

  const loadVocabulary = useCallback(async () => {
    if (!ego) return
    setVocabularyError(null)
    try {
      const res = await listDistinctTags({ ego })
      const nextTags = Array.isArray(res) ? res : (res?.tags || [])
      setAvailableTags(nextTags)
      onVocabularyLoaded?.(nextTags)
    } catch (err) {
      setVocabularyError(err.message || 'Failed to load existing tags')
      setAvailableTags([])
      onVocabularyLoaded?.([])
    }
  }, [ego, onVocabularyLoaded])

  useEffect(() => {
    load()
    return () => {
      loadRequest.current += 1
    }
  }, [load])

  useEffect(() => {
    loadVocabulary()
  }, [loadVocabulary])

  const normalizedDraft = useMemo(() => tagDraft.trim(), [tagDraft])

  const saveTag = async ({ tag, polarity: nextPolarity }) => {
    if (!canMutate || !tag) return false
    setLoading(true)
    setError(null)
    try {
      await upsertAccountTag({
        ego,
        accountId,
        tag,
        polarity: nextPolarity,
      })
      await Promise.all([load(), loadVocabulary()])
      onTagChanged?.({ action: 'set', polarity: nextPolarity, tag })
      return true
    } catch (err) {
      setError(err.message || 'Failed to save tag')
      return false
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async () => {
    const saved = await saveTag({ tag: normalizedDraft, polarity })
    if (saved) setTagDraft('')
  }

  const handleDelete = async (tag) => {
    if (!canMutate || !tag) return
    setLoading(true)
    setError(null)
    try {
      await deleteAccountTag({ ego, accountId, tag })
      await Promise.all([load(), loadVocabulary()])
      onTagChanged?.({ action: 'remove', polarity: null, tag })
    } catch (err) {
      setError(err.message || 'Failed to delete tag')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--panel-border)' }}>
      <h2 style={{ fontSize: 16, margin: '0 0 8px' }}>Account tags</h2>
      {!canEdit && (
        <div style={{ color: 'var(--text-muted)' }}>
          Set a curator identity to tag accounts.
        </div>
      )}
      {error && (
        <div style={{ color: '#b91c1c', marginBottom: 8 }}>
          <span>{error}</span>
          {!tagsLoaded && canEdit && (
            <button type="button" onClick={load} style={{ marginLeft: 8 }}>
              Retry tags
            </button>
          )}
        </div>
      )}
      {vocabularyError && (
        <div style={{ color: '#b91c1c', marginBottom: 8 }}>{vocabularyError}</div>
      )}
      <TagSuggestions
        disabled={!canMutate}
        loading={loading}
        onAccept={saveTag}
        suggestions={suggestions}
        tags={tags}
      />
      {availableTags.length > 0 && (
        <div
          aria-label="Existing tag palette"
          role="group"
          style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}
        >
          {availableTags.map((tag) => (
            <button
              key={tag}
              type="button"
              aria-label={`Use ${tag} tag`}
              disabled={!canMutate || loading}
              onClick={() => setTagDraft(tag)}
              style={{
                padding: '5px 8px',
                borderRadius: 999,
                border: '1px solid var(--panel-border)',
                background: 'var(--bg-muted)',
                color: 'var(--text)',
              }}
            >
              {tag}
            </button>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <input
          value={tagDraft}
          onChange={(e) => setTagDraft(e.target.value)}
          placeholder="e.g. AI alignment"
          disabled={!canMutate || loading}
          style={{ flex: 1, padding: '8px 10px', borderRadius: 8, border: '1px solid #cbd5e1' }}
        />
        <select
          value={polarity}
          onChange={(e) => setPolarity(e.target.value)}
          disabled={!canMutate || loading}
          style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #cbd5e1' }}
        >
          <option value="in">IN</option>
          <option value="not_in">NOT IN</option>
        </select>
        <button
          onClick={handleAdd}
          disabled={!canMutate || loading || !normalizedDraft}
          style={{ padding: '8px 12px', borderRadius: 8, background: '#0ea5e9', color: 'white', border: 'none', opacity: (!canMutate || loading || !normalizedDraft) ? 0.6 : 1 }}
        >
          Add
        </button>
      </div>
      {loading && <div style={{ color: 'var(--text-muted)' }}>Loading tags…</div>}
      {!loading && tagsLoaded && tags.length === 0 && <div style={{ color: 'var(--text-muted)' }}>No tags yet.</div>}
      {tags.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {tags.map((t) => (
            <div
              key={`${t.tag}-${t.polarity}`}
              style={{ border: '1px solid var(--panel-border)', borderRadius: 8, padding: 8, display: 'flex', justifyContent: 'space-between', gap: 8 }}
            >
              <div>
                <div style={{ fontWeight: 700 }}>{t.tag}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {polarityLabel(t.polarity)} • {t.updated_at}
                </div>
              </div>
              <button
                onClick={() => handleDelete(t.tag)}
                disabled={!canMutate || loading}
                style={{ padding: '6px 10px', borderRadius: 8, background: '#e11d48', color: 'white', border: 'none', opacity: (!canMutate || loading) ? 0.6 : 1 }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
      {events.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Recent changes</div>
          <ol style={{ margin: 0, paddingLeft: 20, color: 'var(--text-muted)', fontSize: 12 }}>
            {events.map((event) => (
              <li key={event.event_id}>
                {event.action === 'remove'
                  ? `Removed ${event.tag}`
                  : `Set ${event.tag} · ${polarityLabel(event.polarity)}`}
                {event.recorded_at ? ` · ${event.recorded_at}` : ''}
                {event.source ? ` · ${event.source.replaceAll('_', ' ')}` : ''}
                {event.evidence_binding_status
                  ? ` · evidence ${event.evidence_binding_status.replaceAll('_', ' ')}`
                  : ''}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
