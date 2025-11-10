/**
 * API client for graph-explorer backend.
 *
 * Connects to Flask backend running on localhost:5001
 * to fetch graph data and compute metrics dynamically.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';

/**
 * Performance tracking utility.
 */
const performanceLog = {
  calls: [],
  log(operation, duration, details = {}) {
    const entry = {
      operation,
      duration_ms: duration,
      timestamp: new Date().toISOString(),
      ...details,
    };
    this.calls.push(entry);

    // Log to console with color coding
    const color = duration < 500 ? 'green' : duration < 1000 ? 'orange' : 'red';
    console.log(
      `%c[API] ${operation}: ${duration.toFixed(2)}ms`,
      `color: ${color}; font-weight: bold`,
      details
    );

    // Keep only last 100 entries
    if (this.calls.length > 100) {
      this.calls = this.calls.slice(-100);
    }
  },
  getStats() {
    const byOperation = {};
    this.calls.forEach(call => {
      if (!byOperation[call.operation]) {
        byOperation[call.operation] = [];
      }
      byOperation[call.operation].push(call.duration_ms);
    });

    const stats = {};
    Object.entries(byOperation).forEach(([op, durations]) => {
      const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
      stats[op] = {
        count: durations.length,
        avg: avg.toFixed(2),
        min: Math.min(...durations).toFixed(2),
        max: Math.max(...durations).toFixed(2),
      };
    });
    return stats;
  },
  clear() {
    this.calls = [];
  }
};

// Expose to window for debugging
if (typeof window !== 'undefined') {
  window.apiPerformance = performanceLog;
}

/**
 * Fetch raw graph structure (nodes and edges) from backend.
 *
 * @param {Object} options - Graph options
 * @param {boolean} options.includeShadow - Include shadow nodes (default: true)
 * @param {boolean} options.mutualOnly - Only mutual edges (default: false)
 * @param {number} options.minFollowers - Min followers filter (default: 0)
 * @returns {Promise<Object>} Graph data with nodes and edges
 */
export const fetchGraphData = async (options = {}) => {
  const startTime = performance.now();

  const {
    includeShadow = true,
    mutualOnly = false,
    minFollowers = 0,
  } = options;

  const params = new URLSearchParams({
    include_shadow: includeShadow.toString(),
    mutual_only: mutualOnly.toString(),
    min_followers: minFollowers.toString(),
  });

  try {
    const response = await fetch(`${API_BASE_URL}/api/graph-data?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch graph data: ${response.statusText}`);
    }

    const data = await response.json();
    const duration = performance.now() - startTime;

    // Extract server timing from header
    const serverTime = response.headers.get('X-Response-Time');

    performanceLog.log('fetchGraphData', duration, {
      serverTime,
      nodeCount: data.directed_nodes,
      edgeCount: data.directed_edges,
      includeShadow,
    });

    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('fetchGraphData [ERROR]', duration, { error: error.message });
    throw error;
  }
};

/**
 * Compute graph metrics with custom seeds and weights.
 *
 * @param {Object} options - Computation options
 * @param {string[]} options.seeds - Seed usernames/account_ids
 * @param {number[]} options.weights - [alpha, beta, gamma] for PageRank, Betweenness, Engagement
 * @param {number} options.alpha - PageRank damping factor (default: 0.85)
 * @param {number} options.resolution - Louvain resolution (default: 1.0)
 * @param {boolean} options.includeShadow - Include shadow nodes (default: true)
 * @param {boolean} options.mutualOnly - Only mutual edges (default: false)
 * @param {number} options.minFollowers - Min followers filter (default: 0)
 * @returns {Promise<Object>} Computed metrics
 */
export const computeMetrics = async (options = {}) => {
  const startTime = performance.now();

  const {
    seeds = [],
    weights = [0.4, 0.3, 0.3],
    alpha = 0.85,
    resolution = 1.0,
    includeShadow = true,
    mutualOnly = false,
    minFollowers = 0,
  } = options;

  try {
    const response = await fetch(`${API_BASE_URL}/api/metrics/compute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        seeds,
        weights,
        alpha,
        resolution,
        include_shadow: includeShadow,
        mutual_only: mutualOnly,
        min_followers: minFollowers,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to compute metrics: ${response.statusText}`);
    }

    const data = await response.json();
    const duration = performance.now() - startTime;

    // Extract server timing from header
    const serverTime = response.headers.get('X-Response-Time');

    performanceLog.log('computeMetrics', duration, {
      serverTime,
      seedCount: seeds.length,
      resolvedSeeds: data.resolved_seeds?.length || 0,
      weights,
    });

    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('computeMetrics [ERROR]', duration, { error: error.message });
    throw error;
  }
};

/**
 * Fetch available seed presets.
 *
 * @returns {Promise<Object>} Preset configurations
 */
export const fetchPresets = async () => {
  const response = await fetch(`${API_BASE_URL}/api/metrics/presets`);
  if (!response.ok) {
    throw new Error(`Failed to fetch presets: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Check if backend is available.
 *
 * @returns {Promise<boolean>} True if backend is healthy
 */
export const checkHealth = async () => {
  const startTime = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    const duration = performance.now() - startTime;
    performanceLog.log('checkHealth', duration, { ok: response.ok });
    return response.ok;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('checkHealth [ERROR]', duration, { error: error.message });
    return false;
  }
};

/**
 * Fetch backend performance metrics.
 *
 * @returns {Promise<Object>} Performance metrics from backend
 */
export const fetchPerformanceMetrics = async () => {
  const startTime = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}/api/metrics/performance`);
    if (!response.ok) {
      throw new Error(`Failed to fetch performance metrics: ${response.statusText}`);
    }
    const data = await response.json();
    const duration = performance.now() - startTime;
    performanceLog.log('fetchPerformanceMetrics', duration);
    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('fetchPerformanceMetrics [ERROR]', duration, { error: error.message });
    throw error;
  }
};

/**
 * Get client-side performance statistics.
 *
 * @returns {Object} Performance statistics
 */
export const getClientPerformanceStats = () => {
  return performanceLog.getStats();
};

/**
 * Clear client-side performance logs.
 */
export const clearClientPerformanceLogs = () => {
  performanceLog.clear();
};
/**
 * Fetch base metrics WITHOUT composite scores for client-side reweighting.
 *
 * This is the optimized endpoint - it caches PageRank, betweenness, and engagement.
 * Composite scores can be computed client-side in <1ms when weights change.
 *
 * @param {Object} options - Computation options (same as computeMetrics, minus weights)
 * @param {string[]} options.seeds - Seed usernames/account_ids
 * @param {number} options.alpha - PageRank damping factor (default: 0.85)
 * @param {number} options.resolution - Louvain resolution (default: 1.0)
 * @param {boolean} options.includeShadow - Include shadow nodes (default: true)
 * @param {boolean} options.mutualOnly - Only mutual edges (default: false)
 * @param {number} options.minFollowers - Min followers filter (default: 0)
 * @returns {Promise<Object>} Base metrics (without composite)
 */
export const fetchBaseMetrics = async (options = {}) => {
  const startTime = performance.now();

  const {
    seeds = [],
    alpha = 0.85,
    resolution = 1.0,
    includeShadow = true,
    mutualOnly = false,
    minFollowers = 0,
  } = options;

  try {
    const response = await fetch(`${API_BASE_URL}/api/metrics/base`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        seeds,
        alpha,
        resolution,
        include_shadow: includeShadow,
        mutual_only: mutualOnly,
        min_followers: minFollowers,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch base metrics: ${response.statusText}`);
    }

    const data = await response.json();
    const duration = performance.now() - startTime;

    // Extract server timing and cache status
    const serverTime = response.headers.get('X-Response-Time');
    const cacheStatus = response.headers.get('X-Cache-Status') || 'UNKNOWN';

    performanceLog.log('fetchBaseMetrics', duration, {
      serverTime,
      cacheStatus,
      seedCount: seeds.length,
      resolvedSeeds: data.resolved_seeds?.length || 0,
    });

    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('fetchBaseMetrics [ERROR]', duration, { error: error.message });
    throw error;
  }
};

/**
 * Fetch cache statistics from backend.
 *
 * @returns {Promise<Object>} Cache stats (hit rate, size, entries)
 */
export const fetchCacheStats = async () => {
  const startTime = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}/api/cache/stats`);
    if (!response.ok) {
      throw new Error(`Failed to fetch cache stats: ${response.statusText}`);
    }
    const data = await response.json();
    const duration = performance.now() - startTime;
    performanceLog.log('fetchCacheStats', duration);
    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('fetchCacheStats [ERROR]', duration, { error: error.message });
    throw error;
  }
};

/**
 * Invalidate backend cache.
 *
 * @param {string|null} prefix - Cache prefix to invalidate ('graph', 'pagerank', etc) or null for all
 * @returns {Promise<Object>} Invalidation result
 */
export const invalidateCache = async (prefix = null) => {
  const startTime = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}/api/cache/invalidate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ prefix }),
    });

    if (!response.ok) {
      throw new Error(`Failed to invalidate cache: ${response.statusText}`);
    }

    const data = await response.json();
    const duration = performance.now() - startTime;
    performanceLog.log('invalidateCache', duration, { prefix: prefix || 'all', invalidated: data.invalidated });
    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('invalidateCache [ERROR]', duration, { error: error.message });
    throw error;
  }
};
