import { describe, it, expect } from 'vitest'
import { buildCardRequest } from './cardPrompt'

const communityMap = new Map([
  [1, { id: 1, name: 'Core TPOT', short_name: 'core', color: '#ff0', description: 'The core of TPOT' }],
  [2, { id: 2, name: 'LLM Whisperers', short_name: 'llm', color: '#0f0', description: 'AI builders' }],
  [3, { id: 3, name: 'Qualia Researchers', short_name: 'qualia', color: '#00f', description: 'Consciousness explorers' }],
])

describe('buildCardRequest', () => {
  it('resolves community names and colors from map', () => {
    const result = buildCardRequest({
      handle: 'alice',
      bio: 'Test bio',
      memberships: [{ community_id: 1, weight: 0.6 }, { community_id: 2, weight: 0.3 }],
      sampleTweets: [],
      communityMap,
    })

    expect(result.handle).toBe('alice')
    expect(result.bio).toBe('Test bio')
    expect(result.communities).toHaveLength(2)
    expect(result.communities[0].name).toBe('Core TPOT')
    expect(result.communities[0].color).toBe('#ff0')
    expect(result.communities[0].weight).toBe(0.6)
  })

  it('sorts communities by weight descending', () => {
    const result = buildCardRequest({
      handle: 'bob',
      bio: null,
      memberships: [
        { community_id: 2, weight: 0.2 },
        { community_id: 1, weight: 0.5 },
        { community_id: 3, weight: 0.3 },
      ],
      sampleTweets: [],
      communityMap,
    })

    expect(result.communities[0].name).toBe('Core TPOT')      // 0.5
    expect(result.communities[1].name).toBe('Qualia Researchers') // 0.3
    expect(result.communities[2].name).toBe('LLM Whisperers')   // 0.2
  })

  it('handles null bio', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: [{ community_id: 1, weight: 1.0 }],
      sampleTweets: [],
      communityMap,
    })

    expect(result.bio).toBeNull()
  })

  it('handles undefined bio', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: undefined,
      memberships: [{ community_id: 1, weight: 1.0 }],
      sampleTweets: [],
      communityMap,
    })

    expect(result.bio).toBeNull()
  })

  it('limits tweets to 5', () => {
    const tweets = Array.from({ length: 10 }, (_, i) => `Tweet ${i}`)
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: [{ community_id: 1, weight: 1.0 }],
      sampleTweets: tweets,
      communityMap,
    })

    expect(result.tweets).toHaveLength(5)
    expect(result.tweets[4]).toBe('Tweet 4')
  })

  it('handles empty memberships', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: [],
      sampleTweets: [],
      communityMap,
    })

    expect(result.communities).toEqual([])
  })

  it('handles null memberships', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: null,
      sampleTweets: null,
      communityMap,
    })

    expect(result.communities).toEqual([])
    expect(result.tweets).toEqual([])
  })

  it('falls back to community_name when ID not in map', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: [{ community_id: 999, weight: 0.5, community_name: 'New Community' }],
      sampleTweets: [],
      communityMap,
    })

    expect(result.communities[0].name).toBe('New Community')
    expect(result.communities[0].color).toBe('#666')
  })

  it('falls back to "Unknown" when no name available', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: [{ community_id: 999, weight: 0.5 }],
      sampleTweets: [],
      communityMap,
    })

    expect(result.communities[0].name).toBe('Unknown')
  })

  it('includes description and short_name from community map', () => {
    const result = buildCardRequest({
      handle: 'test',
      bio: null,
      memberships: [{ community_id: 1, weight: 1.0 }],
      sampleTweets: [],
      communityMap,
    })

    expect(result.communities[0].description).toBe('The core of TPOT')
    expect(result.communities[0].short_name).toBe('core')
  })
})
