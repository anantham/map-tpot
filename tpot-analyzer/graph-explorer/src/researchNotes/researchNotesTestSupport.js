import { fireEvent, screen } from '@testing-library/react'

export const UNBOUND_DOSSIER = {
  bindingStatus: 'unbound',
  provenance: {
    source: 'mutable_local_archive',
    snapshotBound: false,
  },
  account: {
    accountId: 'acct-alice',
    username: 'alice',
    displayName: 'Alice',
    bio: 'Meditation and distributed systems.',
    location: 'Somewhere',
    website: 'https://alice.example',
    fetchedAt: '2026-07-22T00:00:00+00:00',
  },
  tweets: [{
    tweetId: 'tweet-1',
    text: 'A note about jhana practice.',
    createdAt: '2026-07-20T00:00:00+00:00',
    favoriteCount: 12,
    retweetCount: 2,
    fetchedAt: '2026-07-22T00:00:00+00:00',
  }],
}

export function addAccounts(text) {
  fireEvent.change(screen.getByLabelText('Paste accounts and notes'), {
    target: { value: text },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add to queue' }))
}
