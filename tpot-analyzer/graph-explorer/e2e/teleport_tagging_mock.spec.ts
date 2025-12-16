import { test, expect, Page } from '@playwright/test'

/**
 * Mocked E2E: search → teleport → tag an account → tag summary refresh.
 *
 * This is the primary “Phase 1 loop” regression gate.
 */

type TagRow = {
  ego: string
  account_id: string
  tag: string
  polarity: number
  confidence: number | null
  updated_at: string
}

const BASE_CLUSTERS = [
  { id: 'root_a', size: 30, label: 'Root A', childrenIds: ['a1', 'a2'], parentId: null, isLeaf: false },
  { id: 'root_b', size: 20, label: 'Root B', childrenIds: ['b1', 'b2'], parentId: null, isLeaf: false },
  { id: 'root_c', size: 15, label: 'Root C', childrenIds: [], parentId: null, isLeaf: true },
]

const CHILDREN: Record<string, any[]> = {
  root_a: [
    { id: 'a1', size: 15, label: 'A1', parentId: 'root_a', childrenIds: [], isLeaf: true },
    { id: 'a2', size: 15, label: 'A2', parentId: 'root_a', childrenIds: [], isLeaf: true },
  ],
  root_b: [
    { id: 'b1', size: 10, label: 'B1', parentId: 'root_b', childrenIds: [], isLeaf: true },
    { id: 'b2', size: 10, label: 'B2', parentId: 'root_b', childrenIds: [], isLeaf: true },
  ],
}

const positionsFor = (clusters: any[]) => {
  const step = 130
  const startX = 220
  const startY = 220
  return Object.fromEntries(clusters.map((c, idx) => [c.id, [startX + idx * step, startY]]))
}

const nowIso = () => new Date().toISOString()

const setupMockApi = async (page: Page) => {
  const tagsByEgoAccount = new Map<string, Map<string, TagRow[]>>() // ego -> account -> tags[]

  const getTags = (ego: string, accountId: string) => {
    const byAccount = tagsByEgoAccount.get(ego)
    return (byAccount && byAccount.get(accountId)) || []
  }
  const setTags = (ego: string, accountId: string, next: TagRow[]) => {
    const byAccount = tagsByEgoAccount.get(ego) || new Map<string, TagRow[]>()
    byAccount.set(accountId, next)
    tagsByEgoAccount.set(ego, byAccount)
  }

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname

    if (pathname === '/api/log') {
      return route.fulfill({ status: 200, body: '{}' })
    }

    if (pathname === '/api/accounts/search') {
      const q = (url.searchParams.get('q') || '').toLowerCase().replace(/^@/, '')
      const results = q.startsWith('ali')
        ? [{ id: 'u1', username: 'alice', displayName: 'Alice A', numFollowers: 10, isShadow: false }]
        : q.startsWith('bo')
          ? [{ id: 'u2', username: 'bob', displayName: 'Bob B', numFollowers: 20, isShadow: false }]
          : []
      return route.fulfill({ status: 200, body: JSON.stringify(results), contentType: 'application/json' })
    }

    if (pathname.match(/^\/api\/accounts\/[^/]+\/teleport_plan$/)) {
      const accountId = pathname.split('/')[3]
      // Deterministically pick leaf a1 for our mocked hierarchy.
      const payload = {
        accountId,
        leafClusterId: 'a1',
        targetVisible: 10,
        budget: Number(url.searchParams.get('budget') || 10),
        pathDepth: 1,
        leaderClusterId: 'root_a',
        recommended: { n: 10, expanded: '', collapsed: '', focus_leaf: 'a1' },
      }
      return route.fulfill({ status: 200, body: JSON.stringify(payload), contentType: 'application/json' })
    }

    if (pathname.match(/^\/api\/accounts\/[^/]+\/tags$/)) {
      const accountId = pathname.split('/')[3]
      const ego = (url.searchParams.get('ego') || '').trim()
      if (!ego) {
        return route.fulfill({ status: 400, body: JSON.stringify({ error: 'ego query param is required' }), contentType: 'application/json' })
      }

      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({ ego, accountId, tags: getTags(ego, accountId) }),
          contentType: 'application/json',
        })
      }

      if (route.request().method() === 'POST') {
        let data: any = {}
        try {
          data = route.request().postDataJSON() as any
        } catch {
          data = {}
        }
        const tag = String(data.tag || '').trim()
        const polarityRaw = data.polarity
        const polarity = polarityRaw === 'not_in' ? -1 : 1
        const existing = getTags(ego, accountId).filter((t) => t.tag.toLowerCase() !== tag.toLowerCase())
        const next: TagRow[] = existing.concat([
          {
            ego,
            account_id: accountId,
            tag,
            polarity,
            confidence: data.confidence ?? null,
            updated_at: nowIso(),
          },
        ])
        setTags(ego, accountId, next)
        return route.fulfill({ status: 200, body: JSON.stringify({ status: 'ok' }), contentType: 'application/json' })
      }
    }

    if (pathname.match(/^\/api\/accounts\/[^/]+\/tags\/.+/)) {
      const parts = pathname.split('/')
      const accountId = parts[3]
      const tag = decodeURIComponent(parts.slice(5).join('/'))
      const ego = (url.searchParams.get('ego') || '').trim()
      if (!ego) {
        return route.fulfill({ status: 400, body: JSON.stringify({ error: 'ego query param is required' }), contentType: 'application/json' })
      }
      const next = getTags(ego, accountId).filter((t) => t.tag.toLowerCase() !== tag.toLowerCase())
      setTags(ego, accountId, next)
      return route.fulfill({ status: 200, body: JSON.stringify({ status: 'deleted' }), contentType: 'application/json' })
    }

    if (pathname === '/api/clusters') {
      const budget = Number(url.searchParams.get('budget') || 10)
      const focusLeaf = url.searchParams.get('focus_leaf') || ''
      const clusters = focusLeaf ? [CHILDREN.root_a[0], CHILDREN.root_a[1], BASE_CLUSTERS[1], BASE_CLUSTERS[2]] : BASE_CLUSTERS
      const payload = {
        clusters,
        edges: [],
        positions: positionsFor(clusters),
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

    if (pathname.match(/^\/api\/clusters\/[^/]+\/preview$/)) {
      const clusterId = pathname.split('/')[3]
      const cluster = [...BASE_CLUSTERS, ...CHILDREN.root_a, ...CHILDREN.root_b].find((c) => c.id === clusterId)
      const expand = {
        can_expand: Boolean(CHILDREN[clusterId]?.length),
        predicted_children: CHILDREN[clusterId]?.length || 0,
        budget_impact: (CHILDREN[clusterId]?.length || 0) - 1,
        reason: '',
      }
      const siblingIds = cluster?.parentId ? (CHILDREN[cluster.parentId] || []).map((c) => c.id).filter((id) => id !== clusterId) : []
      const collapse = {
        can_collapse: Boolean(cluster?.parentId),
        parent_id: cluster?.parentId || null,
        sibling_ids: siblingIds,
        nodes_freed: siblingIds.length + 1,
      }
      return route.fulfill({ status: 200, body: JSON.stringify({ expand, collapse }), contentType: 'application/json' })
    }

    if (pathname.match(/^\/api\/clusters\/[^/]+\/members$/)) {
      return route.fulfill({
        status: 200,
        body: JSON.stringify({
          total: 3,
          members: [
            { id: 'u1', username: 'alice', displayName: 'Alice A', numFollowers: 10 },
            { id: 'u2', username: 'bob', displayName: 'Bob B', numFollowers: 20 },
            { id: 'u3', username: 'carol', displayName: 'Carol C', numFollowers: 30 },
          ],
        }),
        contentType: 'application/json',
      })
    }

    if (pathname.match(/^\/api\/clusters\/[^/]+\/tag_summary$/)) {
      const clusterId = pathname.split('/')[3]
      const ego = (url.searchParams.get('ego') || '').trim()
      if (!ego) {
        return route.fulfill({ status: 400, body: JSON.stringify({ error: 'ego query param is required' }), contentType: 'application/json' })
      }

      const memberIds = ['u1', 'u2', 'u3']
      const counts: Record<string, { inCount: number; notInCount: number }> = {}
      let taggedMembers = 0
      let assignments = 0
      for (const memberId of memberIds) {
        const rows = getTags(ego, memberId)
        if (rows.length) taggedMembers += 1
        for (const row of rows) {
          assignments += 1
          const entry = counts[row.tag] || { inCount: 0, notInCount: 0 }
          if (row.polarity === 1) entry.inCount += 1
          if (row.polarity === -1) entry.notInCount += 1
          counts[row.tag] = entry
        }
      }

      const tagCounts = Object.entries(counts)
        .map(([tag, v]) => ({ tag, inCount: v.inCount, notInCount: v.notInCount, score: v.inCount - v.notInCount }))
        .sort((a, b) => (b.score - a.score) || (b.inCount - a.inCount))
      const suggestedLabel = tagCounts.find((row) => row.score > 0) || null

      const payload = {
        clusterId,
        ego,
        totalMembers: memberIds.length,
        taggedMembers,
        tagAssignments: assignments,
        tagCounts,
        suggestedLabel,
        computeMs: 1,
      }
      return route.fulfill({ status: 200, body: JSON.stringify(payload), contentType: 'application/json' })
    }

    return route.fulfill({ status: 200, body: '{}' })
  })
}

declare global {
  interface Window {
    __CLUSTER_CANVAS_TEST__?: {
      getNodeIds: () => string[]
    }
  }
}

test.describe('ClusterView teleport + tagging (mocked backend)', () => {
  test('teleports to an account, tags it, and refreshes tag summary', async ({ page }) => {
    await setupMockApi(page)
    await page.goto('/?view=cluster&n=10&budget=10&ego=adityaarpitha')

    await expect(page.locator('canvas')).toBeVisible()
    await page.waitForFunction(() => window.__CLUSTER_CANVAS_TEST__?.getNodeIds()?.length > 0)

    const search = page.getByPlaceholder('Teleport to @account…')
    await search.fill('@ali')

    const option = page.getByText('@alice')
    await expect(option).toBeVisible({ timeout: 5000 })
    await option.click()

    await expect(page.getByText('Cluster details')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Selected account')).toBeVisible()
    await expect(page.getByText('@alice · Alice A')).toBeVisible({ timeout: 5000 })

    const tagInput = page.getByPlaceholder('e.g. AI alignment')
    await tagInput.fill('AI alignment')
    await page.getByRole('button', { name: 'Add' }).click()

    const tagPanel = page.getByText('Account tags').locator('..')
    await expect(tagPanel).toBeVisible()
    await expect(tagPanel.getByText('AI alignment')).toBeVisible({ timeout: 5000 })
    await expect(tagPanel.getByRole('button', { name: 'Remove' })).toBeVisible()

    await expect(page.getByText('Top tags')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Suggested label', { exact: true })).toBeVisible()
  })
})
