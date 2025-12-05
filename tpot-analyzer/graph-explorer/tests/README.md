# Graph Explorer Playwright Tests

Automated end-to-end tests for the Graph Explorer frontend using Playwright.

## Setup

### 1. Install Playwright

```bash
cd tpot-analyzer/graph-explorer
npm install --save-dev @playwright/test
npx playwright install
```

### 2. Update package.json

Add test script to `package.json`:

```json
{
  "scripts": {
    "test": "playwright test",
    "test:headed": "playwright test --headed",
    "test:debug": "playwright test --debug",
    "test:ui": "playwright test --ui",
    "test:report": "playwright show-report"
  }
}
```

### 3. Start Required Servers

Before running tests, ensure both servers are running:

**Terminal 1 - Backend:**
```bash
cd tpot-analyzer
python -m scripts.start_api_server
```

**Terminal 2 - Frontend:**
```bash
cd tpot-analyzer/graph-explorer
npm run dev
```

Or configure `playwright.config.js` to auto-start servers (see webServer option).

## Running Tests

### Run all tests
```bash
npm test
```

### Run with browser UI (headed mode)
```bash
npm run test:headed
```

### Debug mode (step through tests)
```bash
npm run test:debug
```

### Interactive UI mode
```bash
npm run test:ui
```

### Run specific test file
```bash
npx playwright test smoke.spec.js
```

### Run tests in specific browser
```bash
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

### View HTML report
```bash
npm run test:report
```

## Test Coverage

The smoke tests verify:

### ✅ Core Functionality
- Page loads without errors
- Backend connectivity
- Graph rendering (nodes, edges)
- Data loading from API

### ✅ Controls
- Weight sliders (α, β, γ)
- Seed input and "Apply Seeds" button
- Shadow nodes toggle
- Mutual-only edges toggle

### ✅ Interactions
- Graph zoom (mouse wheel)
- Graph pan (drag)
- Node selection (if implemented)

### ✅ Loading States
- Loading indicators during data fetch
- Error messages when backend is down

### ✅ Export
- CSV export functionality

### ✅ Responsive Design
- Mobile viewport (375x667)
- Tablet viewport (768x1024)
- Desktop viewports

### ✅ Accessibility
- Labeled controls
- Keyboard navigation (if implemented)

### ✅ Performance
- Page load time (<10s)
- Graph rendering performance

## CI/CD Integration

To run tests in CI:

```yaml
# .github/workflows/test.yml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd tpot-analyzer/graph-explorer
          npm ci
          npx playwright install --with-deps

      - name: Start backend
        run: |
          cd tpot-analyzer
          pip install -r requirements.txt
          python -m scripts.start_api_server &
          sleep 5

      - name: Run Playwright tests
        run: |
          cd tpot-analyzer/graph-explorer
          npm test

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: tpot-analyzer/graph-explorer/playwright-report
```

## Debugging Tips

### Test Failures
1. Run with `--headed` to see browser UI
2. Run with `--debug` to step through
3. Check `playwright-report/` for screenshots/videos
4. Verify both servers are running and accessible

### Common Issues

**"page.goto: net::ERR_CONNECTION_REFUSED"**
- Ensure frontend is running on http://localhost:5173
- Check `npm run dev` is active

**"Backend API not responding"**
- Ensure backend is running on http://localhost:5001
- Check `python -m scripts.start_api_server` is active
- Verify `/health` endpoint returns 200

**"Timeout waiting for element"**
- Graph may be loading slowly
- Increase timeout in test: `await expect(element).toBeVisible({ timeout: 10000 })`
- Check for console errors in browser

**"Screenshot/video artifacts missing"**
- Check `playwright.config.js` has `screenshot` and `video` options set
- Artifacts are saved to `test-results/` and `playwright-report/`

## Writing New Tests

### Test Structure
```javascript
test('should do something', async ({ page }) => {
  // Navigate
  await page.goto('/');

  // Interact
  await page.click('button');

  // Assert
  await expect(page.locator('h1')).toBeVisible();
});
```

### Best Practices
- Use `data-testid` attributes for reliable selectors
- Wait for network idle before assertions
- Use `page.waitForSelector()` for dynamic content
- Take screenshots for documentation: `await page.screenshot({ path: 'screenshot.png' })`

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Test API Reference](https://playwright.dev/docs/api/class-test)
- [Best Practices](https://playwright.dev/docs/best-practices)
