import { useCallback, useEffect, useMemo, useState } from 'react'

import { parseResearchNotes } from './parseResearchNotes'
import { fetchResearchDossier } from './researchNotesApi'

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
  }
}
