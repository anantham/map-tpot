import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RawDossier from './RawDossier'

// Test intent: preserve typed context and precision without inferring social meaning;
// absent/unsafe references must not create links or hide the surrounding evidence.
describe('RawDossier', () => {
  it('puts the saved contact card before the longer evidence sections', () => {
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},tweets:[],
      contactCard:{status:'available',accountId:'100',coverage:[],items:[{
        platform:'email',value:'team@example.test',observations:[{kind:'organisation_forwarding',
          label:'Reported contact route',association:'Organisation inbox; ask for the author'}],
      }]}}} />)
    const card = screen.getByRole('heading',{name:'Saved contact and channel clues'})
    expect(screen.getByText('team@example.test')).toBeInTheDocument()
    const posts = screen.getByRole('heading',{name:'Recent stored posts (0)'})
    expect(card.compareDocumentPosition(posts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
  it.each(['²','٣','123\n'])('does not link non-exact context identity %j', value => {
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      tweets:[{tweetId:'2100000000000000001',text:'Still readable',context:{quotedTweetId:value}}]}} />)
    expect(screen.getByText('Still readable')).toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'Quoted post ↗'})).not.toBeInTheDocument()
  })
  it.each(['2100000000000000001','2000000000000000001'])('does not repeat the conversation link for %s', root => {
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},tweets:[{
      tweetId:'2100000000000000001',text:'Reply',context:{replyToTweetId:'2000000000000000001',conversationId:root},
    }]}} />)
    expect(screen.getByRole('link',{name:'Reply context ↗'})).toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'Conversation root ↗'})).not.toBeInTheDocument()
  })
  it('links original, reply, quote and conversation posts without losing exact IDs', () => {
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'}, tweets:[{
      tweetId:'2100000000000000001',text:'Evidence with context',source:'community_archive_rest',
      context:{replyToTweetId:'2000000000000000001',replyToAccountId:'9007199254740993',
        quotedTweetId:'2000000000000000002',conversationId:'2000000000000000003'},
    }]}} />)
    for (const [label,id] of [['This post on X ↗','2100000000000000001'],
      ['Reply context ↗','2000000000000000001'],['Quoted post ↗','2000000000000000002'],
      ['Conversation root ↗','2000000000000000003']]) {
      expect(screen.getByRole('link',{name:label})).toHaveAttribute('href',`https://x.com/i/status/${id}`)
    }
    expect(screen.getByText('Reply-to account ID: 9007199254740993')).toBeInTheDocument()
    expect(screen.getByText(/References only.*not agreement or membership/)).toBeInTheDocument()
  })
  it('keeps text visible without inventing absent or malformed context links', () => {
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},tweets:[{
      tweetId:'not-a-post-id',text:'@someone is not an inferred reply edge',
      context:{replyToTweetId:'javascript:alert(1)',quotedTweetId:Number('9007199254740993'),
        conversationId:null,replyToAccountId:'unknown'},
    }]}} />)
    expect(screen.getByText('@someone is not an inferred reply edge')).toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'This post on X ↗'})).not.toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'Reply context ↗'})).not.toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'Quoted post ↗'})).not.toBeInTheDocument()
    expect(screen.queryByText(/Reply-to account ID/)).not.toBeInTheDocument()
  })
  it('shows saved-data read failure without hiding healthy evidence', () => {
    render(<RawDossier dossier={{ account: { accountId: '100', username: 'example', bio: 'Still visible' },
      savedEvidenceStatus: 'unavailable', tweets: [],
    }} />)
    expect(screen.getByText('Still visible')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('does not mean no research exists')
  })
  it('does not suppress local contacts with another account sidecar', () => {
    const route={type:'work_email',address:'alice@example.test',source_url:'https://example.test/contact'}
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      joinedEvidence:{status:'available',contacts:[route]},
      relationshipEvidence:{status:'available',accountId:'200',contacts:[route],paths:[]},tweets:[]}} />)
    expect(screen.getByText('alice@example.test')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('different account')
  })

  it('keeps joined routes and check notes when the matching sidecar is empty', () => {
    render(<RawDossier dossier={{ account:{accountId:'100',username:'example'},
      joinedEvidence:{status:'available', contacts:[{type:'work_email',address:'new@example.test',source_url:'https://example.test/contact'}],
        contactChecks:[{reason:'New contact source checked today'}]},
      relationshipEvidence:{status:'available',accountId:'100',contacts:[],paths:[]}, tweets:[] }} />)
    expect(screen.getByText('new@example.test')).toBeInTheDocument()
    expect(screen.getByText('New contact source checked today')).toBeInTheDocument()
    expect(screen.getByRole('heading',{name:'How this account connects'})).toBeInTheDocument()
  })

  it('deduplicates matching routes without hiding check notes or different claims', () => {
    const route={type:'organisation_forwarding',address:'hello@example.test',source_url:'https://example.test/contact',instruction:'Ask for Alice'}
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      joinedEvidence:{status:'available',contacts:[route,{...route,instruction:'Different reported instruction'}],contactChecks:[{reason:'Delivery remains unknown'}]},
      relationshipEvidence:{status:'available',accountId:'100',contacts:[route],paths:[]},tweets:[]}} />)
    expect(screen.getByText('Ask for Alice')).toBeInTheDocument()
    expect(screen.getByText('Different reported instruction')).toBeInTheDocument()
    expect(screen.getByText('Delivery remains unknown')).toBeInTheDocument()
    expect(screen.getAllByText('hello@example.test')).toHaveLength(2)
  })

  it('distinguishes unavailable posts from an empty activity claim', () => {
    render(<RawDossier dossier={{
      provenance: { source: 'community_archive_public_rest', postsStatus: 'unavailable' },
      account: { accountId: '100', username: 'example', bio: 'Still available' }, tweets: [],
    }} />)
    expect(screen.getByText('Still available')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('not evidence of no activity')
  })

  it('names current public REST evidence and makes a capture failure visible', () => {
    render(<RawDossier dossier={{
      provenance: { source: 'community_archive_public_rest', snapshotBound: false, cacheStatus: 'unavailable' },
      account: { accountId: '9000000000000000001', username: 'example', fetchedAt: '2026-10-14T00:00:00Z' },
      tweets: [{ tweetId: '2100000000000000001', text: 'Current public evidence', source: 'community_archive_rest' }],
    }} />)
    expect(screen.getByText('Community Archive public API post')).toBeInTheDocument()
    expect(screen.getByText(/current public archive read.*not snapshot-bound/i)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('could not be saved locally')
  })

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
            source: 'archive',
          }],
        }}
      />,
    )

    expect(
      screen.queryByRole('link', { name: 'Website ↗' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('1 like')).toBeInTheDocument()
    expect(screen.getByText('1 repost')).toBeInTheDocument()
    expect(screen.getByText('Archive post')).toBeInTheDocument()
    expect(screen.getByText(/mutable local archive.*not snapshot-bound/i)).toBeInTheDocument()
    expect(screen.getAllByText(/captured/i).length).toBeGreaterThan(0)
  })

  it('labels acquired posts by their stored source without asserting authorship', () => {
    render(<RawDossier dossier={{
      account: { accountId: 'acct-1', username: 'alice' },
      tweets: [{ tweetId: 'acquired-1', text: 'Stored acquired evidence',
        source: 'enriched', fetchSource: 'last_tweets' }],
    }} />)
    expect(screen.getByRole('heading', { name: 'Recent stored posts (1)' })).toBeInTheDocument()
    expect(screen.getByText('Acquired post · last_tweets')).toBeInTheDocument()
    expect(screen.queryByText(/authored posts/i)).not.toBeInTheDocument()
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
