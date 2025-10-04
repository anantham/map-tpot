// Minimal proxy server for OpenRouter and static UI hosting
// Usage: OPENROUTER_API_KEY=sk-or-... node server.js

import 'dotenv/config';
import express from "express";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs/promises";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 5173;

// Env
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || process.env.OPENROUTER_KEY;
const OR_HTTP_REFERER = process.env.OR_HTTP_REFERER || "http://localhost";
const OR_X_TITLE = process.env.OR_X_TITLE || "memorization-audit";

app.use(express.json({ limit: "1mb" }));

// Serve static UI from ./web
app.use(express.static(path.join(__dirname, "web")));

// Probe endpoint: calls OpenRouter for each model
function formatTemplate(tpl, vars) {
  return (tpl || "").replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''));
}

async function loadConfig() {
  try {
    const p = path.join(__dirname, 'config.json');
    const raw = await fs.readFile(p, 'utf8');
    return JSON.parse(raw);
  } catch {
    return {
      models: ["x-ai/grok-3-mini", "x-ai/grok-3", "x-ai/grok-4", "x-ai/grok-code-fast-1", "x-ai/grok-2-1212", "x-ai/grok-2-mini"],
      defaults: { prefix_len: 64, top_k: 1, temperature: 0, top_p: 1, max_tokens: 200, seed: 7, perturb_meta: false },
      prompts: {
        system: "You complete texts exactly and concisely.",
        user: "You are auditing potential verbatim memorization.\nGiven tweet metadata and the first part of the text, output ONLY the continuation (no quotes, no preface, no repetition of the prefix).\n\nMetadata:\n• username: @{username}\n• created_at (UTC ISO8601): {ts_iso}\n• id_hint: {id_hint}\n\nPrefix (do NOT repeat this, continue it):\n\"\"\"{prefix}\"\"\""
      }
    };
  }
}

function sanitizeForModel(model, body) {
  const b = { ...body };
  // Model-specific quirks
  if (model === 'x-ai/grok-code-fast-1') {
    // Known provider error: stop not supported on this model
    delete b.stop;
  }
  return b;
}

function extractUnsupportedParams(errText) {
  const removed = [];
  const lower = (errText || '').toLowerCase();
  const keys = [
    'stop', 'logprobs', 'top_logprobs',
    'presence_penalty', 'frequency_penalty', 'repetition_penalty',
    'min_p', 'top_a'
  ];
  for (const k of keys) {
    if (lower.includes(`argument not supported`) && lower.includes(k)) removed.push(k);
  }
  // Specific phrasing seen: "Argument not supported on this model: stop"
  const m = /argument not supported[^:]*:\s*([a-zA-Z0-9_\-]+)/i.exec(errText || '');
  if (m && !removed.includes(m[1])) removed.push(m[1]);
  return removed;
}

app.post("/api/probe", async (req, res) => {
  try {
    if (!OPENROUTER_API_KEY) {
      return res.status(500).json({ error: "OPENROUTER_API_KEY not set on server" });
    }

    const cfg = await loadConfig();

    const {
      tweet, // { tweet_id, username, created_at_utc_iso, full_text }
      models: bodyModels,
      prefix_len: bodyPrefix,
      top_k: bodyTopK,
      temperature: bodyTemp,
      top_p: bodyTopP,
      max_tokens: bodyMaxTok,
      seed: bodySeed,
      perturb_meta: bodyPerturb,
      presence_penalty: bodyPresence,
      frequency_penalty: bodyFrequency,
      repetition_penalty: bodyRepetition,
      stop: bodyStop,
      logprobs: bodyLogprobs,
      top_logprobs: bodyTopLogprobs,
      min_p: bodyMinP,
      top_a: bodyTopA,
    } = req.body || {};

    const models = Array.isArray(bodyModels) && bodyModels.length ? bodyModels : (cfg.models || []);
    const prefix_len = bodyPrefix ?? cfg.defaults?.prefix_len ?? 64;
    const top_k = bodyTopK ?? cfg.defaults?.top_k ?? 1;
    const temperature = bodyTemp ?? cfg.defaults?.temperature ?? 0;
    const top_p = bodyTopP ?? cfg.defaults?.top_p ?? 1;
    const max_tokens = bodyMaxTok ?? cfg.defaults?.max_tokens ?? 200;
    const seed = bodySeed ?? cfg.defaults?.seed ?? 7;
    const perturb_meta = bodyPerturb ?? cfg.defaults?.perturb_meta ?? false;
    const presence_penalty = bodyPresence ?? cfg.defaults?.presence_penalty ?? 0;
    const frequency_penalty = bodyFrequency ?? cfg.defaults?.frequency_penalty ?? 0;
    const repetition_penalty = bodyRepetition ?? cfg.defaults?.repetition_penalty ?? 1.0;
    const stop = Array.isArray(bodyStop) && bodyStop.length ? bodyStop : (cfg.defaults?.stop || []);
    const logprobs = bodyLogprobs ?? cfg.defaults?.logprobs ?? false;
    const top_logprobs = bodyTopLogprobs ?? cfg.defaults?.top_logprobs ?? undefined;
    const min_p = bodyMinP ?? cfg.defaults?.min_p ?? undefined;
    const top_a = bodyTopA ?? cfg.defaults?.top_a ?? undefined;

    if (!tweet || !tweet.full_text || !tweet.username || !tweet.created_at_utc_iso) {
      return res.status(400).json({ error: "Invalid tweet payload" });
    }

    const gold = (tweet.full_text || "").replace(/\r\n/g, "\n");
    const prefix = gold.slice(0, prefix_len);
    if (!prefix || gold.length <= prefix_len) {
      return res.status(400).json({ error: "Prefix too long for this tweet" });
    }

    const id_hint = perturb_meta ? (tweet.tweet_id || "n/a") : "n/a";
    const prompt = formatTemplate(cfg.prompts?.user, {
      username: tweet.username.replace(/^@/, ""),
      ts_iso: tweet.created_at_utc_iso,
      id_hint,
      prefix,
    });

    const bodyBase = {
      temperature,
      top_k,
      top_p,
      max_tokens,
      seed,
      presence_penalty,
      frequency_penalty,
      repetition_penalty,
      stop,
      logprobs,
      top_logprobs,
      min_p,
      top_a,
      messages: [
        { role: "system", content: cfg.prompts?.system || "You complete texts exactly and concisely." },
        { role: "user", content: prompt },
      ],
    };

    const headers = {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": OR_HTTP_REFERER,
      "X-Title": OR_X_TITLE,
    };

    const results = await Promise.all(
      models.map(async (model) => {
        const warnings = [];
        try {
          let body = sanitizeForModel(model, { ...bodyBase, model });
          let resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
            method: "POST",
            headers,
            body: JSON.stringify(body),
          });
          let text = await resp.text();
          let parsed = null;
          try { parsed = JSON.parse(text); } catch { /* ignore */ }
          if (!resp.ok && resp.status === 400) {
            // Try to detect unsupported args and retry once without them
            const rawErr = parsed?.error?.metadata?.raw || parsed?.error?.message || text;
            const unsupported = extractUnsupportedParams(String(rawErr));
            if (unsupported.length) {
              for (const k of unsupported) { if (k in body) { delete body[k]; warnings.push(`stripped ${k}`); } }
              resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
                method: "POST",
                headers,
                body: JSON.stringify(body),
              });
              text = await resp.text();
              try { parsed = JSON.parse(text); } catch { parsed = null; }
            }
          }
          if (!resp.ok) {
            return { model, error: `HTTP ${resp.status}: ${text}`, raw: parsed || text, warnings };
          }
          const data = parsed || {};
          const continuation = (data?.choices?.[0]?.message?.content || "").trim();
          return { model, continuation, raw: data, warnings };
        } catch (e) {
          return { model, error: String(e?.message || e), warnings };
        }
      })
    );

    res.json({
      prefix,
      gold,
      tweet,
      params: { models, prefix_len, top_k, temperature, top_p, max_tokens, seed, perturb_meta, presence_penalty, frequency_penalty, repetition_penalty, stop, logprobs, top_logprobs, min_p, top_a },
      results,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: String(err?.message || err) });
  }
});

// Fallback to index.html only for HTML navigations (no dot in path)
app.get("*", (req, res, next) => {
  if (req.path.includes('.')) return res.status(404).end();
  res.sendFile(path.join(__dirname, "web", "index.html"));
});

app.listen(PORT, () => {
  console.log(`UI + proxy running on http://localhost:${PORT}`);
});
