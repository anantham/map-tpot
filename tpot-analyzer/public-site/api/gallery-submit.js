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

let blobPut = null;
try {
  const { put } = require("@vercel/blob");
  blobPut = put;
} catch {}

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
      async hget(key, field) {
        try { await redis.connect(); } catch {}
        return redis.hget(key, field);
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
    // Upload base64 images to Blob for permanent CDN URL
    let permanentUrl = imageUrl;
    if (blobPut && imageUrl.startsWith("data:image/")) {
      try {
        const match = imageUrl.match(/^data:image\/(png|jpeg|jpg|webp);base64,(.+)$/);
        if (match) {
          const mimeType = match[1] === "jpg" ? "jpeg" : match[1];
          const buffer = Buffer.from(match[2], "base64");
          const blob = await blobPut(
            `cards/${handle.toLowerCase()}-${Date.now()}.${mimeType === "jpeg" ? "jpg" : mimeType}`,
            buffer,
            { access: "public", contentType: `image/${mimeType}` },
          );
          permanentUrl = blob.url;
        }
      } catch (blobErr) {
        console.warn("[gallery-submit] Blob upload failed, using original URL:", blobErr.message);
      }
    }

    const galleryKey = handle.toLowerCase();
    let versions = [];
    try {
      const existing = await kv.hget("gallery", galleryKey);
      if (existing) {
        const parsed = JSON.parse(existing);
        versions = Array.isArray(parsed) ? parsed : [parsed];
      }
    } catch {}
    versions.push({
      url: permanentUrl,
      generatedAt: Date.now(),
      communities: (communities || []).slice(0, 5).map(c => ({
        name: c.name, color: c.color, weight: c.weight,
      })),
    });
    if (versions.length > 10) versions = versions.slice(-10);
    await kv.hset("gallery", galleryKey, JSON.stringify(versions));
    return res.status(200).json({ ok: true, stored: true });
  } catch (err) {
    console.error("[gallery-submit] KV write failed:", err.message);
    return res.status(200).json({ ok: true, stored: false });
  }
};
