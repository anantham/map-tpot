/**
 * GenerateCard.jsx — Custom hook for JIT collectible card generation.
 *
 * Handles two paths:
 *  1. BYOK (Bring Your Own Key): calls OpenRouter directly from the browser
 *  2. Serverless: calls /api/generate-card which manages cache + budget
 *
 * Returns { imageUrl, status } where status is one of:
 *   'idle' | 'generating' | 'generated' | 'error' | 'exhausted'
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { buildCardRequest } from "./cardPrompt";

const MODEL = "google/gemini-2.5-flash-image";
const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const RETRY_DELAY_MS = 5000;
const MAX_RETRIES = 3;
const LOCALSTORAGE_KEY = "openrouter_key";
const GEN_COUNT_KEY = "ingroup_gen_count";
const CARD_CACHE_KEY = "ingroup_card_cache";
const MAX_FREE_GENS = 10;

// --- Card image cache ---

function getCardCache() {
  try {
    return JSON.parse(localStorage.getItem(CARD_CACHE_KEY) || '{}');
  } catch { return {}; }
}

function getCachedCard(handle) {
  const cache = getCardCache();
  const entry = cache[handle.toLowerCase()];
  if (!entry) return null;
  // Migrate old format (single {url, cachedAt}) to versions array
  if (entry.url && !entry.versions) {
    return { url: entry.url, cachedAt: entry.cachedAt, versions: [{ url: entry.url, cachedAt: entry.cachedAt }] };
  }
  return entry;
}

/** Get all versions for a handle. */
export function getCachedVersions(handle) {
  const cached = getCachedCard(handle);
  return cached?.versions || [];
}

function cacheCard(handle, imageUrl) {
  try {
    const cache = getCardCache();
    const key = handle.toLowerCase();
    const existing = cache[key];
    // Build versions array
    let versions = [];
    if (existing) {
      if (existing.versions) {
        versions = existing.versions;
      } else if (existing.url) {
        versions = [{ url: existing.url, cachedAt: existing.cachedAt }];
      }
    }
    versions.push({ url: imageUrl, cachedAt: Date.now() });
    // Keep max 10 versions
    if (versions.length > 10) versions = versions.slice(-10);
    cache[key] = {
      url: imageUrl,
      cachedAt: Date.now(),
      versions,
    };
    localStorage.setItem(CARD_CACHE_KEY, JSON.stringify(cache));
  } catch (e) {
    if (e.name === 'QuotaExceededError') {
      try {
        const cache = getCardCache();
        const entries = Object.entries(cache).sort((a, b) => (a[1].cachedAt || 0) - (b[1].cachedAt || 0));
        const keep = Object.fromEntries(entries.slice(Math.floor(entries.length / 2)));
        keep[handle.toLowerCase()] = { url: imageUrl, cachedAt: Date.now(), versions: [{ url: imageUrl, cachedAt: Date.now() }] };
        localStorage.setItem(CARD_CACHE_KEY, JSON.stringify(keep));
      } catch { /* give up */ }
    }
  }
}

/** Get all cached cards as an array sorted by most recent first. */
export function getAllCachedCards() {
  const cache = getCardCache();
  return Object.entries(cache)
    .map(([handle, entry]) => ({ handle, url: entry.url, cachedAt: entry.cachedAt }))
    .sort((a, b) => b.cachedAt - a.cachedAt);
}

function clearCachedCard(handle) {
  try {
    const cache = getCardCache();
    delete cache[handle.toLowerCase()];
    localStorage.setItem(CARD_CACHE_KEY, JSON.stringify(cache));
  } catch {}
}

function getGenCount() {
  try { return parseInt(localStorage.getItem(GEN_COUNT_KEY) || '0', 10); } catch { return 0; }
}

function incrementGenCount() {
  try {
    const count = getGenCount() + 1;
    localStorage.setItem(GEN_COUNT_KEY, String(count));
    return count;
  } catch { return 0; }
}

/**
 * Build the image generation prompt text.
 * Duplicated from the serverless function for the BYOK path —
 * simpler than trying to share code between Vercel functions and Vite client.
 */
function buildPromptText({ handle, bio, communities, tweets }) {
  const sorted = [...communities].sort((a, b) => b.weight - a.weight);
  const primary = sorted[0];
  const secondary = sorted[1];

  let prompt = `Generate a collectible tarot-style card image.

SUBJECT: @${handle}
${bio ? `BIO: ${bio}` : ""}

PRIMARY COMMUNITY (${Math.round(primary.weight * 100)}%): ${primary.name}
  Spirit: ${(primary.description || primary.name).slice(0, 200)}
  Color: ${primary.color}
`;

  if (secondary) {
    prompt += `
SECONDARY COMMUNITY (${Math.round(secondary.weight * 100)}%): ${secondary.name}
  Spirit: ${(secondary.description || secondary.name).slice(0, 200)}
  Color: ${secondary.color}
`;
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
- Primary color: ${primary.color} (${primary.name})
${secondary ? `- Secondary accent: ${secondary.color} (${secondary.name})` : ""}
- The card should visually EMBODY what this person cares about
- Use the tweets and bio to choose symbolic imagery (not literal illustrations)
- Example: an ML researcher → neural network constellations, data streams as rivers
- Example: a contemplative practitioner → mandalas, meditation geometry, inner light
- Example: a builder/founder → forges, architectures, crystalline structures
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

/**
 * Call OpenRouter directly with a user-provided API key (BYOK path).
 */
async function generateDirect(apiKey, prompt, signal) {
  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": window.location.origin,
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [{ role: "user", content: prompt }],
      modalities: ["image", "text"],
      image_config: { aspect_ratio: "2:3", image_size: "1K" },
    }),
    signal,
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`OpenRouter ${response.status}: ${errText.slice(0, 200)}`);
  }

  const data = await response.json();
  const images = data.choices?.[0]?.message?.images;
  if (!images || images.length === 0) {
    throw new Error("Model returned no image");
  }

  const imageUrl = images[0].image_url?.url || images[0].url;
  if (!imageUrl) {
    throw new Error("Malformed image object in response");
  }

  return imageUrl;
}

/**
 * Call the serverless /api/generate-card endpoint.
 * Handles 202 (in-progress) with retry.
 */
async function generateServerless(cardRequest, signal, retryCount = 0) {
  const response = await fetch("/api/generate-card", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cardRequest),
    signal,
  });

  if (response.status === 202 && retryCount < MAX_RETRIES) {
    // In-progress, retry after delay
    await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
    return generateServerless(cardRequest, signal, retryCount + 1);
  }

  if (response.status === 429) {
    const body = await response.json();
    throw Object.assign(new Error(body.error || "Budget exhausted"), { code: "budget_exhausted" });
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Server error ${response.status}`);
  }

  const data = await response.json();
  return data.imageUrl;
}

/**
 * Custom hook for card generation.
 *
 * @param {Object} params
 * @param {string} params.handle
 * @param {string|null} params.bio
 * @param {Array} params.memberships
 * @param {string[]} params.sampleTweets
 * @param {Map} params.communityMap
 * @param {string} params.tier
 * @returns {{ imageUrl: string|null, status: 'idle'|'generating'|'generated'|'error'|'exhausted' }}
 */
export function useCardGeneration({ handle, bio, memberships, sampleTweets, communityMap, tier }) {
  const [imageUrl, setImageUrl] = useState(null);
  const [status, setStatus] = useState("idle");
  const [remaining, setRemaining] = useState(() => Math.max(0, MAX_FREE_GENS - getGenCount()));
  const inflightRef = useRef(null); // tracks current in-flight handle
  const abortRef = useRef(null);
  const skipCacheRef = useRef(false);

  const generate = useCallback(async () => {
    // Only generate for accounts with communities
    if (!handle || !memberships || memberships.length === 0) {
      return;
    }

    // Debounce: skip if already generating for this handle
    if (inflightRef.current === handle) {
      return;
    }

    // Check cache first — skip API call if we have a cached card
    if (!skipCacheRef.current) {
      const cached = getCachedCard(handle);
      if (cached) {
        setImageUrl(cached.url);
        setStatus("generated");
        return;
      }
    }
    skipCacheRef.current = false; // reset after use

    // Check per-user limit (skip for BYOK users)
    let byokKey = null;
    try { byokKey = localStorage.getItem(LOCALSTORAGE_KEY); } catch {}

    if (!byokKey && getGenCount() >= MAX_FREE_GENS) {
      setStatus("user_exhausted");
      setRemaining(0);
      return;
    }

    // Abort any previous in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }

    inflightRef.current = handle;
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("generating");
    setImageUrl(null);

    try {
      const cardRequest = buildCardRequest({
        handle,
        bio,
        memberships,
        sampleTweets,
        communityMap,
      });

      let url;
      if (byokKey) {
        // Direct call with user's key
        const prompt = buildPromptText(cardRequest);
        url = await generateDirect(byokKey, prompt, controller.signal);
      } else {
        // Serverless path
        url = await generateServerless(cardRequest, controller.signal);
      }

      // Only update state if this is still the current request
      if (inflightRef.current === handle) {
        setImageUrl(url);
        setStatus("generated");
        // Cache the generated card for instant recall
        cacheCard(handle, url);
        // Submit BYOK-generated cards to server gallery
        // (serverless path already stores in gallery via generate-card.js)
        if (byokKey) {
          fetch('/api/gallery-submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              handle,
              imageUrl: url,
              communities: cardRequest.communities,
            }),
          }).catch(() => {}); // fire-and-forget
        }
        // Increment per-user generation count (only for serverless path)
        if (!byokKey) {
          const newCount = incrementGenCount();
          setRemaining(Math.max(0, MAX_FREE_GENS - newCount));
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        // Request was superseded, don't update state
        return;
      }

      if (inflightRef.current === handle) {
        if (err.code === "budget_exhausted") {
          setStatus("exhausted");
        } else {
          setStatus("error");
          console.error("[GenerateCard] Generation failed:", err.message);
        }
      }
    } finally {
      if (inflightRef.current === handle) {
        inflightRef.current = null;
      }
    }
  }, [handle, bio, memberships, sampleTweets, communityMap]);

  // Trigger generation when handle changes
  useEffect(() => {
    if (handle && memberships && memberships.length > 0) {
      generate();
    }

    return () => {
      // Cleanup on unmount or handle change
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [handle]); // eslint-disable-line react-hooks/exhaustive-deps

  const regenerate = useCallback(() => {
    if (!handle) return;
    // Clear local cache
    clearCachedCard(handle);
    // Clear inflight lock so generate() doesn't skip
    inflightRef.current = null;
    // Skip cache on next generate call
    skipCacheRef.current = true;
    // Trigger
    generate();
  }, [handle, generate]);

  return { imageUrl, status, remaining, regenerate };
}
