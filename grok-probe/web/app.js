// UI logic for Grok memorization probe

const q = (s, el = document) => el.querySelector(s);
const qa = (s, el = document) => Array.from(el.querySelectorAll(s));

const state = {
  tweet: null,
  prefixLen: 64,
  historyKey: 'probeHistoryV1',
  history: [],
};

// Initialize fetch adapter with safe preflight to avoid MIME errors
let fetchRandomTweet = null;
await (async function initFetchAdapter() {
  // Preflight: only attempt dynamic import if file exists and is JS
  try {
    const resp = await fetch('./fetchTweet.js', { method: 'HEAD' });
    const ct = resp.headers.get('content-type') || '';
    if (resp.ok && ct.includes('javascript')) {
      const mod = await import('./fetchTweet.js');
      fetchRandomTweet = mod.fetchRandomTweet || mod.getRandomTweet || mod.default || null;
      if (fetchRandomTweet) return; // done
    }
  } catch (_) {
    // ignore; fall through to Supabase fallback
  }

  // Fallback: Supabase UMD client against your project
  if (window.supabase) {
    const supabaseUrl = 'https://fabxmporizzqflnftavs.supabase.co';
    const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8';
    const client = window.supabase.createClient(supabaseUrl, supabaseKey);
    fetchRandomTweet = async function () {
      // Get total count
      const { count } = await client.from('tweets').select('tweet_id', { count: 'exact', head: true });
      const total = count || 0;
      const offset = total > 0 ? Math.floor(Math.random() * total) : 0;
      const { data, error } = await client
        .from('tweets')
        .select('*')
        .range(offset, offset)
        .limit(1);
      if (error) throw error;
      const t = data?.[0];
      if (!t) throw new Error('No tweets available');
      // Fetch username like your helper
      const { data: acc } = await client.from('account').select('*').eq('account_id', t.account_id).limit(1);
      const username = acc?.[0]?.username || 'user';
      return {
        tweet_id: t.tweet_id,
        username,
        created_at_utc_iso: t.created_at,
        full_text: t.full_text,
      };
    };
  }
})();

function setStatus(msg, kind = 'ok') {
  const el = q('#status');
  el.textContent = msg || '';
  el.classList.remove('status-ok','status-warn','status-error');
  el.classList.add(kind === 'error' ? 'status-error' : kind === 'warn' ? 'status-warn' : 'status-ok');
}

function renderTweet() {
  const metaEl = q('#tweetMeta');
  const textEl = q('#tweetText');
  const rawEl = q('#tweetRaw');
  const t = state.tweet;
  if (!t) {
    metaEl.textContent = 'No tweet loaded yet.';
    textEl.textContent = '';
    rawEl.textContent = '';
    return;
  }
  const username = t.username?.startsWith('@') ? t.username : `@${t.username}`;
  metaEl.textContent = `${username} • ${t.created_at_utc_iso || ''} • id: ${t.tweet_id || 'n/a'}`;
  const gold = (t.full_text || '').replace(/\r\n/g, '\n');
  const L = Math.min(state.prefixLen, gold.length);
  const prefix = gold.slice(0, L);
  const suffix = gold.slice(L);
  textEl.innerHTML = `<span class="prefix">${escapeHtml(prefix)}</span><span class="suffix">${escapeHtml(suffix)}</span>`;
  rawEl.textContent = JSON.stringify(t, null, 2);
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
}

// Basic Levenshtein distance
function levenshtein(a, b) {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  const dp = new Array(n + 1);
  for (let j = 0; j <= n; j++) dp[j] = j;
  for (let i = 1; i <= m; i++) {
    let prev = i - 1; // dp[i-1][j-1]
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[j] = Math.min(
        dp[j] + 1,      // deletion
        dp[j - 1] + 1,  // insertion
        prev + cost     // substitution
      );
      prev = tmp;
    }
  }
  return dp[n];
}

function continuationMetrics(prefix, gold, modelOut) {
  const out = (modelOut || '').trim().replace(/^['"“”‘’]+|['"“”‘’]+$/g, '');
  const goldCont = gold.slice(prefix.length);
  const exactContinuation = out === goldCont;
  const fullExact = (prefix + out) === gold;
  const d = levenshtein(goldCont, out);
  const denom = Math.max(goldCont.length, out.length, 1);
  const ratio = 1 - d / denom;
  return { exactContinuation, fullExact, ratio, out };
}

function getSelectedModels() {
  return qa('.model:checked').map(el => el.value);
}

async function runProbe() {
  const models = getSelectedModels();
  if (!models.length) { alert('Select at least one model'); return; }
  if (!state.tweet) { alert('Load a tweet first'); return; }
  const prefix_len = Number(q('#prefixLen').value || 64);
  const top_k = Number(q('#topK').value || 1);
  const top_p = Number(q('#topP').value || 1);
  const max_tokens = Number(q('#maxTokens').value || 200);
  const seed = Number(q('#seed').value || 7);
  const perturb_meta = q('#perturbMeta').checked;
  const presence_penalty = parseFloat(q('#presencePenalty').value);
  const frequency_penalty = parseFloat(q('#frequencyPenalty').value);
  const repetition_penalty = parseFloat(q('#repetitionPenalty').value);
  const stop = (q('#stop').value || '').split(',').map(s => s.replace(/&quot;/g,'"').trim()).filter(Boolean);
  const logprobs = q('#logprobs').checked;
  const top_logprobs = Number(q('#topLogprobs').value || 5);
  const min_p_raw = q('#minP').value;
  const top_a_raw = q('#topA').value;
  const min_p = min_p_raw === '' ? null : Number(min_p_raw);
  const top_a = top_a_raw === '' ? null : Number(top_a_raw);

  setStatus('Running probe…','warn');
  q('#btnProbe').disabled = true;
  try {
    const resp = await fetch('/api/probe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Do not force temperature here; let server/config.json decide
      body: JSON.stringify({
        tweet: state.tweet,
        models,
        prefix_len,
        top_k,
        top_p,
        max_tokens,
        seed,
        perturb_meta,
        presence_penalty,
        frequency_penalty,
        repetition_penalty,
        stop,
        logprobs,
        top_logprobs,
        min_p,
        top_a,
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Probe failed');
    renderResults(data);
    const errors = (data.results || []).filter(r => r.error).length;
    setStatus(errors ? `Done with ${errors} model error(s).` : 'Done.');
  } catch (e) {
    console.error(e);
    setStatus(`Error: ${e.message}`,'error');
  } finally {
    q('#btnProbe').disabled = false;
  }
}

function renderResults(data) {
  const { prefix, gold, results = [] } = data;
  const container = q('#results');
  container.innerHTML = '';
  for (const r of results) {
    const card = document.createElement('div');
    card.className = 'card';
    if (r.error) {
      card.innerHTML = `
        <div class="model">${escapeHtml(r.model)}</div>
        <div class="cont" style="color:#fca5a5;">Error: ${escapeHtml(r.error)}</div>
        <details class="raw"><summary>Raw JSON</summary><pre>${escapeHtml(JSON.stringify(r.raw ?? {}, null, 2))}</pre></details>
      `;
      container.appendChild(card);
      continue;
    }
    const m = continuationMetrics(prefix, gold, r.continuation);
    const warnHtml = Array.isArray(r.warnings) && r.warnings.length ? `<div class="warn">${r.warnings.map(w => escapeHtml(w)).join(', ')}</div>` : '';
    card.innerHTML = `
      <div class="model">${escapeHtml(r.model)}</div>
      <div class="cont">${escapeHtml(m.out)}</div>
      ${warnHtml}
      <div class="metrics">
        <div>exact_continuation: <span class="${m.exactContinuation ? 'metric-ok' : 'metric-bad'}">${m.exactContinuation}</span></div>
        <div>full_exact: <span class="${m.fullExact ? 'metric-ok' : 'metric-bad'}">${m.fullExact}</span></div>
        <div>char_similarity: <span class="${m.ratio > 0.9 ? 'metric-ok' : m.ratio > 0.6 ? 'metric-warn' : 'metric-bad'}">${m.ratio.toFixed(4)}</span></div>
      </div>
      ${renderLogprobs(r.raw)}
      <details class="raw"><summary>Raw JSON</summary><pre>${escapeHtml(JSON.stringify(r.raw ?? {}, null, 2))}</pre></details>
    `;
    container.appendChild(card);
  }
  // Save to history (last 10)
  pushHistory({
    ts: Date.now(),
    tweet: data.tweet,
    prefix: data.prefix,
    gold: data.gold,
    params: data.params,
    results: data.results,
  });
}

async function loadRandomTweet() {
  setStatus('Fetching random tweet…');
  q('#btnProbe').disabled = true;
  try {
    if (typeof fetchRandomTweet === 'function') {
      const t = await fetchRandomTweet();
      // Normalize expected fields
      state.tweet = {
        tweet_id: t.tweet_id || t.id || t.id_str || t.id_hint || 'n/a',
        username: (t.username || t.user?.username || t.user?.screen_name || '').replace(/^@/, ''),
        created_at_utc_iso: t.created_at_utc_iso || t.created_at || t.createdAt || new Date().toISOString(),
        full_text: t.full_text || t.text || t.fullText || '',
      };
    } else {
      // Fallback: prompt user to paste
      const pasted = prompt('No fetchTweet.js found. Paste a tweet text to test.');
      if (!pasted) throw new Error('No tweet provided');
      state.tweet = {
        tweet_id: 'manual',
        username: 'user',
        created_at_utc_iso: new Date().toISOString(),
        full_text: pasted,
      };
    }
    state.prefixLen = Number(q('#prefixLen').value || 64);
    renderTweet();
    q('#btnProbe').disabled = false;
    setStatus('Tweet loaded.');
  } catch (e) {
    console.error(e);
    setStatus(`Error: ${e.message}`);
  }
}

// Wire controls
q('#btnFetch').addEventListener('click', loadRandomTweet);
q('#btnProbe').addEventListener('click', runProbe);
q('#prefixLen').addEventListener('change', (e) => {
  state.prefixLen = Number(e.target.value || 64);
  renderTweet();
});

// Presets
q('#preset').addEventListener('change', (e) => {
  const v = e.target.value;
  const set = (id, val) => (q(id).value = String(val));
  const setBool = (id, val) => (q(id).checked = !!val);
  if (v === 'strict') {
    set('#prefixLen', 64); set('#topK', 1); set('#topP', 1); setBool('#perturbMeta', false);
  } else if (v === 'long') {
    set('#prefixLen', 128); set('#topK', 1); set('#topP', 1); setBool('#perturbMeta', false);
  } else if (v === 'broader') {
    set('#prefixLen', 64); set('#topK', 2); set('#topP', 1); setBool('#perturbMeta', false);
  } else if (v === 'noisy') {
    set('#prefixLen', 64); set('#topK', 5); set('#topP', 1); setBool('#perturbMeta', false);
  } else if (v === 'perturbed') {
    set('#prefixLen', 64); set('#topK', 1); set('#topP', 1); setBool('#perturbMeta', true);
  }
  // Trigger re-highlight
  state.prefixLen = Number(q('#prefixLen').value || 64);
  renderTweet();
});

// History management
function loadHistory() {
  try {
    const raw = localStorage.getItem(state.historyKey);
    state.history = raw ? JSON.parse(raw) : [];
  } catch { state.history = []; }
  renderHistory();
}

function pushHistory(item) {
  loadHistory();
  state.history.unshift(item);
  state.history = state.history.slice(0, 10);
  localStorage.setItem(state.historyKey, JSON.stringify(state.history));
  renderHistory();
}

function renderHistory() {
  const box = q('#history');
  if (!box) return;
  box.innerHTML = '';
  for (const h of state.history) {
    const d = new Date(h.ts);
    const el = document.createElement('div');
    el.className = 'hist-item';
    el.innerHTML = `
      <div class="hist-head">
        <div>${escapeHtml(h.tweet?.username || 'user')} · ${escapeHtml(h.tweet?.tweet_id || '')}</div>
        <div>${d.toLocaleString()}</div>
      </div>
      <div class="hist-actions">
        <button class="view">View</button>
        <button class="rerun">Re-run</button>
      </div>
    `;
    el.querySelector('.view').addEventListener('click', () => {
      state.tweet = h.tweet; state.prefixLen = h.prefix.length; renderTweet();
      renderResults(h); // reuse rendering from saved data
      setStatus('Loaded from history.');
    });
    el.querySelector('.rerun').addEventListener('click', async () => {
      state.tweet = h.tweet; state.prefixLen = h.prefix.length; renderTweet();
      // set params in UI to match
      q('#prefixLen').value = String(h.params.prefix_len);
      q('#topK').value = String(h.params.top_k);
      q('#topP').value = String(h.params.top_p);
      q('#maxTokens').value = String(h.params.max_tokens);
      q('#seed').value = String(h.params.seed);
      q('#perturbMeta').checked = !!h.params.perturb_meta;
      if ('presence_penalty' in h.params) q('#presencePenalty').value = String(h.params.presence_penalty);
      if ('frequency_penalty' in h.params) q('#frequencyPenalty').value = String(h.params.frequency_penalty);
      if ('repetition_penalty' in h.params) q('#repetitionPenalty').value = String(h.params.repetition_penalty);
      if (Array.isArray(h.params.stop)) q('#stop').value = h.params.stop.map(s => s === '"' ? '&quot;' : s).join(', ');
      if ('logprobs' in h.params) q('#logprobs').checked = !!h.params.logprobs;
      if ('top_logprobs' in h.params && h.params.top_logprobs != null) q('#topLogprobs').value = String(h.params.top_logprobs);
      if ('min_p' in h.params && h.params.min_p != null) q('#minP').value = String(h.params.min_p);
      if ('top_a' in h.params && h.params.top_a != null) q('#topA').value = String(h.params.top_a);
      await runProbe();
    });
    box.appendChild(el);
  }
}

// Initial render
renderTweet();
loadHistory();

function renderLogprobs(raw) {
  try {
    const items = raw?.choices?.[0]?.logprobs?.content;
    if (!Array.isArray(items) || !items.length) return '';
    const rows = items.map((tok) => {
      const token = tok?.token ?? '';
      const lp = typeof tok?.logprob === 'number' ? tok.logprob : null;
      const prob = lp != null ? Math.exp(lp) : null;
      const tops = (tok?.top_logprobs || []).slice(0, 5).map(t => `${escapeHtml(t.token ?? '')} (${fmtProb(t.logprob)})`).join(', ');
      return `<div><code>${escapeHtml(token)}</code> · lp=${lp != null ? lp.toFixed(3) : 'n/a'} · p=${prob != null ? prob.toFixed(3) : 'n/a'}${tops ? ` · top: ${tops}` : ''}</div>`;
    }).join('');
    return `<details class="raw"><summary>Token Logprobs</summary><div class="logprobs">${rows}</div></details>`;
  } catch {
    return '';
  }
}

function fmtProb(lp) {
  if (typeof lp !== 'number') return 'n/a';
  const p = Math.exp(lp);
  return p.toFixed(3);
}
