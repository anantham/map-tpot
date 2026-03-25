/**
 * Vercel serverless function: GET /api/card-image?handle=xxx
 *
 * Serves the generated card image as a PNG. Used as the og:image URL
 * so Twitter/X crawler can fetch the actual image bytes.
 *
 * If the image is a base64 data URI, decodes and serves as PNG.
 * If it's a URL, redirects to it.
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

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const handle = (req.query.handle || "").replace(/^@/, "").trim().toLowerCase();
  if (!handle) {
    return res.status(400).json({ error: "Missing handle" });
  }

  if (!kv) {
    return res.status(404).json({ error: "No image available" });
  }

  try {
    const raw = await kv.hget("gallery", handle);
    if (!raw) {
      return res.status(404).json({ error: "No card generated for this handle" });
    }

    // Parse gallery entry — supports both old format and versioned array
    let imageUrl;
    try {
      const entry = JSON.parse(raw);
      if (Array.isArray(entry)) {
        imageUrl = entry[entry.length - 1]?.url;
      } else {
        imageUrl = entry.url || entry;
      }
    } catch {
      // Raw string (legacy: bare URL or data URI)
      imageUrl = raw;
    }

    if (!imageUrl) {
      return res.status(404).json({ error: "No image URL" });
    }

    // Blob URL or external URL → redirect (fast path, no decoding)
    if (imageUrl.startsWith("https://")) {
      res.setHeader("Cache-Control", "public, s-maxage=86400, stale-while-revalidate=604800");
      return res.redirect(302, imageUrl);
    }

    // Legacy: Base64 data URI → decode and serve as image
    if (imageUrl.startsWith("data:image/")) {
      const match = imageUrl.match(/^data:image\/(png|jpeg|jpg|webp);base64,(.+)$/);
      if (!match) {
        return res.status(500).json({ error: "Malformed data URI" });
      }
      const mimeType = match[1] === "jpg" ? "jpeg" : match[1];
      const buffer = Buffer.from(match[2], "base64");

      res.setHeader("Content-Type", `image/${mimeType}`);
      res.setHeader("Cache-Control", "public, s-maxage=86400, stale-while-revalidate=604800");
      return res.status(200).send(buffer);
    }

    // Unknown format
    return res.status(500).json({ error: "Unrecognized image format" });
  } catch (err) {
    console.error("[card-image] Error:", err.message);
    return res.status(500).json({ error: "Internal error" });
  }
};
