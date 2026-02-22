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
    expect(screen.getByText(/Set `ego` in Settings/i)).toBeInTheDocument()
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
    expect(screen.getByText(/Loading membership/i)).toBeInTheDocument()
  })

  it('renders membership metrics', () => {
    render(
      <AccountMembershipPanel
        ego="ego1"
        account={account}
        loading={false}
        error={null}
        membership={{
          probability: 0.81,
          confidenceInterval95: [0.7, 0.9],
          uncertainty: 0.12,
          engine: 'grf',
          evidence: { coverage: 0.6 },
          anchorCounts: { positive: 12, negative: 9 },
        }}
      />
    )
    expect(screen.getByText('81%')).toBeInTheDocument()
    expect(screen.getByText(/Engine grf/)).toBeInTheDocument()
    expect(screen.getByText(/Anchors \+12 \/ -9/)).toBeInTheDocument()
  })
})
