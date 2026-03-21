/**
 * Vercel serverless function: GET /api/og?handle=xxx
 *
 * Serves a minimal HTML page with OpenGraph + Twitter Card meta tags
 * so that when a card URL is shared on X, the preview shows the
 * generated card image.
 *
 * Falls back to a generic site card if no generated image exists in KV.
 */

let kv = null;
try {
  const Redis = require("ioredis");
  const redisUrl = process.env.KV_REDIS_URL;
  if (redisUrl) {
    const redis = new Redis(redisUrl, {
      maxRetriesPerRequest: 1,
      connectTimeout: 3000,
      lazyConnect: true,
    });
    kv = {
      async hget(key, field) {
        try { await redis.connect(); } catch {}
        return redis.hget(key, field);
      },
    };
  }
} catch {}

const SITE_URL = "https://amiingroup.vercel.app";
const SITE_NAME = "Find My Ingroup";

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const handle = (req.query.handle || "").replace(/^@/, "").trim().toLowerCase();
  if (!handle) {
    return res.redirect(302, SITE_URL);
  }

  // Try to get the card image from gallery
  let imageUrl = null;
  let communities = [];
  if (kv) {
    try {
      const raw = await kv.hget("gallery", handle);
      if (raw) {
        const entry = JSON.parse(raw);
        imageUrl = entry.url;
        communities = entry.communities || [];
      }
    } catch {}
  }

  // Build description from communities
  const communityText = communities.length > 0
    ? communities
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 3)
        .map(c => `${c.name} (${Math.round(c.weight * 100)}%)`)
        .join(", ")
    : null;

  const title = `@${handle} — ${SITE_NAME}`;
  const description = communityText
    ? `${communityText}. Discover which corners of TPOT you belong to.`
    : `Find out which TPOT communities @${handle} belongs to.`;
  const cardUrl = `${SITE_URL}/?handle=${encodeURIComponent(handle)}`;

  // Use the card-image endpoint as og:image (serves actual PNG bytes)
  // Twitter can't handle base64 data URIs, needs a fetchable HTTPS URL
  const ogImageUrl = imageUrl
    ? `${SITE_URL}/api/card-image?handle=${encodeURIComponent(handle)}`
    : null;
  const twitterCard = ogImageUrl ? "summary_large_image" : "summary";

  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "public, s-maxage=3600, stale-while-revalidate=86400");

  return res.status(200).send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtml(title)}</title>
  <meta property="og:title" content="${escapeAttr(title)}">
  <meta property="og:description" content="${escapeAttr(description)}">
  <meta property="og:url" content="${escapeAttr(cardUrl)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="${SITE_NAME}">
  ${ogImageUrl ? `<meta property="og:image" content="${escapeAttr(ogImageUrl)}">` : ""}
  <meta name="twitter:card" content="${twitterCard}">
  <meta name="twitter:title" content="${escapeAttr(title)}">
  <meta name="twitter:description" content="${escapeAttr(description)}">
  ${ogImageUrl ? `<meta name="twitter:image" content="${escapeAttr(ogImageUrl)}">` : ""}
  <meta http-equiv="refresh" content="0;url=${escapeAttr(cardUrl)}">
</head>
<body>
  <p>Redirecting to <a href="${escapeAttr(cardUrl)}">${escapeHtml(title)}</a>...</p>
</body>
</html>`);
};

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
