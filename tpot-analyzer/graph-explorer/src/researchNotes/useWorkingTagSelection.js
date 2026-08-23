import { useCallback, useEffect, useMemo, useState } from 'react'

const isCommunityKind = (kind) => (
  ['affiliation', 'community_affiliation'].includes(kind)
)

export function useWorkingTagSelection({ selectedHandle, suggestionsByHandle }) {
  const [activeTag, setActiveTag] = useState('')
  const [activeTagKind, setActiveTagKind] = useState('')
  const [revision, setRevision] = useState(0)
  const [tagVocabulary, setTagVocabulary] = useState([])
  const selectedSuggestions = useMemo(
    () => (selectedHandle ? (suggestionsByHandle[selectedHandle] || []) : []),
    [selectedHandle, suggestionsByHandle],
  )
  const proposalMetadata = useMemo(() => {
    const kinds = new Map()
    const tags = []
    Object.values(suggestionsByHandle).flat().forEach((suggestion) => {
      const tag = String(suggestion?.tag || '').trim()
      if (!tag) return
      tags.push(tag)
      if (!kinds.has(tag)) {
        kinds.set(tag, suggestion.tagKind || suggestion.kind || '')
      }
    })
    return { kinds, tags: [...new Set(tags)] }
  }, [suggestionsByHandle])
  const availableTags = useMemo(
    () => [...new Set([...tagVocabulary, ...proposalMetadata.tags])],
    [proposalMetadata.tags, tagVocabulary],
  )

  useEffect(() => {
    if (activeTag) return
    const candidates = selectedSuggestions.filter((suggestion) => (
      suggestion?.tag && !['review', 'abstain'].includes(suggestion.polarity)
    ))
    const proposal = candidates.find((suggestion) => (
      isCommunityKind(suggestion.tagKind || suggestion.kind)
    )) || candidates[0]
    if (!proposal) return
    setActiveTag(proposal.tag)
    setActiveTagKind(proposal.tagKind || proposal.kind || '')
  }, [activeTag, selectedSuggestions])

  const recordVocabulary = useCallback((tags) => {
    setTagVocabulary(Array.isArray(tags) ? tags : [])
  }, [])
  const tagChanged = useCallback((change) => {
    if (change?.tag) {
      setActiveTag(change.tag)
      setActiveTagKind(proposalMetadata.kinds.get(change.tag) || '')
    }
    setRevision((current) => current + 1)
  }, [proposalMetadata.kinds])
  const selectTag = useCallback((tag) => {
    setActiveTag(tag)
    setActiveTagKind(proposalMetadata.kinds.get(tag) || '')
  }, [proposalMetadata.kinds])

  return {
    activeTag,
    activeTagKind,
    availableTags,
    recordVocabulary,
    revision,
    selectedSuggestions,
    selectTag,
    tagChanged,
  }
}
