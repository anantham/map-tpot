import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  clearGoldLabel,
  evaluateGoldScoreboard,
  fetchGoldLabels,
  upsertGoldLabel,
} from '../communityGoldApi'
import { cardStyle, sectionHeaderStyle } from './accountDeepDiveUtils'
import GoldLabelEditor from './GoldLabelEditor'
import GoldLabelHistory from './GoldLabelHistory'
import GoldScorecard from './GoldScorecard'

export default function GoldLabelPanel({
  accountId,
  reviewer,
  selectedCommunity,
  allCommunities,
  previewCommunities,
  onRequestNextCandidate,
  queueLoading = false,
}) {
  const [labels, setLabels] = useState([])
  const [labelsLoading, setLabelsLoading] = useState(true)
  const [labelsError, setLabelsError] = useState(null)
  const [saving, setSaving] = useState(false)

  const [targetCommunityId, setTargetCommunityId] = useState('')
  const [judgment, setJudgment] = useState('in')
  const [confidencePct, setConfidencePct] = useState(75)
  const [note, setNote] = useState('')

  const [evaluationSplit, setEvaluationSplit] = useState('dev')
  const [scorecard, setScorecard] = useState(null)
  const [scorecardLoading, setScorecardLoading] = useState(false)
  const [scorecardError, setScorecardError] = useState(null)

  const previewCommunityMap = useMemo(
    () => Object.fromEntries((previewCommunities || []).map((row) => [row.community_id, row])),
    [previewCommunities],
  )
  const communityOptions = useMemo(
    () => [...allCommunities].sort((left, right) => left.name.localeCompare(right.name)),
    [allCommunities],
  )

  const loadLabels = useCallback(async () => {
    setLabelsLoading(true)
    setLabelsError(null)
    try {
      const data = await fetchGoldLabels({
        accountId,
        reviewer,
        includeInactive: true,
        limit: 100,
      })
      setLabels(data.labels || [])
    } catch (error) {
      setLabelsError(error.message)
    } finally {
      setLabelsLoading(false)
    }
  }, [accountId, reviewer])

  useEffect(() => {
    loadLabels()
  }, [loadLabels])

  useEffect(() => {
    if (selectedCommunity?.id) {
      setTargetCommunityId(selectedCommunity.id)
      return
    }
    if (!targetCommunityId && communityOptions[0]?.id) {
      setTargetCommunityId(communityOptions[0].id)
    }
  }, [communityOptions, selectedCommunity?.id, targetCommunityId])

  const activeLabels = labels.filter((label) => label.isActive)
  const split = activeLabels[0]?.split || labels[0]?.split || null
  const currentLabel = activeLabels.find((label) => label.communityId === targetCommunityId) || null
  const targetPreviewCommunity = previewCommunityMap[targetCommunityId]
  const canonicalWeight = currentLabel?.canonicalMembershipWeight ?? targetPreviewCommunity?.weight ?? null
  const canonicalSource = currentLabel?.canonicalMembershipSource ?? targetPreviewCommunity?.source ?? null
  const labelHistory = labels.filter((label) => label.communityId === targetCommunityId).slice(0, 6)

  useEffect(() => {
    if (currentLabel) {
      setJudgment(currentLabel.judgment)
      setConfidencePct(currentLabel.confidence != null ? Math.round(currentLabel.confidence * 100) : 75)
      setNote(currentLabel.note || '')
      return
    }
    setJudgment('in')
    setConfidencePct(75)
    setNote('')
  }, [currentLabel, targetCommunityId])

  useEffect(() => {
    if (!targetCommunityId) return

    let cancelled = false
    async function loadScorecard() {
      setScorecardLoading(true)
      setScorecardError(null)
      try {
        const result = await evaluateGoldScoreboard({
          split: evaluationSplit,
          reviewer,
          communityIds: [targetCommunityId],
        })
        if (cancelled) return
        setScorecard({
          bestMethodByMacroAucPr: result.bestMethodByMacroAucPr,
          community: result.communities?.[0] || null,
        })
      } catch (error) {
        if (cancelled) return
        setScorecard(null)
        setScorecardError(error.message)
      } finally {
        if (!cancelled) setScorecardLoading(false)
      }
    }

    loadScorecard()
    return () => {
      cancelled = true
    }
  }, [evaluationSplit, reviewer, targetCommunityId, labels])

  const handleSave = useCallback(async () => {
    if (!targetCommunityId) return
    setSaving(true)
    setLabelsError(null)
    try {
      await upsertGoldLabel({
        accountId,
        communityId: targetCommunityId,
        reviewer,
        judgment,
        confidence: confidencePct / 100,
        note: note.trim() || undefined,
        evidence: { source: 'communities-tab' },
      })
      await loadLabels()
    } catch (error) {
      setLabelsError(error.message)
    } finally {
      setSaving(false)
    }
  }, [accountId, confidencePct, judgment, loadLabels, note, reviewer, targetCommunityId])

  const handleClear = useCallback(async () => {
    if (!targetCommunityId) return
    setSaving(true)
    setLabelsError(null)
    try {
      await clearGoldLabel({ accountId, communityId: targetCommunityId, reviewer })
      await loadLabels()
    } catch (error) {
      setLabelsError(error.message)
    } finally {
      setSaving(false)
    }
  }, [accountId, loadLabels, reviewer, targetCommunityId])

  return (
    <div>
      <div style={sectionHeaderStyle}>Gold Review</div>
      <div style={cardStyle}>
        <GoldLabelEditor
          reviewer={reviewer}
          split={split}
          currentLabel={currentLabel}
          targetCommunityId={targetCommunityId}
          communityOptions={communityOptions}
          onTargetCommunityChange={setTargetCommunityId}
          judgment={judgment}
          onJudgmentChange={setJudgment}
          confidencePct={confidencePct}
          onConfidenceChange={setConfidencePct}
          note={note}
          onNoteChange={setNote}
          canonicalWeight={canonicalWeight}
          canonicalSource={canonicalSource}
          saving={saving}
          onSave={handleSave}
          onClear={handleClear}
          onRequestNextCandidate={onRequestNextCandidate ? () => onRequestNextCandidate(targetCommunityId) : null}
          queueLoading={queueLoading}
          labelsError={labelsError}
        />

        <GoldScorecard
          evaluationSplit={evaluationSplit}
          onEvaluationSplitChange={setEvaluationSplit}
          scorecard={scorecard}
          scorecardLoading={scorecardLoading}
          scorecardError={scorecardError}
        />
        <GoldLabelHistory labelsLoading={labelsLoading} labelHistory={labelHistory} />
      </div>
    </div>
  )
}
