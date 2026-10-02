const { AdmissionError } = require('./_cardAdmission');
function invalid() { throw new AdmissionError(400, 'validation_error', 'Invalid card request'); }
function text(value, max, optional = false) {
  if (optional && (value === undefined || value === null)) return;
  if (typeof value !== 'string' || value.length > max || (!optional && !value.length)) invalid();
}
function validateCardRequest(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) invalid();
  if (Object.keys(body).some(k => !['handle','bio','communities','tweets','force'].includes(k))) invalid();
  if (Buffer.byteLength(JSON.stringify(body)) > 16000) throw new AdmissionError(413,'request_too_large');
  if (typeof body.handle !== 'string' || !/^[A-Za-z0-9_]{1,15}$/.test(body.handle)) invalid();
  text(body.bio, 2000, true);
  if (body.force !== undefined && typeof body.force !== 'boolean') invalid();
  if (!Array.isArray(body.communities) || body.communities.length < 1 || body.communities.length > 15) invalid();
  for (const c of body.communities) {
    if (!c || typeof c !== 'object' || Array.isArray(c) ||
        Object.keys(c).some(k => !['name','color','weight','short_name','description'].includes(k))) invalid();
    text(c.name, 80); text(c.short_name, 50, true); text(c.description, 500, true);
    if (typeof c.color !== 'string' || !/^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(c.color) ||
        !Number.isFinite(c.weight) || Math.abs(c.weight) > 1000000) invalid();
  }
  if (body.tweets !== undefined) {
    if (!Array.isArray(body.tweets) || body.tweets.length > 5) invalid();
    body.tweets.forEach(t => text(t, 1000, true));
  }
  return {...body, handle:body.handle.toLowerCase()};
}
module.exports = { validateCardRequest };
