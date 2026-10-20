import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { fetchTagEstimates, saveTagEstimate } from '../tagEstimatesApi'
import TagEstimateEditor from './TagEstimateEditor'

vi.mock('../tagEstimatesApi', () => ({
  fetchTagEstimates: vi.fn(),
  saveTagEstimate: vi.fn(),
}))

describe('TagEstimateEditor', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    fetchTagEstimates.mockResolvedValue({ current: null, history: [] })
  })

  it('keeps an unknown estimate compact until the curator elects to add one', async () => {
    // Test intent:
    // - Loading a legacy tag must not manufacture a point estimate.
    // - Controls stay behind one active-tag disclosure to limit attention cost.
    render(
      <TagEstimateEditor
        accountId="123"
        ego="aditya"
        reviewSessionId="review-one"
        tag="Dharma"
      />,
    )

    expect(await screen.findByText('Estimate not recorded')).toBeInTheDocument()
    const reveal = screen.getByRole('button', { name: 'Add estimate for Dharma' })
    expect(reveal).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('Current membership estimate')).toBeNull()
    fireEvent.click(reveal)
    expect(screen.getByLabelText('Current membership estimate')).toBeVisible()
    expect(screen.getByText(/plausible eventual range is your forecast/i))
      .toBeInTheDocument()
    expect(saveTagEstimate).not.toHaveBeenCalled()
  })

  it('appends a sample and shows the trajectory without claiming convergence', async () => {
    // Test intent:
    // - Save the three bounded values with a stable review-session receipt.
    // - Show prior samples as a trajectory, never as a one-sample endpoint.
    const saved = {
      event_id: 2,
      point_estimate: 0.7,
      plausible_low: 0.5,
      plausible_high: 0.85,
      review_session_id: 'review-two',
      recorded_at: '2026-08-23T12:00:00Z',
    }
    fetchTagEstimates.mockResolvedValue({
      current: {
        event_id: 1,
        point_estimate: 0.55,
        plausible_low: 0.25,
        plausible_high: 0.75,
        review_session_id: 'review-one',
        recorded_at: '2026-08-20T12:00:00Z',
      },
      history: [],
    })
    saveTagEstimate.mockResolvedValue({
      status: 'appended',
      current: saved,
      history: [saved],
    })

    render(
      <TagEstimateEditor
        accountId="123"
        ego="aditya"
        reviewSessionId="review-two"
        tag="Dharma"
      />,
    )

    const reveal = await screen.findByRole('button', { name: 'Adjust estimate for Dharma' })
    fireEvent.click(reveal)
    fireEvent.change(screen.getByLabelText('Current membership estimate'), {
      target: { value: '70' },
    })
    fireEvent.change(screen.getByLabelText('Plausible eventual minimum'), {
      target: { value: '50' },
    })
    fireEvent.change(screen.getByLabelText('Plausible eventual maximum'), {
      target: { value: '85' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save estimate sample' }))

    await waitFor(() => expect(saveTagEstimate).toHaveBeenCalledWith({
      ego: 'aditya',
      accountId: '123',
      tag: 'Dharma',
      pointEstimate: 0.7,
      plausibleLow: 0.5,
      plausibleHigh: 0.85,
      reviewSessionId: 'review-two',
    }))
    expect(await screen.findAllByText('70% · plausible eventual range 50–85%'))
      .toHaveLength(2)
    expect(screen.getByText(/not yet a stabilized endpoint/i)).toBeInTheDocument()
    expect(screen.queryByText(/converged/i)).toBeNull()
  })
})
