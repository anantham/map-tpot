import { test, expect } from '@playwright/test';
import * as fs from 'fs';

const LOG_FILE = 'e2e/hybrid-zoom-console.log';

test.describe('Hybrid Zoom System', () => {
  test.beforeEach(async ({ page }) => {
    // Clear log file
    fs.writeFileSync(LOG_FILE, `=== Hybrid Zoom Test Run ${new Date().toISOString()} ===\n`);
    
    // Capture all console messages
    page.on('console', msg => {
      const text = msg.text();
      if (text.includes('[ClusterCanvas]') || text.includes('Hybrid') || text.includes('expand') || text.includes('collapse')) {
        const line = `[${msg.type()}] ${text}\n`;
        fs.appendFileSync(LOG_FILE, line);
        console.log(line.trim());
      }
    });
    
    // Navigate to cluster view WITH budget set via URL
    await page.goto('/?view=cluster&n=10&budget=25');
    
    // Wait for clusters to load
    await page.waitForSelector('canvas', { timeout: 60000 });
    await page.waitForTimeout(3000); // Let initial render and data fetch settle
  });

  test('visual zoom in and out', async ({ page }) => {
    fs.appendFileSync(LOG_FILE, '\n--- Test: Visual zoom in and out ---\n');
    
    const canvas = page.locator('canvas');
    
    // Scroll in (visual zoom)
    await canvas.hover();
    for (let i = 0; i < 5; i++) {
      await page.mouse.wheel(0, -100);
      await page.waitForTimeout(200);
    }
    
    fs.appendFileSync(LOG_FILE, '--- Zoomed in 5 steps ---\n');
    
    // Scroll out (visual zoom)
    for (let i = 0; i < 5; i++) {
      await page.mouse.wheel(0, 100);
      await page.waitForTimeout(200);
    }
    
    fs.appendFileSync(LOG_FILE, '--- Zoomed out 5 steps ---\n');
  });

  test('semantic zoom - zoom in past threshold triggers expand', async ({ page }) => {
    fs.appendFileSync(LOG_FILE, '\n--- Test: Semantic expand on deep zoom ---\n');
    
    const canvas = page.locator('canvas');
    await canvas.hover();
    
    // Zoom in significantly to cross expand threshold
    fs.appendFileSync(LOG_FILE, 'Zooming in 15 steps to cross expand threshold...\n');
    for (let i = 0; i < 15; i++) {
      await page.mouse.wheel(0, -120);
      await page.waitForTimeout(300);
    }
    
    fs.appendFileSync(LOG_FILE, '--- Finished zooming in ---\n');
    await page.waitForTimeout(1000);
  });

  test('double-click expands node', async ({ page }) => {
    fs.appendFileSync(LOG_FILE, '\n--- Test: Double-click expand ---\n');
    
    const canvas = page.locator('canvas');
    const box = await canvas.boundingBox();
    
    if (box) {
      // Double-click near center
      const centerX = box.x + box.width / 2;
      const centerY = box.y + box.height / 2;
      
      fs.appendFileSync(LOG_FILE, `Double-clicking at (${centerX.toFixed(0)}, ${centerY.toFixed(0)})\n`);
      await page.mouse.dblclick(centerX, centerY);
      await page.waitForTimeout(1500);
    }
    
    fs.appendFileSync(LOG_FILE, '--- Double-click test complete ---\n');
  });

  test('semantic zoom - zoom out past threshold triggers collapse', async ({ page }) => {
    fs.appendFileSync(LOG_FILE, '\n--- Test: Semantic collapse on zoom out ---\n');
    
    const canvas = page.locator('canvas');
    await canvas.hover();
    
    // First expand something via double-click
    const box = await canvas.boundingBox();
    if (box) {
      const centerX = box.x + box.width / 2;
      const centerY = box.y + box.height / 2;
      
      fs.appendFileSync(LOG_FILE, 'Step 1: Expanding via double-click\n');
      await page.mouse.dblclick(centerX, centerY);
      await page.waitForTimeout(2000);
    }
    
    // Now zoom out significantly to cross collapse threshold
    fs.appendFileSync(LOG_FILE, 'Step 2: Zooming out 20 steps to trigger collapse...\n');
    for (let i = 0; i < 20; i++) {
      await page.mouse.wheel(0, 150);
      await page.waitForTimeout(200);
    }
    
    fs.appendFileSync(LOG_FILE, '--- Collapse test complete ---\n');
    await page.waitForTimeout(1000);
  });

  test('ctrl+scroll forces visual zoom', async ({ page }) => {
    fs.appendFileSync(LOG_FILE, '\n--- Test: Ctrl+scroll forces visual zoom ---\n');
    
    const canvas = page.locator('canvas');
    await canvas.hover();
    
    // First zoom in a lot to be in expand-ready zone
    fs.appendFileSync(LOG_FILE, 'Step 1: Zoom in to expand-ready zone\n');
    for (let i = 0; i < 12; i++) {
      await page.mouse.wheel(0, -120);
      await page.waitForTimeout(150);
    }
    
    fs.appendFileSync(LOG_FILE, 'Step 2: Ctrl+scroll should still do visual zoom\n');
    // Now ctrl+scroll should still do visual zoom, not semantic
    await page.keyboard.down('Control');
    for (let i = 0; i < 3; i++) {
      await page.mouse.wheel(0, -100);
      await page.waitForTimeout(200);
    }
    await page.keyboard.up('Control');
    
    fs.appendFileSync(LOG_FILE, '--- Ctrl+scroll test complete ---\n');
    await page.waitForTimeout(500);
  });
});
