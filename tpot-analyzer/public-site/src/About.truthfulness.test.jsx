import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import About from './About'

describe('About methodology truthfulness', () => {
  it('quarantines historical independent-Lift band labels', () => {
    const { container } = render(
      <About
        meta={{
          counts: {
            communities: 16,
            total_accounts: 298347,
            by_band: { exemplar: 361, bridge: 1451 },
          },
          links: {},
        }}
      />,
    )

    fireEvent.click(screen.getByRole('button', {
      name: /I want to be inspired by your math/i,
    }))

    expect(screen.getAllByText(/quarantined legacy metadata/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/1,451 historical rows labeled “bridge”/i)).toBeInTheDocument()
    expect(screen.getByText(/Historical specialist \+ bridge \+ frontier labels/i)).toBeInTheDocument()
    expect(screen.getByText(/historical frontier ranking is currently blocked/i)).toBeInTheDocument()
    expect(screen.getByText(/historical fallback label from the stale band export/i)).toBeInTheDocument()
    expect(screen.getByText(/current independent-Lift path refuses/i)).toBeInTheDocument()
    expect(screen.getByText(/classic legacy export is also not provenance-bound/i)).toBeInTheDocument()
    expect(screen.getByText(/current exporter suppresses every existing band row/i)).toBeInTheDocument()
    expect(screen.getByText(/historical seed rows combine NMF-derived assignments/i)).toBeInTheDocument()
    expect(screen.getByText(/assembled from NMF, LLM-ensemble, and curator inputs/i)).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/well-classified/i)
    expect(container).not.toHaveTextContent(/seeds I classified/i)
    expect(screen.queryByText(/Most TPOT Members Are Bridges/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Lift and entropy help determine the displayed band/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/One affinity clears the current Lift\/entropy display thresholds/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Barely visible in the network/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/pipeline refuses to regenerate or re-export those bands/i)).not.toBeInTheDocument()
  })

  it('describes the PPR walk direction and tweet weighting as the code implements them', () => {
    const { container } = render(<About meta={{ counts: {}, links: {} }} />)

    fireEvent.click(screen.getByRole('button', {
      name: /I want to be inspired by your math/i,
    }))

    // engine.compute_ppr walks adj.T: mass moves from a followed account to its followers.
    expect(screen.getByText(/if A follows B, probability moves from B to A/i)).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/attention flows from the followers backward/i)

    // rollup_bits computes pct from unweighted counts; simulacrum weighting is opt-in.
    expect(screen.getByText(/every kept tag currently counts\s+equally/i)).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/currently count double/i)
  })

  it('states the ensemble tag rule and the current veil numbers as measured', () => {
    const { container } = render(<About meta={{ counts: {}, links: {} }} />)

    fireEvent.click(screen.getByRole('button', {
      name: /I want to be inspired by your math/i,
    }))

    // label_tweets_ensemble.consensus: 3/3 median, 2/3 lower, 1/3 capped at +1 (not dropped).
    expect(screen.getByText(/named by only one model is\s+kept at the weakest strength/i)).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/only keep tags where at\s+least two agree/i)

    // verify_veil_cv.py on production propagate, 4 Nov 2026 (EXPERIMENT_LOG).
    expect(screen.getByText(/came from a propagation method the map no longer uses/i)).toBeInTheDocument()
    expect(screen.getByText(/AUC is 0\.60/i)).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/Raw propagation scores yield an AUC of 0\.178\. TPOT accounts score lower/i)
    expect(container).not.toHaveTextContent(/hub nodes near many communities inherit diffuse signal/i)
  })
})
