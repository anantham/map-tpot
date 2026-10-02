const CARD_CACHE_KEY = "ingroup_card_cache";
const GEN_COUNT_KEY = "ingroup_gen_count";
function localRaster(url) {
  return typeof url==='string' && url.length<=6*1024*1024 && /^data:image\/(png|jpe?g|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(url);
}
function currentUrl(url,handle) {
  if (localRaster(url)) return true;
  try {
    const parsed=new URL(url);
    return parsed.protocol==='https:' && !parsed.username && !parsed.password && !parsed.port && !parsed.search && !parsed.hash &&
      /^[a-z0-9]+\.public\.blob\.vercel-storage\.com$/.test(parsed.hostname) &&
      new RegExp(`^/cards/${handle}-[a-zA-Z0-9-]{1,100}\\.(png|jpe?g|webp)$`).test(parsed.pathname);
  } catch {return false;}
}
// --- Card image cache ---

function getCardCache() {
  try {
    const raw=JSON.parse(localStorage.getItem(CARD_CACHE_KEY) || '{}');
    const cache=Object.create(null);
    for (const [handle,entry] of Object.entries(raw)) {
      if (!/^[a-z0-9_]{1,15}$/.test(handle) || !entry) continue;
      // Prior galleries accepted arbitrary remote URLs. Preserve only local BYOK
      // pixels from that format; schema2 remote entries originate in checked APIs.
      const valid=url=>entry.schema===2 ? currentUrl(url,handle) : localRaster(url);
      const versions=(Array.isArray(entry.versions) ? entry.versions : [entry]).filter(item=>item && valid(item.url)).slice(-10);
      if (!versions.length) continue;
      const latest=versions[versions.length-1];
      cache[handle]={schema:2,url:latest.url,cachedAt:latest.cachedAt,versions};
    }
    return cache;
  } catch { return Object.create(null); }
}

export function getCachedCard(handle) {
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

export function cacheCard(handle, imageUrl) {
  if (!/^[a-z0-9_]{1,15}$/i.test(handle) || !currentUrl(imageUrl,handle.toLowerCase())) return;
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
      schema:2,
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
        keep[handle.toLowerCase()] = { schema:2,url: imageUrl, cachedAt: Date.now(), versions: [{ url: imageUrl, cachedAt: Date.now() }] };
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

export function clearCachedCard(handle) {
  try {
    const cache = getCardCache();
    delete cache[handle.toLowerCase()];
    localStorage.setItem(CARD_CACHE_KEY, JSON.stringify(cache));
  } catch {}
}

export function getGenCount() {
  try { return parseInt(localStorage.getItem(GEN_COUNT_KEY) || '0', 10); } catch { return 0; }
}

export function incrementGenCount() {
  try {
    const count = getGenCount() + 1;
    localStorage.setItem(GEN_COUNT_KEY, String(count));
    return count;
  } catch { return 0; }
}
