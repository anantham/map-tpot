const { createHash, createHmac, timingSafeEqual, randomUUID } = require('node:crypto');

class AdmissionError extends Error {
  constructor(status, code, message = code) { super(message); this.status = status; this.code = code; }
}
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  }
  return value;
}
function digestBody(body) {
  return createHash('sha256').update(JSON.stringify(canonical(body))).digest('hex');
}
function signingKey() {
  const key = process.env.CARD_CAPABILITY_SECRET;
  if (!key || Buffer.byteLength(key) < 32) throw new AdmissionError(503, 'authorization_unavailable');
  return key;
}
function verifyCapability(token, { kind, handle, digest }) {
  if (typeof token !== 'string' || token.length > 4096) throw new AdmissionError(403, 'authorization_required');
  const parts = token.split('.');
  if (parts.length !== 2 || !parts.every(p => /^[A-Za-z0-9_-]+$/.test(p))) {
    throw new AdmissionError(403, 'invalid_grant');
  }
  const signature = createHmac('sha256', signingKey()).update(parts[0]).digest();
  const supplied = Buffer.from(parts[1], 'base64url');
  if (supplied.length !== signature.length || !timingSafeEqual(signature, supplied)) {
    throw new AdmissionError(403, 'invalid_grant');
  }
  let grant;
  try { grant = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8')); }
  catch { throw new AdmissionError(403, 'invalid_grant'); }
  const now = Math.floor(Date.now() / 1000);
  if (grant.v !== 1 || grant.kind !== kind || grant.handle !== handle || grant.digest !== digest ||
      typeof grant.jti !== 'string' || !/^[A-Za-z0-9_-]{16,128}$/.test(grant.jti) ||
      typeof grant.subject !== 'string' || !/^[A-Za-z0-9:_-]{1,128}$/.test(grant.subject) ||
      !Number.isSafeInteger(grant.expiresAt) || grant.expiresAt <= now || grant.expiresAt > now + 600 ||
      typeof grant.force !== 'boolean') throw new AdmissionError(403, 'invalid_grant');
  return grant;
}
function requestCapability(req, expected) {
  const header = req.headers?.authorization || req.headers?.Authorization;
  const token = typeof header === 'string' && header.startsWith('Bearer ') ? header.slice(7) : null;
  return verifyCapability(token, expected);
}
function signCapability(payload) {
  // Offline operator helper. Never exposed through an anonymous HTTP issuer.
  const encoded = Buffer.from(JSON.stringify({v:1, jti:randomUUID(), force:false, ...payload})).toString('base64url');
  return `${encoded}.${createHmac('sha256', signingKey()).update(encoded).digest('base64url')}`;
}
module.exports = { AdmissionError, digestBody, verifyCapability, requestCapability, signCapability };
