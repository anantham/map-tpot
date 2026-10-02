/** Signed single-use publication of a BYOK raster card to owned storage. */
const { getKv, getBlobPut } = require('./_lib');
const { digestBody, requestCapability } = require('./_cardAdmission');
const { normalizeHandle, assertImageInfrastructure, uploadRawCard, MAX_INPUT_BYTES } = require('./_imagePolicy');
const { normalizeCommunities, reservePublication, storePublication, releasePublication } = require('./_galleryPolicy');

module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const kv = getKv();
  let reservation;
  try {
    const body = req.body;
    if (!body || typeof body !== 'object' || Array.isArray(body) ||
        Object.keys(body).some(key => !['handle', 'imageUrl', 'communities'].includes(key)) ||
        typeof body.imageUrl !== 'string' || !body.imageUrl.length)
      return res.status(400).json({ error: 'invalid_gallery_request' });
    const handle = normalizeHandle(body.handle);
    const communities = normalizeCommunities(body.communities === undefined ? [] : body.communities);
    if (body.imageUrl.length > Math.ceil(MAX_INPUT_BYTES / 3) * 4 + 64)
      return res.status(413).json({ error: 'image_too_large' });
    const grant = requestCapability(req, { kind: 'gallery', handle, digest: digestBody(body) });
    if (!body.imageUrl.startsWith('data:image/')) return res.status(400).json({ error: 'invalid_image' });
    const blobPut = getBlobPut();
    assertImageInfrastructure(blobPut);
    reservation = await reservePublication(kv, { handle, grant });
    const image = await uploadRawCard(blobPut, { handle, imageUrl: body.imageUrl });
    const saved = await storePublication(kv, reservation, { ...image, communities });
    reservation = null;
    if (saved.supersededUrls.length) console.info('[gallery-submit] Superseded objects require retention cleanup', { count: saved.supersededUrls.length });
    return res.status(200).json({ ok: true, stored: true, imageUrl: image.url });
  } catch (error) {
    const status = Number.isInteger(error.status) ? error.status : 503;
    if (status >= 500) console.error('[gallery-submit] Publication unavailable', { code: error.code || 'publication_failed' });
    return res.status(status).json({ error: error.code || 'publication_failed' });
  } finally {
    if (reservation) {
      try { await releasePublication(kv, reservation); }
      catch { console.error('[gallery-submit] Reservation release failed; expiry will clear it'); }
    }
  }
};
