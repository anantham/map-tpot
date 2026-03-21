import { useCallback, useState } from 'react'

import { fetchGoldCandidates } from '../communityGoldApi'

export default function useGoldCandidateQueue({
  communities,
  reviewer,
  setSelectedCommunity,
  setDeepDiveAccountId,
  setSearchQuery,
  setError,
}) {
  const [queueLoading, setQueueLoading] = useState(false)

  const openNextCandidate = useCallback(async (communityId = null) => {
    setQueueLoading(true)
    try {
      const result = await fetchGoldCandidates({
        reviewer,
        limit: 1,
        communityId,
      })
      const candidate = result.candidates?.[0]
      if (!candidate) {
        setError(
          communityId
            ? 'No gold-review candidates remain for this community.'
            : 'No gold-review candidates remain in the current queue.'
        )
        return
      }

      const nextCommunity = communities.find((community) => community.id === candidate.communityId)
      if (nextCommunity) {
        setSelectedCommunity(nextCommunity)
      }
      setSearchQuery('')
      setDeepDiveAccountId(candidate.accountId)
      setError(null)
    } catch (queueError) {
      setError(queueError.message)
    } finally {
      setQueueLoading(false)
    }
  }, [communities, reviewer, setDeepDiveAccountId, setError, setSearchQuery, setSelectedCommunity])

  return { openNextCandidate, queueLoading }
}
