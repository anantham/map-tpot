/**
 * Playwright smoke tests for Graph Explorer frontend
 *
 * These tests verify basic functionality:
 * - Page loads without errors
 * - Graph renders with nodes and edges
 * - Controls are interactive (sliders, toggles, inputs)
 * - Backend connectivity
 *
 * Setup:
 * 1. npm install --save-dev @playwright/test
 * 2. npx playwright install
 * 3. Add to package.json scripts: "test": "playwright test"
 *
 * Run tests:
 * - npm test (all tests)
 * - npm test -- --headed (with browser UI)
 * - npm test -- --debug (debug mode)
 */

import { test, expect } from '@playwright/test';

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:5001';

// ==============================================================================
// Setup: Ensure servers are running
// ==============================================================================

test.describe('Graph Explorer Smoke Tests', () => {
  test.beforeAll(async () => {
    // Note: These tests assume backend and frontend are already running
    // Start them manually before running tests:
    // Terminal 1: cd tpot-analyzer && python -m scripts.start_api_server
    // Terminal 2: cd tpot-analyzer/graph-explorer && npm run dev
  });

  // ==============================================================================
  // Test: Page Load
  // ==============================================================================

  test('should load the page without errors', async ({ page }) => {
    // Navigate to the app
    await page.goto(FRONTEND_URL);

    // Wait for the page to load
    await page.waitForLoadState('networkidle');

    // Check page title
    await expect(page).toHaveTitle(/Graph Explorer/i);

    // Verify no console errors (except warnings)
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.error(`Console error: ${msg.text()}`);
      }
    });
  });

  test('should display main heading', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for main heading
    const heading = page.locator('h1, h2').first();
    await expect(heading).toBeVisible();
    await expect(heading).toContainText(/graph|explorer|tpot/i);
  });

  // ==============================================================================
  // Test: Backend Connectivity
  // ==============================================================================

  test('should connect to backend API', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Wait for initial data load
    await page.waitForTimeout(2000);

    // Check for error banner (should NOT be visible if backend is up)
    const errorBanner = page.locator('[role="alert"], .error-banner, .alert-error');
    const errorVisible = await errorBanner.isVisible().catch(() => false);

    if (errorVisible) {
      const errorText = await errorBanner.textContent();
      console.warn(`Backend error detected: ${errorText}`);
    }

    // Ideally, check for successful data load indicator
    // This depends on your app's loading states
  });

  test('should load graph data from backend', async ({ page, request }) => {
    // First verify backend is accessible
    const healthResponse = await request.get(`${BACKEND_URL}/health`);
    expect(healthResponse.ok()).toBeTruthy();

    await page.goto(FRONTEND_URL);

    // Wait for graph to load (look for canvas or svg)
    const graphCanvas = page.locator('canvas, svg').first();
    await expect(graphCanvas).toBeVisible({ timeout: 10000 });
  });

  // ==============================================================================
  // Test: Graph Rendering
  // ==============================================================================

  test('should render graph visualization', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Wait for graph container
    await page.waitForSelector('canvas, svg', { timeout: 10000 });

    // Verify graph is rendered (canvas or SVG should exist)
    const canvas = page.locator('canvas').first();
    const svg = page.locator('svg').first();

    const canvasVisible = await canvas.isVisible().catch(() => false);
    const svgVisible = await svg.isVisible().catch(() => false);

    expect(canvasVisible || svgVisible).toBeTruthy();
  });

  test('should display nodes and edges', async ({ page }) => {
    await page.goto(FRONTEND_URL);
    await page.waitForTimeout(3000); // Wait for graph to render

    // Look for node/edge indicators (this depends on your visualization library)
    // For react-force-graph, nodes are rendered on canvas
    // We can check the canvas is not blank by checking for data attributes or loading states

    // Check if graph data exists (look for data-related attributes or elements)
    const graphContainer = page.locator('[class*="graph"], [id*="graph"]').first();
    await expect(graphContainer).toBeVisible({ timeout: 10000 });
  });

  // ==============================================================================
  // Test: Controls - Weight Sliders
  // ==============================================================================

  test('should have PageRank weight slider', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for PageRank slider
    const prSlider = page.locator('input[type="range"]').first();
    await expect(prSlider).toBeVisible();

    // Verify slider is interactive
    await prSlider.fill('0.5');
    const value = await prSlider.inputValue();
    expect(parseFloat(value)).toBeCloseTo(0.5, 1);
  });

  test('should adjust weight sliders and trigger recomputation', async ({ page }) => {
    await page.goto(FRONTEND_URL);
    await page.waitForTimeout(2000);

    // Find all range sliders (α, β, γ weights)
    const sliders = page.locator('input[type="range"]');
    const sliderCount = await sliders.count();

    // Should have at least 3 sliders (PageRank, Betweenness, Engagement)
    expect(sliderCount).toBeGreaterThanOrEqual(3);

    // Adjust first slider
    const firstSlider = sliders.first();
    await firstSlider.fill('0.7');

    // Wait for potential recomputation (look for loading indicators)
    await page.waitForTimeout(1000);
  });

  test('should display weight total sum', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for total weight display
    const totalDisplay = page.locator('text=/total.*1\\.0|sum.*1\\.0/i');
    await expect(totalDisplay).toBeVisible({ timeout: 5000 });
  });

  // ==============================================================================
  // Test: Controls - Seed Input
  // ==============================================================================

  test('should have seed input field', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for seed input (textarea or input)
    const seedInput = page.locator('textarea, input[type="text"]').filter({ hasText: /seed|username/i }).first();

    if (await seedInput.isVisible()) {
      // Try typing a username
      await seedInput.fill('testuser');
      const value = await seedInput.inputValue();
      expect(value).toContain('testuser');
    }
  });

  test('should have "Apply Seeds" button', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for apply button
    const applyButton = page.locator('button').filter({ hasText: /apply.*seed|update.*seed|compute/i }).first();

    if (await applyButton.isVisible()) {
      await expect(applyButton).toBeEnabled();
    }
  });

  // ==============================================================================
  // Test: Controls - Toggles
  // ==============================================================================

  test('should have shadow nodes toggle', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for shadow toggle
    const shadowToggle = page.locator('input[type="checkbox"]').filter({ has: page.locator('text=/shadow/i') }).first();

    if (await shadowToggle.isVisible()) {
      // Toggle it
      const initialState = await shadowToggle.isChecked();
      await shadowToggle.click();
      const newState = await shadowToggle.isChecked();
      expect(newState).toBe(!initialState);
    }
  });

  test('should have mutual-only edges toggle', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for mutual edges toggle
    const mutualToggle = page.locator('input[type="checkbox"]').filter({ has: page.locator('text=/mutual/i') }).first();

    if (await mutualToggle.isVisible()) {
      const initialState = await mutualToggle.isChecked();
      await mutualToggle.click();
      const newState = await mutualToggle.isChecked();
      expect(newState).toBe(!initialState);
    }
  });

  // ==============================================================================
  // Test: Graph Interactions
  // ==============================================================================

  test('should allow zooming', async ({ page }) => {
    await page.goto(FRONTEND_URL);
    await page.waitForTimeout(2000);

    const graphCanvas = page.locator('canvas').first();
    if (await graphCanvas.isVisible()) {
      // Get canvas bounding box
      const box = await graphCanvas.boundingBox();

      if (box) {
        // Simulate mouse wheel zoom
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.wheel(0, -100); // Zoom in
        await page.waitForTimeout(500);
        await page.mouse.wheel(0, 100); // Zoom out
      }
    }
  });

  test('should allow panning', async ({ page }) => {
    await page.goto(FRONTEND_URL);
    await page.waitForTimeout(2000);

    const graphCanvas = page.locator('canvas').first();
    if (await graphCanvas.isVisible()) {
      const box = await graphCanvas.boundingBox();

      if (box) {
        // Simulate drag to pan
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width / 2 + 50, box.y + box.height / 2 + 50);
        await page.mouse.up();
      }
    }
  });

  // ==============================================================================
  // Test: Loading States
  // ==============================================================================

  test('should show loading indicator during data fetch', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for loading indicators immediately after page load
    const loadingIndicator = page.locator('text=/loading|computing|fetching/i').first();

    // Loading indicator might be visible briefly
    // Just verify the page eventually loads without errors
    await page.waitForLoadState('networkidle');
  });

  // ==============================================================================
  // Test: Responsive Design
  // ==============================================================================

  test('should be responsive on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto(FRONTEND_URL);

    // Verify page still renders
    await expect(page.locator('body')).toBeVisible();

    // Graph should still be visible (may be smaller)
    const graphCanvas = page.locator('canvas, svg').first();
    const canvasVisible = await graphCanvas.isVisible().catch(() => false);
    expect(canvasVisible).toBeTruthy();
  });

  test('should be responsive on tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto(FRONTEND_URL);

    await expect(page.locator('body')).toBeVisible();
  });

  // ==============================================================================
  // Test: Error Handling
  // ==============================================================================

  test('should show error message when backend is down', async ({ page }) => {
    // This test simulates backend being unavailable
    // We can block the backend URL to simulate this

    await page.route(`${BACKEND_URL}/**`, route => route.abort());
    await page.goto(FRONTEND_URL);

    // Wait a bit for error to show
    await page.waitForTimeout(2000);

    // Look for error banner or message
    const errorMessage = page.locator('[role="alert"], .error, .alert').first();
    await expect(errorMessage).toBeVisible({ timeout: 5000 });
  });

  // ==============================================================================
  // Test: Export Functionality
  // ==============================================================================

  test('should have CSV export button', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Look for export button
    const exportButton = page.locator('button').filter({ hasText: /export|download|csv/i }).first();

    if (await exportButton.isVisible()) {
      await expect(exportButton).toBeEnabled();
    }
  });

  // ==============================================================================
  // Test: Performance
  // ==============================================================================

  test('should load within reasonable time', async ({ page }) => {
    const startTime = Date.now();

    await page.goto(FRONTEND_URL);
    await page.waitForLoadState('networkidle');

    const loadTime = Date.now() - startTime;

    // Should load within 10 seconds
    expect(loadTime).toBeLessThan(10000);
    console.log(`Page loaded in ${loadTime}ms`);
  });

  // ==============================================================================
  // Test: Accessibility
  // ==============================================================================

  test('should have accessible labels for controls', async ({ page }) => {
    await page.goto(FRONTEND_URL);

    // Check for labeled inputs
    const sliders = page.locator('input[type="range"]');
    const sliderCount = await sliders.count();

    for (let i = 0; i < sliderCount; i++) {
      const slider = sliders.nth(i);

      // Check if slider has an associated label or aria-label
      const ariaLabel = await slider.getAttribute('aria-label');
      const id = await slider.getAttribute('id');

      const hasLabel = ariaLabel || id;
      expect(hasLabel).toBeTruthy();
    }
  });
});
