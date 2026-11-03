/** Public reads use the same ownership and retention checks as paid generation. */
const {ownedCardUrl} = require('./_imagePolicy');
const {readGallery} = require('./_galleryPolicy');
async function readCachedCard(kv,handle) {
  const raw=await kv.get(`card:${handle}`);
  let cached;
  try {cached=typeof raw==='string' && raw.length<1024 ? JSON.parse(raw) : null;} catch {}
  if (cached?.schema===2 && cached.expiresAt>Date.now() && ownedCardUrl(cached.url,handle)) return cached.url;
  const versions=await readGallery(kv,handle);
  return versions[versions.length-1]?.url || null;
}
module.exports={readCachedCard};
