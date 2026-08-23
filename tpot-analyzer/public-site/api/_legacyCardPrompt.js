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

function iconographyFor(affinity, iconography) {
  if (!iconography || !affinity?.short_name) return null;
  return iconography[affinity.short_name] || null;
}

function describeAffinity(affinity, index, iconography) {
  const icon = iconographyFor(affinity, iconography);
  let direction = `
LEGACY EXPLORATORY AFFINITY RANK ${index + 1}: ${affinity.name}
  Visual role: ${VISUAL_ROLES[index]}
`;

  if (icon && index === 0) {
    direction += `  Mascot energy: ${icon.mascot}
  Sigil: ${icon.sigil}
  Color palette: ${icon.color_names}
  Elemental vibe: ${icon.elemental_vibe}
  Visual treatment: ${icon.card_integration}
  Motif pattern: ${icon.flag_motif}
`;
  } else if (icon && index === 1) {
    direction += `  Accent elements: ${icon.accent_when_secondary}
  Color accents: ${icon.color_names}
  Sigil detail: ${icon.sigil}
`;
  } else if (icon && index === 2) {
    direction += `  Background texture: ${icon.texture_when_tertiary}
`;
  } else {
    direction += `  Motif source: ${(affinity.description || affinity.name).slice(0, 200)}
  Color cue: ${affinity.color || "#666"}
`;
  }

  return direction;
}

function buildLegacyCardPrompt({
  handle,
  bio,
  communities,
  tweets,
  iconography = null,
}) {
  const ranked = rankedAffinities(communities);
  if (ranked.length === 0) {
    throw new Error("Cannot build a card prompt without a legacy affinity");
  }

  const affinityDirections = ranked
    .map((affinity, index) => describeAffinity(affinity, index, iconography))
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
- Use the ranked names, descriptions, colors, and iconography only as visual motifs.
${affinityDirections}${tweetContext}
VISUAL REQUIREMENTS:
- Vertical 2:3 tarot card, ornate border, dark background
- Let rank 1 guide the central motif, rank 2 an accent, and rank 3 background texture
- Use the tweets and bio to personalize symbolic imagery
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

module.exports = { buildLegacyCardPrompt };
