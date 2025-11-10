/**
 * Playwright E2E tests for performance features
 *
 * Tests caching behavior, client-side reweighting, and performance optimizations.
 */

import { test, expect } from '@playwright/test';

// ==============================================================================
// Cache Hit/Miss Tests
// ==============================================================================

test.describe('API Caching', () => {
  test('should show cache MISS on first request', async ({ page }) => {
    // Navigate to the app
    await page.goto('/');

    // Wait for the app to load
    await page.waitForLoadState('networkidle');

    // Listen for network requests
    const apiRequests = [];
    page.on('response', async (response) => {
      if (response.url().includes('/api/metrics/base')) {
        const cacheStatus = response.headers()['x-cache-status'];
        apiRequests.push({ url: response.url(), cacheStatus });
      }
    });

    // Trigger metrics computation (e.g., by selecting seeds)
    // This depends on your UI - adjust selectors as needed
    await page.click('[data-testid="compute-metrics"]');

    // Wait for API response
    await page.waitForTimeout(1000);

    // First request should be cache MISS
    expect(apiRequests.length).toBeGreaterThan(0);
    expect(apiRequests[0].cacheStatus).toBe('MISS');
  });

  test('should show cache HIT on subsequent identical requests', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const cacheStatuses = [];
    page.on('response', async (response) => {
      if (response.url().includes('/api/metrics/base')) {
        const cacheStatus = response.headers()['x-cache-status'];
        cacheStatuses.push(cacheStatus);
      }
    });

    // Make first request
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(500);

    // Make second identical request
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(500);

    // First = MISS, Second = HIT
    expect(cacheStatuses.length).toBeGreaterThanOrEqual(2);
    expect(cacheStatuses[0]).toBe('MISS');
    expect(cacheStatuses[1]).toBe('HIT');
  });
});

// ==============================================================================
// Client-Side Reweighting Tests
// ==============================================================================

test.describe('Client-Side Reweighting', () => {
  test('weight slider adjustments should not trigger API calls', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Initial metrics computation
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Track API calls after initial load
    let apiCallCount = 0;
    page.on('request', (request) => {
      if (request.url().includes('/api/metrics')) {
        apiCallCount++;
      }
    });

    // Adjust weight slider
    const slider = page.locator('[data-testid="weight-slider-pagerank"]');
    await slider.fill('0.6');
    await page.waitForTimeout(500);

    // Adjust another slider
    const slider2 = page.locator('[data-testid="weight-slider-betweenness"]');
    await slider2.fill('0.3');
    await page.waitForTimeout(500);

    // Should NOT have made API calls (client-side reweighting)
    expect(apiCallCount).toBe(0);
  });

  test('weight adjustments should update visualization immediately', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Compute initial metrics
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Get initial node ranking
    const initialRanking = await page.textContent('[data-testid="top-nodes"]');

    // Adjust weights dramatically
    await page.fill('[data-testid="weight-slider-pagerank"]', '0.1');
    await page.fill('[data-testid="weight-slider-betweenness"]', '0.8');
    await page.waitForTimeout(500);

    // Get new ranking
    const newRanking = await page.textContent('[data-testid="top-nodes"]');

    // Ranking should have changed
    expect(newRanking).not.toBe(initialRanking);
  });
});

// ==============================================================================
// Performance Tests
// ==============================================================================

test.describe('Performance', () => {
  test('cache hits should be significantly faster than cache misses', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    let missTime = 0;
    let hitTime = 0;

    page.on('response', async (response) => {
      if (response.url().includes('/api/metrics/base')) {
        const cacheStatus = response.headers()['x-cache-status'];
        const responseTime = parseFloat(response.headers()['x-response-time'] || '0');

        if (cacheStatus === 'MISS') {
          missTime = responseTime;
        } else if (cacheStatus === 'HIT') {
          hitTime = responseTime;
        }
      }
    });

    // First request (MISS)
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Second request (HIT)
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Cache hit should be at least 2x faster
    expect(hitTime).toBeLessThan(missTime / 2);
  });

  test('weight slider adjustments should complete in <100ms', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Initial computation
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Measure slider adjustment time
    const startTime = Date.now();

    await page.fill('[data-testid="weight-slider-pagerank"]', '0.5');

    // Check that visualization updated
    await page.waitForSelector('[data-testid="top-nodes"]', { state: 'visible' });

    const endTime = Date.now();
    const adjustmentTime = endTime - startTime;

    // Should be nearly instant (<100ms)
    expect(adjustmentTime).toBeLessThan(100);
  });

  test('page should load and be interactive within 3 seconds', async ({ page }) => {
    const startTime = Date.now();

    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Wait for main interactive elements
    await page.waitForSelector('[data-testid="app-container"]', { state: 'visible' });

    const loadTime = Date.now() - startTime;

    // Should load quickly
    expect(loadTime).toBeLessThan(3000);
  });
});

// ==============================================================================
// Cache Statistics Tests
// ==============================================================================

test.describe('Cache Statistics', () => {
  test('cache stats should update after requests', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Navigate to cache stats (if available in UI)
    await page.click('[data-testid="cache-stats-button"]');

    // Initial stats should show 0 hits
    const initialHits = await page.textContent('[data-testid="cache-hits"]');
    expect(initialHits).toContain('0');

    // Make some requests
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(500);
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(500);

    // Refresh cache stats
    await page.click('[data-testid="refresh-cache-stats"]');

    // Stats should show hits
    const updatedHits = await page.textContent('[data-testid="cache-hits"]');
    expect(parseInt(updatedHits)).toBeGreaterThan(0);
  });

  test('cache invalidation should clear statistics', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Make some requests to populate cache
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(500);

    // Open cache stats
    await page.click('[data-testid="cache-stats-button"]');

    // Invalidate cache
    await page.click('[data-testid="invalidate-cache-button"]');
    await page.waitForTimeout(500);

    // Cache size should be 0
    const cacheSize = await page.textContent('[data-testid="cache-size"]');
    expect(cacheSize).toContain('0');
  });
});

// ==============================================================================
// Graph Visualization Tests
// ==============================================================================

test.describe('Graph Visualization', () => {
  test('graph should render nodes and edges', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Compute metrics to trigger graph render
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(2000);

    // Check that SVG or canvas exists
    const graphContainer = await page.locator('[data-testid="graph-container"]');
    expect(await graphContainer.isVisible()).toBeTruthy();

    // Check that nodes are rendered
    const nodes = await page.locator('.graph-node').count();
    expect(nodes).toBeGreaterThan(0);
  });

  test('clicking node should show details', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(2000);

    // Click on first node
    await page.click('.graph-node:first-child');

    // Node details panel should appear
    const detailsPanel = await page.locator('[data-testid="node-details-panel"]');
    expect(await detailsPanel.isVisible()).toBeTruthy();

    // Should show node information
    const nodeInfo = await detailsPanel.textContent();
    expect(nodeInfo.length).toBeGreaterThan(0);
  });

  test('zoom controls should work', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(2000);

    // Test zoom in
    await page.click('[data-testid="zoom-in-button"]');
    await page.waitForTimeout(200);

    // Test zoom out
    await page.click('[data-testid="zoom-out-button"]');
    await page.waitForTimeout(200);

    // Test reset zoom
    await page.click('[data-testid="reset-zoom-button"]');
    await page.waitForTimeout(200);

    // Should not crash
    const graphContainer = await page.locator('[data-testid="graph-container"]');
    expect(await graphContainer.isVisible()).toBeTruthy();
  });
});

// ==============================================================================
// Seed Selection Tests
// ==============================================================================

test.describe('Seed Selection', () => {
  test('should allow adding multiple seeds', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Add first seed
    await page.fill('[data-testid="seed-input"]', 'alice');
    await page.click('[data-testid="add-seed-button"]');

    // Add second seed
    await page.fill('[data-testid="seed-input"]', 'bob');
    await page.click('[data-testid="add-seed-button"]');

    // Check that both seeds appear in list
    const seeds = await page.locator('[data-testid="seed-list-item"]').count();
    expect(seeds).toBe(2);
  });

  test('should allow removing seeds', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Add seeds
    await page.fill('[data-testid="seed-input"]', 'alice');
    await page.click('[data-testid="add-seed-button"]');
    await page.fill('[data-testid="seed-input"]', 'bob');
    await page.click('[data-testid="add-seed-button"]');

    // Remove first seed
    await page.click('[data-testid="remove-seed-button"]:first-child');

    // Should have 1 seed left
    const seeds = await page.locator('[data-testid="seed-list-item"]').count();
    expect(seeds).toBe(1);
  });

  test('should validate seed input', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Try to add empty seed
    await page.click('[data-testid="add-seed-button"]');

    // Should show validation error
    const error = await page.locator('[data-testid="seed-validation-error"]');
    expect(await error.isVisible()).toBeTruthy();
  });
});

// ==============================================================================
// Error Handling Tests
// ==============================================================================

test.describe('Error Handling', () => {
  test('should show error message when API fails', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Mock API failure
    await page.route('**/api/metrics/**', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal Server Error' }),
      });
    });

    // Trigger API call
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Error message should appear
    const errorMessage = await page.locator('[data-testid="error-message"]');
    expect(await errorMessage.isVisible()).toBeTruthy();
  });

  test('should handle invalid seeds gracefully', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Add invalid seed
    await page.fill('[data-testid="seed-input"]', 'nonexistent_user_12345');
    await page.click('[data-testid="add-seed-button"]');
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(1000);

    // Should show warning or empty result (not crash)
    const warning = await page.locator('[data-testid="no-results-warning"]');
    const errorMsg = await page.locator('[data-testid="error-message"]');

    expect(await warning.isVisible() || await errorMsg.isVisible()).toBeTruthy();
  });

  test('should recover from network timeout', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Mock slow API response
    await page.route('**/api/metrics/**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      route.abort();
    });

    // Trigger API call
    await page.click('[data-testid="compute-metrics"]');
    await page.waitForTimeout(6000);

    // Should show timeout error
    const errorMessage = await page.locator('[data-testid="error-message"]');
    expect(await errorMessage.isVisible()).toBeTruthy();
  });
});

// ==============================================================================
// Accessibility Tests
// ==============================================================================

test.describe('Accessibility', () => {
  test('should be keyboard navigable', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Tab through interactive elements
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // Should not have any focus traps
    const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
    expect(focusedElement).toBeTruthy();
  });

  test('should have proper ARIA labels', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check for important ARIA labels
    const computeButton = await page.locator('[data-testid="compute-metrics"]');
    const ariaLabel = await computeButton.getAttribute('aria-label');

    expect(ariaLabel).toBeTruthy();
  });
});

// ==============================================================================
// Mobile Responsiveness Tests
// ==============================================================================

test.describe('Mobile Responsiveness', () => {
  test('should render correctly on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check that main container is visible
    const container = await page.locator('[data-testid="app-container"]');
    expect(await container.isVisible()).toBeTruthy();

    // Check that controls are accessible (not hidden off-screen)
    const controls = await page.locator('[data-testid="controls-panel"]');
    expect(await controls.isVisible()).toBeTruthy();
  });

  test('should have mobile-friendly touch targets', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check button sizes (should be at least 44x44px for touch)
    const button = await page.locator('[data-testid="compute-metrics"]');
    const box = await button.boundingBox();

    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
  });
});
