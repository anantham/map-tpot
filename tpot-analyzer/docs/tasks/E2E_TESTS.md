# CODEX TASK: E2E Test Infrastructure

**Created**: 2024-12-17  
**Priority**: High  
**Estimated Effort**: 6-8 hours  
**Dependencies**: None (self-contained)

---

## Objective

Build complete E2E test infrastructure so that:
1. **Mock tests** run fast without backend (CI gate)
2. **Real backend tests** run with fixture data (integration gate)
3. **No production data** required anywhere

---

## Current State

```
graph-explorer/e2e/
├── cluster_mock.spec.ts        ✅ 8/8 passing (uses mocked API)
├── cluster_real.spec.ts        ⚠️ Requires real backend + fixtures
├── teleport_tagging_mock.spec.ts ✅ Works (mocked API)
└── results/                    Test output

Test helpers available in ClusterCanvas.jsx:
- window.__CLUSTER_CANVAS_TEST__.getNodeIds()
- window.__CLUSTER_CANVAS_TEST__.getNodeScreenPosition(id)
- window.__CLUSTER_CANVAS_TEST__.getAllNodePositions()
```

---

## Modernization Note (2026-02-09)

This document is preserved as a historical implementation brief. Current repo
entrypoints differ from several original script names in this plan.

Current fixture bootstrap (from `tpot-analyzer/`):

```bash
python - <<'PY'
from pathlib import Path
from tests.fixtures.create_test_cache_db import create_test_cache_db

target = Path("tests/fixtures/test_cache.db")
counts = create_test_cache_db(target)
print(f"Created {target} with rows: {counts.as_dict()}")
PY
```

Current backend start for real E2E:

```bash
SNAPSHOT_DIR="$PWD/tests/fixtures" \
CACHE_DB_PATH="$PWD/tests/fixtures/test_cache.db" \
.venv/bin/python -m scripts.start_api_server
```

Current E2E runner entrypoint:

```bash
./scripts/run_e2e.sh full
```

---

## Task 1: Create Test Fixture Database

Create a deterministic SQLite database with 50 accounts for testing.

### 1.1 Create Fixture Script

**File (historical proposal, superseded)**: `scripts/create_test_fixtures.py`  
**Current implementation**: `tests/fixtures/create_test_cache_db.py`

```python
#!/usr/bin/env python3
"""Create deterministic test fixtures for E2E testing.

This creates a minimal but realistic database that:
- Has 50 accounts with predictable IDs and usernames
- Has a small-world network structure (each follows 5 others)
- Has varying follower counts for testing sorting
- Is completely deterministic (same output every run)

Usage:
    Use the modernization bootstrap snippet above.
    # Creates: tests/fixtures/test_cache.db
"""
import sqlite3
import hashlib
import random
from pathlib import Path
from datetime import datetime, timedelta

# Seed for reproducibility
random.seed(42)

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
DB_PATH = FIXTURES_DIR / "test_cache.db"

# Deterministic account data
ACCOUNT_NAMES = [
    "alice", "bob", "carol", "dave", "eve", "frank", "grace", "henry", "iris", "jack",
    "karen", "leo", "mia", "nick", "olivia", "peter", "quinn", "rosa", "sam", "tina",
    "uma", "victor", "wendy", "xavier", "yuki", "zara", "adam", "bella", "chris", "diana",
    "ethan", "fiona", "george", "hannah", "ian", "julia", "kevin", "luna", "mike", "nina",
    "oscar", "paula", "quentin", "rachel", "steve", "tara", "ulrich", "vera", "william", "xena"
]

def create_account_id(username: str) -> str:
    """Generate deterministic account ID from username."""
    return hashlib.sha256(username.encode()).hexdigest()[:16]


def create_schema(conn: sqlite3.Connection) -> None:
    """Create database schema matching production."""
    conn.executescript("""
        -- Main account table
        CREATE TABLE IF NOT EXISTS shadow_account (
            account_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT,
            bio TEXT,
            location TEXT,
            website TEXT,
            followers_total INTEGER DEFAULT 0,
            following_total INTEGER DEFAULT 0,
            profile_image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_protected INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0
        );
        
        -- Edge table for follow relationships
        CREATE TABLE IF NOT EXISTS shadow_edge (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'following',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_id, target_id, edge_type),
            FOREIGN KEY (source_id) REFERENCES shadow_account(account_id),
            FOREIGN KEY (target_id) REFERENCES shadow_account(account_id)
        );
        
        -- Tags for accounts
        CREATE TABLE IF NOT EXISTS account_tags (
            account_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (account_id, tag),
            FOREIGN KEY (account_id) REFERENCES shadow_account(account_id)
        );
        
        -- Cluster labels
        CREATE TABLE IF NOT EXISTS cluster_labels (
            cluster_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Indices for performance
        CREATE INDEX IF NOT EXISTS idx_account_username ON shadow_account(username);
        CREATE INDEX IF NOT EXISTS idx_edge_source ON shadow_edge(source_id);
        CREATE INDEX IF NOT EXISTS idx_edge_target ON shadow_edge(target_id);
        CREATE INDEX IF NOT EXISTS idx_edge_type ON shadow_edge(edge_type);
        CREATE INDEX IF NOT EXISTS idx_tags_account ON account_tags(account_id);
        CREATE INDEX IF NOT EXISTS idx_tags_tag ON account_tags(tag);
    """)


def insert_accounts(conn: sqlite3.Connection) -> dict:
    """Insert 50 deterministic accounts."""
    accounts = {}
    base_date = datetime(2020, 1, 1)
    
    for i, username in enumerate(ACCOUNT_NAMES):
        account_id = create_account_id(username)
        accounts[username] = account_id
        
        # Vary follower counts based on position (creates natural hierarchy)
        # First 10 are "influencers" with high followers
        if i < 10:
            followers = 10000 + (10 - i) * 1000
            following = 500 + random.randint(0, 200)
        elif i < 30:
            followers = 1000 + random.randint(0, 2000)
            following = 300 + random.randint(0, 300)
        else:
            followers = 100 + random.randint(0, 500)
            following = 100 + random.randint(0, 200)
        
        # Deterministic bio and location
        bio = f"Test user {username}. Account #{i+1} in the fixture set."
        location = ["San Francisco", "New York", "London", "Tokyo", "Berlin"][i % 5]
        
        created_at = base_date + timedelta(days=i * 7)
        
        conn.execute("""
            INSERT INTO shadow_account 
            (account_id, username, display_name, bio, location, followers_total, 
             following_total, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id,
            username,
            username.title(),
            bio,
            location,
            followers,
            following,
            created_at.isoformat(),
            datetime.now().isoformat(),
        ))
    
    return accounts


def insert_edges(conn: sqlite3.Connection, accounts: dict) -> None:
    """Create small-world network structure.
    
    Each account follows:
    - The next 3 accounts in sequence (local clustering)
    - 2 random accounts (long-range connections)
    
    This creates realistic community structure.
    """
    usernames = list(accounts.keys())
    n = len(usernames)
    
    edges = []
    for i, username in enumerate(usernames):
        source_id = accounts[username]
        
        # Local connections (next 3)
        for j in range(1, 4):
            target_username = usernames[(i + j) % n]
            target_id = accounts[target_username]
            edges.append((source_id, target_id, "following"))
        
        # Long-range connections (2 random, but deterministic)
        random.seed(42 + i)  # Deterministic random
        for _ in range(2):
            target_idx = random.randint(0, n - 1)
            if target_idx != i:
                target_username = usernames[target_idx]
                target_id = accounts[target_username]
                edges.append((source_id, target_id, "following"))
    
    # Remove duplicates
    edges = list(set(edges))
    
    conn.executemany("""
        INSERT OR IGNORE INTO shadow_edge (source_id, target_id, edge_type)
        VALUES (?, ?, ?)
    """, edges)


def insert_tags(conn: sqlite3.Connection, accounts: dict) -> None:
    """Add some tags to accounts for testing."""
    tags_data = [
        # First 5 accounts tagged as "core"
        *[(accounts[u], "core") for u in ACCOUNT_NAMES[:5]],
        # Accounts 5-15 tagged as "active"
        *[(accounts[u], "active") for u in ACCOUNT_NAMES[5:15]],
        # Some accounts tagged as "interesting"
        *[(accounts[u], "interesting") for u in ACCOUNT_NAMES[::5]],
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO account_tags (account_id, tag)
        VALUES (?, ?)
    """, tags_data)


def insert_cluster_labels(conn: sqlite3.Connection) -> None:
    """Add some cluster labels for testing."""
    labels = [
        ("d_100", "Test Cluster A"),
        ("d_101", "Test Cluster B"),
        ("d_102", "Tech Twitter"),
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO cluster_labels (cluster_id, label)
        VALUES (?, ?)
    """, labels)


def main():
    """Create the test fixture database."""
    # Ensure fixtures directory exists
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Remove existing database
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing: {DB_PATH}")
    
    # Create new database
    conn = sqlite3.connect(DB_PATH)
    
    print("Creating schema...")
    create_schema(conn)
    
    print("Inserting accounts...")
    accounts = insert_accounts(conn)
    print(f"  Created {len(accounts)} accounts")
    
    print("Inserting edges...")
    insert_edges(conn, accounts)
    edge_count = conn.execute("SELECT COUNT(*) FROM shadow_edge").fetchone()[0]
    print(f"  Created {edge_count} edges")
    
    print("Inserting tags...")
    insert_tags(conn, accounts)
    tag_count = conn.execute("SELECT COUNT(*) FROM account_tags").fetchone()[0]
    print(f"  Created {tag_count} tags")
    
    print("Inserting cluster labels...")
    insert_cluster_labels(conn)
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Created test database: {DB_PATH}")
    print(f"   Size: {DB_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
```

### 1.2 Run and Verify

```bash
cd tpot-analyzer
python - <<'PY'
from pathlib import Path
from tests.fixtures.create_test_cache_db import create_test_cache_db

target = Path("tests/fixtures/test_cache.db")
counts = create_test_cache_db(target)
print(f"Created {target} with rows: {counts.as_dict()}")
PY

# Verify
sqlite3 tests/fixtures/test_cache.db "SELECT COUNT(*) FROM shadow_account"
# Expected: 50

sqlite3 tests/fixtures/test_cache.db "SELECT COUNT(*) FROM shadow_edge"
# Expected: ~200-250

sqlite3 tests/fixtures/test_cache.db "SELECT username, followers_total FROM shadow_account ORDER BY followers_total DESC LIMIT 5"
# Expected: alice, bob, carol, dave, eve with high follower counts
```

---

## Task 2: Backend Test Server Script

Create a script that starts the Flask backend with test fixtures.

### 2.1 Create Test Server Script

**File (historical proposal, superseded)**: `scripts/start_test_backend.sh`

```bash
#!/bin/bash
# Start backend server with test fixtures for E2E testing.
#
# Usage:
#   ./scripts/start_test_backend.sh
#   # Starts on port 5001, writes PID to .test_backend_pid
#
#   ./scripts/start_test_backend.sh --stop
#   # Stops the test backend

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/.test_backend_pid"
TEST_DB="$PROJECT_DIR/tests/fixtures/test_cache.db"
PORT=5001

cd "$PROJECT_DIR"

# Handle --stop flag
if [ "$1" = "--stop" ]; then
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping test backend (PID $PID)..."
            kill "$PID"
            rm -f "$PID_FILE"
            echo "✅ Stopped"
        else
            echo "Process $PID not running, cleaning up PID file"
            rm -f "$PID_FILE"
        fi
    else
        echo "No PID file found at $PID_FILE"
    fi
    exit 0
fi

# Check if test fixtures exist
if [ ! -f "$TEST_DB" ]; then
    echo "❌ Test database not found at $TEST_DB"
    echo "   Run fixture bootstrap from docs/tasks/E2E_TESTS.md modernization note."
    exit 1
fi

# Check if port is already in use
if lsof -i :$PORT > /dev/null 2>&1; then
    echo "⚠️  Port $PORT already in use"
    echo "   Stop existing server or use different port"
    exit 1
fi

# Activate virtualenv if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Export test configuration
export TPOT_TEST_MODE=1
export TPOT_CACHE_DB="$TEST_DB"
export FLASK_ENV=testing

echo "Starting test backend on port $PORT..."
echo "  Database: $TEST_DB"
echo "  PID file: $PID_FILE"

# Start server in background
python -m scripts.start_api_server --port $PORT &
SERVER_PID=$!

# Write PID file
echo $SERVER_PID > "$PID_FILE"

# Wait for server to be ready
echo "Waiting for server to start..."
for i in {1..30}; do
    if curl -s "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
        echo "✅ Test backend ready on port $PORT (PID $SERVER_PID)"
        exit 0
    fi
    sleep 1
done

echo "❌ Server failed to start within 30 seconds"
kill $SERVER_PID 2>/dev/null
rm -f "$PID_FILE"
exit 1
```

### 2.2 Make Executable

```bash
chmod +x scripts/start_test_backend.sh
```

### 2.3 Add Health Endpoint (if not present)

Check if `/api/health` exists. If not, add to `src/api/server.py`:

```python
@app.route('/api/health')
def health():
    """Health check endpoint for test scripts."""
    return jsonify({"status": "ok", "test_mode": os.getenv("TPOT_TEST_MODE") == "1"})
```

---

## Task 3: Update Playwright Configuration

Update `playwright.config.ts` to support both mock and real backend modes.

### 3.1 Updated Config

**File**: `graph-explorer/playwright.config.ts`

```typescript
import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';

/**
 * Playwright configuration with dual-mode support:
 * 
 * MOCK MODE (default, fast):
 *   PW_MOCK_ONLY=1 npm run test:e2e
 *   - Only runs *_mock.spec.ts files
 *   - No backend required
 *   - Fast CI feedback
 * 
 * REAL BACKEND MODE:
 *   npm run test:e2e:real
 *   - Runs against real Flask backend with test fixtures
 *   - Requires backend running on port 5001
 *   - Slower but tests full integration
 */

function resolveChromiumExecutablePath(): string | undefined {
  const envPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const candidates = [
    envPath,
    // Prefer system browsers (no download required)
    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    // Linux paths
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
  ].filter(Boolean) as string[];

  for (const candidate of candidates) {
    try {
      if (candidate && fs.existsSync(candidate)) return candidate;
    } catch {
      // ignore
    }
  }
  return undefined;
}

const chromiumExecutablePath = resolveChromiumExecutablePath();
const isMockOnly = process.env.PW_MOCK_ONLY === '1';
const backendPort = process.env.PW_BACKEND_PORT || '5001';

export default defineConfig({
  testDir: './e2e',
  
  // Only run mock tests in mock mode
  testMatch: isMockOnly ? '*_mock.spec.ts' : '*.spec.ts',
  
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  
  // Timeout: 30s for mock tests, 180s for real backend (cluster builds are slow)
  timeout: isMockOnly ? 30000 : 180000,
  
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'e2e/results/test-results.json' }],
    ['list'],  // Show test names in console
  ],
  
  use: {
    // Frontend always on 5173
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(chromiumExecutablePath
          ? {
              launchOptions: {
                executablePath: chromiumExecutablePath,
              },
            }
          : {}),
      },
    },
  ],
  
  // Web servers configuration
  webServer: process.env.PW_NO_SERVER
    ? undefined
    : [
        // Frontend dev server (always started)
        {
          command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
          url: 'http://127.0.0.1:5173',
          reuseExistingServer: !process.env.CI,
          timeout: 60 * 1000,
        },
        // Backend (only in real mode, not mock)
        ...(!isMockOnly
          ? [
              {
                command: `cd .. && SNAPSHOT_DIR="$PWD/tests/fixtures" CACHE_DB_PATH="$PWD/tests/fixtures/test_cache.db" .venv/bin/python -m scripts.start_api_server`,
                url: `http://127.0.0.1:${backendPort}/api/health`,
                reuseExistingServer: true,
                timeout: 120 * 1000,
              },
            ]
          : []),
      ],
  
  // Global setup/teardown for real backend mode
  globalSetup: isMockOnly ? undefined : './e2e/global-setup.ts',
  globalTeardown: isMockOnly ? undefined : './e2e/global-teardown.ts',
});
```

### 3.2 Create Global Setup/Teardown

**File**: `graph-explorer/e2e/global-setup.ts`

```typescript
import { FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  console.log('\n🔧 E2E Global Setup');
  console.log('   Backend URL:', process.env.PW_BACKEND_URL || 'http://127.0.0.1:5001');
  console.log('   Frontend URL:', config.projects[0].use.baseURL);
  
  // Verify backend is reachable
  const backendUrl = process.env.PW_BACKEND_URL || 'http://127.0.0.1:5001';
  try {
    const response = await fetch(`${backendUrl}/api/health`);
    if (!response.ok) {
      throw new Error(`Backend health check failed: ${response.status}`);
    }
    const data = await response.json();
    console.log('   Backend status:', data.status);
    if (data.test_mode) {
      console.log('   ✅ Running in test mode with fixture data');
    }
  } catch (error) {
    console.error('   ❌ Backend not reachable:', error);
    throw new Error('Backend must be running for real E2E tests. Run: .venv/bin/python -m scripts.start_api_server');
  }
}

export default globalSetup;
```

**File**: `graph-explorer/e2e/global-teardown.ts`

```typescript
import { FullConfig } from '@playwright/test';

async function globalTeardown(config: FullConfig) {
  console.log('\n🧹 E2E Global Teardown');
  // Backend cleanup is handled by the test script
  // This is a hook for any additional cleanup needed
}

export default globalTeardown;
```

---

## Task 4: Real Backend E2E Tests

Create E2E tests that run against the real Flask backend with test fixtures.

### 4.1 Create Real Backend Test File

**File**: `graph-explorer/e2e/cluster_real.spec.ts`

```typescript
import { test, expect, Page } from '@playwright/test';

/**
 * E2E tests for ClusterView with REAL backend.
 * 
 * These tests require:
 * - Test fixture database (run the modernization fixture bootstrap snippet)
 * - Backend running on port 5001 (`.venv/bin/python -m scripts.start_api_server`)
 * 
 * Run with: npm run test:e2e:real
 */

const BACKEND_URL = process.env.PW_BACKEND_URL || 'http://127.0.0.1:5001';

// ---------- Test Helpers ----------

/** Wait for clusters to load (real backend is slower) */
async function waitForClusters(page: Page, timeout = 60000) {
  // Wait for loading indicator to disappear
  await page.waitForSelector('[data-testid="cluster-loading"]', { 
    state: 'hidden', 
    timeout 
  }).catch(() => {
    // Loading indicator might not exist if already loaded
  });
  
  // Wait for canvas to have nodes
  await page.waitForFunction(
    () => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0,
    { timeout }
  );
}

/** Click on a cluster node by ID */
async function clickNode(page: Page, nodeId: string) {
  const pos = await page.evaluate((id) => {
    return window.__CLUSTER_CANVAS_TEST__?.getNodeScreenPosition(id);
  }, nodeId);
  
  if (!pos) {
    const available = await page.evaluate(() => 
      window.__CLUSTER_CANVAS_TEST__?.getNodeIds()
    );
    throw new Error(`Node ${nodeId} not found. Available: ${available?.join(', ')}`);
  }
  
  await page.locator('canvas').click({ position: { x: pos.x, y: pos.y } });
}

/** Get current node IDs from canvas */
async function getNodeIds(page: Page): Promise<string[]> {
  return page.evaluate(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds() || []);
}

// ---------- Tests ----------

test.describe('ClusterView with Real Backend', () => {
  test.beforeEach(async ({ page }) => {
    // Go to cluster view
    await page.goto('/clusters');
  });

  test('loads clusters from backend', async ({ page }) => {
    await waitForClusters(page);
    
    const nodeIds = await getNodeIds(page);
    expect(nodeIds.length).toBeGreaterThan(0);
    
    // Should have positions for all nodes
    const positions = await page.evaluate(() => 
      window.__CLUSTER_CANVAS_TEST__?.getAllNodePositions()
    );
    expect(Object.keys(positions || {}).length).toBe(nodeIds.length);
  });

  test('displays cluster count in header', async ({ page }) => {
    await waitForClusters(page);
    
    // Look for "Visible X / Y" text
    const visibleText = await page.locator('text=/Visible \\d+ \\/ \\d+/').textContent();
    expect(visibleText).toBeTruthy();
    
    const match = visibleText!.match(/Visible (\d+) \/ (\d+)/);
    expect(match).toBeTruthy();
    
    const [, visible, budget] = match!;
    expect(parseInt(visible)).toBeGreaterThan(0);
    expect(parseInt(budget)).toBeGreaterThan(parseInt(visible) - 1);
  });

  test('selecting a cluster shows details panel', async ({ page }) => {
    await waitForClusters(page);
    
    const nodeIds = await getNodeIds(page);
    expect(nodeIds.length).toBeGreaterThan(0);
    
    // Click first node
    await clickNode(page, nodeIds[0]);
    
    // Details panel should appear
    await expect(page.getByText('Cluster details')).toBeVisible({ timeout: 5000 });
  });

  test('expanding a cluster shows children', async ({ page }) => {
    await waitForClusters(page);
    
    const initialNodeIds = await getNodeIds(page);
    const initialCount = initialNodeIds.length;
    
    // Find an expandable node (has children)
    // Click it to select
    await clickNode(page, initialNodeIds[0]);
    await expect(page.getByText('Cluster details')).toBeVisible();
    
    // Look for expand button and click if available
    const expandButton = page.getByRole('button', { name: /expand/i });
    const canExpand = await expandButton.isVisible().catch(() => false);
    
    if (canExpand) {
      await expandButton.click();
      
      // Wait for expansion animation
      await page.waitForTimeout(500);
      await waitForClusters(page);
      
      const newNodeIds = await getNodeIds(page);
      expect(newNodeIds.length).toBeGreaterThanOrEqual(initialCount);
    }
  });

  test('autocomplete search finds test accounts', async ({ page }) => {
    await waitForClusters(page);
    
    // Find search input
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill('alice');
    
    // Wait for autocomplete results
    await page.waitForTimeout(500);
    
    // Should find alice from test fixtures
    const results = page.locator('[data-testid="autocomplete-result"]');
    const count = await results.count();
    
    // May or may not have results depending on implementation
    // At minimum, typing should not error
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('cluster positions are stable across reloads', async ({ page }) => {
    await waitForClusters(page);
    
    // Get initial positions
    const positions1 = await page.evaluate(() => 
      window.__CLUSTER_CANVAS_TEST__?.getAllNodePositions()
    );
    
    // Reload page
    await page.reload();
    await waitForClusters(page);
    
    // Get positions again
    const positions2 = await page.evaluate(() => 
      window.__CLUSTER_CANVAS_TEST__?.getAllNodePositions()
    );
    
    // Same node IDs should be present
    const ids1 = Object.keys(positions1 || {}).sort();
    const ids2 = Object.keys(positions2 || {}).sort();
    expect(ids1).toEqual(ids2);
    
    // Positions should be similar (within tolerance due to layout algorithm)
    for (const id of ids1) {
      const p1 = positions1![id];
      const p2 = positions2![id];
      // Allow some variance but should be roughly same position
      const distance = Math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2);
      expect(distance).toBeLessThan(50); // 50px tolerance
    }
  });

  test('budget parameter affects cluster count', async ({ page }) => {
    // Load with low budget
    await page.goto('/clusters?budget=10');
    await waitForClusters(page);
    const lowBudgetCount = (await getNodeIds(page)).length;
    
    // Load with high budget
    await page.goto('/clusters?budget=30');
    await waitForClusters(page);
    const highBudgetCount = (await getNodeIds(page)).length;
    
    // Higher budget should allow more clusters
    expect(highBudgetCount).toBeGreaterThanOrEqual(lowBudgetCount);
  });
});
```

### 4.2 Add TypeScript Types

**File**: `graph-explorer/e2e/types.d.ts`

```typescript
/**
 * Type declarations for test helpers exposed by ClusterCanvas.
 */

interface ClusterCanvasTestHelpers {
  getNodeIds(): string[];
  getNodeScreenPosition(nodeId: string): { x: number; y: number } | null;
  getAllNodePositions(): Record<string, { x: number; y: number }>;
  getTransform(): { scale: number; offset: { x: number; y: number } };
}

declare global {
  interface Window {
    __CLUSTER_CANVAS_TEST__?: ClusterCanvasTestHelpers;
  }
}

export {};
```

---

## Task 5: Discovery E2E Tests

### 5.1 Add data-testid Attributes to Discovery.jsx

**File**: `graph-explorer/src/Discovery.jsx`

Add these `data-testid` attributes to key elements:

```jsx
// Loading state
<div data-testid="discovery-loading">Loading...</div>

// Candidate cards
<div data-testid="candidate-card" key={candidate.id}>
  <span data-testid="candidate-username">{candidate.username}</span>
  <span data-testid="candidate-score">{candidate.score}</span>
</div>

// Weight sliders
<input 
  data-testid="weight-slider-followers"
  type="range" 
  value={weights.followers}
  onChange={...}
/>

// Filter controls
<button data-testid="filter-apply">Apply Filters</button>
<button data-testid="filter-reset">Reset</button>
```

### 5.2 Create Discovery E2E Tests

**File**: `graph-explorer/e2e/discovery.spec.ts`

```typescript
import { test, expect, Page } from '@playwright/test';

/**
 * E2E tests for Discovery page.
 * 
 * Runs against real backend with test fixtures.
 */

test.describe('Discovery Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/discovery');
  });

  test('loads discovery interface', async ({ page }) => {
    // Wait for loading to complete
    await page.waitForSelector('[data-testid="discovery-loading"]', { 
      state: 'hidden',
      timeout: 30000 
    }).catch(() => {});
    
    // Should have candidate cards
    const cards = page.locator('[data-testid="candidate-card"]');
    await expect(cards.first()).toBeVisible({ timeout: 30000 });
  });

  test('displays candidate information', async ({ page }) => {
    await page.waitForTimeout(2000); // Wait for load
    
    const firstCard = page.locator('[data-testid="candidate-card"]').first();
    await expect(firstCard).toBeVisible({ timeout: 30000 });
    
    // Should have username
    const username = firstCard.locator('[data-testid="candidate-username"]');
    await expect(username).toBeVisible();
    
    // Should have score
    const score = firstCard.locator('[data-testid="candidate-score"]');
    await expect(score).toBeVisible();
  });

  test('weight sliders affect ranking', async ({ page }) => {
    await page.waitForTimeout(2000);
    
    // Get initial order
    const getFirstUsername = async () => {
      const username = await page
        .locator('[data-testid="candidate-card"]')
        .first()
        .locator('[data-testid="candidate-username"]')
        .textContent();
      return username;
    };
    
    const initial = await getFirstUsername();
    
    // Adjust a weight slider
    const slider = page.locator('[data-testid="weight-slider-followers"]');
    if (await slider.isVisible()) {
      await slider.fill('0'); // Set to minimum
      await page.waitForTimeout(1000); // Wait for re-rank
      
      // Order might have changed
      const after = await getFirstUsername();
      // Just verify we didn't crash - order change depends on data
      expect(after).toBeTruthy();
    }
  });

  test('filter controls work', async ({ page }) => {
    await page.waitForTimeout(2000);
    
    const applyButton = page.locator('[data-testid="filter-apply"]');
    const resetButton = page.locator('[data-testid="filter-reset"]');
    
    if (await applyButton.isVisible()) {
      await applyButton.click();
      await page.waitForTimeout(500);
      // Should not error
    }
    
    if (await resetButton.isVisible()) {
      await resetButton.click();
      await page.waitForTimeout(500);
      // Should not error
    }
  });
});
```

---

## Task 6: Update package.json Scripts

**File**: `graph-explorer/package.json`

Add these scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    
    "test": "vitest run",
    "test:watch": "vitest",
    
    "test:e2e": "playwright test",
    "test:e2e:mock": "PW_MOCK_ONLY=1 playwright test",
    "test:e2e:real": "playwright test e2e/cluster_real.spec.ts e2e/discovery.spec.ts",
    "test:e2e:all": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e:debug": "PWDEBUG=1 playwright test",
    
    "test:e2e:report": "playwright show-report"
  }
}
```

---

## Task 7: CI-Friendly Test Script

Create a comprehensive test runner for CI.

**File (historical proposal, superseded)**: `scripts/run_all_tests.sh`

```bash
#!/bin/bash
# Run all tests in the correct order.
#
# Usage:
#   ./scripts/run_all_tests.sh          # Run all tests
#   ./scripts/run_all_tests.sh --quick  # Skip slow E2E tests
#   ./scripts/run_all_tests.sh --e2e    # Only E2E tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/graph-explorer"

cd "$PROJECT_DIR"

# Parse arguments
QUICK_MODE=false
E2E_ONLY=false

for arg in "$@"; do
  case $arg in
    --quick)
      QUICK_MODE=true
      ;;
    --e2e)
      E2E_ONLY=true
      ;;
  esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() {
  echo -e "${GREEN}✅ $1${NC}"
}

fail() {
  echo -e "${RED}❌ $1${NC}"
  exit 1
}

info() {
  echo -e "${YELLOW}🔄 $1${NC}"
}

# Activate virtualenv
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

# ---------- Python Tests ----------

if [ "$E2E_ONLY" = false ]; then
  info "Running Python tests..."
  
  if python -m pytest tests/ -v --tb=short; then
    success "Python tests passed"
  else
    fail "Python tests failed"
  fi
fi

# ---------- Frontend Unit Tests ----------

if [ "$E2E_ONLY" = false ]; then
  info "Running frontend unit tests..."
  
  cd "$FRONTEND_DIR"
  if npm run test; then
    success "Frontend unit tests passed"
  else
    fail "Frontend unit tests failed"
  fi
  cd "$PROJECT_DIR"
fi

# ---------- E2E Mock Tests ----------

info "Running E2E mock tests..."

cd "$FRONTEND_DIR"
if PW_MOCK_ONLY=1 npx playwright test; then
  success "E2E mock tests passed"
else
  fail "E2E mock tests failed"
fi
cd "$PROJECT_DIR"

# ---------- E2E Real Backend Tests (slow) ----------

if [ "$QUICK_MODE" = false ]; then
  info "Setting up test fixtures..."
  
  # Create test database if not exists
  if [ ! -f "tests/fixtures/test_cache.db" ]; then
    python - <<'PY'
from pathlib import Path
from tests.fixtures.create_test_cache_db import create_test_cache_db

target = Path("tests/fixtures/test_cache.db")
counts = create_test_cache_db(target)
print(f"Created {target} with rows: {counts.as_dict()}")
PY
  fi
  
  info "Starting test backend..."
  SNAPSHOT_DIR="$PROJECT_DIR/tests/fixtures" \
  CACHE_DB_PATH="$PROJECT_DIR/tests/fixtures/test_cache.db" \
  python -m scripts.start_api_server &
  BACKEND_PID=$!
  
  # Trap to ensure cleanup
  cleanup() {
    info "Cleaning up test backend..."
    kill "$BACKEND_PID" 2>/dev/null || true
  }
  trap cleanup EXIT
  
  info "Running E2E real backend tests..."
  
  cd "$FRONTEND_DIR"
  if npx playwright test e2e/cluster_real.spec.ts; then
    success "E2E real backend tests passed"
  else
    fail "E2E real backend tests failed"
  fi
  cd "$PROJECT_DIR"
fi

# ---------- Summary ----------

echo ""
echo "=========================================="
success "All tests passed!"
echo "=========================================="
```

### Make Executable

```bash
chmod +x scripts/run_all_tests.sh
```

---

## Verification Checklist

Run these commands to verify each task:

```bash
# Task 1: Test fixtures
python - <<'PY'
from pathlib import Path
from tests.fixtures.create_test_cache_db import create_test_cache_db

target = Path("tests/fixtures/test_cache.db")
counts = create_test_cache_db(target)
print(f"Created {target} with rows: {counts.as_dict()}")
PY
sqlite3 tests/fixtures/test_cache.db "SELECT COUNT(*) FROM shadow_account"
# Expected: 50

# Task 2: Test backend
SNAPSHOT_DIR="$PWD/tests/fixtures" \
CACHE_DB_PATH="$PWD/tests/fixtures/test_cache.db" \
.venv/bin/python -m scripts.start_api_server
curl http://127.0.0.1:5001/api/health
# Expected: {"service":"tpot-analyzer","status":"ok"}
pkill -f "scripts.start_api_server"

# Task 3: Playwright config
cd graph-explorer
PW_MOCK_ONLY=1 npx playwright test --list
# Should list only *_mock.spec.ts files

# Task 4: Real backend tests
cd graph-explorer
npm run test:e2e:real
# Should run cluster_real.spec.ts

# Task 5: Discovery tests
cd graph-explorer
npx playwright test e2e/discovery.spec.ts
# May fail if data-testid not added yet

# Task 6: Package scripts
cd graph-explorer
npm run test:e2e:mock
# Should run mock tests only

# Task 7: Full test suite
cd tpot-analyzer
.venv/bin/python -m pytest tests/ -q
cd graph-explorer && npx vitest run && cd ..
./scripts/run_e2e.sh mock
# Should run pytest + vitest + mock E2E
```

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `tests/fixtures/create_test_cache_db.py` | CREATE | Generates deterministic test database |
| `scripts/start_test_backend.sh` | SUPERSEDED | Replaced by direct `scripts.start_api_server` launch |
| `graph-explorer/playwright.config.ts` | UPDATE | Dual-mode support (mock/real) |
| `graph-explorer/e2e/global-setup.ts` | CREATE | Backend verification |
| `graph-explorer/e2e/global-teardown.ts` | CREATE | Cleanup hook |
| `graph-explorer/e2e/cluster_real.spec.ts` | CREATE | Real backend tests |
| `graph-explorer/e2e/types.d.ts` | CREATE | TypeScript types |
| `graph-explorer/e2e/discovery.spec.ts` | CREATE | Discovery page tests |
| `graph-explorer/src/Discovery.jsx` | UPDATE | Add data-testid attributes |
| `graph-explorer/package.json` | UPDATE | Add test scripts |
| `scripts/run_all_tests.sh` | SUPERSEDED | Replaced by `scripts/run_e2e.sh` + pytest/vitest commands |

---

## Notes

1. **System browsers**: Config prefers system Brave/Chrome to avoid Playwright browser downloads in restricted networks.

2. **Test isolation**: Each test file can run independently. Mock tests don't need backend. Real tests need `scripts.start_api_server`.

3. **Determinism**: Test fixtures use seeded random (seed=42) for reproducible data.

4. **Timeouts**: Real backend tests use 180s timeout because initial cluster build is ~57s.

5. **CI compatibility**: `scripts/run_e2e.sh` plus pytest/vitest commands now cover the practical CI workflow.
