// Short-lived grants stay in this tab's memory and are never placed in a URL.
const grants = new Map();
export function setCardCapability(token) {
  if (typeof token !== 'string' || token.length > 4096) throw new Error('Invalid card grant');
  let grant;
  try {
    const encoded = token.split('.')[0].replace(/-/g,'+').replace(/_/g,'/');
    grant = JSON.parse(atob(encoded));
  } catch { throw new Error('Invalid card grant'); }
  if (!['generate','gallery'].includes(grant.kind) || !/^[a-z0-9_]{1,15}$/.test(grant.handle) ||
      !Number.isSafeInteger(grant.expiresAt) || grant.expiresAt * 1000 <= Date.now() ||
      grant.expiresAt * 1000 > Date.now()+600000) throw new Error('Invalid or expired card grant');
  // This parse only chooses the outgoing request; server verifies signature and content.
  grants.set(`${grant.kind}:${grant.handle}`,{token,expiresAt:grant.expiresAt});
  window.dispatchEvent(new CustomEvent('card-capability-added',{detail:{kind:grant.kind,handle:grant.handle}}));
  return grant.handle;
}
export function getCardCapability(handle,kind) {
  const key = `${kind}:${handle.toLowerCase()}`;
  const grant = grants.get(key);
  if (!grant || grant.expiresAt*1000 <= Date.now()) {grants.delete(key);return null;}
  return grant.token;
}
