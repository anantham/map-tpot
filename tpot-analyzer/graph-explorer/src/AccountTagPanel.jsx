import { useCallback, useEffect, useMemo, useState } from 'react'
import { deleteAccountTag, fetchAccountTags, upsertAccountTag } from './accountsApi'

const polarityLabel = (polarity) => (polarity === 1 ? 'IN' : polarity === -1 ? 'NOT IN' : '—')

export default function AccountTagPanel({ ego, account, onTagChanged }) {
  const accountId = account?.id
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tags, setTags] = useState([])
  const [tagDraft, setTagDraft] = useState('')
  const [polarity, setPolarity] = useState('in')

  const canEdit = Boolean(ego && accountId)

  const load = useCallback(async () => {
    if (!ego || !accountId) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetchAccountTags({ ego, accountId })
      setTags(res?.tags || [])
    } catch (err) {
      setError(err.message || 'Failed to load tags')
      setTags([])
    } finally {
      setLoading(false)
    }
  }, [ego, accountId])

  useEffect(() => {
    load()
  }, [load])

  const normalizedDraft = useMemo(() => tagDraft.trim(), [tagDraft])

  const handleAdd = async () => {
    if (!canEdit || !normalizedDraft) return
    setLoading(true)
    setError(null)
    try {
      await upsertAccountTag({
        ego,
        accountId,
        tag: normalizedDraft,
        polarity,
      })
      setTagDraft('')
      await load()
      onTagChanged?.()
    } catch (err) {
      setError(err.message || 'Failed to save tag')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (tag) => {
    if (!canEdit || !tag) return
    setLoading(true)
    setError(null)
    try {
      await deleteAccountTag({ ego, accountId, tag })
      await load()
      onTagChanged?.()
    } catch (err) {
      setError(err.message || 'Failed to delete tag')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--panel-border)' }}>
      <div style={{ fontWeight: 800, marginBottom: 8 }}>Account tags</div>
      {!canEdit && <div style={{ color: 'var(--text-muted)' }}>Set `ego` to tag accounts.</div>}
      {error && <div style={{ color: '#b91c1c', marginBottom: 8 }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <input
          value={tagDraft}
          onChange={(e) => setTagDraft(e.target.value)}
          placeholder="e.g. AI alignment"
          disabled={!canEdit || loading}
          style={{ flex: 1, padding: '8px 10px', borderRadius: 8, border: '1px solid #cbd5e1' }}
        />
        <select
          value={polarity}
          onChange={(e) => setPolarity(e.target.value)}
          disabled={!canEdit || loading}
          style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #cbd5e1' }}
        >
          <option value="in">IN</option>
          <option value="not_in">NOT IN</option>
        </select>
        <button
          onClick={handleAdd}
          disabled={!canEdit || loading || !normalizedDraft}
          style={{ padding: '8px 12px', borderRadius: 8, background: '#0ea5e9', color: 'white', border: 'none', opacity: (!canEdit || loading || !normalizedDraft) ? 0.6 : 1 }}
        >
          Add
        </button>
      </div>
      {loading && <div style={{ color: 'var(--text-muted)' }}>Loading tags…</div>}
      {!loading && tags.length === 0 && <div style={{ color: 'var(--text-muted)' }}>No tags yet.</div>}
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
                disabled={!canEdit || loading}
                style={{ padding: '6px 10px', borderRadius: 8, background: '#e11d48', color: 'white', border: 'none', opacity: (!canEdit || loading) ? 0.6 : 1 }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

