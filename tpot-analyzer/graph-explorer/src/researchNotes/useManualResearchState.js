import { useCallback, useEffect, useState } from 'react'

import {
  loadManualResearchState,
  saveManualResearchState,
} from './manualResearchStore'

export function useManualResearchState() {
  const [initial] = useState(() => loadManualResearchState())
  const [items, setItems] = useState(initial.items)
  const [drafts, setDrafts] = useState(initial.drafts)
  const [revision, setRevision] = useState(0)
  const [readWarning, setReadWarning] = useState(initial.warning)
  const [writeWarning, setWriteWarning] = useState(null)

  useEffect(() => {
    if (revision === 0) return
    const result = saveManualResearchState({ drafts, items })
    setWriteWarning(result.warning)
    if (!result.warning) setReadWarning(null)
  }, [drafts, items, revision])

  const updateItems = useCallback((update) => {
    setItems((current) => (
      typeof update === 'function' ? update(current) : update
    ))
    setRevision((current) => current + 1)
  }, [])

  const updateDrafts = useCallback((update) => {
    setDrafts((current) => (
      typeof update === 'function' ? update(current) : update
    ))
    setRevision((current) => current + 1)
  }, [])

  return {
    drafts,
    items,
    persistenceEnabled: !(writeWarning || readWarning),
    persistenceWarning: writeWarning || readWarning,
    setDrafts: updateDrafts,
    setItems: updateItems,
  }
}
