import { test, expect, Page } from '@playwright/test'

/**
 * E2E tests for ClusterView with mocked backend.
 * 
 * These tests verify the cluster visualization UI works correctly
 * without requiring the real Python backend.
 * 
 * Test helpers exposed by ClusterCanvas:
 * - window.__CLUSTER_CANVAS_TEST__.getNodeIds() - list of node IDs
 * - window.__CLUSTER_CANVAS_TEST__.getNodeScreenPosition(id) - {x, y} screen coords
 * - window.__CLUSTER_CANVAS_TEST__.getAllNodePositions() - all nodes with screen coords
 */

// ---------- Mock Data ----------
const BASE_CLUSTERS = [
  { id: 'root_a', size: 30, label: 'Root A', childrenIds: ['a1', 'a2'], parentId: null },
  { id: 'root_b', size: 20, label: 'Root B', childrenIds: ['b1', 'b2'], parentId: null },
  { id: 'root_c', size: 15, label: 'Root C', childrenIds: [], parentId: null },
]

const CHILDREN: Record<string, any[]> = {
  root_a: [
    { id: 'a1', size: 15, label: 'A1', parentId: 'root_a', childrenIds: [] },
    { id: 'a2', size: 15, label: 'A2', parentId: 'root_a', childrenIds: [] },
  ],
  root_b: [
    { id: 'b1', size: 10, label: 'B1', parentId: 'root_b', childrenIds: [] },
    { id: 'b2', size: 10, label: 'B2', parentId: 'root_b', childrenIds: [] },
  ],
}

// ---------- Helpers ----------

const positionsFor = (clusters: any[]) => {
  // Spread clusters horizontally for easy clicking
  const step = 100
  const startX = 200
  const startY = 200
  return Object.fromEntries(
    clusters.map((c, idx) => [c.id, [startX + idx * step, startY]])
  )
}

const buildClusters = (expanded: Set<string>, collapsed: Set<string>) => {
  let clusters = [...BASE_CLUSTERS]

  // Apply expands
  expanded.forEach(id => {
    if (collapsed.has(id)) return
    const children = CHILDREN[id]
    if (!children) return
    clusters = clusters.filter(c => c.id !== id).concat(children)
  })

  // Apply collapses
  collapsed.forEach(id => {
    const parent = BASE_CLUSTERS.find(c => c.id === id)
    if (!parent) return
    clusters = clusters.filter(c => c.parentId !== id && c.id !== id)
    clusters.push(parent)
  })

  return clusters
}

const parseVisible = (text: string) => {
  const match = text.match(/Visible\s+(\d+)\s*\/\s*(\d+)/i)
  if (!match) throw new Error(`Could not parse visible text: ${text}`)
  return { visible: Number(match[1]), budget: Number(match[2]) }
}

/** Click on a cluster node by ID using test helpers */
const clickNode = async (page: Page, nodeId: string) => {
  // Wait for test helper to be available
  await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds)
  
  const pos = await page.evaluate((id) => {
    return window.__CLUSTER_CANVAS_TEST__?.getNodeScreenPosition(id)
  }, nodeId)
  
  if (!pos) {
    throw new Error(`Node ${nodeId} not found. Available: ${await page.evaluate(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds())}`)
  }
  
  await page.locator('canvas').click({ position: { x: pos.x, y: pos.y } })
}

/** Wait for cluster details panel to appear */
const waitForSelection = async (page: Page) => {
  await expect(page.getByText('Cluster details')).toBeVisible({ timeout: 5000 })
}

// ---------- Mock API Setup ----------

const setupMockApi = async (page: Page, { failClusters = false } = {}) => {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const pathname = url.pathname

    if (failClusters && pathname === '/api/clusters') {
      return route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Mock server error' }),
        contentType: 'application/json',
      })
    }

    if (pathname === '/api/clusters') {
      const expanded = new Set((url.searchParams.get('expanded') || '').split(',').filter(Boolean))
      const collapsed = new Set((url.searchParams.get('collapsed') || '').split(',').filter(Boolean))
      const budget = Number(url.searchParams.get('budget') || 10)
      const clusters = buildClusters(expanded, collapsed)
      const positions = positionsFor(clusters)
      const payload = {
        clusters,
        edges: [],
        positions,
        meta: {
          budget,
          budget_remaining: Math.max(0, budget - clusters.length),
          approximate_mode: false,
        },
        cache_hit: false,
        total_nodes: 100,
        granularity: Number(url.searchParams.get('n') || 10),
      }
      return route.fulfill({ status: 200, body: JSON.stringify(payload), contentType: 'application/json' })
    }

    if (pathname.match(/\/api\/clusters\/[^/]+\/preview/)) {
      const parts = pathname.split('/')
      const clusterId = parts[3]
      const expanded = new Set((url.searchParams.get('expanded') || '').split(',').filter(Boolean))
      const collapsed = new Set((url.searchParams.get('collapsed') || '').split(',').filter(Boolean))
      const budget = Number(url.searchParams.get('budget') || 10)
      const clusters = buildClusters(expanded, collapsed)
      const cluster = clusters.find(c => c.id === clusterId)
      const remaining = Math.max(0, budget - clusters.length)
      const children = CHILDREN[clusterId] || []
      const budgetImpact = children.length ? children.length - 1 : 0
      const canAfford = remaining >= budgetImpact
      const expand = {
        can_expand: children.length > 0 && !collapsed.has(clusterId) && canAfford,
        predicted_children: children.length || 0,
        budget_impact: budgetImpact,
        reason: !canAfford ? 'budget' : '',
      }
      const siblingIds = cluster?.parentId ? (CHILDREN[cluster.parentId] || []).map(c => c.id).filter(id => id !== clusterId) : []
      const collapse = {
        can_collapse: !!cluster?.parentId,
        parent_id: cluster?.parentId || null,
        sibling_ids: siblingIds,
        nodes_freed: siblingIds.length + 1,
      }
      return route.fulfill({ status: 200, body: JSON.stringify({ expand, collapse }), contentType: 'application/json' })
    }

    if (pathname.match(/\/api\/clusters\/[^/]+\/members/)) {
      return route.fulfill({
        status: 200,
        body: JSON.stringify({
          total: 3,
          members: [
            { id: 'u1', username: 'alice', numFollowers: 10 },
            { id: 'u2', username: 'bob', numFollowers: 20 },
            { id: 'u3', username: 'carol', numFollowers: 30 },
          ],
        }),
        contentType: 'application/json',
      })
    }

    if (pathname === '/api/log') {
      return route.fulfill({ status: 200, body: '{}' })
    }

    return route.fulfill({ status: 200, body: '{}' })
  })
}

// ---------- Tests ----------

// Extend window type for TypeScript
declare global {
  interface Window {
    __CLUSTER_CANVAS_TEST__?: {
      getNodeIds: () => string[]
      getNodeScreenPosition: (id: string) => { x: number; y: number } | null
      getAllNodePositions: () => Array<{ id: string; x: number; y: number; radius: number }>
      getTransform: () => { scale: number; offset: { x: number; y: number } }
    }
  }
}

test.describe('ClusterView (mocked backend)', () => {
  
  test('loads clusters and displays them on canvas', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10')
    
    // Canvas should be visible
    await expect(page.locator('canvas')).toBeVisible()
    
    // Wait for clusters to load
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    
    // Should have 3 base clusters
    const nodeIds = await page.evaluate(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds())
    expect(nodeIds).toContain('root_a')
    expect(nodeIds).toContain('root_b')
    expect(nodeIds).toContain('root_c')
    
    // Visible count should show in UI
    const visibleText = await page.locator('text=Visible').first().innerText()
    const { visible } = parseVisible(visibleText)
    expect(visible).toBe(3)
  })

  test('selecting a cluster shows details panel', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    
    // Click on root_a
    await clickNode(page, 'root_a')
    
    // Details panel should appear
    await waitForSelection(page)
    
    // Should show expand button (root_a has children)
    await expect(page.getByRole('button', { name: /Expand/ })).toBeVisible()
  })

  test('expand button increases visible cluster count', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    
    const initialVisible = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(initialVisible.visible).toBe(3)
    
    // Select expandable cluster
    await clickNode(page, 'root_a')
    await waitForSelection(page)
    
    // Click expand
    const expandBtn = page.getByRole('button', { name: /Expand/ })
    await expect(expandBtn).toBeVisible()
    await expect(expandBtn).toBeEnabled()
    await expandBtn.click()
    
    // Wait for new clusters to load
    await page.waitForTimeout(500)
    
    // Visible count should increase (root_a replaced by a1, a2 = net +1)
    const afterVisible = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(afterVisible.visible).toBeGreaterThan(initialVisible.visible)
  })

  test('collapse button decreases visible cluster count', async ({ page }) => {
    await setupMockApi(page)
    // Start with root_a already expanded
    await page.goto('/?view=cluster&n=10&budget=10&expanded=root_a')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    
    // Should have a1, a2, root_b, root_c (4 clusters)
    const beforeVisible = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(beforeVisible.visible).toBe(4)
    
    // Select a child cluster (a1)
    await clickNode(page, 'a1')
    await waitForSelection(page)
    
    // Click collapse
    const collapseBtn = page.getByRole('button', { name: /^Collapse/ })
    await expect(collapseBtn).toBeVisible()
    await collapseBtn.click()
    
    // Wait for collapse
    await page.waitForTimeout(500)
    
    // Visible count should decrease
    const afterVisible = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(afterVisible.visible).toBeLessThan(beforeVisible.visible)
  })

  test('expand button is disabled when budget exhausted', async ({ page }) => {
    await setupMockApi(page)
    // Budget=3 with 3 clusters. Expanding root_a costs +1 (2 children - 1 parent).
    // With 0 remaining budget, expand should be blocked.
    await page.goto('/?view=cluster&n=10&budget=3')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    
    const beforeVisible = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(beforeVisible.visible).toBe(3)
    expect(beforeVisible.budget).toBe(3) // At capacity
    
    // Select expandable cluster
    await clickNode(page, 'root_a')
    await waitForSelection(page)
    
    // Expand button should be disabled due to budget constraint
    const expandBtn = page.getByRole('button', { name: /Expand/ })
    await expect(expandBtn).toBeVisible()
    await expect(expandBtn).toBeDisabled()
  })

  test('shows error message on cluster fetch failure', async ({ page }) => {
    await setupMockApi(page, { failClusters: true })
    await page.goto('/?view=cluster&n=10&budget=10')
    await expect(page.getByText(/HTTP 500/)).toBeVisible({ timeout: 10000 })
  })

  test('multi-select mode allows selecting multiple clusters', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    
    // Enable multi-select
    await page.getByRole('button', { name: /Multi-select off/ }).click()
    await expect(page.getByRole('button', { name: /Multi-select on/ })).toBeVisible()
    
    // Click two nodes
    await clickNode(page, 'root_a')
    await clickNode(page, 'root_b')
    
    // Multi-select should still be on
    await expect(page.getByRole('button', { name: /Multi-select on/ })).toBeVisible()
  })

  test('navigating with expanded param pre-expands clusters', async ({ page }) => {
    await setupMockApi(page)
    
    // Load without expansion first
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)
    const beforeIds = await page.evaluate(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds())
    expect(beforeIds).toContain('root_a')
    expect(beforeIds).not.toContain('a1')
    
    // Navigate with expanded param
    await page.goto('/?view=cluster&n=10&budget=10&expanded=root_a')
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.includes('a1'))
    
    const afterIds = await page.evaluate(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds())
    expect(afterIds).not.toContain('root_a') // Replaced by children
    expect(afterIds).toContain('a1')
    expect(afterIds).toContain('a2')
  })
})
