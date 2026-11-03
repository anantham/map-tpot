import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchDiscoveryReview, saveDiscoveryReviewAnswer } from './discoveryReviewApi'

function answerFields(answer = {}) {
  return {
    relevance: answer.relevance || '', known: answer.known || '',
    glad: answer.glad || '', note: answer.note || '',
  }
}

export function isComplete(answer) {
  return ['IN', 'OUT', 'ABSTAIN'].includes(answer?.relevance)
    && ['YES', 'NO', 'UNSURE'].includes(answer?.known)
    && ['YES', 'NO', 'UNSURE'].includes(answer?.glad)
}

function sameAnswers(left, right) {
  return Object.keys(answerFields()).every((key) => answerFields(left)[key] === answerFields(right)[key])
}

export default function useDiscoveryReview(apiMode) {
  const [packet, setPacket] = useState(null)
  const [answers, setAnswers] = useState({})
  const [drafts, setDrafts] = useState({})
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const requestGeneration = useRef(0)
  const saveLock = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    const generation = ++requestGeneration.current
    setLoading(true)
    setLoadError('')
    fetchDiscoveryReview({ apiMode, signal: controller.signal }).then((loaded) => {
      if (generation !== requestGeneration.current) return
      if (!loaded.packetId || !Array.isArray(loaded.cards)
        || loaded.cards.length !== loaded.totalCount || !loaded.answers) {
        throw new Error('The review could not be loaded completely. Please retry.')
      }
      setPacket(loaded)
      setAnswers(loaded.answers)
      setDrafts({})
      const firstUnanswered = loaded.cards.findIndex((card) => !isComplete(loaded.answers[card.accountId]))
      setIndex(Math.max(firstUnanswered, 0))
    }).catch((error) => {
      if (generation === requestGeneration.current && error.name !== 'AbortError') {
        setLoadError(error.message)
      }
    }).finally(() => {
      if (generation === requestGeneration.current) setLoading(false)
    })
    return () => {
      controller.abort()
      requestGeneration.current += 1
    }
  }, [apiMode, attempt])

  const card = packet?.cards[index]
  const answer = answers[card?.accountId]
  const draft = drafts[card?.accountId] || answerFields(answer)
  const dirty = !sameAnswers(draft, answer)
  const unsavedCount = Object.entries(drafts).filter(([id, value]) => !sameAnswers(value, answers[id])).length
  const completedCount = packet?.cards.filter((item) => isComplete(answers[item.accountId])).length || 0

  useEffect(() => {
    if (!unsavedCount) return undefined
    const warn = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsavedCount])

  const update = (field, value) => {
    if (saveLock.current || !card) return
    setSaveError('')
    setDrafts((current) => ({ ...current, [card.accountId]: { ...draft, [field]: value } }))
  }

  const navigate = useCallback((next) => {
    if (saveLock.current) return
    setSaveError('')
    setIndex(Math.max(0, Math.min(next, (packet?.cards.length || 1) - 1)))
  }, [packet])

  const save = async (advance) => {
    if (saveLock.current || !card || !isComplete(draft)) return
    if (!dirty) {
      if (advance) navigate(index + 1)
      return
    }
    const accountId = card.accountId
    const generation = requestGeneration.current
    saveLock.current = true
    setSaving(true)
    setSaveError('')
    try {
      const receipt = await saveDiscoveryReviewAnswer(accountId, {
        packetId: packet.packetId, ...answerFields(draft),
      }, { apiMode })
      if (generation !== requestGeneration.current) return
      setAnswers((current) => ({ ...current, [accountId]: receipt.answer }))
      setDrafts((current) => {
        const next = { ...current }
        delete next[accountId]
        return next
      })
      if (advance) setIndex((current) => Math.min(current + 1, packet.cards.length - 1))
    } catch (error) {
      if (generation === requestGeneration.current) setSaveError(`Not saved. ${error.message}`)
    } finally {
      saveLock.current = false
      setSaving(false)
    }
  }

  return {
    packet, answers, index, card, answer, draft, dirty, unsavedCount, completedCount,
    loading, loadError, saveError, saving, update, navigate, save,
    retry: () => setAttempt((current) => current + 1),
  }
}
