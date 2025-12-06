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
 * IndexedDB cache for graph data with TTL.
 * Uses stale-while-revalidate pattern.
 * Much larger quota than localStorage (~50MB+ vs 5-10MB).
 */
const graphCache = {
  dbName: 'tpot-graph-cache',
  storeName: 'graph-data',
  db: null,

  async init() {
    if (this.db) return this.db;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName);
        }
      };
    });
  },

  getCacheKey(options) {
    const { includeShadow, mutualOnly, minFollowers } = options;
    return `graph_data_${includeShadow}_${mutualOnly}_${minFollowers}`;
  },

  async get(options) {
    try {
      await this.init();
      const key = this.getCacheKey(options);

      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([this.storeName], 'readonly');
        const store = transaction.objectStore(this.storeName);
        const request = store.get(key);

        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const cached = request.result;
          if (!cached) {
            resolve(null);
            return;
          }

          const { data, timestamp } = cached;
          const age = Date.now() - timestamp;
          const maxAge = 5 * 60 * 1000; // 5 minutes

          resolve({
            data,
            isStale: age > maxAge,
            age: Math.floor(age / 1000)
          });
        };
      });
    } catch (error) {
      console.warn('[Cache] Failed to read cache:', error);
      return null;
    }
  },

  async set(options, data) {
    try {
      await this.init();
      const key = this.getCacheKey(options);
      const cached = {
        data,
        timestamp: Date.now()
      };

      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([this.storeName], 'readwrite');
        const store = transaction.objectStore(this.storeName);
        const request = store.put(cached, key);

        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          console.log(`[Cache] Saved graph data to IndexedDB: ${key}`);
          resolve();
        };
      });
    } catch (error) {
      console.warn('[Cache] Failed to write cache:', error);
      await this.clear();
    }
  },

  async clear() {
    try {
      await this.init();
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([this.storeName], 'readwrite');
        const store = transaction.objectStore(this.storeName);
        const request = store.clear();

        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          console.log('[Cache] Cleared IndexedDB graph cache');
          resolve();
        };
      });
    } catch (error) {
      console.warn('[Cache] Failed to clear cache:', error);
    }
  }
};

/**
 * Fetch raw graph structure (nodes and edges) from backend.
 * Uses IndexedDB cache with stale-while-revalidate pattern.
 */
export const fetchGraphData = async (options = {}) => {
  const startTime = performance.now();

  const {
    includeShadow = true,
    mutualOnly = false,
    minFollowers = 0,
    skipCache = false,
  } = options;

  // Check cache first (unless skipCache is true)
  if (!skipCache) {
    const cached = await graphCache.get({ includeShadow, mutualOnly, minFollowers });
    if (cached) {
      console.log(
        `[Cache] ${cached.isStale ? 'Stale' : 'Fresh'} cache hit (age: ${cached.age}s) - returning immediately`
      );

      if (cached.isStale) {
        console.log('[Cache] Refreshing stale cache in background...');
        fetchGraphData({ ...options, skipCache: true }).then(() => {
          console.log('[Cache] Background refresh complete');
        }).catch(err => {
          console.warn('[Cache] Background refresh failed:', err);
        });
      }

      return cached.data;
    }
  }

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
    const serverTime = response.headers.get('X-Response-Time');

    performanceLog.log('fetchGraphData', duration, {
      serverTime,
      nodeCount: data.directed_nodes,
      edgeCount: data.directed_edges,
      includeShadow,
      fromCache: false,
    });

    graphCache.set({ includeShadow, mutualOnly, minFollowers }, data).catch(err => {
      console.warn('[Cache] Failed to save to cache:', err);
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
    fast = true,  // Default to fast mode - reuses snapshot when possible
  } = options;

  try {
    const response = await fetch(`${API_BASE_URL}/api/metrics/compute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seeds,
        weights,
        alpha,
        resolution,
        include_shadow: includeShadow,
        mutual_only: mutualOnly,
        min_followers: minFollowers,
        fast,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to compute metrics: ${response.statusText}`);
    }

    const data = await response.json();
    const duration = performance.now() - startTime;
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

export const fetchGraphSettings = async () => {
  const response = await fetch(`${API_BASE_URL}/api/seeds`);
  if (!response.ok) {
    throw new Error(`Failed to fetch graph settings: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Persist a seed list to the backend.
 */
export const saveSeedList = async ({ name, seeds = [], setActive = true } = {}) => {
  const targetName = (name || '').trim();
  if (!targetName) {
    throw new Error('A seed list name is required');
  }

  const payload = {
    name: targetName,
    set_active: Boolean(setActive)
  };

  if (Array.isArray(seeds)) {
    payload.seeds = seeds;
  }

  const response = await fetch(`${API_BASE_URL}/api/seeds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.error || `Failed to persist seed list (${response.status})`);
  }
  return data?.state || null;
};

/**
 * Fetch discovery ranking for a given seed configuration.
 */
export const fetchDiscoveryRanking = async ({
  seeds = [],
  weights = {},
  filters = {},
  limit = 200,
  offset = 0,
} = {}) => {
  const startTime = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}/api/subgraph/discover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seeds,
        weights,
        filters,
        limit,
        offset,
        debug: false,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch discovery ranking: ${response.statusText}`);
    }

    const data = await response.json();
    const duration = performance.now() - startTime;
    performanceLog.log('fetchDiscoveryRanking', duration, {
      seedCount: seeds.length,
      limit,
      offset,
    });
    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('fetchDiscoveryRanking [ERROR]', duration, { error: error.message });
    throw error;
  }
};

/**
 * Fetch clustered view from /api/clusters with optional Louvain weight.
 *
 * @param {Object} options
 * @param {number} [options.n=25] Granularity
 * @param {string} [options.ego] Ego node id
 * @param {number} [options.wl=0] Louvain weight (0..1)
 * @param {string} [options.focus] Focus cluster id
 */
export const fetchClusterView = async (options = {}) => {
  const startTime = performance.now();
  const params = new URLSearchParams();
  const granularity = options.n ?? 25;
  params.set('n', granularity);
  if (options.ego) params.set('ego', options.ego);
  if (options.focus) params.set('focus', options.focus);
  if (Array.isArray(options.expanded) && options.expanded.length) {
    params.set('expanded', options.expanded.join(','));
  }
  if (typeof options.budget === 'number') {
    params.set('budget', options.budget);
  }
  if (typeof options.wl === 'number') {
    const wl = Math.min(1, Math.max(0, options.wl));
    params.set('wl', wl.toFixed(2));
  }
  if (typeof options.expand_depth === 'number') {
    const ed = Math.min(1, Math.max(0, options.expand_depth));
    params.set('expand_depth', ed.toFixed(2));
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/clusters?${params.toString()}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch clusters: ${response.statusText}`);
    }
    const data = await response.json();
    performanceLog.log('fetchClusterView', performance.now() - startTime, { granularity, ego: options.ego });
    return data;
  } catch (error) {
    const duration = performance.now() - startTime;
    performanceLog.log('fetchClusterView [ERROR]', duration, { error: error.message });
    throw error;
  }
};

export const fetchClusterMembers = async ({ clusterId, n = 25, wl = 0, expand_depth = 0.5, ego, expanded = [], focus, limit = 100, offset = 0 }) => {
  const params = new URLSearchParams();
  params.set('n', n);
  params.set('limit', limit);
  params.set('offset', offset);
  if (ego) params.set('ego', ego);
  if (focus) params.set('focus', focus);
  if (Array.isArray(expanded) && expanded.length) {
    params.set('expanded', expanded.join(','));
  }
  params.set('wl', Math.min(1, Math.max(0, wl)).toFixed(2));
  params.set('expand_depth', Math.min(1, Math.max(0, expand_depth)).toFixed(2));

  const response = await fetch(`${API_BASE_URL}/api/clusters/${clusterId}/members?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch members: ${response.statusText}`);
  }
  return response.json();
};

export const setClusterLabel = async ({ clusterId, n = 25, wl = 0, label }) => {
  const params = new URLSearchParams();
  params.set('n', n);
  params.set('wl', Math.min(1, Math.max(0, wl)).toFixed(2));
  const response = await fetch(`${API_BASE_URL}/api/clusters/${clusterId}/label?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  });
  if (!response.ok) {
    throw new Error(`Failed to set label: ${response.statusText}`);
  }
  return response.json();
};

export const deleteClusterLabel = async ({ clusterId, n = 25, wl = 0 }) => {
  const params = new URLSearchParams();
  params.set('n', n);
  params.set('wl', Math.min(1, Math.max(0, wl)).toFixed(2));
  const response = await fetch(`${API_BASE_URL}/api/clusters/${clusterId}/label?${params.toString()}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`Failed to delete label: ${response.statusText}`);
  }
  return response.json();
};

export const fetchClusterPreview = async ({ clusterId, n = 25, expand_depth = 0.5, budget = 25, expanded = [], visible = [] }) => {
  const params = new URLSearchParams();
  params.set('n', n);
  params.set('budget', budget);
  params.set('expand_depth', Math.min(1, Math.max(0, expand_depth)).toFixed(2));
  if (Array.isArray(expanded) && expanded.length) {
    params.set('expanded', expanded.join(','));
  }
  if (Array.isArray(visible) && visible.length) {
    params.set('visible', visible.join(','));
  }
  const response = await fetch(`${API_BASE_URL}/api/clusters/${clusterId}/preview?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch preview: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Get client-side performance statistics.
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
 * Clear graph data cache.
 */
export const clearGraphCache = () => {
  graphCache.clear();
};

// Expose cache to window for debugging
if (typeof window !== 'undefined') {
  window.graphCache = graphCache;
}
