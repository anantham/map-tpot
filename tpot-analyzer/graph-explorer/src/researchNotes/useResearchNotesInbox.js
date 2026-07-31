import { useCallback, useEffect, useMemo, useState } from 'react'

import { parseResearchNotes } from './parseResearchNotes'
import { fetchResearchDossier } from './researchNotesApi'

export function useResearchNotesInbox() {
  const [pasteText, setPasteText] = useState('')
  const [queue, setQueue] = useState([])
  const [selectedKey, setSelectedKey] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [dossierLoading, setDossierLoading] = useState(false)
  const [dossierError, setDossierError] = useState(null)
  const [dossierAttempt, setDossierAttempt] = useState(0)
  const [drafts, setDrafts] = useState({})

  const selectedItem = useMemo(
    () => queue.find((item) => item.normalizedHandle === selectedKey) || null,
    [queue, selectedKey],
  )
  const selectedDraft = useMemo(
    () => drafts[selectedKey] || {
      judgments: {},
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
        judgments: {},
        note: selectedItem.note || '',
      }
      return { ...current, [selectedKey]: update(draft) }
    })
  }, [selectedItem, selectedKey])

  const setProbeJudgment = useCallback((probeId, value) => {
    updateSelectedDraft((draft) => ({
      ...draft,
      judgments: { ...draft.judgments, [probeId]: value },
    }))
  }, [updateSelectedDraft])

  const setNote = useCallback((note) => {
    updateSelectedDraft((draft) => ({ ...draft, note }))
  }, [updateSelectedDraft])

  useEffect(() => {
    if (!selectedItem) {
      setDossier(null)
      setDossierError(null)
      return undefined
    }
    let cancelled = false
    setDossier(null)
    setDossierLoading(true)
    setDossierError(null)
    fetchResearchDossier({ handle: selectedItem.handle })
      .then((result) => {
        if (!cancelled) setDossier(result)
      })
      .catch((error) => {
        if (!cancelled) setDossierError(error.message)
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
    dossier,
    dossierError,
    dossierLoading,
    drafts,
    note: selectedDraft.note,
    pasteText,
    probeJudgments: selectedDraft.judgments,
    queue,
    retryDossier: () => setDossierAttempt((attempt) => attempt + 1),
    selectedItem,
    selectedKey,
    setNote,
    setPasteText,
    setProbeJudgment,
    setSelectedKey,
  }
}
