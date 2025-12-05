/**
 * Client-side metrics utilities for fast composite score computation.
 *
 * These functions allow recomputing composite scores without backend calls
 * when only weights change. This reduces response time from 500-2000ms to <1ms.
 */

/**
 * Normalize scores to [0, 1] range.
 *
 * @param {Object<string, number>} scores - Raw scores by node ID
 * @returns {Object<string, number>} Normalized scores
 */
export function normalizeScores(scores) {
  const values = Object.values(scores);

  if (values.length === 0) {
    return {};
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;

  // If all values are equal, return 0.5 for all
  if (range === 0) {
    const result = {};
    for (const nodeId in scores) {
      result[nodeId] = 0.5;
    }
    return result;
  }

  // Normalize to [0, 1]
  const normalized = {};
  for (const nodeId in scores) {
    normalized[nodeId] = (scores[nodeId] - min) / range;
  }

  return normalized;
}

/**
 * Compute composite scores from base metrics.
 *
 * This is the same calculation the backend does:
 * composite = α * pagerank + β * betweenness + γ * engagement
 *
 * @param {Object} baseMetrics - Base metrics from backend
 * @param {Object<string, number>} baseMetrics.pagerank - PageRank scores
 * @param {Object<string, number>} baseMetrics.betweenness - Betweenness scores
 * @param {Object<string, number>} baseMetrics.engagement - Engagement scores
 * @param {number[]} weights - [alpha, beta, gamma] weights
 * @returns {Object<string, number>} Composite scores by node ID
 */
export function computeCompositeScores(baseMetrics, weights) {
  const [alpha, beta, gamma] = weights;

  // Normalize base metrics to [0, 1] range
  const prNorm = normalizeScores(baseMetrics.pagerank);
  const btNorm = normalizeScores(baseMetrics.betweenness);
  const engNorm = normalizeScores(baseMetrics.engagement);

  // Compute weighted sum
  const composite = {};
  const nodeIds = Object.keys(baseMetrics.pagerank);

  for (const nodeId of nodeIds) {
    composite[nodeId] =
      alpha * (prNorm[nodeId] || 0) +
      beta * (btNorm[nodeId] || 0) +
      gamma * (engNorm[nodeId] || 0);
  }

  return composite;
}

/**
 * Get top N nodes by score.
 *
 * @param {Object<string, number>} scores - Scores by node ID
 * @param {number} n - Number of top nodes to return
 * @returns {Array<[string, number]>} Top N [nodeId, score] pairs, sorted descending
 */
export function getTopScores(scores, n = 20) {
  return Object.entries(scores)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

/**
 * Validate that weights sum to approximately 1.0.
 *
 * @param {number[]} weights - [alpha, beta, gamma] weights
 * @param {number} tolerance - Allowed deviation from 1.0 (default: 0.01)
 * @returns {boolean} True if weights are valid
 */
export function validateWeights(weights, tolerance = 0.01) {
  const sum = weights.reduce((a, b) => a + b, 0);
  return Math.abs(sum - 1.0) < tolerance;
}

/**
 * Check if two arrays of weights are approximately equal.
 *
 * @param {number[]} weights1 - First weights array
 * @param {number[]} weights2 - Second weights array
 * @param {number} epsilon - Tolerance for floating point comparison
 * @returns {boolean} True if weights are approximately equal
 */
export function weightsEqual(weights1, weights2, epsilon = 0.001) {
  if (weights1.length !== weights2.length) {
    return false;
  }

  for (let i = 0; i < weights1.length; i++) {
    if (Math.abs(weights1[i] - weights2[i]) > epsilon) {
      return false;
    }
  }

  return true;
}

/**
 * Create a cache key for base metrics.
 *
 * @param {Object} params - Parameters for metrics computation
 * @param {string[]} params.seeds - Seed usernames/IDs
 * @param {number} params.alpha - PageRank alpha
 * @param {number} params.resolution - Louvain resolution
 * @param {boolean} params.includeShadow - Include shadow nodes
 * @param {boolean} params.mutualOnly - Only mutual edges
 * @param {number} params.minFollowers - Min followers filter
 * @returns {string} Cache key
 */
export function createBaseMetricsCacheKey(params) {
  const {
    seeds = [],
    alpha = 0.85,
    resolution = 1.0,
    includeShadow = true,
    mutualOnly = false,
    minFollowers = 0,
  } = params;

  // Sort seeds for consistent key
  const sortedSeeds = [...seeds].sort().join(',');

  return `base:${sortedSeeds}:${alpha}:${resolution}:${includeShadow}:${mutualOnly}:${minFollowers}`;
}

/**
 * Performance timer utility.
 */
export class PerformanceTimer {
  constructor(operation) {
    this.operation = operation;
    this.startTime = performance.now();
  }

  end(details = {}) {
    const duration = performance.now() - this.startTime;
    const color = duration < 10 ? 'green' : duration < 50 ? 'orange' : 'red';

    console.log(
      `%c[CLIENT] ${this.operation}: ${duration.toFixed(2)}ms`,
      `color: ${color}; font-weight: bold`,
      details
    );

    return duration;
  }
}

/**
 * Simple in-memory cache for base metrics.
 *
 * Stores base metrics to avoid re-fetching when only weights change.
 */
class BaseMetricsCache {
  constructor(maxSize = 10) {
    this.cache = new Map();
    this.maxSize = maxSize;
    this.stats = {
      hits: 0,
      misses: 0,
    };
  }

  get(key) {
    if (this.cache.has(key)) {
      this.stats.hits++;
      const entry = this.cache.get(key);

      // Move to end (LRU)
      this.cache.delete(key);
      this.cache.set(key, entry);

      console.log(`%c[CACHE HIT] Base metrics`, 'color: green; font-weight: bold', {
        key: key.substring(0, 50) + '...',
        hitRate: `${((this.stats.hits / (this.stats.hits + this.stats.misses)) * 100).toFixed(1)}%`
      });

      return entry;
    }

    this.stats.misses++;
    console.log(`%c[CACHE MISS] Base metrics`, 'color: orange; font-weight: bold', {
      key: key.substring(0, 50) + '...'
    });
    return null;
  }

  set(key, value) {
    // Evict oldest if at capacity
    if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
      console.log(`%c[CACHE EVICT]`, 'color: gray', { evicted: firstKey.substring(0, 30) + '...' });
    }

    this.cache.set(key, value);
    console.log(`%c[CACHE SET] Base metrics`, 'color: blue', {
      key: key.substring(0, 50) + '...',
      size: `${this.cache.size}/${this.maxSize}`
    });
  }

  clear() {
    this.cache.clear();
    this.stats = { hits: 0, misses: 0 };
    console.log('%c[CACHE CLEAR] All base metrics cleared', 'color: red; font-weight: bold');
  }

  getStats() {
    const total = this.stats.hits + this.stats.misses;
    const hitRate = total > 0 ? (this.stats.hits / total * 100).toFixed(1) : 0;

    return {
      size: this.cache.size,
      maxSize: this.maxSize,
      hits: this.stats.hits,
      misses: this.stats.misses,
      hitRate: `${hitRate}%`,
    };
  }
}

// Global cache instance
export const baseMetricsCache = new BaseMetricsCache(10);

// Expose to window for debugging
if (typeof window !== 'undefined') {
  window.metricsCache = baseMetricsCache;
}
