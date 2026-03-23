/**
 * Vercel serverless function: GET /api/gallery
 *
 * Returns all permanently stored card images from KV.
 * Response: { cards: [{ handle, url, generatedAt, communities }] }
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
      async hgetall(key) {
        try { await redis.connect(); } catch {}
        return redis.hgetall(key);
      },
    };
  }
} catch {}

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!kv) {
    return res.status(200).json({ cards: [] });
  }

  try {
    const raw = await kv.hgetall("gallery");
    const cards = Object.entries(raw || {}).map(([handle, json]) => {
      try {
        const parsed = JSON.parse(json);
        // Support both old format (single object) and new format (array)
        const versions = Array.isArray(parsed) ? parsed : [parsed];
        const latest = versions[versions.length - 1];
        return {
          handle,
          url: latest.url,
          generatedAt: latest.generatedAt || 0,
          communities: latest.communities || [],
          versions: versions.map(v => ({ url: v.url, generatedAt: v.generatedAt || 0 })),
        };
      } catch {
        return { handle, url: json, generatedAt: 0, communities: [], versions: [{ url: json, generatedAt: 0 }] };
      }
    });

    // Sort by most recent first
    cards.sort((a, b) => (b.generatedAt || 0) - (a.generatedAt || 0));

    return res.status(200).json({ cards });
  } catch (err) {
    console.error("[gallery] KV read failed:", err.message);
    return res.status(200).json({ cards: [] });
  }
};
