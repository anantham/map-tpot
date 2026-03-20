import { API_BASE_URL } from './config'

const BASE = `${API_BASE_URL}/api/golden`
const LOG = '[labelingApi]'

async function apiFetch(url, opts = {}) {
  console.debug(`${LOG} → ${opts.method || 'GET'} ${url}`)
  const t0 = performance.now()
  let res
  try {
    res = await fetch(url, opts)
  } catch (e) {
    console.error(`${LOG} ✗ fetch failed (network): ${url}`, e)
    throw new Error(`Network error: ${e.message}`)
  }
  const ms = (performance.now() - t0).toFixed(0)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    console.error(`${LOG} ✗ ${res.status} in ${ms}ms: ${url}`, body)
    throw new Error(`${res.status} ${res.statusText}${body ? ': ' + body.slice(0, 200) : ''}`)
  }
  console.debug(`${LOG} ✓ ${res.status} in ${ms}ms: ${url}`)
  return res
}

export async function fetchCandidate({ split = 'train', reviewer = 'human' } = {}) {
  const params = new URLSearchParams({ split, reviewer, status: 'unlabeled', limit: 1 })
  const res = await apiFetch(`${BASE}/candidates?${params}`)
  const data = await res.json()
  return data.candidates?.[0] ?? null
}

export async function fetchMetrics({ reviewer = 'human' } = {}) {
  const res = await apiFetch(`${BASE}/metrics?reviewer=${reviewer}`)
  return res.json()
}

export async function fetchAuthorProfile(username) {
  const res = await apiFetch(`${BASE}/accounts/${encodeURIComponent(username)}/profile`)
  return res.json()
}

export async function fetchReplies(tweetId, { limit = 50 } = {}) {
  const res = await apiFetch(`${BASE}/tweets/${tweetId}/replies?limit=${limit}`)
  return res.json()
}

export async function fetchEngagement(tweetId) {
  const res = await apiFetch(`${BASE}/tweets/${tweetId}/engagement`)
  return res.json()
}

export async function fetchInterpretModels() {
  const res = await apiFetch(`${BASE}/interpret/models`)
  return res.json()
}

export async function interpretTweet({ text, threadContext = [], model } = {}) {
  const res = await apiFetch(`${BASE}/interpret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, threadContext, model }),
  })
  const data = await res.json()
  return data
}

export async function submitLabel({ tweetId, distribution, note, reviewer = 'human' } = {}) {
  const res = await apiFetch(`${BASE}/labels`, {
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
  return res.json()
}

export async function saveTags({ tweetId, tags, addedBy = 'human', category } = {}) {
  const res = await apiFetch(`${BASE}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tweet_id: tweetId,
      tags,
      added_by: addedBy,
      category: category || undefined,
    }),
  })
  return res.json()
}

export async function fetchTweetTags(tweetId) {
  const res = await apiFetch(`${BASE}/tags/${encodeURIComponent(tweetId)}`)
  return res.json()
}

export async function deleteTweetTag(tweetId, tag) {
  const res = await apiFetch(`${BASE}/tags/${encodeURIComponent(tweetId)}/${encodeURIComponent(tag)}`, {
    method: 'DELETE',
  })
  return res.json()
}

export async function fetchTagVocabulary({ limit = 200 } = {}) {
  const res = await apiFetch(`${BASE}/tags/vocabulary?limit=${limit}`)
  return res.json()
}
