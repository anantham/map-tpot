const { randomUUID } = require('node:crypto');
const { normalizeHandle, ownedCardUrl } = require('./_imagePolicy');
const scripts = require('./_galleryScripts');

const LIMITS = Object.freeze({ handles: 500, versions: 3, days: 90, daily: 100, handleDaily: 5, lifetime: 1500, concurrent: 2, reservationSeconds: 180 });

class GalleryPolicyError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

async function evaluate(kv, script, keys, args) {
  if (!kv || typeof kv.eval !== 'function') throw new GalleryPolicyError(503, 'gallery_storage_unavailable');
  try { return await kv.eval(script, keys, args.map(String)); }
  catch { throw new GalleryPolicyError(503, 'gallery_storage_unavailable'); }
}

function checked(result) {
  if (Array.isArray(result) && Number(result[0]) === 1) return result;
  const code = result?.[1] || 'gallery_storage_unavailable';
  const status = code === 'gallery_owner_mismatch' ? 403 :
    code === 'gallery_capability_replayed' ? 409 :
    code === 'gallery_migration_required' ? 409 :
    ['gallery_busy', 'gallery_capacity', 'gallery_quota'].includes(code) ? 429 : 503;
  throw new GalleryPolicyError(status, code);
}

function normalizeCommunities(value = []) {
  if (!Array.isArray(value) || value.length > 5) throw new GalleryPolicyError(400, 'invalid_communities');
  return value.map((entry) => {
    if (!entry || typeof entry.name !== 'string' || entry.name.length < 1 || entry.name.length > 80 ||
        typeof entry.color !== 'string' || !/^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(entry.color) ||
        typeof entry.weight !== 'number' || !Number.isFinite(entry.weight) || Math.abs(entry.weight) > 1e6)
      throw new GalleryPolicyError(400, 'invalid_communities');
    return { name: entry.name, color: entry.color, weight: entry.weight };
  });
}

async function reservePublication(kv, { handle, grant, trusted = false }) {
  const owner = normalizeHandle(handle);
  if (!grant || grant.handle !== owner || typeof grant.subject !== 'string' || !grant.subject.length ||
      grant.subject.length > 128 || !/^[a-zA-Z0-9_-]{16,128}$/.test(grant.jti) ||
      !Number.isSafeInteger(grant.expiresAt) || (trusted ? grant.kind !== 'generate' : grant.kind !== 'gallery'))
    throw new GalleryPolicyError(403, 'invalid_gallery_grant');
  const now = Math.floor(Date.now() / 1000);
  if (grant.expiresAt <= now) throw new GalleryPolicyError(403, 'expired_gallery_grant');
  const id = randomUUID();
  const day = new Date(now * 1000).toISOString().slice(0, 10);
  const reservation = { id, handle: owner, subject: grant.subject, deadline: now + LIMITS.reservationSeconds };
  checked(await evaluate(kv, scripts.RESERVE, [
    'gallery', 'gallery:active', `gallery:daily:${day}`, `gallery:daily:${day}:${owner}`,
    `gallery:used:${grant.kind}:${grant.jti}`, `gallery:reservation:${id}`, 'gallery:lifetime-uploads', 'gallery:published',
  ], [now, reservation.deadline, owner, grant.subject, trusted ? 1 : 0, LIMITS.concurrent,
    LIMITS.handles, LIMITS.daily, LIMITS.handleDaily, LIMITS.lifetime,
    Math.max(1, grant.expiresAt - now + LIMITS.reservationSeconds), JSON.stringify(reservation), LIMITS.reservationSeconds, id]));
  return reservation;
}

async function storePublication(kv, reservation, entry) {
  if (!reservation || !ownedCardUrl(entry?.url, reservation.handle) || !Number.isSafeInteger(entry.bytes) ||
      entry.bytes < 1 || entry.bytes > 4 * 1024 * 1024) throw new GalleryPolicyError(400, 'invalid_gallery_image');
  const now = Date.now();
  const record = { schema: 2, owner: reservation.subject, url: entry.url, bytes: entry.bytes,
    generatedAt: now, expiresAt: now + LIMITS.days * 86400000, communities: normalizeCommunities(entry.communities) };
  const result = checked(await evaluate(kv, scripts.STORE,
    ['gallery', `gallery:reservation:${reservation.id}`, 'gallery:active', 'gallery:published'],
    [reservation.id, reservation.handle, reservation.subject, Math.floor(now / 1000), JSON.stringify(record), LIMITS.versions]));
  return { record, supersededUrls: JSON.parse(result[1] || '[]') };
}

async function releasePublication(kv, reservation) {
  if (!reservation) return;
  await evaluate(kv, scripts.RELEASE, [`gallery:reservation:${reservation.id}`, 'gallery:active'], [reservation.id]);
  // Daily/lifetime quotas and single-use nonce remain consumed after a failed upload.
}

function publicVersions(raw, handle, now = Date.now()) {
  if (typeof raw !== 'string' || raw.length > 32768) return [];
  try {
    const parsed = JSON.parse(raw);
    const versions = Array.isArray(parsed) ? parsed : [parsed];
    return versions.filter((entry) => entry && entry.schema === 2 && ownedCardUrl(entry.url, handle) &&
      Number.isSafeInteger(entry.generatedAt) && entry.generatedAt > now - LIMITS.days * 86400000 &&
      entry.generatedAt <= now && (entry.expiresAt === undefined || entry.expiresAt > now))
      .slice(-LIMITS.versions).map((entry) => ({ url: entry.url, generatedAt: entry.generatedAt,
        communities: normalizeCommunities(entry.communities || []) }));
  } catch { return []; }
}

async function listGallery(kv, cursor = '0') {
  if (typeof cursor !== 'string' || !/^\d{1,20}$/.test(cursor)) throw new GalleryPolicyError(400, 'invalid_cursor');
  const result = await evaluate(kv, scripts.LIST, ['gallery', 'gallery:published'], [cursor, LIMITS.handles]);
  if (!Array.isArray(result) || !Array.isArray(result[1])) throw new GalleryPolicyError(503, 'gallery_storage_unavailable');
  const cards = [];
  for (let i = 0; i < result[1].length && cards.length < 50; i += 2) {
    const handle = result[1][i];
    const versions = publicVersions(result[1][i + 1], handle);
    if (!versions.length) continue;
    const latest = versions[versions.length - 1];
    cards.push({ handle, ...latest, versions: versions.map(({ url, generatedAt }) => ({ url, generatedAt })) });
  }
  cards.sort((a, b) => b.generatedAt - a.generatedAt);
  return { cards, nextCursor: result[0] === '0' ? null : String(result[0]) };
}

async function readGallery(kv, handle) {
  const owner = normalizeHandle(handle);
  const raw = await evaluate(kv, scripts.READ, ['gallery'], [owner]);
  return publicVersions(raw, owner);
}

module.exports = { GalleryPolicyError, LIMITS, normalizeCommunities, reservePublication,
  storePublication, releasePublication, publicVersions, listGallery, readGallery };
