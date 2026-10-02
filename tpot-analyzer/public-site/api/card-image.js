/** GET /api/card-image?handle=xxx: redirect only to a retained owned raster object. */
const { getKv } = require('./_lib');
const { normalizeHandle } = require('./_imagePolicy');
const { readGallery } = require('./_galleryPolicy');

module.exports = async function handler(req, res) {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  try {
    const handle = normalizeHandle(req.query?.handle);
    const kv = getKv();
    if (!kv) return res.status(404).json({ error: 'No image available' });
    const versions = await readGallery(kv, handle);
    const image = versions[versions.length - 1];
    if (!image) return res.status(404).json({ error: 'No retained card for this handle' });
    res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=60');
    return res.redirect(302, image.url);
  } catch (error) {
    if ((error.status || 503) >= 500) console.error('[card-image] Read unavailable', { code: error.code || 'image_unavailable' });
    return res.status(error.status || 503).json({ error: error.code || 'image_unavailable' });
  }
};
