/**
 * Shared configuration constants for graph-explorer.
 *
 * Single source of truth for API URLs, default seeds, weights, and timeouts.
 * All files should import from here instead of defining their own copies.
 */

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001'

export const API_TIMEOUT_MS = 8000       // Default timeout for fast endpoints
export const API_TIMEOUT_SLOW_MS = 30000 // Timeout for slow endpoints (health, clusters, seeds during init)

export const DEFAULT_ACCOUNT = 'adityaarpitha'

export const DEFAULT_SEEDS = [
  'prerationalist',
  'gptbrooke',
  'the_wilderless',
  'nosilverv',
  'qorprate',
  'vividvoid_',
  'pli_cachete',
  'goblinodds',
  'eigenrobot',
  'pragueyerrr',
  'exgenesis',
  'becomingcritter',
  'astridwilde1',
  'malcolm_ocean',
  'm_ashcroft',
  'visakanv',
  'drmaciver',
  'tasshinfogleman',
]

export const DEFAULT_PRESETS = {
  "Adi's Seeds": DEFAULT_SEEDS,
}

export const DEFAULT_WEIGHTS = {
  neighbor_overlap: 0.4,
  pagerank: 0.3,
  community: 0.2,
  path_distance: 0.1,
}
