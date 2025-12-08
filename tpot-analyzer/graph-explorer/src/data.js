/**
 * API client for graph-explorer backend.
 *
 * Connects to Flask backend running on localhost:5001
 * to fetch graph data and compute metrics dynamically.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';
const API_TIMEOUT_MS = 8000; // Default timeout for fast endpoints
const API_TIMEOUT_SLOW_MS = 30000; // Timeout for slow endpoints (health, clusters, seeds during init)

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

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const fetchWithRetry = async (url, options = {}, { retries = 2, backoffMs = 400, timeoutMs = API_TIMEOUT_MS } = {}) => {
  // Extract external signal (e.g., from caller's AbortController)
  const externalSignal = options.signal;
  
  // If already aborted before we start, bail immediately
  if (externalSignal?.aborted) {
    const err = new Error('Aborted');
    err.name = 'AbortError';
    throw err;
  }

  let attempt = 0;
  let lastError;
  const start = performance.now();
  const attemptsMeta = [];
  
  while (attempt <= retries) {
    // Check external abort before each attempt
    if (externalSignal?.aborted) {
      const err = new Error('Aborted');
      err.name = 'AbortError';
      throw err;
    }

    const attemptStart = performance.now();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    
    // Listen to external signal and propagate abort
    const externalAbortHandler = () => controller.abort();
    externalSignal?.addEventListener('abort', externalAbortHandler);
    
    try {
      console.debug('[API] fetch start', { url, attempt: attempt + 1, timeoutMs });
      const res = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timeout);
      externalSignal?.removeEventListener('abort', externalAbortHandler);
      const dur = Math.round(performance.now() - attemptStart);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText}`);
      }
      console.debug('[API] fetch ok', { url, attempt: attempt + 1, durationMs: dur, totalMs: Math.round(performance.now() - start) });
      attemptsMeta.push({ attempt: attempt + 1, durationMs: dur, totalMs: Math.round(performance.now() - start), success: true, aborted: false, error: null });
      res._timing = { attempt: attempt + 1, durationMs: dur, totalMs: Math.round(performance.now() - start), attempts: [...attemptsMeta] }; // attach timing for consumers
      return res;
    } catch (err) {
      clearTimeout(timeout);
      externalSignal?.removeEventListener('abort', externalAbortHandler);
      lastError = err;
      const dur = Math.round(performance.now() - attemptStart);
      const total = Math.round(performance.now() - start);
      const wasExternalAbort = externalSignal?.aborted;
      attemptsMeta.push({ attempt: attempt + 1, durationMs: dur, totalMs: total, success: false, aborted: err.name === 'AbortError', externalAbort: wasExternalAbort, error: err.message });
      
      // If externally aborted, don't retry - propagate immediately
      if (wasExternalAbort) {
        console.debug('[API] fetch aborted by caller', { url, attempt: attempt + 1, durationMs: dur, totalMs: total });
        throw err;
      }
      
      if (attempt === retries) {
        console.error('[API] fetch failed (no retries left)', { url, attempt: attempt + 1, durationMs: dur, totalMs: total, error: err.message, aborted: err.name === 'AbortError' });
        break;
      }
      const delay = backoffMs * Math.pow(2, attempt);
      console.warn('[API] retrying', { url, attempt: attempt + 1, durationMs: dur, totalMs: total, nextDelayMs: delay, error: err.message, aborted: err.name === 'AbortError' });
      await sleep(delay);
    }
    attempt += 1;
  }
  throw lastError;
};

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
    const response = await fetchWithRetry(`${API_BASE_URL}/api/graph-data?${params}`, {}, { timeoutMs: API_TIMEOUT_SLOW_MS });
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
 * IndexedDB cache for metrics with TTL and request deduplication.
 */
const metricsCache = {
  dbName: 'tpot-metrics-cache',
  storeName: 'metrics-data',
  db: null,
  inFlightRequests: new Map(), // Request deduplication

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
    const { seeds, weights, alpha, resolution, includeShadow, mutualOnly, minFollowers } = options;
    // Sort seeds to ensure consistent cache key
    const sortedSeeds = [...seeds].sort().join(',');
    const weightsStr = weights.join(',');
    return `metrics_${sortedSeeds}_${weightsStr}_${alpha}_${resolution}_${includeShadow}_${mutualOnly}_${minFollowers}`;
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
          const maxAge = 60 * 60 * 1000; // 1 hour - metrics are stable for same seeds

          resolve({
            data,
            isStale: age > maxAge,
            age: Math.floor(age / 1000)
          });
        };
      });
    } catch (error) {
      console.warn('[MetricsCache] Failed to read cache:', error);
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
          console.log(`[MetricsCache] Saved metrics to IndexedDB: ${key.substring(0, 80)}...`);
          resolve();
        };
      });
    } catch (error) {
      console.warn('[MetricsCache] Failed to write cache:', error);
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
          console.log('[MetricsCache] Cleared IndexedDB metrics cache');
          resolve();
        };
      });
    } catch (error) {
      console.warn('[MetricsCache] Failed to clear cache:', error);
    }
  }
};

/**
 * Compute graph metrics with custom seeds and weights.
 * Uses caching and request deduplication to avoid redundant computations.
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
    fast = true,
    skipCache = false,
  } = options;

  const cacheKey = metricsCache.getCacheKey({
    seeds,
    weights,
    alpha,
    resolution,
    includeShadow,
    mutualOnly,
    minFollowers
  });

  // Request deduplication: If identical request is in-flight, wait for it
  if (metricsCache.inFlightRequests.has(cacheKey)) {
    console.log('[MetricsCache] Deduplicating concurrent request, waiting for in-flight request...');
    try {
      return await metricsCache.inFlightRequests.get(cacheKey);
    } catch (error) {
      // If in-flight request failed, fall through to retry
      console.warn('[MetricsCache] In-flight request failed, retrying:', error);
    }
  }

  // Check cache first (unless skipCache is true)
  if (!skipCache) {
    const cached = await metricsCache.get({ seeds, weights, alpha, resolution, includeShadow, mutualOnly, minFollowers });
    if (cached) {
      console.log(
        `[MetricsCache] ${cached.isStale ? 'Stale' : 'Fresh'} cache hit (age: ${cached.age}s) - returning immediately`
      );

      if (cached.isStale) {
        console.log('[MetricsCache] Refreshing stale cache in background...');
        computeMetrics({ ...options, skipCache: true }).then(() => {
          console.log('[MetricsCache] Background refresh complete');
        }).catch(err => {
          console.warn('[MetricsCache] Background refresh failed:', err);
        });
      }

      return cached.data;
    }
  }

  // Create promise for request deduplication
  const requestPromise = (async () => {
    try {
      const response = await fetchWithRetry(`${API_BASE_URL}/api/metrics/compute`, {
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
      }, { timeoutMs: API_TIMEOUT_SLOW_MS });

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

      // Cache the result
      metricsCache.set({ seeds, weights, alpha, resolution, includeShadow, mutualOnly, minFollowers }, data).catch(err => {
        console.warn('[MetricsCache] Failed to save to cache:', err);
      });

      return data;
    } catch (error) {
      const duration = performance.now() - startTime;
      performanceLog.log('computeMetrics [ERROR]', duration, { error: error.message });
      throw error;
    } finally {
      // Remove from in-flight requests
      metricsCache.inFlightRequests.delete(cacheKey);
    }
  })();

  // Store in-flight request
  metricsCache.inFlightRequests.set(cacheKey, requestPromise);

  return requestPromise;
};

/**
 * Fetch available seed presets.
 */
export const fetchPresets = async () => {
  const response = await fetchWithRetry(`${API_BASE_URL}/api/metrics/presets`);
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
    const response = await fetchWithRetry(`${API_BASE_URL}/health`, {}, { retries: 1, backoffMs: 300, timeoutMs: API_TIMEOUT_SLOW_MS });
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
    const response = await fetchWithRetry(`${API_BASE_URL}/api/metrics/performance`);
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
  const response = await fetchWithRetry(`${API_BASE_URL}/api/seeds`, {}, { timeoutMs: API_TIMEOUT_SLOW_MS });
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

  const response = await fetchWithRetry(`${API_BASE_URL}/api/seeds`, {
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
    const response = await fetchWithRetry(`${API_BASE_URL}/api/subgraph/discover`, {
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
  if (!fetchClusterView._inflight) {
    fetchClusterView._inflight = new Map();
  }
  const cacheKey = JSON.stringify({
    n: options.n ?? 25,
    ego: options.ego || '',
    expanded: Array.isArray(options.expanded) ? [...options.expanded].sort() : [],
    collapsed: Array.isArray(options.collapsed) ? [...options.collapsed].sort() : [],
    budget: options.budget ?? 25,
    wl: typeof options.wl === 'number' ? Math.min(1, Math.max(0, options.wl)).toFixed(2) : '0.00',
    expand_depth: typeof options.expand_depth === 'number'
      ? Math.min(1, Math.max(0, options.expand_depth)).toFixed(2)
      : '0.50',
  });
  const inflight = fetchClusterView._inflight.get(cacheKey);
  if (inflight) {
    console.debug('[API] fetchClusterView inflight dedupe hit', { cacheKey });
    // Must await and destructure to match the normal return shape
    const { data, timing } = await inflight;
    const total = Math.round(performance.now() - startTime);
    return { ...data, _timing: { totalMs: total, lastAttempt: timing, attempts: [], deduped: true } };
  }
  const params = new URLSearchParams();
  const granularity = options.n ?? 25;
  params.set('n', granularity);
  if (options.ego) params.set('ego', options.ego);
  if (options.focus) params.set('focus', options.focus);
  if (Array.isArray(options.expanded) && options.expanded.length) {
    params.set('expanded', options.expanded.join(','));
  }
  if (Array.isArray(options.collapsed) && options.collapsed.length) {
    params.set('collapsed', options.collapsed.join(','));
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

  const attemptMeta = { attempts: [] };
  const url = `${API_BASE_URL}/api/clusters?${params.toString()}`;

  // Extract signal before storing promise (signal shouldn't be part of cache key)
  const { signal } = options;

  try {
    console.log('[API] Dedup check (clusters)', {
      cacheKey,
      hasInflight: !!inflight,
      mapSize: fetchClusterView._inflight.size,
      mapKeysSample: Array.from(fetchClusterView._inflight.keys()).slice(0, 3),
    });

    const promise = (async () => {
      const res = await fetchWithRetry(url, { signal }, { timeoutMs: API_TIMEOUT_SLOW_MS });
      const rawText = await res.clone().text();
      console.log('[API] Raw cluster response', {
        url,
        status: res.status,
        statusText: res.statusText,
        bodyLength: rawText.length,
        bodyPreview: rawText.slice(0, 200),
        timing: res._timing,
      });
      const data = rawText ? JSON.parse(rawText) : {};
      return { data, timing: res._timing };
    })();
    fetchClusterView._inflight.set(cacheKey, promise);

    const { data, timing } = await promise;
    const total = Math.round(performance.now() - startTime);
    performanceLog.log('fetchClusterView', total, { granularity, ego: options.ego, attempts: attemptMeta.attempts, lastAttempt: timing });
    return { ...data, _timing: { totalMs: total, lastAttempt: timing, attempts: attemptMeta.attempts } };
  } catch (error) {
    const duration = performance.now() - startTime;
    // Don't log aborts as errors - they're expected when requests are superseded
    if (error.name === 'AbortError') {
      console.debug('[API] fetchClusterView aborted (expected)', { duration: Math.round(duration), ego: options.ego, cacheKey });
    } else {
      performanceLog.log('fetchClusterView [ERROR]', duration, { error: error.message });
    }
    throw error;
  } finally {
    fetchClusterView._inflight.delete(cacheKey);
  }
};

export const fetchClusterMembers = async ({ clusterId, n = 25, wl = 0, expand_depth = 0.5, ego, expanded = [], collapsed = [], focus, limit = 100, offset = 0 }) => {
  const params = new URLSearchParams();
  params.set('n', n);
  params.set('limit', limit);
  params.set('offset', offset);
  if (ego) params.set('ego', ego);
  if (focus) params.set('focus', focus);
  if (Array.isArray(expanded) && expanded.length) {
    params.set('expanded', expanded.join(','));
  }
  if (Array.isArray(collapsed) && collapsed.length) {
    params.set('collapsed', collapsed.join(','));
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

export const fetchClusterPreview = async ({ clusterId, n = 25, expand_depth = 0.5, budget = 25, expanded = [], collapsed = [], visible = [] }) => {
  const params = new URLSearchParams();
  params.set('n', n);
  params.set('budget', budget);
  params.set('expand_depth', Math.min(1, Math.max(0, expand_depth)).toFixed(2));
  if (Array.isArray(expanded) && expanded.length) {
    params.set('expanded', expanded.join(','));
  }
  if (Array.isArray(collapsed) && collapsed.length) {
    params.set('collapsed', collapsed.join(','));
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

/**
 * Clear metrics cache.
 */
export const clearMetricsCache = () => {
  metricsCache.clear();
};

// Expose caches to window for debugging
if (typeof window !== 'undefined') {
  window.graphCache = graphCache;
  window.metricsCache = metricsCache;
}
