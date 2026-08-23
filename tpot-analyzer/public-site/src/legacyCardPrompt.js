const VISUAL_ROLES = [
  "central visual motif",
  "supporting accent motif",
  "background texture motif",
];

function scoreValue(affinity) {
  const value = Number(affinity?.weight);
  return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
}

function rankedAffinities(communities) {
  return [...(Array.isArray(communities) ? communities : [])]
    .sort((a, b) => scoreValue(b) - scoreValue(a))
    .slice(0, 3);
}

function describeAffinity(affinity, index) {
  return `
LEGACY EXPLORATORY AFFINITY RANK ${index + 1}: ${affinity.name}
  Visual role: ${VISUAL_ROLES[index]}
  Motif source: ${(affinity.description || affinity.name).slice(0, 200)}
  Color cue: ${affinity.color || "#666"}
`;
}

export function buildLegacyCardPrompt({ handle, bio, communities, tweets }) {
  const ranked = rankedAffinities(communities);
  if (ranked.length === 0) {
    throw new Error("Cannot build a card prompt without a legacy affinity");
  }

  const affinityDirections = ranked
    .map((affinity, index) => describeAffinity(affinity, index))
    .join("");
  const tweetContext = Array.isArray(tweets) && tweets.length > 0
    ? `
REPRESENTATIVE TWEETS (context for voice and interests):
${tweets.slice(0, 3).map((tweet, index) => `  ${index + 1}. ${tweet.slice(0, 200)}`).join("\n")}
`
    : "";

  return `Generate a collectible tarot-style card image.

SUBJECT: @${handle}
${bio ? `BIO: ${bio}` : ""}

METHODOLOGY NOTE:
- These legacy exploratory affinities are uncalibrated and not membership probabilities.
- Their order is a within-account ranking, not evidence that the subject belongs to any named group.
- Use the ranked names, descriptions, and colors only as visual motifs.
${affinityDirections}${tweetContext}
VISUAL REQUIREMENTS:
- Vertical 2:3 tarot card, ornate border, dark background
- Let rank 1 guide the central motif, rank 2 an accent, and rank 3 background texture
- Use the tweets and bio to choose symbolic imagery rather than literal illustrations
- Mystical/arcane aesthetic: sacred geometry, constellation maps, subtle glow

TEXT ON CARD (keep minimal):
- The handle "@${handle}" at top or bottom
- NO other text. No quotes, affinity names, descriptions, or paragraphs
- Let the imagery speak. The card is a portrait, not an infographic.

CRITICAL CONSTRAINTS:
- Do NOT include real human faces or photographs
- Use abstract symbols, cosmic imagery, or stylized avatars
- NO walls of text and NO labels beyond the handle
- Do not portray the ranked affinities as verified facts about the subject
- The card should be visually striking enough to share on social media

Style: premium collectible trading card, digital art, high contrast, rich saturated colors`;
}
