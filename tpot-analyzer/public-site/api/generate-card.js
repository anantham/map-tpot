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

  // --- 2. Check cache (skip if force=true for regeneration) ---
  if (kv && !force) {
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
        // Cache latest image URL for 24h
        await kv.set(cacheKey, imageUrl, { ex: 86400 });
        // Persist to permanent gallery — append to version history
        const galleryKey = handle.toLowerCase();
        let versions = [];
        try {
          const existing = await kv.hget("gallery", galleryKey);
          if (existing) {
            const parsed = JSON.parse(existing);
            // Migrate from old format (single entry) to array
            versions = Array.isArray(parsed) ? parsed : [parsed];
          }
        } catch {}
        versions.push({
          url: imageUrl,
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
 * TPOT Tarot Iconography — maps community short_name to visual identity.
 * Each community has a mascot, sigil, motif, colors, and layering rules.
 * Community fractions become art direction weights, not labels.
 */
let ICONOGRAPHY = null;
try {
  ICONOGRAPHY = require("../config/community_iconography.json").communities;
} catch {
  // Fallback: generic prompt if config not found at build time
}

function getIconography(community) {
  if (!ICONOGRAPHY) return null;
  return ICONOGRAPHY[community.short_name] || null;
}

/**
 * Build the image-generation prompt from card data.
 *
 * Uses the TPOT Tarot Iconography system: primary community = mascot energy +
 * dominant colors + elemental vibe. Secondary = accent elements the figure
 * "holds" or "wears". Tertiary = background texture only.
 * The viewer FEELS community membership intuitively — no labels, no charts.
 */
function buildPrompt({ handle, bio, communities, tweets }) {
  const sorted = [...communities].sort((a, b) => b.weight - a.weight);
  const primary = sorted[0];
  const secondary = sorted[1];
  const tertiary = sorted[2];

  const pIcon = getIconography(primary);
  const sIcon = secondary ? getIconography(secondary) : null;
  const tIcon = tertiary ? getIconography(tertiary) : null;

  let prompt = `Generate a collectible tarot-style card image.

SUBJECT: @${handle}
${bio ? `BIO: ${bio}` : ""}
`;

  // === PRIMARY COMMUNITY — full visual treatment ===
  if (pIcon) {
    prompt += `
PRIMARY COMMUNITY (${Math.round(primary.weight * 100)}%): ${primary.name}
  Mascot energy: ${pIcon.mascot}
  Sigil: ${pIcon.sigil}
  Color palette: ${pIcon.color_names}
  Elemental vibe: ${pIcon.elemental_vibe}
  Visual treatment: ${pIcon.card_integration}
  Flag/motif pattern: ${pIcon.flag_motif}
`;
  } else {
    prompt += `
PRIMARY COMMUNITY (${Math.round(primary.weight * 100)}%): ${primary.name}
  Spirit: ${(primary.description || primary.name).slice(0, 200)}
  Color: ${primary.color}
`;
  }

  // === SECONDARY COMMUNITY — accent treatment ===
  if (secondary && secondary.weight >= 0.10) {
    if (sIcon) {
      prompt += `
SECONDARY COMMUNITY (${Math.round(secondary.weight * 100)}%): ${secondary.name}
  Accent elements: ${sIcon.accent_when_secondary}
  Color accents: ${sIcon.color_names}
  Sigil detail: ${sIcon.sigil}
`;
    } else {
      prompt += `
SECONDARY COMMUNITY (${Math.round(secondary.weight * 100)}%): ${secondary.name}
  Spirit: ${(secondary.description || secondary.name).slice(0, 200)}
  Color accent: ${secondary.color}
`;
    }
  }

  // === TERTIARY COMMUNITY — background texture only ===
  if (tertiary && tertiary.weight >= 0.10) {
    if (tIcon) {
      prompt += `
TERTIARY COMMUNITY (${Math.round(tertiary.weight * 100)}%): ${tertiary.name}
  Background texture: ${tIcon.texture_when_tertiary}
`;
    }
  }

  if (tweets && tweets.length > 0) {
    prompt += `
REPRESENTATIVE TWEETS (these reveal the person's voice and interests):
${tweets.slice(0, 3).map((t, i) => `  ${i + 1}. ${t.slice(0, 200)}`).join("\n")}
`;
  }

  prompt += `
VISUAL REQUIREMENTS:
- Vertical 2:3 tarot card, ornate border, dark background
- The primary community's mascot energy, colors, and elemental vibe should DOMINATE the composition
- Secondary community appears as subtle accents the figure "holds" or "wears"
- Tertiary community is background texture or border pattern only
- The viewer should FEEL the community membership intuitively — no labels, no charts
- Use the tweets and bio to personalize within the community's visual language
- Mystical/arcane aesthetic: sacred geometry, constellation maps, subtle glow

TEXT ON CARD (keep minimal):
- The handle "@${handle}" at top or bottom
- NO other text. No quotes, no community names, no descriptions, no paragraphs
- Let the imagery speak. The card is a portrait, not an infographic.

CRITICAL CONSTRAINTS:
- Do NOT include real human faces or photographs
- Use abstract symbols, cosmic imagery, stylized avatars
- NO walls of text, NO labels beyond the handle
- The card should be visually striking enough to share on social media

Style: premium collectible trading card, digital art, high contrast, rich saturated colors`;

  return prompt;
}
