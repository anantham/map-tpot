import { useCallback, useEffect, useMemo, useState } from 'react'

import { parseResearchNotes } from './parseResearchNotes'
import {
  fetchResearchDossier,
  fetchResearchNotesSource,
} from './researchNotesApi'

function normalizedSuggestions(suggestionsByHandle) {
  if (!suggestionsByHandle || typeof suggestionsByHandle !== 'object') return {}
  return Object.fromEntries(
    Object.entries(suggestionsByHandle).map(([handle, suggestions]) => [
      handle.trim().replace(/^@/, '').toLowerCase(),
      Array.isArray(suggestions) ? suggestions : [],
    ]),
  )
}

export function useResearchNotesInbox() {
  const [pasteText, setPasteText] = useState('')
  const [queue, setQueue] = useState([])
  const [selectedKey, setSelectedKey] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [dossierKey, setDossierKey] = useState(null)
  const [dossierLoading, setDossierLoading] = useState(false)
  const [dossierError, setDossierError] = useState(null)
  const [dossierErrorKey, setDossierErrorKey] = useState(null)
  const [dossierAttempt, setDossierAttempt] = useState(0)
  const [drafts, setDrafts] = useState({})
  const [source, setSource] = useState(null)
  const [sourceLoading, setSourceLoading] = useState(true)
  const [sourceError, setSourceError] = useState(null)
  const [suggestionsByHandle, setSuggestionsByHandle] = useState({})

  const selectedItem = useMemo(
    () => queue.find((item) => item.normalizedHandle === selectedKey) || null,
    [queue, selectedKey],
  )
  const selectedDraft = useMemo(
    () => drafts[selectedKey] || {
      note: selectedItem?.note || '',
    },
    [drafts, selectedItem, selectedKey],
  )

  const addToQueue = useCallback(() => {
    const parsed = parseResearchNotes(pasteText)
    if (parsed.length === 0) return
    const existing = new Set(queue.map((item) => item.normalizedHandle))
    const additions = parsed.filter((item) => !existing.has(item.normalizedHandle))
    const combined = [...queue, ...additions]
    setQueue(combined)
    if (!selectedKey && combined[0]) {
      setSelectedKey(combined[0].normalizedHandle)
    }
  }, [pasteText, queue, selectedKey])

  const addCandidate = useCallback(({ accountId, username }) => {
    const handle = String(username || '').trim().replace(/^@/, '')
    if (!handle) return
    const normalizedHandle = handle.toLowerCase()
    setQueue((current) => {
      const existing = current.find((item) => (
        item.normalizedHandle === normalizedHandle
      ))
      if (existing) {
        if (!accountId || existing.accountId) return current
        return current.map((item) => (
          item.normalizedHandle === normalizedHandle
            ? { ...item, accountId: String(accountId) }
            : item
        ))
      }
      return [...current, {
        accountId: accountId ? String(accountId) : null,
        handle,
        normalizedHandle,
        note: `Surfaced by the target-scoped frontier for review.`,
        sourceEnd: null,
        sourceLine: `@${handle}`,
        sourceStart: null,
        sourceText: `@${handle}`,
      }]
    })
    setSelectedKey(normalizedHandle)
  }, [])

  useEffect(() => {
    let cancelled = false
    setSourceLoading(true)
    setSourceError(null)
    fetchResearchNotesSource()
      .then((result) => {
        if (cancelled) return
        setSource(result?.configured ? result.source : null)
        setSuggestionsByHandle(normalizedSuggestions(result?.suggestionsByHandle))
        if (!result?.configured || typeof result?.source?.text !== 'string') return
        setPasteText(result.source.text)
        const parsed = parseResearchNotes(result.source.text)
        setQueue((current) => (current.length > 0 ? current : parsed))
      })
      .catch((error) => {
        if (!cancelled) setSourceError(error.message)
      })
      .finally(() => {
        if (!cancelled) setSourceLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedKey && queue[0]) setSelectedKey(queue[0].normalizedHandle)
  }, [queue, selectedKey])

  const updateSelectedDraft = useCallback((update) => {
    if (!selectedItem || !selectedKey) return
    setDrafts((current) => {
      const draft = current[selectedKey] || {
        note: selectedItem.note || '',
      }
      return { ...current, [selectedKey]: update(draft) }
    })
  }, [selectedItem, selectedKey])

  const setNote = useCallback((note) => {
    updateSelectedDraft((draft) => ({ ...draft, note }))
  }, [updateSelectedDraft])

  useEffect(() => {
    if (!selectedItem) {
      setDossier(null)
      setDossierKey(null)
      setDossierError(null)
      setDossierErrorKey(null)
      return undefined
    }
    let cancelled = false
    setDossier(null)
    setDossierKey(null)
    setDossierLoading(true)
    setDossierError(null)
    setDossierErrorKey(null)
    fetchResearchDossier({ handle: selectedItem.handle })
      .then((result) => {
        if (!cancelled) {
          setDossier(result)
          setDossierKey(selectedItem.normalizedHandle)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setDossierError(error.message)
          setDossierErrorKey(selectedItem.normalizedHandle)
        }
      })
      .finally(() => {
        if (!cancelled) setDossierLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [dossierAttempt, selectedItem])

  return {
    addCandidate,
    addToQueue,
    dossier: dossierKey === selectedKey ? dossier : null,
    dossierError: dossierErrorKey === selectedKey ? dossierError : null,
    dossierLoading,
    drafts,
    note: selectedDraft.note,
    pasteText,
    queue,
    retryDossier: () => setDossierAttempt((attempt) => attempt + 1),
    selectedItem,
    selectedKey,
    setNote,
    setPasteText,
    setSelectedKey,
    source,
    sourceError,
    sourceLoading,
    suggestionsByHandle,
  }
}
