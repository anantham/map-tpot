import { useCallback, useEffect, useMemo, useState } from 'react'

import { parseResearchNotes } from './parseResearchNotes'
import {
  mergeResearchQueues,
  withQueueProvenance,
} from './manualResearchStore'
import {
  fetchResearchDossier,
  fetchResearchNotesSource,
} from './researchNotesApi'
import { useManualResearchState } from './useManualResearchState'

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
  const manual = useManualResearchState()
  const [pasteText, setPasteText] = useState('')
  const [sourceQueue, setSourceQueue] = useState([])
  const [selectedKey, setSelectedKey] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [dossierKey, setDossierKey] = useState(null)
  const [dossierLoading, setDossierLoading] = useState(false)
  const [dossierError, setDossierError] = useState(null)
  const [dossierErrorKey, setDossierErrorKey] = useState(null)
  const [dossierAttempt, setDossierAttempt] = useState(0)
  const [source, setSource] = useState(null)
  const [sourceLoading, setSourceLoading] = useState(true)
  const [sourceError, setSourceError] = useState(null)
  const [sourceAttempt, setSourceAttempt] = useState(0)
  const [proposalMetadata, setProposalMetadata] = useState(null)
  const [suggestionsByHandle, setSuggestionsByHandle] = useState({})
  const queue = useMemo(
    () => mergeResearchQueues(sourceQueue, manual.items),
    [manual.items, sourceQueue],
  )

  const selectedItem = useMemo(
    () => queue.find((item) => item.normalizedHandle === selectedKey) || null,
    [queue, selectedKey],
  )
  const selectedDraft = useMemo(
    () => manual.drafts[selectedKey] || {
      note: selectedItem?.note || '',
    },
    [manual.drafts, selectedItem, selectedKey],
  )

  const addToQueue = useCallback(() => {
    const parsed = parseResearchNotes(pasteText)
    if (parsed.length === 0) return
    const sourceHandles = new Set(sourceQueue.map((item) => item.normalizedHandle))
    const existing = new Set(manual.items.map((item) => item.normalizedHandle))
    const additions = parsed
      .filter((item) => (
        !sourceHandles.has(item.normalizedHandle)
        && !existing.has(item.normalizedHandle)
      ))
      .map((item) => withQueueProvenance(item, 'manual_paste'))
    if (additions.length === 0) return
    manual.setItems((current) => [...current, ...additions])
    if (!selectedKey) {
      setSelectedKey(additions[0].normalizedHandle)
    }
  }, [manual, pasteText, selectedKey, sourceQueue])

  const addCandidate = useCallback(({ accountId, username }) => {
    const handle = String(username || '').trim().replace(/^@/, '')
    if (!handle) return
    const normalizedHandle = handle.toLowerCase()
    manual.setItems((current) => {
      const existing = current.find((item) => (
        item.normalizedHandle === normalizedHandle
      ))
      if (existing) {
        const alreadySourced = existing.queueProvenance?.some(
          (row) => row.kind === 'frontier_candidate',
        )
        if ((!accountId || existing.accountId) && alreadySourced) return current
        const enriched = alreadySourced
          ? existing
          : withQueueProvenance(existing, 'frontier_candidate', {
              sourceLine: `@${handle}`,
              sourceText: `@${handle}`,
            })
        return current.map((item) => (
          item.normalizedHandle === normalizedHandle
            ? {
                ...enriched,
                accountId: existing.accountId || (accountId ? String(accountId) : null),
              }
            : item
        ))
      }
      return [...current, withQueueProvenance({
        accountId: accountId ? String(accountId) : null,
        handle,
        normalizedHandle,
        note: `Surfaced by the target-scoped frontier for review.`,
        sourceEnd: null,
        sourceLine: `@${handle}`,
        sourceStart: null,
        sourceText: `@${handle}`,
      }, 'frontier_candidate')]
    })
    setSelectedKey(normalizedHandle)
  }, [manual])

  useEffect(() => {
    let cancelled = false
    setSourceLoading(true)
    setSourceError(null)
    setProposalMetadata(null)
    setSuggestionsByHandle({})
    fetchResearchNotesSource()
      .then((result) => {
        if (cancelled) return
        setSource(result?.configured ? result.source : null)
        setProposalMetadata(result?.proposalMetadata || null)
        setSuggestionsByHandle(normalizedSuggestions(result?.suggestionsByHandle))
        if (!result?.configured || typeof result?.source?.text !== 'string') {
          setSourceQueue([])
          return
        }
        const parsed = parseResearchNotes(result.source.text).map((item) => (
          withQueueProvenance(item, 'takes_source', {
            sourceName: result.source.name,
            sourceSha256: result.source.sha256,
          })
        ))
        setSourceQueue(parsed)
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
  }, [sourceAttempt])

  useEffect(() => {
    if (queue.length === 0) {
      if (selectedKey) setSelectedKey(null)
      return
    }
    if (!queue.some((item) => item.normalizedHandle === selectedKey)) {
      setSelectedKey(queue[0].normalizedHandle)
    }
  }, [queue, selectedKey])

  const updateSelectedDraft = useCallback((update) => {
    if (!selectedItem || !selectedKey) return
    manual.setDrafts((current) => {
      const draft = current[selectedKey] || {
        note: selectedItem.note || '',
      }
      return { ...current, [selectedKey]: update(draft) }
    })
  }, [manual, selectedItem, selectedKey])

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
    drafts: manual.drafts,
    manualQueueCount: manual.items.length,
    note: selectedDraft.note,
    pasteText,
    persistenceEnabled: manual.persistenceEnabled,
    persistenceWarning: manual.persistenceWarning,
    proposalMetadata,
    queue,
    reloadSource: () => setSourceAttempt((attempt) => attempt + 1),
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
