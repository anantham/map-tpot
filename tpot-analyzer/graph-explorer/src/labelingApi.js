import { API_BASE_URL } from './config'

const BASE = `${API_BASE_URL}/api/golden`

export async function fetchCandidate({ split = 'train', reviewer = 'human' } = {}) {
  const params = new URLSearchParams({ split, reviewer, status: 'unlabeled', limit: 1 })
  const res = await fetch(`${BASE}/candidates?${params}`)
  if (!res.ok) throw new Error(`candidates failed: ${res.status}`)
  const data = await res.json()
  return data.candidates?.[0] ?? null
}

export async function fetchMetrics({ reviewer = 'human' } = {}) {
  const res = await fetch(`${BASE}/metrics?reviewer=${reviewer}`)
  if (!res.ok) throw new Error(`metrics failed: ${res.status}`)
  return res.json()
}

export async function interpretTweet({ text, threadContext = [], model } = {}) {
  const res = await fetch(`${BASE}/interpret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, threadContext, model }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.error || `interpret failed: ${res.status}`)
  }
  return res.json()
}

export async function submitLabel({ tweetId, distribution, lucidity, note, reviewer = 'human' } = {}) {
  const res = await fetch(`${BASE}/labels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tweet_id: tweetId,
      axis: 'simulacrum',
      reviewer,
      distribution: {
        l1: distribution.l1,
        l2: distribution.l2,
        l3: distribution.l3,
        l4: distribution.l4,
      },
      note: note || undefined,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.error || `label failed: ${res.status}`)
  }
  return res.json()
}
