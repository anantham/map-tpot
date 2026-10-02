const { randomUUID } = require('node:crypto');

const MAX_INPUT_BYTES = 3 * 1024 * 1024;
const MAX_OUTPUT_BYTES = 4 * 1024 * 1024;
const MAX_DIMENSION = 2048;
const MAX_PIXELS = MAX_DIMENSION * MAX_DIMENSION;

class ImagePolicyError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

function normalizeHandle(value) {
  if (typeof value !== 'string') throw new ImagePolicyError(400, 'invalid_handle');
  const handle = value.replace(/^@/, '').trim().toLowerCase();
  if (!/^[a-z0-9_]{1,15}$/.test(handle)) throw new ImagePolicyError(400, 'invalid_handle');
  return handle;
}

function blobOrigin() {
  try {
    const configured = process.env.CARD_BLOB_BASE_URL;
    const parsed = new URL(configured);
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port ||
        parsed.pathname !== '/' || parsed.search || parsed.hash ||
        !/^[a-z0-9]+\.public\.blob\.vercel-storage\.com$/.test(parsed.hostname)) throw new Error();
    return parsed.origin;
  } catch { throw new ImagePolicyError(503, 'card_storage_not_configured'); }
}

function ownedCardUrl(value, handle) {
  if (typeof value !== 'string' || value.length > 512) return false;
  try {
    const owner = normalizeHandle(handle);
    const parsed = new URL(value);
    if (parsed.origin !== blobOrigin() || parsed.username || parsed.password || parsed.port ||
        parsed.search || parsed.hash || value !== parsed.href) return false;
    // Reject encoded separators, dot segments, arbitrary storage objects and active formats.
    return new RegExp(`^/cards/${owner}-[a-zA-Z0-9-]{1,100}\\.(png|jpg|jpeg|webp)$`).test(parsed.pathname);
  } catch { return false; }
}

function decodeDataUrl(value) {
  if (typeof value !== 'string' || value.length > Math.ceil(MAX_INPUT_BYTES / 3) * 4 + 64)
    throw new ImagePolicyError(413, 'image_too_large');
  const match = /^data:image\/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/]+={0,2})$/.exec(value);
  if (!match || match[2].length % 4 !== 0) throw new ImagePolicyError(400, 'invalid_image');
  const buffer = Buffer.from(match[2], 'base64');
  if (buffer.length > MAX_INPUT_BYTES) throw new ImagePolicyError(413, 'image_too_large');
  if (!buffer.length || buffer.toString('base64') !== match[2])
    throw new ImagePolicyError(400, 'invalid_image');
  const declaredFormat = match[1] === 'jpg' ? 'jpeg' : match[1];
  const rasterSignature = declaredFormat === 'png' ? buffer.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) :
    declaredFormat === 'jpeg' ? buffer.subarray(0, 3).equals(Buffer.from([255,216,255])) :
      buffer.subarray(0, 4).toString('ascii') === 'RIFF' && buffer.subarray(8, 12).toString('ascii') === 'WEBP';
  // Keep active/vector formats out of the decoder, even when labelled as PNG.
  if (!rasterSignature) throw new ImagePolicyError(400, 'invalid_image');
  return { buffer, declaredFormat };
}

async function normalizeImage(value) {
  const { buffer, declaredFormat } = decodeDataUrl(value);
  const sharp = assertImageInfrastructure();
  try {
    const decoder = sharp(buffer, { failOn: 'warning', limitInputPixels: MAX_PIXELS, sequentialRead: true });
    const metadata = await decoder.metadata();
    if (metadata.format !== declaredFormat || !['png', 'jpeg', 'webp'].includes(metadata.format) ||
        !metadata.width || !metadata.height || metadata.width > MAX_DIMENSION ||
        metadata.height > MAX_DIMENSION || (metadata.pages || 1) !== 1)
      throw new ImagePolicyError(400, 'invalid_image');
    // Fully decode pixels and emit a new PNG. Sharp strips source metadata by default.
    const output = await decoder.rotate().png().timeout({ seconds: 5 }).toBuffer();
    if (output.length > MAX_OUTPUT_BYTES) throw new ImagePolicyError(413, 'image_too_large');
    return { buffer: output, contentType: 'image/png', bytes: output.length };
  } catch (error) {
    if (error instanceof ImagePolicyError) throw error;
    throw new ImagePolicyError(400, 'invalid_image');
  }
}

function assertImageInfrastructure(blobPut) {
  blobOrigin();
  if (blobPut !== undefined && typeof blobPut !== 'function')
    throw new ImagePolicyError(503, 'card_storage_unavailable');
  try { return require('sharp'); }
  catch { throw new ImagePolicyError(503, 'image_decoder_unavailable'); }
}

async function uploadRawCard(blobPut, { handle, imageUrl }) {
  const owner = normalizeHandle(handle);
  blobOrigin();
  if (typeof blobPut !== 'function') throw new ImagePolicyError(503, 'card_storage_unavailable');
  const image = await normalizeImage(imageUrl);
  const stored = await blobPut(`cards/${owner}-${randomUUID()}.png`, image.buffer, {
    access: 'public', contentType: image.contentType, addRandomSuffix: false,
  });
  if (!ownedCardUrl(stored?.url, owner)) throw new ImagePolicyError(503, 'unexpected_storage_url');
  return { url: stored.url, bytes: image.bytes };
}

module.exports = {
  ImagePolicyError, normalizeHandle, blobOrigin, ownedCardUrl, normalizeImage,
  uploadRawCard, assertImageInfrastructure, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES,
};
