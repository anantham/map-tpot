import {
  API_BASE_URL,
  CURATION_SOURCE_HEADER,
  withCuratorAuth,
} from './config'

const jsonOrError = async (res, fallbackMessage) => {
  const text = await res.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!res.ok) {
    const message = payload?.error
      || `${fallbackMessage}: ${res.status} ${res.statusText}`
    const error = new Error(message)
    error.status = res.status
    error.payload = payload
    throw error
  }
  return payload
}

const estimateUrl = ({ ego, accountId, tag }) => {
  const params = new URLSearchParams({ ego, tag })
  return `${API_BASE_URL}/api/accounts/${encodeURIComponent(accountId)}/tag-estimates?${params.toString()}`
}

export const fetchTagEstimates = async (subject) => {
  const res = await fetch(estimateUrl(subject), withCuratorAuth({ cache: 'no-store' }))
  return jsonOrError(res, 'Failed to fetch tag estimate trajectory')
}

export const saveTagEstimate = async ({
  ego,
  accountId,
  tag,
  pointEstimate,
  plausibleLow,
  plausibleHigh,
  reviewSessionId,
}) => {
  const res = await fetch(
    estimateUrl({ ego, accountId, tag }),
    withCuratorAuth({
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [CURATION_SOURCE_HEADER]: 'human_curator_api',
      },
      body: JSON.stringify({
        pointEstimate,
        plausibleLow,
        plausibleHigh,
        reviewSessionId,
      }),
    }),
  )
  return jsonOrError(res, 'Failed to save tag estimate sample')
}
