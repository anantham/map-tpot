import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'

import GraphExplorer from './GraphExplorer'

vi.mock('react-force-graph-2d', async () => {
  const React = (await import('react')).default
  const ForceGraphStub = React.forwardRef(function ForceGraphStub(_props, ref) {
    React.useImperativeHandle(
      ref,
      () => ({
        d3Force: () => ({
          strength: () => {},
          distance: () => {},
        }),
        d3ReheatSimulation: () => {},
        centerAt: () => {},
        zoom: () => {},
      }),
      []
    )
    return <div data-testid="force-graph" />
  })

  return { default: ForceGraphStub }
})

vi.mock('./data', () => ({
  checkHealth: vi.fn().mockResolvedValue(true),
  fetchGraphSettings: vi.fn().mockResolvedValue({
    active_list: 'adi_tpot',
    lists: { adi_tpot: ['alice'] },
    preset_names: ['adi_tpot'],
    user_list_names: [],
    settings: {
      alpha: 0.85,
      auto_include_shadow: true,
      discovery_weights: {
        neighbor_overlap: 0.4,
        pagerank: 0.3,
        community: 0.2,
        path_distance: 0.1,
      },
      max_distance: 3,
      limit: 500,
    },
    updated_at: null,
  }),
  fetchGraphData: vi.fn().mockResolvedValue({
    nodes: [
      {
        id: '1',
        username: 'alice',
        display_name: 'Alice',
        provenance: 'archive',
        pagerank: 0.01,
        shadow: false,
      },
    ],
    edges: [{ source: '1', target: '1', mutual: true, shadow: false }],
    directed_nodes: [
      {
        id: '1',
        username: 'alice',
        display_name: 'Alice',
        provenance: 'archive',
        pagerank: 0.01,
        shadow: false,
      },
    ],
    directed_edges: [{ source: '1', target: '1', mutual: true, shadow: false }],
    undirected_edges: 0,
  }),
  computeMetrics: vi.fn().mockResolvedValue({
    metrics: { composite: {} },
    seeds: [],
    resolved_seeds: [],
  }),
  saveSeedList: vi.fn().mockResolvedValue({
    active_list: 'adi_tpot',
    lists: { adi_tpot: ['alice'] },
    preset_names: ['adi_tpot'],
    user_list_names: [],
    settings: { auto_include_shadow: true },
    updated_at: null,
  }),
}))

describe('GraphExplorer', () => {
  it('renders summary counts when backend returns directed_nodes arrays', async () => {
    const { container } = render(<GraphExplorer />)

    await waitFor(() => {
      expect(container.querySelector('.summary-grid')).toBeTruthy()
    })

    const values = Array.from(container.querySelectorAll('.summary-value')).map((el) => el.textContent)
    expect(values).toContain('1')
  })
})

