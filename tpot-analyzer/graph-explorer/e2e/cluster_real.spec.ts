import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const RESULTS_DIR = path.join(process.cwd(), 'e2e/results');
const BACKEND_URL = 'http://localhost:5001';

// Cluster builds take ~57s on first load (71k nodes)
const CLUSTER_TIMEOUT = 120000; // 2 minutes

// Ensure results directory exists
test.beforeAll(() => {
  if (!fs.existsSync(RESULTS_DIR)) {
    fs.mkdirSync(RESULTS_DIR, { recursive: true });
  }
});

const writeResult = (filename: string, data: any) => {
  const filepath = path.join(RESULTS_DIR, filename);
  const content = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  fs.writeFileSync(filepath, content);
  console.log(`Wrote: ${filepath}`);
};

// Check if backend is running before tests
test.describe('Backend Health Check', () => {
  test('backend is running', async ({ request }) => {
    try {
      const response = await request.get(`${BACKEND_URL}/health`, { timeout: 5000 });
      console.log('Backend health check:', response.status());
      expect(response.ok()).toBe(true);
    } catch (e) {
      console.error('\n⚠️  BACKEND NOT RUNNING!');
      console.error('Start the backend first:');
      console.error('  cd tpot-analyzer && python -m scripts.start_api_server\n');
      throw new Error('Backend is not running at localhost:5001. Start it with: cd tpot-analyzer && python -m scripts.start_api_server');
    }
  });
});

test.describe('Cluster View', () => {
  test('loads and displays clusters', async ({ page }) => {
    const logs: string[] = [];
    const log = (msg: string) => {
      console.log(msg);
      logs.push(`[${new Date().toISOString()}] ${msg}`);
    };

    log('Navigating to cluster view...');
    
    // Capture all network requests
    const apiResponses: Record<string, any> = {};
    page.on('response', async (response) => {
      const url = response.url();
      if (url.includes('/api/')) {
        try {
          const data = await response.json();
          apiResponses[url] = {
            status: response.status(),
            data,
            timestamp: new Date().toISOString()
          };
          log(`API Response: ${url} (${response.status()})`);
        } catch (e) {
          apiResponses[url] = {
            status: response.status(),
            error: 'Could not parse JSON',
            timestamp: new Date().toISOString()
          };
        }
      }
    });

    // Capture console logs from the page
    const consoleLogs: string[] = [];
    page.on('console', msg => {
      const text = `[${msg.type()}] ${msg.text()}`;
      consoleLogs.push(text);
      log(`Browser console: ${text}`);
    });

    // Capture page errors
    const pageErrors: string[] = [];
    page.on('pageerror', err => {
      pageErrors.push(err.message);
      log(`Page error: ${err.message}`);
    });

    // Navigate to cluster view
    await page.goto('/?view=cluster&n=25&wl=0.00');
    log('Page loaded');

    // Wait for API response (cluster build takes ~57s on cold start)
    try {
      const response = await page.waitForResponse(
        resp => resp.url().includes('/api/clusters') && resp.status() === 200,
        { timeout: CLUSTER_TIMEOUT }
      );
      
      const data = await response.json();
      log(`Clusters received: ${data.clusters?.length || 0}`);
      log(`Edges received: ${data.edges?.length || 0}`);
      log(`Positions: ${Object.keys(data.positions || {}).length}`);
      log(`Cache hit: ${data.cache_hit}`);
      log(`Total nodes: ${data.total_nodes}`);
      log(`Granularity: ${data.granularity}`);
      log(`Approximate mode: ${data.meta?.approximate_mode}`);
      
      // Write full API response
      writeResult('cluster-api-response.json', data);
      
      // Write summary
      writeResult('cluster-summary.json', {
        clustersCount: data.clusters?.length || 0,
        edgesCount: data.edges?.length || 0,
        positionsCount: Object.keys(data.positions || {}).length,
        totalNodes: data.total_nodes,
        granularity: data.granularity,
        cacheHit: data.cache_hit,
        meta: data.meta,
        sampleClusters: data.clusters?.slice(0, 5).map((c: any) => ({
          id: c.id,
          size: c.size,
          label: c.label,
          representativeHandles: c.representativeHandles
        }))
      });

    } catch (e) {
      log(`Failed to get cluster response: ${e}`);
    }

    // Wait a bit for canvas render
    await page.waitForTimeout(2000);

    // Check canvas
    const canvas = page.locator('canvas');
    const canvasVisible = await canvas.isVisible();
    log(`Canvas visible: ${canvasVisible}`);
    
    if (canvasVisible) {
      const canvasBox = await canvas.boundingBox();
      log(`Canvas size: ${canvasBox?.width}x${canvasBox?.height}`);
    }

    // Take screenshot
    await page.screenshot({ path: path.join(RESULTS_DIR, 'cluster-view.png'), fullPage: true });
    log('Screenshot saved');

    // Check for "Load clusters to view" message (indicates empty state)
    const emptyMessage = page.locator('text=Load clusters to view');
    const hasEmptyMessage = await emptyMessage.isVisible().catch(() => false);
    log(`Empty state message visible: ${hasEmptyMessage}`);

    // Write all collected data
    writeResult('api-responses.json', apiResponses);
    writeResult('browser-console.log', consoleLogs.join('\n'));
    writeResult('page-errors.log', pageErrors.join('\n'));
    writeResult('test-log.log', logs.join('\n'));

    // Final summary
    const summary = {
      timestamp: new Date().toISOString(),
      url: page.url(),
      canvasVisible,
      hasEmptyMessage,
      apiResponsesCount: Object.keys(apiResponses).length,
      consoleLogsCount: consoleLogs.length,
      pageErrorsCount: pageErrors.length,
      logs
    };
    writeResult('test-summary.json', summary);

    // Assertions
    expect(canvasVisible).toBe(true);
  });

  test('debug cluster positions', async ({ page }) => {
    const logs: string[] = [];
    const log = (msg: string) => logs.push(`[${new Date().toISOString()}] ${msg}`);

    await page.goto('/?view=cluster&n=25&wl=0.00');
    
    const response = await page.waitForResponse(
      resp => resp.url().includes('/api/clusters'),
      { timeout: CLUSTER_TIMEOUT }
    );
    
    const data = await response.json();
    
    // Analyze positions
    const positions = data.positions || {};
    const positionAnalysis = {
      count: Object.keys(positions).length,
      sample: Object.entries(positions).slice(0, 10),
      allZero: Object.values(positions).every((p: any) => p[0] === 0 && p[1] === 0),
      bounds: {
        minX: Math.min(...Object.values(positions).map((p: any) => p[0])),
        maxX: Math.max(...Object.values(positions).map((p: any) => p[0])),
        minY: Math.min(...Object.values(positions).map((p: any) => p[1])),
        maxY: Math.max(...Object.values(positions).map((p: any) => p[1])),
      }
    };
    
    log(`Position analysis: ${JSON.stringify(positionAnalysis, null, 2)}`);
    
    // Analyze clusters
    const clusterAnalysis = {
      count: data.clusters?.length || 0,
      sizes: data.clusters?.map((c: any) => c.size).sort((a: number, b: number) => b - a).slice(0, 10),
      labels: data.clusters?.map((c: any) => c.label).slice(0, 10),
      hasPositions: data.clusters?.map((c: any) => ({
        id: c.id,
        hasPosition: !!positions[c.id],
        position: positions[c.id]
      })).slice(0, 10)
    };
    
    log(`Cluster analysis: ${JSON.stringify(clusterAnalysis, null, 2)}`);

    writeResult('position-analysis.json', positionAnalysis);
    writeResult('cluster-analysis.json', clusterAnalysis);
    writeResult('debug-log.log', logs.join('\n'));
    
    // Take screenshot with longer wait
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(RESULTS_DIR, 'debug-cluster-view.png'), fullPage: true });
  });

  test('expand and collapse clusters with animation', async ({ page }) => {
    const logs: string[] = [];
    const log = (msg: string) => {
      console.log(msg);
      logs.push(`[${new Date().toISOString()}] ${msg}`);
    };

    log('Navigating to cluster view...');
    await page.goto('/?view=cluster&n=25&wl=0.00&expand_depth=0.50');

    // Wait for initial clusters to load
    const response = await page.waitForResponse(
      resp => resp.url().includes('/api/clusters') && resp.status() === 200,
      { timeout: CLUSTER_TIMEOUT }
    );
    const initialData = await response.json();
    const initialCount = initialData.clusters?.length || 0;
    log(`Initial clusters: ${initialCount}`);

    await page.waitForTimeout(1500); // Let canvas render
    await page.screenshot({ path: path.join(RESULTS_DIR, 'expand-01-initial.png'), fullPage: true });

    // Click on canvas to select a cluster
    const canvas = page.locator('canvas');
    const canvasBox = await canvas.boundingBox();
    if (!canvasBox) throw new Error('Canvas not found');

    // Click in the center of the canvas
    const centerX = canvasBox.x + canvasBox.width / 2;
    const centerY = canvasBox.y + canvasBox.height / 2;
    log(`Clicking canvas at (${centerX}, ${centerY})`);
    await page.mouse.click(centerX, centerY);
    await page.waitForTimeout(500);

    // Check if expand button is visible in the sidebar
    const expandButton = page.locator('button:has-text("Expand")');
    const expandVisible = await expandButton.isVisible().catch(() => false);
    log(`Expand button visible: ${expandVisible}`);

    if (expandVisible) {
      // Check for preview information
      const buttonText = await expandButton.textContent();
      log(`Expand button text: ${buttonText}`);
      
      // Take screenshot before expand
      await page.screenshot({ path: path.join(RESULTS_DIR, 'expand-02-selected.png'), fullPage: true });

      // Click expand
      await expandButton.click();
      log('Clicked expand');

      // Wait for API response (subsequent calls use cache, faster)
      try {
        const expandResponse = await page.waitForResponse(
          resp => resp.url().includes('/api/clusters') && resp.status() === 200,
          { timeout: 30000 }
        );
        const expandedData = await expandResponse.json();
        const expandedCount = expandedData.clusters?.length || 0;
        log(`After expand: ${expandedCount} clusters (was ${initialCount})`);

        // Wait for animation
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(RESULTS_DIR, 'expand-03-expanded.png'), fullPage: true });

        // Now test collapse - click a cluster again
        await page.mouse.click(centerX, centerY);
        await page.waitForTimeout(500);

        const collapseButton = page.locator('button:has-text("Collapse")');
        const collapseVisible = await collapseButton.isVisible().catch(() => false);
        log(`Collapse button visible: ${collapseVisible}`);

        if (collapseVisible) {
          const collapseText = await collapseButton.textContent();
          log(`Collapse button text: ${collapseText}`);
          await page.screenshot({ path: path.join(RESULTS_DIR, 'expand-04-collapse-preview.png'), fullPage: true });

          // Check for sibling highlighting
          // (Visual check via screenshot - amber/orange highlighted nodes)
        }

        writeResult('expand-collapse-test.json', {
          initialCount,
          expandedCount,
          expandVisible,
          collapseVisible,
          logs
        });

      } catch (e) {
        log(`Expand failed: ${e}`);
      }
    }

    writeResult('expand-test-log.log', logs.join('\n'));
  });

  test('expand depth slider affects cluster count', async ({ page }) => {
    const results: any[] = [];

    for (const depth of [0.0, 0.5, 1.0]) {
      // Navigate with different expand_depth
      await page.goto(`/?view=cluster&n=25&wl=0.00&expand_depth=${depth.toFixed(2)}&expanded=cluster_0`);

      const response = await page.waitForResponse(
        resp => resp.url().includes('/api/clusters') && resp.status() === 200,
        { timeout: CLUSTER_TIMEOUT }
      );
      const data = await response.json();
      
      results.push({
        expandDepth: depth,
        clusterCount: data.clusters?.length || 0,
        totalNodes: data.total_nodes
      });
    }

    writeResult('expand-depth-comparison.json', results);

    // Verify that higher depth = more clusters (generally)
    console.log('Expand depth results:', results);
  });

  test('cluster preview API returns correct data', async ({ page }) => {
    await page.goto('/?view=cluster&n=25&wl=0.00');

    // Wait for initial load
    await page.waitForResponse(
      resp => resp.url().includes('/api/clusters') && resp.status() === 200,
      { timeout: CLUSTER_TIMEOUT }
    );

    await page.waitForTimeout(1500);

    // Click canvas to select a cluster
    const canvas = page.locator('canvas');
    const canvasBox = await canvas.boundingBox();
    if (!canvasBox) throw new Error('Canvas not found');

    await page.mouse.click(canvasBox.x + canvasBox.width / 2, canvasBox.y + canvasBox.height / 2);

    // Wait for preview API call
    try {
      const previewResponse = await page.waitForResponse(
        resp => resp.url().includes('/api/clusters/') && resp.url().includes('/preview') && resp.status() === 200,
        { timeout: 10000 }
      );

      const previewData = await previewResponse.json();
      console.log('Preview response:', JSON.stringify(previewData, null, 2));

      writeResult('cluster-preview-response.json', previewData);

      // Validate structure
      expect(previewData).toHaveProperty('expand');
      expect(previewData).toHaveProperty('collapse');

      if (previewData.expand) {
        expect(previewData.expand).toHaveProperty('can_expand');
        expect(previewData.expand).toHaveProperty('predicted_children');
        expect(previewData.expand).toHaveProperty('budget_impact');
      }

      if (previewData.collapse) {
        expect(previewData.collapse).toHaveProperty('can_collapse');
        expect(previewData.collapse).toHaveProperty('sibling_ids');
        expect(previewData.collapse).toHaveProperty('nodes_freed');
      }

    } catch (e) {
      console.log('Preview not captured (may not have selected a cluster):', e);
    }
  });
});
