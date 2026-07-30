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
  const [judgment, setJudgment] = useState(null)
  const [note, setNote] = useState('')

  const selectedItem = useMemo(
    () => queue.find((item) => item.normalizedHandle === selectedKey) || null,
    [queue, selectedKey],
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

  useEffect(() => {
    setJudgment(null)
    setNote(selectedItem?.note || '')
  }, [selectedItem])

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
    judgment,
    note,
    pasteText,
    queue,
    retryDossier: () => setDossierAttempt((attempt) => attempt + 1),
    selectedItem,
    selectedKey,
    setJudgment,
    setNote,
    setPasteText,
    setSelectedKey,
  }
}
