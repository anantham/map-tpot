const { randomUUID } = require('node:crypto');
const { AdmissionError } = require('./_cardAdmission');
const PREFIX = 'card:{admission}:';
const LEASE_MS = 180000;
// All keys share a Redis Cluster hash slot. No write occurs until every gate passes.
const RESERVE = `-- card-budget-reserve-v1
local budget = tonumber(redis.call('GET', KEYS[1]) or '0')
if not budget or budget < 0 then return {'quota_invalid'} end
if redis.call('EXISTS', KEYS[2]) == 1 then return {'in_progress'} end
if redis.call('EXISTS', KEYS[4]) == 1 then return {'grant_replayed'} end
local now = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now)
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[4]) then return {'concurrency_limited'} end
if budget + tonumber(ARGV[2]) > tonumber(ARGV[3]) then return {'budget_exhausted'} end
local locked = redis.call('SET', KEYS[2], ARGV[5], 'PX', ARGV[6], 'NX')
if not locked then return {'in_progress'} end
redis.call('SET', KEYS[4], ARGV[5], 'EX', ARGV[7])
redis.call('INCRBY', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], 172800)
redis.call('ZADD', KEYS[3], now + tonumber(ARGV[6]), ARGV[5])
redis.call('PEXPIRE', KEYS[3], tonumber(ARGV[6]) * 2)
return {'ok', tostring(budget + tonumber(ARGV[2]))}`;
const RELEASE = `-- card-budget-release-v1
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[1])
return 1`;
function money(raw, fallback) {
  const value = raw === undefined ? fallback : Number(raw);
  const micros = Math.ceil(value * 1000000);
  if (!Number.isFinite(value) || value <= 0 || !Number.isSafeInteger(micros) || micros > 1000000000) {
    throw new AdmissionError(503, 'quota_config_error');
  }
  return micros;
}
function budgetConfig() {
  if (process.env.CARD_SPONSORED_ENABLED !== 'true') throw new AdmissionError(503, 'sponsored_disabled');
  const daily = money(process.env.CARD_DAILY_BUDGET, 5);
  const reservation = money(process.env.CARD_REQUEST_RESERVATION_USD, 0.5);
  if (reservation < 500000 || reservation > daily) throw new AdmissionError(503, 'quota_config_error');
  const concurrency = Number(process.env.CARD_MAX_CONCURRENCY || 2);
  if (!Number.isSafeInteger(concurrency) || concurrency < 1 || concurrency > 4) {
    throw new AdmissionError(503, 'quota_config_error');
  }
  return { daily, reservation, concurrency };
}
async function reserveGeneration(kv, {handle, grant}) {
  if (!kv || typeof kv.eval !== 'function') throw new AdmissionError(503, 'quota_unavailable');
  const config = budgetConfig();
  const now = Date.now();
  const id = randomUUID();
  const keys = [PREFIX + 'budget:' + new Date(now).toISOString().slice(0, 10),
    PREFIX + 'lock:' + handle, PREFIX + 'active', PREFIX + 'nonce:' + grant.jti];
  let result;
  try {
    result = await kv.eval(RESERVE, keys, [now, config.reservation, config.daily, config.concurrency,
      id, LEASE_MS, Math.max(1, grant.expiresAt - Math.floor(now / 1000) + 60)].map(String));
  } catch { throw new AdmissionError(503, 'quota_unavailable'); }
  const code = Array.isArray(result) && result[0];
  if (code !== 'ok') {
    const status = code === 'in_progress' ? 202 : code === 'grant_replayed' ? 403 :
      ['concurrency_limited','budget_exhausted'].includes(code) ? 429 : 503;
    throw new AdmissionError(status, typeof code === 'string' ? code : 'quota_unavailable');
  }
  return { id, keys, reservedMicros:config.reservation };
}
async function releaseGeneration(kv, reservation) {
  // Budget and nonce are never refunded: failures and uncertain provider billing remain reserved.
  return kv.eval(RELEASE, [reservation.keys[1], reservation.keys[2]], [reservation.id]);
}
module.exports = { reserveGeneration, releaseGeneration, budgetConfig, RESERVE, RELEASE };
