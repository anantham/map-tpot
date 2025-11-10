/**
 * Unit tests for metricsUtils.js
 *
 * Tests client-side metrics computation and caching utilities.
 * These functions enable fast client-side reweighting without backend calls.
 *
 * To run these tests:
 * npm install --save-dev vitest
 * npx vitest run metricsUtils.test.js
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  normalizeScores,
  computeCompositeScores,
  getTopScores,
  validateWeights,
  weightsEqual,
  createBaseMetricsCacheKey,
  PerformanceTimer,
  baseMetricsCache,
} from './metricsUtils.js';

// ==============================================================================
// normalizeScores Tests
// ==============================================================================

describe('normalizeScores', () => {
  it('should normalize scores to [0, 1] range', () => {
    const scores = {
      node1: 10,
      node2: 50,
      node3: 30,
    };

    const normalized = normalizeScores(scores);

    expect(normalized.node1).toBe(0.0); // Min value
    expect(normalized.node2).toBe(1.0); // Max value
    expect(normalized.node3).toBe(0.5); // Middle value
  });

  it('should return 0.5 for all nodes when all scores are equal', () => {
    const scores = {
      node1: 42,
      node2: 42,
      node3: 42,
    };

    const normalized = normalizeScores(scores);

    expect(normalized.node1).toBe(0.5);
    expect(normalized.node2).toBe(0.5);
    expect(normalized.node3).toBe(0.5);
  });

  it('should return empty object for empty input', () => {
    const scores = {};
    const normalized = normalizeScores(scores);
    expect(normalized).toEqual({});
  });

  it('should handle single node', () => {
    const scores = { node1: 100 };
    const normalized = normalizeScores(scores);
    expect(normalized.node1).toBe(0.5); // Single value = all equal
  });

  it('should handle negative scores', () => {
    const scores = {
      node1: -10,
      node2: 0,
      node3: 10,
    };

    const normalized = normalizeScores(scores);

    expect(normalized.node1).toBe(0.0);
    expect(normalized.node2).toBe(0.5);
    expect(normalized.node3).toBe(1.0);
  });

  it('should preserve node IDs', () => {
    const scores = {
      'alice': 1,
      'bob': 2,
      'charlie': 3,
    };

    const normalized = normalizeScores(scores);

    expect(Object.keys(normalized)).toEqual(['alice', 'bob', 'charlie']);
  });
});

// ==============================================================================
// computeCompositeScores Tests
// ==============================================================================

describe('computeCompositeScores', () => {
  const baseMetrics = {
    pagerank: {
      node1: 0.5,
      node2: 0.3,
      node3: 0.2,
    },
    betweenness: {
      node1: 0.1,
      node2: 0.7,
      node3: 0.2,
    },
    engagement: {
      node1: 0.8,
      node2: 0.4,
      node3: 0.3,
    },
  };

  it('should compute composite scores with equal weights', () => {
    const weights = [1 / 3, 1 / 3, 1 / 3];
    const composite = computeCompositeScores(baseMetrics, weights);

    expect(Object.keys(composite)).toEqual(['node1', 'node2', 'node3']);
    expect(composite.node1).toBeGreaterThan(0);
    expect(composite.node2).toBeGreaterThan(0);
    expect(composite.node3).toBeGreaterThan(0);
  });

  it('should weight PageRank higher with [1, 0, 0]', () => {
    const weightsPageRankOnly = [1.0, 0.0, 0.0];
    const composite = computeCompositeScores(baseMetrics, weightsPageRankOnly);

    // With weights [1, 0, 0], ranking should match PageRank
    // node1 (0.5) > node2 (0.3) > node3 (0.2)
    expect(composite.node1).toBeGreaterThan(composite.node2);
    expect(composite.node2).toBeGreaterThan(composite.node3);
  });

  it('should weight betweenness higher with [0, 1, 0]', () => {
    const weightsBetweennessOnly = [0.0, 1.0, 0.0];
    const composite = computeCompositeScores(baseMetrics, weightsBetweennessOnly);

    // With weights [0, 1, 0], ranking should match betweenness
    // node2 (0.7) > node3 (0.2) > node1 (0.1)
    expect(composite.node2).toBeGreaterThan(composite.node3);
    expect(composite.node3).toBeGreaterThan(composite.node1);
  });

  it('should weight engagement higher with [0, 0, 1]', () => {
    const weightsEngagementOnly = [0.0, 0.0, 1.0];
    const composite = computeCompositeScores(baseMetrics, weightsEngagementOnly);

    // With weights [0, 0, 1], ranking should match engagement
    // node1 (0.8) > node2 (0.4) > node3 (0.3)
    expect(composite.node1).toBeGreaterThan(composite.node2);
    expect(composite.node2).toBeGreaterThan(composite.node3);
  });

  it('should return all scores between 0 and 1', () => {
    const weights = [0.4, 0.3, 0.3];
    const composite = computeCompositeScores(baseMetrics, weights);

    Object.values(composite).forEach(score => {
      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(1);
    });
  });

  it('should handle missing nodes gracefully', () => {
    const incompleteMetrics = {
      pagerank: { node1: 0.5, node2: 0.3 },
      betweenness: { node1: 0.1 }, // Missing node2
      engagement: { node1: 0.8, node2: 0.4 },
    };

    const weights = [0.4, 0.3, 0.3];
    const composite = computeCompositeScores(incompleteMetrics, weights);

    // Should not throw, missing values treated as 0
    expect(composite).toBeDefined();
    expect(Object.keys(composite).length).toBe(2);
  });

  it('should produce different results for different weights', () => {
    const weights1 = [0.7, 0.2, 0.1];
    const weights2 = [0.1, 0.2, 0.7];

    const composite1 = computeCompositeScores(baseMetrics, weights1);
    const composite2 = computeCompositeScores(baseMetrics, weights2);

    // Results should be different for at least some nodes
    expect(composite1.node1).not.toBeCloseTo(composite2.node1, 3);
  });
});

// ==============================================================================
// getTopScores Tests
// ==============================================================================

describe('getTopScores', () => {
  const scores = {
    node1: 0.9,
    node2: 0.1,
    node3: 0.7,
    node4: 0.3,
    node5: 0.5,
  };

  it('should return top N scores in descending order', () => {
    const top3 = getTopScores(scores, 3);

    expect(top3).toEqual([
      ['node1', 0.9],
      ['node3', 0.7],
      ['node5', 0.5],
    ]);
  });

  it('should default to top 20 if N not specified', () => {
    const top = getTopScores(scores);
    expect(top.length).toBe(5); // Less than 20 scores available
  });

  it('should handle N larger than scores length', () => {
    const top100 = getTopScores(scores, 100);
    expect(top100.length).toBe(5);
  });

  it('should handle empty scores', () => {
    const empty = getTopScores({}, 10);
    expect(empty).toEqual([]);
  });

  it('should return single score for N=1', () => {
    const top1 = getTopScores(scores, 1);
    expect(top1).toEqual([['node1', 0.9]]);
  });

  it('should handle ties correctly', () => {
    const scoresWithTies = {
      node1: 0.5,
      node2: 0.5,
      node3: 0.3,
    };

    const top2 = getTopScores(scoresWithTies, 2);
    expect(top2.length).toBe(2);
    expect(top2[0][1]).toBe(0.5);
    expect(top2[1][1]).toBe(0.5);
  });
});

// ==============================================================================
// validateWeights Tests
// ==============================================================================

describe('validateWeights', () => {
  it('should accept weights that sum to 1.0', () => {
    expect(validateWeights([0.4, 0.3, 0.3])).toBe(true);
    expect(validateWeights([1.0, 0.0, 0.0])).toBe(true);
    expect(validateWeights([0.33, 0.33, 0.34])).toBe(true);
  });

  it('should reject weights that do not sum to 1.0', () => {
    expect(validateWeights([0.5, 0.5, 0.5])).toBe(false); // Sums to 1.5
    expect(validateWeights([0.1, 0.1, 0.1])).toBe(false); // Sums to 0.3
  });

  it('should handle floating point precision', () => {
    // 0.1 + 0.2 + 0.7 = 0.99999... due to floating point
    const weights = [0.1, 0.2, 0.7];
    expect(validateWeights(weights, 0.01)).toBe(true);
  });

  it('should respect custom tolerance', () => {
    const weights = [0.35, 0.35, 0.35]; // Sums to 1.05

    expect(validateWeights(weights, 0.01)).toBe(false); // Too far
    expect(validateWeights(weights, 0.1)).toBe(true);   // Within tolerance
  });

  it('should handle edge cases', () => {
    expect(validateWeights([1.0])).toBe(true);
    expect(validateWeights([0.0, 0.0, 1.0])).toBe(true);
    expect(validateWeights([0.5, 0.5])).toBe(true);
  });
});

// ==============================================================================
// weightsEqual Tests
// ==============================================================================

describe('weightsEqual', () => {
  it('should return true for identical weights', () => {
    const weights1 = [0.4, 0.3, 0.3];
    const weights2 = [0.4, 0.3, 0.3];

    expect(weightsEqual(weights1, weights2)).toBe(true);
  });

  it('should return false for different weights', () => {
    const weights1 = [0.4, 0.3, 0.3];
    const weights2 = [0.5, 0.3, 0.2];

    expect(weightsEqual(weights1, weights2)).toBe(false);
  });

  it('should handle floating point comparison with epsilon', () => {
    const weights1 = [0.333333, 0.333333, 0.333334];
    const weights2 = [1 / 3, 1 / 3, 1 / 3];

    expect(weightsEqual(weights1, weights2, 0.001)).toBe(true);
    expect(weightsEqual(weights1, weights2, 0.000001)).toBe(false);
  });

  it('should return false for different length arrays', () => {
    const weights1 = [0.5, 0.5];
    const weights2 = [0.4, 0.3, 0.3];

    expect(weightsEqual(weights1, weights2)).toBe(false);
  });

  it('should handle edge cases', () => {
    expect(weightsEqual([], [])).toBe(true);
    expect(weightsEqual([1.0], [1.0])).toBe(true);
    expect(weightsEqual([0.0, 0.0], [0.0, 0.0])).toBe(true);
  });
});

// ==============================================================================
// createBaseMetricsCacheKey Tests
// ==============================================================================

describe('createBaseMetricsCacheKey', () => {
  it('should create deterministic cache key', () => {
    const params = {
      seeds: ['alice', 'bob'],
      alpha: 0.85,
      resolution: 1.0,
      includeShadow: true,
      mutualOnly: false,
      minFollowers: 0,
    };

    const key1 = createBaseMetricsCacheKey(params);
    const key2 = createBaseMetricsCacheKey(params);

    expect(key1).toBe(key2);
  });

  it('should create different keys for different seeds', () => {
    const params1 = { seeds: ['alice'] };
    const params2 = { seeds: ['bob'] };

    const key1 = createBaseMetricsCacheKey(params1);
    const key2 = createBaseMetricsCacheKey(params2);

    expect(key1).not.toBe(key2);
  });

  it('should create different keys for different alpha', () => {
    const params1 = { seeds: ['alice'], alpha: 0.85 };
    const params2 = { seeds: ['alice'], alpha: 0.90 };

    const key1 = createBaseMetricsCacheKey(params1);
    const key2 = createBaseMetricsCacheKey(params2);

    expect(key1).not.toBe(key2);
  });

  it('should sort seeds for consistent key', () => {
    const params1 = { seeds: ['alice', 'bob', 'charlie'] };
    const params2 = { seeds: ['charlie', 'alice', 'bob'] };

    const key1 = createBaseMetricsCacheKey(params1);
    const key2 = createBaseMetricsCacheKey(params2);

    expect(key1).toBe(key2);
  });

  it('should use default values when params missing', () => {
    const params = { seeds: ['alice'] };
    const key = createBaseMetricsCacheKey(params);

    expect(key).toContain('0.85'); // Default alpha
    expect(key).toContain('1.0');  // Default resolution
    expect(key).toContain('true'); // Default includeShadow
  });

  it('should include all parameters in key', () => {
    const params = {
      seeds: ['alice'],
      alpha: 0.90,
      resolution: 1.5,
      includeShadow: false,
      mutualOnly: true,
      minFollowers: 100,
    };

    const key = createBaseMetricsCacheKey(params);

    expect(key).toContain('alice');
    expect(key).toContain('0.90');
    expect(key).toContain('1.5');
    expect(key).toContain('false');
    expect(key).toContain('true');
    expect(key).toContain('100');
  });
});

// ==============================================================================
// PerformanceTimer Tests
// ==============================================================================

describe('PerformanceTimer', () => {
  it('should measure elapsed time', () => {
    const timer = new PerformanceTimer('test');

    // Simulate some work
    const start = performance.now();
    while (performance.now() - start < 10) {
      // Busy wait for ~10ms
    }

    const duration = timer.end();

    expect(duration).toBeGreaterThanOrEqual(10);
    expect(duration).toBeLessThan(50); // Shouldn't take too long
  });

  it('should accept operation name', () => {
    const timer = new PerformanceTimer('testOperation');
    expect(timer.operation).toBe('testOperation');
  });

  it('should return duration from end()', () => {
    const timer = new PerformanceTimer('test');
    const duration = timer.end();

    expect(typeof duration).toBe('number');
    expect(duration).toBeGreaterThanOrEqual(0);
  });

  it('should accept details object in end()', () => {
    const timer = new PerformanceTimer('test');
    const duration = timer.end({ foo: 'bar', count: 42 });

    expect(duration).toBeGreaterThanOrEqual(0);
  });
});

// ==============================================================================
// BaseMetricsCache Tests
// ==============================================================================

describe('BaseMetricsCache', () => {
  beforeEach(() => {
    // Clear cache before each test
    baseMetricsCache.clear();
  });

  it('should store and retrieve values', () => {
    const key = 'test:key';
    const value = { data: 'test' };

    baseMetricsCache.set(key, value);
    const retrieved = baseMetricsCache.get(key);

    expect(retrieved).toEqual(value);
  });

  it('should return null for cache miss', () => {
    const retrieved = baseMetricsCache.get('nonexistent:key');
    expect(retrieved).toBeNull();
  });

  it('should track cache hits and misses', () => {
    const key = 'test:key';
    const value = { data: 'test' };

    // Miss
    baseMetricsCache.get(key);
    let stats = baseMetricsCache.getStats();
    expect(stats.misses).toBe(1);
    expect(stats.hits).toBe(0);

    // Set
    baseMetricsCache.set(key, value);

    // Hit
    baseMetricsCache.get(key);
    stats = baseMetricsCache.getStats();
    expect(stats.hits).toBe(1);
    expect(stats.misses).toBe(1);
  });

  it('should calculate hit rate correctly', () => {
    const key = 'test:key';
    const value = { data: 'test' };

    baseMetricsCache.set(key, value);

    // 1 hit, 0 misses = 100%
    baseMetricsCache.get(key);
    let stats = baseMetricsCache.getStats();
    expect(stats.hitRate).toBe('100.0%');

    // 1 hit, 1 miss = 50%
    baseMetricsCache.get('nonexistent');
    stats = baseMetricsCache.getStats();
    expect(stats.hitRate).toBe('50.0%');
  });

  it('should evict oldest entry when at capacity', () => {
    // Cache max size is 10 by default
    // Fill cache
    for (let i = 0; i < 10; i++) {
      baseMetricsCache.set(`key${i}`, { value: i });
    }

    // Verify all are present
    expect(baseMetricsCache.getStats().size).toBe(10);

    // Add 11th entry - should evict key0
    baseMetricsCache.set('key10', { value: 10 });

    expect(baseMetricsCache.get('key0')).toBeNull(); // Evicted
    expect(baseMetricsCache.get('key1')).not.toBeNull(); // Still present
    expect(baseMetricsCache.get('key10')).not.toBeNull(); // New entry
  });

  it('should implement LRU eviction', () => {
    // Fill cache to capacity
    for (let i = 0; i < 10; i++) {
      baseMetricsCache.set(`key${i}`, { value: i });
    }

    // Access key0 (moves to end)
    baseMetricsCache.get('key0');

    // Add new entry - should evict key1 (now oldest)
    baseMetricsCache.set('key10', { value: 10 });

    expect(baseMetricsCache.get('key0')).not.toBeNull(); // Recently accessed, kept
    expect(baseMetricsCache.get('key1')).toBeNull();     // Evicted
    expect(baseMetricsCache.get('key10')).not.toBeNull(); // New entry
  });

  it('should clear all entries', () => {
    baseMetricsCache.set('key1', { value: 1 });
    baseMetricsCache.set('key2', { value: 2 });

    expect(baseMetricsCache.getStats().size).toBe(2);

    baseMetricsCache.clear();

    expect(baseMetricsCache.getStats().size).toBe(0);
    expect(baseMetricsCache.getStats().hits).toBe(0);
    expect(baseMetricsCache.getStats().misses).toBe(0);
  });

  it('should provide accurate stats', () => {
    const stats = baseMetricsCache.getStats();

    expect(stats).toHaveProperty('size');
    expect(stats).toHaveProperty('maxSize');
    expect(stats).toHaveProperty('hits');
    expect(stats).toHaveProperty('misses');
    expect(stats).toHaveProperty('hitRate');

    expect(typeof stats.size).toBe('number');
    expect(typeof stats.maxSize).toBe('number');
    expect(typeof stats.hits).toBe('number');
    expect(typeof stats.misses).toBe('number');
    expect(typeof stats.hitRate).toBe('string');
  });

  it('should not evict when updating existing key', () => {
    // Fill to capacity
    for (let i = 0; i < 10; i++) {
      baseMetricsCache.set(`key${i}`, { value: i });
    }

    // Update existing key
    baseMetricsCache.set('key5', { value: 'updated' });

    // Should still have 10 entries
    expect(baseMetricsCache.getStats().size).toBe(10);

    // All original keys should still be present
    expect(baseMetricsCache.get('key0')).not.toBeNull();
    expect(baseMetricsCache.get('key9')).not.toBeNull();

    // Updated value should be present
    expect(baseMetricsCache.get('key5')).toEqual({ value: 'updated' });
  });
});

// ==============================================================================
// Integration Tests
// ==============================================================================

describe('Integration: Full Workflow', () => {
  beforeEach(() => {
    baseMetricsCache.clear();
  });

  it('should compute composite scores and cache correctly', () => {
    const baseMetrics = {
      pagerank: { node1: 0.5, node2: 0.3, node3: 0.2 },
      betweenness: { node1: 0.1, node2: 0.7, node3: 0.2 },
      engagement: { node1: 0.8, node2: 0.4, node3: 0.3 },
    };

    const params = {
      seeds: ['alice', 'bob'],
      alpha: 0.85,
      resolution: 1.0,
    };

    // Create cache key
    const cacheKey = createBaseMetricsCacheKey(params);

    // Cache base metrics
    baseMetricsCache.set(cacheKey, baseMetrics);

    // Retrieve from cache
    const cachedMetrics = baseMetricsCache.get(cacheKey);
    expect(cachedMetrics).toEqual(baseMetrics);

    // Compute composite scores with different weights (client-side)
    const weights1 = [0.5, 0.3, 0.2];
    const weights2 = [0.3, 0.5, 0.2];

    const composite1 = computeCompositeScores(cachedMetrics, weights1);
    const composite2 = computeCompositeScores(cachedMetrics, weights2);

    // Both should succeed
    expect(Object.keys(composite1).length).toBe(3);
    expect(Object.keys(composite2).length).toBe(3);

    // Results should differ
    expect(composite1.node1).not.toBeCloseTo(composite2.node1, 3);
  });

  it('should validate and use weights correctly', () => {
    const validWeights = [0.4, 0.3, 0.3];
    const invalidWeights = [0.5, 0.5, 0.5];

    expect(validateWeights(validWeights)).toBe(true);
    expect(validateWeights(invalidWeights)).toBe(false);

    const baseMetrics = {
      pagerank: { node1: 0.5 },
      betweenness: { node1: 0.3 },
      engagement: { node1: 0.2 },
    };

    // Should compute successfully with valid weights
    const composite = computeCompositeScores(baseMetrics, validWeights);
    expect(composite.node1).toBeGreaterThanOrEqual(0);
  });

  it('should get top scores from composite', () => {
    const baseMetrics = {
      pagerank: { node1: 0.9, node2: 0.5, node3: 0.1 },
      betweenness: { node1: 0.1, node2: 0.5, node3: 0.9 },
      engagement: { node1: 0.5, node2: 0.5, node3: 0.5 },
    };

    const weights = [0.5, 0.3, 0.2];
    const composite = computeCompositeScores(baseMetrics, weights);

    const top2 = getTopScores(composite, 2);

    expect(top2.length).toBe(2);
    expect(top2[0][1]).toBeGreaterThanOrEqual(top2[1][1]); // Descending order
  });
});
