/**
 * cardPrompt.js — Pure function to build the card generation request payload.
 *
 * Resolves community IDs to names/colors via communityMap, sorts by weight,
 * and returns a clean payload for the generation endpoint or BYOK direct call.
 */

/**
 * Build a card generation request from raw account data.
 *
 * @param {Object} params
 * @param {string} params.handle - Twitter handle (without @)
 * @param {string|null} params.bio - Account bio text
 * @param {Array<{community_id: number, weight: number, community_name?: string}>} params.memberships
 * @param {string[]} params.sampleTweets - Up to 5 representative tweets
 * @param {Map<number, {id: number, name: string, color: string}>} params.communityMap
 * @returns {{ handle: string, bio: string|null, communities: Array<{name: string, color: string, weight: number}>, tweets: string[] }}
 */
export function buildCardRequest({ handle, bio, memberships, sampleTweets, communityMap }) {
  const communities = (memberships || [])
    .map((m) => {
      const community = communityMap.get(m.community_id);
      return {
        name: community?.name || m.community_name || "Unknown",
        short_name: community?.short_name || "",
        color: community?.color || "#666",
        weight: m.weight,
        description: community?.description || "",
      };
    })
    .sort((a, b) => b.weight - a.weight);

  return {
    handle,
    bio: bio || null,
    communities,
    tweets: (sampleTweets || []).slice(0, 5),
  };
}
