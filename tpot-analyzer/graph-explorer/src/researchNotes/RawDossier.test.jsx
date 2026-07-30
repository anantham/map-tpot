import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RawDossier from './RawDossier'

describe('RawDossier', () => {
  it('does not render unsafe profile links and pluralizes evidence counts', () => {
    render(
      <RawDossier
        dossier={{
          provenance: {
            source: 'mutable_local_archive',
            snapshotBound: false,
          },
          account: {
            accountId: 'acct-1',
            username: 'alice',
            website: 'javascript:alert(1)',
            fetchedAt: '2026-07-22T00:00:00+00:00',
          },
          tweets: [{
            tweetId: 'tweet-1',
            text: 'Evidence',
            createdAt: '2026-07-20T00:00:00+00:00',
            favoriteCount: 1,
            retweetCount: 1,
            fetchedAt: '2026-07-22T00:00:00+00:00',
          }],
        }}
      />,
    )

    expect(
      screen.queryByRole('link', { name: 'Website ↗' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('1 like')).toBeInTheDocument()
    expect(screen.getByText('1 repost')).toBeInTheDocument()
    expect(screen.getByText(/mutable local archive.*not snapshot-bound/i)).toBeInTheDocument()
    expect(screen.getAllByText(/captured/i).length).toBeGreaterThan(0)
  })

  it('does not infer snapshot status from the source name alone', () => {
    render(
      <RawDossier
        dossier={{
          provenance: {
            source: 'mutable_local_archive',
            snapshotBound: true,
          },
          account: { accountId: 'acct-1', username: 'alice' },
          tweets: [{
            tweetId: 'tweet-missing-capture',
            text: 'Missing capture timestamp',
            createdAt: null,
          }],
        }}
      />,
    )

    expect(screen.queryByText(/not snapshot-bound/i)).not.toBeInTheDocument()
    expect(
      screen.getByText('Profile captured date unavailable'),
    ).toBeInTheDocument()
    expect(screen.getByText('Captured date unavailable')).toBeInTheDocument()
  })
})
