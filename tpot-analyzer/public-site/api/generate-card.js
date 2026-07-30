/**
 * Vercel serverless function: POST /api/generate-card
 *
 * Generates a collectible card image via OpenRouter (Gemini 2.5 Flash).
 * Uses Redis (ioredis) for caching and daily budget tracking.
 *
 * Body: { handle, bio, communities: [{name, color, weight}], tweets: [string] }
 * Returns: { imageUrl, cached, model } | { error, code }
 */

const { getKv, getBlobPut } = require("./_lib");
const { buildLegacyCardPrompt } = require("./_legacyCardPrompt");

const MODEL = "google/gemini-2.5-flash-image";
const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const DEFAULT_ABORT_TIMEOUT_MS = 45000;

let ICONOGRAPHY = null;
try {
  ICONOGRAPHY = require("../config/community_iconography.json").communities;
} catch {
  // The prompt helper falls back to names, descriptions, and colors.
}

function resolveAbortTimeoutMs() {
  const raw = parseInt(process.env.CARD_GENERATION_TIMEOUT_MS || "", 10);
  if (Number.isFinite(raw) && raw >= 5000) return raw;
  return DEFAULT_ABORT_TIMEOUT_MS;
}

module.exports = async function handler(req, res) {
  const kv = getKv();
  const blobPut = getBlobPut();

  // Only accept POST
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed", code: "method_not_allowed" });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: "Server misconfigured: missing API key", code: "config_error" });
  }

  // --- 1. Validate request ---
  const { handle, bio, communities, tweets, force } = req.body || {};
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
  const abortTimeoutMs = resolveAbortTimeoutMs();
  const requestStartedAt = Date.now();
  const requestId = `card-${handle.toLowerCase()}-${requestStartedAt}`;

  console.log("[generate-card] Request received", {
    requestId,
    handle: handle.toLowerCase(),
    communitiesCount: communities.length,
    tweetsCount: Array.isArray(tweets) ? tweets.length : 0,
    force: Boolean(force),
    abortTimeoutMs,
    hasKv: Boolean(kv),
    hasBlobPut: Boolean(blobPut),
  });

  // --- 2. Check cache (skip if force=true for regeneration) ---
  if (kv && !force) {
    try {
      // Primary cache: short-lived key (24h)
      const cached = await kv.get(cacheKey);
      if (cached && cached !== "pending") {
        console.log("[generate-card] Cache hit (primary)", {
          requestId,
          handle: handle.toLowerCase(),
        });
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

      // Secondary cache: permanent gallery hash
      const galleryKey = handle.toLowerCase();
      const existing = await kv.hget("gallery", galleryKey);
      if (existing) {
        const parsed = JSON.parse(existing);
        const versions = Array.isArray(parsed) ? parsed : [parsed];
        const latest = versions[versions.length - 1];
        if (latest && latest.url) {
          console.log("[generate-card] Cache hit (gallery fallback)", {
            requestId,
            handle: handle.toLowerCase(),
          });
          // Back-fill the primary cache for faster subsequent checks
          await kv.set(cacheKey, latest.url, { ex: 86400 });
          return res.status(200).json({ imageUrl: latest.url, cached: true, model: MODEL });
        }
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
  const prompt = buildLegacyCardPrompt({
    handle,
    bio,
    communities,
    tweets,
    iconography: ICONOGRAPHY,
  });
  console.log("[generate-card] Prompt assembled", {
    requestId,
    handle: handle.toLowerCase(),
    promptChars: prompt.length,
    model: MODEL,
  });

  // --- 6. Call OpenRouter ---
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), abortTimeoutMs);
  const upstreamStartedAt = Date.now();
  console.log("[generate-card] OpenRouter request starting", {
    requestId,
    handle: handle.toLowerCase(),
    model: MODEL,
    upstreamUrl: OPENROUTER_URL,
  });

  try {
    const orResponse = await fetch(OPENROUTER_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://maptpot.vercel.app",
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
    console.log("[generate-card] OpenRouter response received", {
      requestId,
      handle: handle.toLowerCase(),
      status: orResponse.status,
      ok: orResponse.ok,
      elapsedMs: Date.now() - upstreamStartedAt,
    });

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
    console.log("[generate-card] OpenRouter payload parsed", {
      requestId,
      handle: handle.toLowerCase(),
      choices: Array.isArray(data.choices) ? data.choices.length : 0,
      completionTokens: data.usage?.completion_tokens || 0,
    });

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

    // --- 8. Upload to Blob storage + track cost ---
    const completionTokens = data.usage?.completion_tokens || 0;
    const costUsd = completionTokens * (30 / 1_000_000); // $30/1M tokens

    // Upload image to Vercel Blob for a permanent CDN URL.
    // Falls back to storing the raw data URI if Blob is unavailable.
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
          console.log("[generate-card] Uploaded to Blob", {
            requestId,
            handle: handle.toLowerCase(),
            permanentUrl,
            approxKb: Math.round(buffer.length / 1024),
          });
        }
      } catch (blobErr) {
        console.warn("[generate-card] Blob upload failed, using data URI:", blobErr.message);
      }
    }

    if (kv) {
      try {
        // Cache latest permanent URL for 24h
        await kv.set(cacheKey, permanentUrl, { ex: 86400 });
        // Persist to permanent gallery — URL only (not the image data)
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
          communities: communities.slice(0, 5).map(c => ({
            name: c.name, color: c.color, weight: c.weight,
          })),
        });
        // Keep max 10 versions per handle
        if (versions.length > 10) versions = versions.slice(-10);
        await kv.hset("gallery", galleryKey, JSON.stringify(versions));
        // Increment daily budget
        await kv.incrbyfloat(budgetKey, costUsd);
        // Ensure budget key expires after 48h (cleanup)
        await kv.expire(budgetKey, 172800);
      } catch (kvErr) {
        console.warn("[generate-card] KV cache/budget write failed:", kvErr.message);
      }
    }

    // --- 9. Return result ---
    console.log("[generate-card] Request succeeded", {
      requestId,
      handle: handle.toLowerCase(),
      cached: false,
      totalElapsedMs: Date.now() - requestStartedAt,
    });
    return res.status(200).json({
      imageUrl: permanentUrl,
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
      console.error("[generate-card] Request aborted (timeout)", {
        requestId,
        handle: handle.toLowerCase(),
        abortTimeoutMs,
        totalElapsedMs: Date.now() - requestStartedAt,
        upstreamElapsedMs: Date.now() - upstreamStartedAt,
      });
      return res.status(500).json({
        error: `Image generation timed out (${Math.round(abortTimeoutMs / 1000)}s limit)`,
        code: "generation_timeout",
      });
    }

    console.error("[generate-card] Unexpected error", {
      requestId,
      handle: handle.toLowerCase(),
      totalElapsedMs: Date.now() - requestStartedAt,
      errorName: err?.name,
      errorMessage: err?.message,
      stack: err?.stack,
    });
    return res.status(500).json({
      error: "Internal server error",
      code: "internal_error",
    });
  }
};
