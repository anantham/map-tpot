/**
 * API functions for the Discovery view.
 *
 * Consolidates the raw fetch() calls that were scattered inside Discovery.jsx.
 * Each function is a thin wrapper around a single backend endpoint.
 */

import { API_BASE_URL } from './config'

/**
 * Fetch all seed collections and global model settings from the server.
 * GET /api/seeds
 */
export const fetchSeedState = async () => {
  const res = await fetch(`${API_BASE_URL}/api/seeds`)
  if (!res.ok) {
    throw new Error(`Failed to fetch seed state: ${res.status}`)
  }
  return res.json()
}

/**
 * Persist a seed list (and optionally set it as active).
 * POST /api/seeds
 */
export const persistSeedList = async ({ name, seeds, setActive = true }) => {
  const body = { name: (name || 'discovery_active').toString().trim() || 'discovery_active', set_active: setActive }
  if (Array.isArray(seeds)) {
    body.seeds = seeds
  }
  const res = await fetch(`${API_BASE_URL}/api/seeds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await res.json()
  if (!res.ok) {
    throw new Error(payload?.error || 'Failed to update seed list')
  }
  return payload
}

/**
 * Save global model settings (alpha, weights, limits, etc.).
 * POST /api/seeds  (with { settings: ... } body)
 */
export const saveModelSettings = async (settings) => {
  const res = await fetch(`${API_BASE_URL}/api/seeds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.error || 'Failed to save settings')
  }
  return res.json()
}

/**
 * Poll the status of a background graph analysis job.
 * GET /api/analysis/status
 */
export const fetchAnalysisStatus = async () => {
  const res = await fetch(`${API_BASE_URL}/api/analysis/status`)
  if (!res.ok) {
    if (res.status === 404) return null // endpoint not implemented yet
    throw new Error(`Analysis status error: ${res.status}`)
  }
  return res.json()
}

/**
 * Trigger a graph analysis rebuild.
 * POST /api/analysis/run
 */
export const runAnalysis = async () => {
  const res = await fetch(`${API_BASE_URL}/api/analysis/run`, { method: 'POST' })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.error || 'Unable to start analysis.')
  }
  return res.json()
}

/**
 * Fetch discovery recommendations using subgraph mode.
 * POST /api/subgraph/discover
 */
export const fetchDiscoverRecommendations = async ({ seeds, weights, filters, limit, offset, debug = true }) => {
  const res = await fetch(`${API_BASE_URL}/api/subgraph/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seeds, weights, filters, limit, offset, debug }),
  })
  const data = await res.json()
  return { data, ok: res.ok, status: res.status }
}

/**
 * Submit user feedback for a single signal.
 * POST /api/signals/feedback
 */
export const submitSignalFeedback = async ({ accountId, signalName, score, userLabel, context }) => {
  const res = await fetch(`${API_BASE_URL}/api/signals/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_id: accountId,
      signal_name: signalName,
      score,
      user_label: userLabel,
      context,
    }),
  })
  if (!res.ok) {
    throw new Error(`Failed to submit feedback: ${res.status}`)
  }
}

/**
 * Fetch the signal quality report.
 * GET /api/signals/quality
 */
export const fetchSignalQualityReport = async () => {
  const res = await fetch(`${API_BASE_URL}/api/signals/quality`)
  if (!res.ok) {
    throw new Error(`Failed to fetch signal quality report: ${res.status}`)
  }
  return res.json()
}
