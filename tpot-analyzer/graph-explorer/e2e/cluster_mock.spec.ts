import { test, expect } from '@playwright/test'

// Mocked cluster view payloads keyed by expanded param
const makeClusters = (expanded: Set<string>) => {
  const budget = 10
  const base = [
    { id: 'root_a', size: 30, label: 'Root A', childrenIds: ['a1', 'a2'], parentId: null },
    { id: 'root_b', size: 20, label: 'Root B', parentId: null, childrenIds: [] },
    { id: 'root_c', size: 15, label: 'Root C', parentId: null, childrenIds: [] },
  ]
  if (!expanded.has('root_a')) {
    return base
  }
  return [
    { id: 'a1', size: 15, label: 'A1', parentId: 'root_a', childrenIds: [] },
    { id: 'a2', size: 15, label: 'A2', parentId: 'root_a', childrenIds: [] },
    { id: 'root_b', size: 20, label: 'Root B', parentId: null, childrenIds: [] },
    { id: 'root_c', size: 15, label: 'Root C', parentId: null, childrenIds: [] },
  ]
}

const positionsFor = (clusters: any[]) => {
  const step = 200
  return Object.fromEntries(
    clusters.map((c, idx) => [c.id, [idx * step, 0]])
  )
}

const parseVisible = (text: string) => {
  const match = text.match(/Visible\s+(\d+)\s*\/\s*(\d+)/i)
  if (!match) throw new Error(`Could not parse visible text: ${text}`)
  return { visible: Number(match[1]), budget: Number(match[2]) }
}

test.describe('ClusterView (mocked backend)', () => {
  test('loads with mocked clusters and reflects expanded param', async ({ page }) => {
    // Mock all API calls
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/clusters') {
        const expandedParam = url.searchParams.get('expanded') || ''
        const expanded = new Set(expandedParam.split(',').filter(Boolean))
        const clusters = makeClusters(expanded)
        const positions = positionsFor(clusters)
        const payload = {
          clusters,
          edges: [],
          positions,
          meta: {
            budget: 10,
            budget_remaining: 10 - clusters.length,
            approximate_mode: false,
          },
          cache_hit: false,
          total_nodes: 100,
          granularity: Number(url.searchParams.get('n') || 10),
        }
        return route.fulfill({ status: 200, body: JSON.stringify(payload), contentType: 'application/json' })
      }
      if (url.pathname.includes('/preview') || url.pathname.includes('/members')) {
        return route.fulfill({ status: 200, body: JSON.stringify({ expand: { can_expand: false }, collapse: { can_collapse: true } }), contentType: 'application/json' })
      }
      return route.fulfill({ status: 200, body: '{}' })
    })

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
})
