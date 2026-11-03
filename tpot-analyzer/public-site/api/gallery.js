/** GET /api/gallery?cursor=0: bounded page of retained, owned-storage cards. */
const { getKv } = require('./_lib');
const { listGallery } = require('./_galleryPolicy');

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  const kv = getKv();
  if (!kv) return res.status(200).json({ cards: [], nextCursor: null });
  try { return res.status(200).json(await listGallery(kv, req.query?.cursor || '0')); }
  catch (error) {
    const status = error.status || 503;
    if (status >= 500) console.error('[gallery] Read unavailable', { code: error.code || 'gallery_unavailable' });
    return res.status(status).json({ error: error.code || 'gallery_unavailable', cards: [], nextCursor: null });
  }
};
