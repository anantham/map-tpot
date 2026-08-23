import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AccountMembershipPanel from './AccountMembershipPanel'

describe('AccountMembershipPanel', () => {
  const account = { id: '123', username: 'alice' }

  it('renders guidance when ego is missing', () => {
    render(
      <AccountMembershipPanel
        ego=""
        account={account}
        loading={false}
        error={null}
        membership={null}
      />
    )
    expect(screen.getByText(/Set `ego` in Settings to compute affinity/i)).toBeInTheDocument()
  })

  it('renders loading state', () => {
    render(
      <AccountMembershipPanel
        ego="ego1"
        account={account}
        loading
        error={null}
        membership={null}
      />
    )
    expect(screen.getByText(/Loading affinity/i)).toBeInTheDocument()
  })

  it('renders uncalibrated affinity without probability or CI language', () => {
    render(
      <AccountMembershipPanel
        ego="ego1"
        account={account}
        loading={false}
        error={null}
        membership={{
          affinity: 0.81,
          scoreSemantics: 'affinity',
          calibrated: false,
          uncertainty: 0.12,
          uncertaintySemantics: 'heuristic_graph_entropy_degree',
          engine: 'grf',
          evidence: { coverage: 0.6 },
          anchorCounts: { positive: 12, negative: 9 },
        }}
      />
    )
    expect(screen.getByText('0.810')).toBeInTheDocument()
    expect(screen.getByText(/Uncalibrated graph affinity/i)).toBeInTheDocument()
    expect(screen.getByText(/Heuristic graph uncertainty 12%/i)).toBeInTheDocument()
    expect(screen.getByText(/Evidence coverage 60%/i)).toBeInTheDocument()
    expect(screen.getByText(/Engine grf/)).toBeInTheDocument()
    expect(screen.getByText(/Anchors \+12 \/ -9/)).toBeInTheDocument()
    expect(screen.queryByText(/probability/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/95% CI/i)).not.toBeInTheDocument()
  })

  it('renders unknown evidence coverage without converting null to zero', () => {
    render(
      <AccountMembershipPanel
        ego="ego1"
        account={account}
        loading={false}
        error={null}
        membership={{
          affinity: 0.42,
          uncertainty: 0.2,
          engine: 'grf',
          evidence: { coverage: null },
          anchorCounts: { positive: 2, negative: 2 },
        }}
      />
    )

    expect(screen.getByText(/Evidence coverage —/i)).toBeInTheDocument()
    expect(screen.queryByText(/Evidence coverage 0%/i)).not.toBeInTheDocument()
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['NaN', Number.NaN],
    ['infinity', Number.POSITIVE_INFINITY],
  ])('renders an unavailable affinity for %s', (_label, affinity) => {
    render(
      <AccountMembershipPanel
        ego="ego1"
        account={account}
        loading={false}
        error={null}
        membership={{
          affinity,
          uncertainty: 0.2,
          engine: 'grf',
          evidence: { coverage: 0.5 },
          anchorCounts: { positive: 2, negative: 2 },
        }}
      />
    )

    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('0.000')).not.toBeInTheDocument()
  })
})
