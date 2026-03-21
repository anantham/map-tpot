/**
 * Vercel serverless function: POST /api/generate-card
 *
 * Generates a collectible card image via OpenRouter (Gemini 2.5 Flash).
 * Uses Redis (ioredis) for caching and daily budget tracking.
 *
 * Body: { handle, bio, communities: [{name, color, weight}], tweets: [string] }
 * Returns: { imageUrl, cached, model } | { error, code }
 */

let kv = null;
let rawRedis = null;
try {
  const Redis = require("ioredis");
  const redisUrl = process.env.KV_REDIS_URL;
  if (redisUrl) {
    rawRedis = new Redis(redisUrl, {
      maxRetriesPerRequest: 1,
      connectTimeout: 3000,
      lazyConnect: true,
    });
    // ioredis API adapter — wrap to match our get/set/del/incrbyfloat/expire pattern
    kv = {
      async get(key) {
        try { await rawRedis.connect(); } catch {}
        return rawRedis.get(key);
      },
      async set(key, value, opts) {
        try { await rawRedis.connect(); } catch {}
        if (opts?.nx && opts?.ex) {
          const result = await rawRedis.set(key, typeof value === 'object' ? JSON.stringify(value) : value, 'EX', opts.ex, 'NX');
          return result === 'OK';
        }
        if (opts?.ex) {
          return rawRedis.set(key, typeof value === 'object' ? JSON.stringify(value) : value, 'EX', opts.ex);
        }
        return rawRedis.set(key, typeof value === 'object' ? JSON.stringify(value) : value);
      },
      async del(key) {
        try { await rawRedis.connect(); } catch {}
        return rawRedis.del(key);
      },
      async incrbyfloat(key, amount) {
        try { await rawRedis.connect(); } catch {}
        return rawRedis.incrbyfloat(key, amount);
      },
      async expire(key, seconds) {
        try { await rawRedis.connect(); } catch {}
        return rawRedis.expire(key, seconds);
      },
      async hset(key, field, value) {
        try { await rawRedis.connect(); } catch {}
        return rawRedis.hset(key, field, value);
      },
      async hgetall(key) {
        try { await rawRedis.connect(); } catch {}
        return rawRedis.hgetall(key);
      },
    };
  }
} catch {
  // Redis unavailable — graceful degradation (no cache, no budget enforcement)
}

const MODEL = "google/gemini-2.5-flash-image";
const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const ABORT_TIMEOUT_MS = 8000; // 8s abort (Vercel Hobby ceiling = 10s)

module.exports = async function handler(req, res) {
  // Only accept POST
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed", code: "method_not_allowed" });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: "Server misconfigured: missing API key", code: "config_error" });
  }

  // --- 1. Validate request ---
  const { handle, bio, communities, tweets } = req.body || {};
  if (!handle || !communities || !Array.isArray(communities) || communities.length === 0) {
    return res.status(400).json({
      error: "Missing required fields: handle, communities[]",
      code: "validation_error",
    });
  }

  const cacheKey = `card:${handle.toLowerCase()}`;
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const budgetKey = `budget:${today}`;
  const dailyLimit = parseFloat(process.env.CARD_DAILY_BUDGET || "5.00");

  // --- 2. Check cache ---
  if (kv) {
    try {
      const cached = await kv.get(cacheKey);
      if (cached && cached !== "pending") {
        return res.status(200).json({ imageUrl: cached, cached: true, model: MODEL });
      }
      if (cached === "pending") {
        // Another request is in-flight for this handle
        return res.status(202).json({
          error: "Generation in progress, retry shortly",
          code: "in_progress",
          retryAfter: 5,
        });
      }
    } catch (kvErr) {
      console.warn("[generate-card] KV cache read failed, proceeding without cache:", kvErr.message);
    }
  }

  // --- 3. Check daily budget ---
  if (kv) {
    try {
      const spent = parseFloat((await kv.get(budgetKey)) || "0");
      if (spent >= dailyLimit) {
        return res.status(429).json({
          error: "Daily generation budget exhausted. Try again tomorrow or use your own API key.",
          code: "budget_exhausted",
        });
      }
    } catch (kvErr) {
      console.warn("[generate-card] KV budget read failed, proceeding without budget check:", kvErr.message);
    }
  }

  // --- 4. Set optimistic lock ---
  if (kv) {
    try {
      // NX = only set if not exists, EX = 30s TTL
      await kv.set(cacheKey, "pending", { nx: true, ex: 30 });
    } catch (kvErr) {
      console.warn("[generate-card] KV lock set failed:", kvErr.message);
    }
  }

  // --- 5. Build prompt ---
  const prompt = buildPrompt({ handle, bio, communities, tweets });

  // --- 6. Call OpenRouter ---
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), ABORT_TIMEOUT_MS);

  try {
    const orResponse = await fetch(OPENROUTER_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://findmyingroup.com",
        "X-Title": "TPOT Collectible Cards",
      },
      body: JSON.stringify({
        model: MODEL,
        messages: [{ role: "user", content: prompt }],
        modalities: ["image", "text"],
        image_config: { aspect_ratio: "2:3", image_size: "1K" },
      }),
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!orResponse.ok) {
      const errBody = await orResponse.text();
      console.error("[generate-card] OpenRouter error:", orResponse.status, errBody);
      // Clear pending lock
      if (kv) {
        try { await kv.del(cacheKey); } catch {}
      }
      return res.status(502).json({
        error: "Upstream generation failed",
        code: "upstream_error",
        detail: errBody.slice(0, 200),
      });
    }

    const data = await orResponse.json();

    // --- 7. Parse image ---
    const images = data.choices?.[0]?.message?.images;
    if (!images || images.length === 0) {
      console.error("[generate-card] No images in response:", JSON.stringify(data).slice(0, 500));
      if (kv) {
        try { await kv.del(cacheKey); } catch {}
      }
      return res.status(500).json({
        error: "Model returned no image",
        code: "generation_failed",
      });
    }

    const imageUrl = images[0].image_url?.url || images[0].url;
    if (!imageUrl) {
      console.error("[generate-card] Image object has no url:", JSON.stringify(images[0]).slice(0, 300));
      if (kv) {
        try { await kv.del(cacheKey); } catch {}
      }
      return res.status(500).json({
        error: "Model returned malformed image object",
        code: "generation_failed",
      });
    }

    // --- 8. Track cost & cache result ---
    const completionTokens = data.usage?.completion_tokens || 0;
    const costUsd = completionTokens * (30 / 1_000_000); // $30/1M tokens

    if (kv) {
      try {
        // Cache image URL for 24h
        await kv.set(cacheKey, imageUrl, { ex: 86400 });
        // Persist to permanent gallery (no TTL)
        await kv.hset("gallery", handle.toLowerCase(), JSON.stringify({
          url: imageUrl,
          generatedAt: Date.now(),
          communities: communities.slice(0, 5).map(c => ({
            name: c.name, color: c.color, weight: c.weight,
          })),
        }));
        // Increment daily budget
        await kv.incrbyfloat(budgetKey, costUsd);
        // Ensure budget key expires after 48h (cleanup)
        await kv.expire(budgetKey, 172800);
      } catch (kvErr) {
        console.warn("[generate-card] KV cache/budget write failed:", kvErr.message);
      }
    }

    // --- 9. Return result ---
    return res.status(200).json({
      imageUrl,
      cached: false,
      model: MODEL,
    });
  } catch (err) {
    clearTimeout(timeout);

    // Clear pending lock
    if (kv) {
      try { await kv.del(cacheKey); } catch {}
    }

    if (err.name === "AbortError") {
      console.error("[generate-card] Request aborted (timeout)");
      return res.status(500).json({
        error: "Image generation timed out (8s limit)",
        code: "generation_timeout",
      });
    }

    console.error("[generate-card] Unexpected error:", err);
    return res.status(500).json({
      error: "Internal server error",
      code: "internal_error",
    });
  }
};

/**
 * Build the image-generation prompt from card data.
 */
function buildPrompt({ handle, bio, communities, tweets }) {
  const sorted = [...communities].sort((a, b) => b.weight - a.weight);
  const primary = sorted[0];
  const secondary = sorted[1];

  const communityLines = sorted
    .map((c) => `- ${c.name} (${Math.round(c.weight * 100)}%) [${c.color}]`)
    .join("\n");

  const tweetSection =
    tweets && tweets.length > 0
      ? `\nSample tweets by @${handle}:\n${tweets.slice(0, 5).map((t) => `> ${t}`).join("\n")}\n`
      : "";

  return `Design a collectible tarot-style card for a Twitter/X personality.

Card subject: @${handle}
${bio ? `Bio: ${bio}` : ""}

Community memberships:
${communityLines}
${tweetSection}
Visual direction:
- Vertical 2:3 tarot card format with ornate border
- Primary color theme: ${primary.color} (${primary.name})
${secondary ? `- Secondary accent: ${secondary.color} (${secondary.name})` : ""}
- Dark background (#1a1a1a or similar)
- Include the handle "@${handle}" as text on the card
- Mystical/arcane aesthetic: think constellation maps, sacred geometry, subtle glow effects
- The card should feel like a collectible trading card — premium, shareable
- Do NOT include any real human faces or photographs
- Use abstract symbols, cosmic imagery, or stylized avatars instead

Style: digital art, high contrast, rich colors against dark background, tarot card aesthetic`;
}
