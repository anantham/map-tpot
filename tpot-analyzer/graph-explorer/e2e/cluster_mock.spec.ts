import { test, expect } from '@playwright/test'

// ---------- Mock helpers ----------
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

const positionsFor = (clusters: any[]) => {
  const step = 90
  const startX = 140
  const startY = 160
  return Object.fromEntries(
    clusters.map((c, idx) => [c.id, [startX + idx * step, startY]])
  )
}

const buildClusters = (expanded: Set<string>, collapsed: Set<string>, budget: number, padToBudget = false) => {
  let clusters = [...BASE_CLUSTERS]

  // Apply expands
  expanded.forEach(id => {
    if (collapsed.has(id)) return
    const children = CHILDREN[id]
    if (!children) return
    clusters = clusters.filter(c => c.id !== id).concat(children)
  })

  // Apply collapses (force parent back, drop children)
  collapsed.forEach(id => {
    const parent = BASE_CLUSTERS.find(c => c.id === id)
    if (!parent) return
    clusters = clusters.filter(c => c.parentId !== id && c.id !== id)
    clusters.push(parent)
  })

  // Optionally pad to budget to force budget_remaining = 0
  if (padToBudget && clusters.length < budget) {
    const needed = budget - clusters.length
    for (let i = 0; i < needed; i++) {
      clusters.push({
        id: `filler_${i}`,
        size: 5,
        label: `Filler ${i + 1}`,
        parentId: null,
        childrenIds: [],
      })
    }
  }

  return clusters
}

const parseVisible = (text: string) => {
  const match = text.match(/Visible\s+(\d+)\s*\/\s*(\d+)/i)
  if (!match) throw new Error(`Could not parse visible text: ${text}`)
  return { visible: Number(match[1]), budget: Number(match[2]) }
}

const trySelectNode = async (page, positions: { x: number, y: number }[]) => {
  const details = page.getByText('Cluster details')
  for (const pos of positions) {
    await page.locator('canvas').click({ position: pos })
    // wait briefly for side panel to appear
    const visible = await details.isVisible().catch(() => false)
    if (visible) return true
    await page.waitForTimeout(100)
  }
  return false
}

const setupMockApi = async (page, { padToBudget = false } = {}) => {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const pathname = url.pathname

    // Allow explicit failure toggle
    if (url.searchParams.get('fail') === '1') {
      return route.fulfill({ status: 500, body: 'Mock 500' })
    }

    if (pathname === '/api/clusters') {
      const expanded = new Set((url.searchParams.get('expanded') || '').split(',').filter(Boolean))
      const collapsed = new Set((url.searchParams.get('collapsed') || '').split(',').filter(Boolean))
      const budget = Number(url.searchParams.get('budget') || 10)
      const clusters = buildClusters(expanded, collapsed, budget, padToBudget)
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
      const clusters = buildClusters(expanded, collapsed, budget, padToBudget)
      const cluster = clusters.find(c => c.id === clusterId)
      const remaining = Math.max(0, budget - clusters.length)
      const children = CHILDREN[clusterId] || []
      const expand = {
        can_expand: children.length > 0 && !collapsed.has(clusterId),
        predicted_children: children.length || 0,
        budget_impact: children.length ? children.length - 1 : 0,
        reason: remaining <= 0 ? 'budget' : '',
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

test.describe('ClusterView (mocked backend)', () => {
  test('loads with mocked clusters and reflects expanded param', async ({ page }) => {
    await setupMockApi(page)

    // Initial load (no expanded)
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForSelector('canvas')
    await page.waitForTimeout(500) // allow render
    const visibleText = await page.locator('text=Visible').first().innerText()
    const initial = parseVisible(visibleText)
    expect(initial.visible).toBeGreaterThan(0)
    const canvasVisible = await page.locator('canvas').isVisible()
    expect(canvasVisible).toBe(true)

    // Navigate with expanded=root_a to increase visible clusters
    await page.goto('/?view=cluster&n=10&budget=10&expanded=root_a')
    await page.waitForSelector('canvas')
    await page.waitForTimeout(500)
    const visibleTextExpanded = await page.locator('text=Visible').first().innerText()
    const expanded = parseVisible(visibleTextExpanded)
    // Expect visible count to increase
    expect(expanded.visible).toBeGreaterThan(initial.visible)
    // Budget should stay the same across navigation
    expect(expanded.budget).toBe(initial.budget)
  })

  test('expand button increases visible count', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForSelector('canvas')
    await page.waitForTimeout(300)
    const initial = parseVisible(await page.locator('text=Visible').first().innerText())
    const selected = await trySelectNode(page, [{ x: 150, y: 170 }, { x: 230, y: 170 }, { x: 320, y: 170 }])
    expect(selected).toBeTruthy()
    const expandButton = page.getByRole('button', { name: /Expand/ }).first()
    await expect(expandButton).toBeVisible()
    await expandButton.click({ trial: false })
    await page.waitForTimeout(300)
    const after = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(after.visible).toBeGreaterThan(initial.visible)
  })

  test('collapse button reduces visible count', async ({ page }) => {
    await setupMockApi(page)
    // Start already expanded so children are visible
    await page.goto('/?view=cluster&n=10&budget=10&expanded=root_a')
    await page.waitForSelector('canvas')
    await page.waitForTimeout(300)
    const before = parseVisible(await page.locator('text=Visible').first().innerText())
    // Select a child (a1 is first node)
    const selected = await trySelectNode(page, [{ x: 150, y: 170 }, { x: 230, y: 170 }])
    expect(selected).toBeTruthy()
    const collapseButton = page.getByRole('button', { name: /^Collapse/ }).first()
    await expect(collapseButton).toBeVisible()
    await collapseButton.click()
    await page.waitForTimeout(300)
    const after = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(after.visible).toBeLessThan(before.visible)
  })

  test('budget slider blocks expand when at capacity', async ({ page }) => {
    await setupMockApi(page, { padToBudget: true })
    await page.goto('/?view=cluster&n=10&budget=5')
    await page.waitForSelector('canvas')
    await page.waitForTimeout(300)
    // Drag budget slider down to 5 (at capacity because of padding)
    const budgetSlider = page.locator('input[type=\"range\"]').first()
    await budgetSlider.evaluate(slider => {
      (slider as HTMLInputElement).value = '5'
      slider.dispatchEvent(new Event('input', { bubbles: true }))
      slider.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await page.waitForTimeout(300)
    const before = parseVisible(await page.locator('text=Visible').first().innerText())
    const selected = await trySelectNode(page, [{ x: 150, y: 170 }, { x: 230, y: 170 }])
    expect(selected).toBeTruthy()
    const expandButton = page.getByRole('button', { name: /Expand/ }).first()
    await expandButton.click()
    await page.waitForTimeout(300)
    const after = parseVisible(await page.locator('text=Visible').first().innerText())
    expect(after.visible).toBe(before.visible) // blocked by budget
  })

  test('shows error message on cluster fetch failure', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10&fail=1')
    // Wait for either error text or the error span
    const errorText = page.locator('text=/HTTP 500|Mock 500|Internal Server Error|Failed/')
    await expect(errorText.first()).toBeVisible({ timeout: 10000 })
  })

  test('selection mode drag selects multiple clusters', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10')
    await page.waitForSelector('canvas')
    await page.getByRole('button', { name: /Selection mode off/ }).click()
    await expect(page.getByRole('button', { name: /Selection mode on/ })).toBeVisible()

    // Click two nodes to select them
    await page.locator('canvas').click({ position: { x: 150, y: 170 } })
    await page.locator('canvas').click({ position: { x: 230, y: 170 } })

    await expect(page.getByRole('button', { name: /Collapse selected/ })).toBeVisible()
  })
})
