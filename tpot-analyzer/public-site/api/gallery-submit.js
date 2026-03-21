/**
 * Vercel serverless function: POST /api/gallery-submit
 *
 * Accepts a generated card image from BYOK users and stores it in the
 * permanent gallery. This allows BYOK-generated cards to appear in the
 * community gallery alongside serverless-generated ones.
 *
 * Body: { handle, imageUrl, communities: [{name, color, weight}] }
 * Returns: 200 OK | 400 validation error
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
      async hset(key, field, value) {
        try { await redis.connect(); } catch {}
        return redis.hset(key, field, value);
      },
    };
  }
} catch {}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { handle, imageUrl, communities } = req.body || {};
  if (!handle || !imageUrl) {
    return res.status(400).json({ error: "Missing handle or imageUrl" });
  }

  if (!kv) {
    // KV unavailable — accept silently (card still cached client-side)
    return res.status(200).json({ ok: true, stored: false });
  }

  try {
    await kv.hset("gallery", handle.toLowerCase(), JSON.stringify({
      url: imageUrl,
      generatedAt: Date.now(),
      communities: (communities || []).slice(0, 5).map(c => ({
        name: c.name, color: c.color, weight: c.weight,
      })),
    }));
    return res.status(200).json({ ok: true, stored: true });
  } catch (err) {
    console.error("[gallery-submit] KV write failed:", err.message);
    return res.status(200).json({ ok: true, stored: false });
  }
};
