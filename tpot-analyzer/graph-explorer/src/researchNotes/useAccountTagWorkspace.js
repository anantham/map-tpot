import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import {
  deleteAccountTag,
  fetchAccountTags,
  listDistinctTags,
  upsertAccountTag,
} from '../accountsApi'

export function useAccountTagWorkspace({
  accountId,
  ego,
  onHistoryLoaded,
  onTagChanged,
  onTagStateLoaded,
  onVocabularyLoaded,
}) {
  const [availableTags, setAvailableTags] = useState([])
  const [error, setError] = useState(null)
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)
  const [tags, setTags] = useState([])
  const [tagsLoaded, setTagsLoaded] = useState(false)
  const [vocabularyError, setVocabularyError] = useState(null)
  const aliveRef = useRef(true)
  const loadRequest = useRef(0)
  const vocabularyRequest = useRef(0)
  const subjectKey = `${ego || ''}:${accountId || ''}`
  const subjectRef = useRef(subjectKey)
  subjectRef.current = subjectKey

  const canEdit = Boolean(ego && accountId)
  const canMutate = canEdit && tagsLoaded

  const load = useCallback(async () => {
    if (!ego || !accountId) return
    const requestedSubject = subjectKey
    const requestId = loadRequest.current + 1
    loadRequest.current = requestId
    setLoading(true)
    setError(null)
    try {
      const response = await fetchAccountTags({ ego, accountId })
      if (
        !aliveRef.current
        || requestId !== loadRequest.current
        || subjectRef.current !== requestedSubject
      ) return
      const nextTags = response?.tags || []
      const nextEvents = response?.events || []
      setTags(nextTags)
      setEvents(nextEvents)
      setTagsLoaded(true)
      onTagStateLoaded?.(nextTags)
      onHistoryLoaded?.(nextEvents)
    } catch (nextError) {
      if (
        !aliveRef.current
        || requestId !== loadRequest.current
        || subjectRef.current !== requestedSubject
      ) return
      setError(nextError.message || 'Failed to load tags')
      setTags([])
      setEvents([])
      setTagsLoaded(false)
      onTagStateLoaded?.(null)
      onHistoryLoaded?.(null)
    } finally {
      if (
        aliveRef.current
        && requestId === loadRequest.current
        && subjectRef.current === requestedSubject
      ) setLoading(false)
    }
  }, [accountId, ego, onHistoryLoaded, onTagStateLoaded, subjectKey])

  const loadVocabulary = useCallback(async () => {
    if (!ego) return
    const requestedEgo = ego
    const requestId = vocabularyRequest.current + 1
    vocabularyRequest.current = requestId
    setVocabularyError(null)
    try {
      const response = await listDistinctTags({ ego })
      if (
        !aliveRef.current
        || requestId !== vocabularyRequest.current
        || subjectRef.current.split(':')[0] !== requestedEgo
      ) return
      const nextTags = Array.isArray(response) ? response : (response?.tags || [])
      setAvailableTags(nextTags)
      onVocabularyLoaded?.(nextTags)
    } catch (nextError) {
      if (
        !aliveRef.current
        || requestId !== vocabularyRequest.current
        || subjectRef.current.split(':')[0] !== requestedEgo
      ) return
      setVocabularyError(nextError.message || 'Failed to load existing tags')
      setAvailableTags([])
      onVocabularyLoaded?.([])
    }
  }, [ego, onVocabularyLoaded])

  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
      loadRequest.current += 1
      vocabularyRequest.current += 1
    }
  }, [])

  useLayoutEffect(() => {
    loadRequest.current += 1
    setTags([])
    setEvents([])
    setTagsLoaded(false)
    setError(null)
    setLoading(Boolean(ego && accountId))
    onTagStateLoaded?.(null)
    onHistoryLoaded?.(null)
  }, [accountId, ego, onHistoryLoaded, onTagStateLoaded])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    loadVocabulary()
  }, [loadVocabulary])

  const saveTag = async ({ tag, polarity }) => {
    if (!canMutate || !tag) return false
    const mutationSubject = subjectKey
    setLoading(true)
    setError(null)
    try {
      await upsertAccountTag({ ego, accountId, tag, polarity })
      if (!aliveRef.current || subjectRef.current !== mutationSubject) return false
      await Promise.all([load(), loadVocabulary()])
      if (!aliveRef.current || subjectRef.current !== mutationSubject) return false
      onTagChanged?.({ action: 'set', polarity, tag })
      return true
    } catch (nextError) {
      if (aliveRef.current && subjectRef.current === mutationSubject) {
        setError(nextError.message || 'Failed to save tag')
      }
      return false
    } finally {
      if (aliveRef.current && subjectRef.current === mutationSubject) {
        setLoading(false)
      }
    }
  }

  const removeTag = async (tag) => {
    if (!canMutate || !tag) return false
    const mutationSubject = subjectKey
    setLoading(true)
    setError(null)
    try {
      await deleteAccountTag({ ego, accountId, tag })
      if (!aliveRef.current || subjectRef.current !== mutationSubject) return false
      await Promise.all([load(), loadVocabulary()])
      if (!aliveRef.current || subjectRef.current !== mutationSubject) return false
      onTagChanged?.({ action: 'remove', polarity: null, tag })
      return true
    } catch (nextError) {
      if (aliveRef.current && subjectRef.current === mutationSubject) {
        setError(nextError.message || 'Failed to delete tag')
      }
      return false
    } finally {
      if (aliveRef.current && subjectRef.current === mutationSubject) {
        setLoading(false)
      }
    }
  }

  return {
    availableTags,
    canEdit,
    canMutate,
    error,
    events,
    load,
    loading,
    removeTag,
    saveTag,
    tags,
    tagsLoaded,
    vocabularyError,
  }
}
