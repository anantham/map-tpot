// All quota, nonce and version mutations run as one Redis operation.
const RESERVE = `
local now = tonumber(ARGV[1])
local deadline = tonumber(ARGV[2])
local handle = ARGV[3]
local subject = ARGV[4]
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[6]) then return {0, 'gallery_busy'} end
local old = redis.call('HGET', KEYS[1], handle)
if old then
  if string.len(old) > 32768 then return {0, 'gallery_migration_required'} end
  local ok, versions = pcall(cjson.decode, old)
  if not ok or type(versions) ~= 'table' then return {0, 'gallery_migration_required'} end
  local latest = versions[#versions]
  if not latest or latest.schema ~= 2 or type(latest.owner) ~= 'string' then
    return {0, 'gallery_migration_required'}
  end
  if latest.owner ~= subject then return {0, 'gallery_owner_mismatch'} end
else
  if redis.call('HLEN', KEYS[1]) + redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[7]) then
    return {0, 'gallery_capacity'}
  end
end
if tonumber(redis.call('GET', KEYS[3]) or '0') >= tonumber(ARGV[8]) or
   tonumber(redis.call('GET', KEYS[4]) or '0') >= tonumber(ARGV[9]) or
   tonumber(redis.call('GET', KEYS[7]) or '0') >= tonumber(ARGV[10]) then
  return {0, 'gallery_quota'}
end
if not redis.call('SET', KEYS[5], 'used', 'NX', 'EX', ARGV[11]) then
  return {0, 'gallery_capability_replayed'}
end
redis.call('INCR', KEYS[3]); redis.call('EXPIRE', KEYS[3], 172800)
redis.call('INCR', KEYS[4]); redis.call('EXPIRE', KEYS[4], 172800)
redis.call('INCR', KEYS[7])
redis.call('SET', KEYS[6], ARGV[12], 'EX', ARGV[13])
redis.call('ZADD', KEYS[2], deadline, ARGV[14])
return {1}
`;

const STORE = `
local raw = redis.call('GET', KEYS[2])
if not raw then return {0, 'gallery_reservation_expired'} end
local reservation = cjson.decode(raw)
if reservation.id ~= ARGV[1] or reservation.handle ~= ARGV[2] or reservation.subject ~= ARGV[3] then
  return {0, 'gallery_reservation_mismatch'}
end
local now = tonumber(ARGV[4])
if reservation.deadline <= now then return {0, 'gallery_reservation_expired'} end
local old = redis.call('HGET', KEYS[1], ARGV[2])
local versions = {}
if old then
  if string.len(old) > 32768 then return {0, 'gallery_migration_required'} end
  local ok, parsed = pcall(cjson.decode, old)
  if not ok or type(parsed) ~= 'table' then return {0, 'gallery_migration_required'} end
  for _, entry in ipairs(parsed) do
    if entry.schema == 2 and entry.owner == ARGV[3] and type(entry.expiresAt) == 'number' and entry.expiresAt > now * 1000 then
      table.insert(versions, entry)
    end
  end
  if parsed[#parsed] and parsed[#parsed].owner ~= ARGV[3] then return {0, 'gallery_owner_mismatch'} end
end
local incoming = cjson.decode(ARGV[5])
-- Redis cjson re-encodes an empty JSON array as {}; omit optional empty metadata.
if type(incoming.communities) == 'table' and next(incoming.communities) == nil then incoming.communities = nil end
table.insert(versions, incoming)
local removed = {}
while #versions > tonumber(ARGV[6]) do table.insert(removed, table.remove(versions, 1).url) end
redis.call('HSET', KEYS[1], ARGV[2], cjson.encode(versions))
redis.call('ZADD', KEYS[4], now, ARGV[2])
redis.call('DEL', KEYS[2])
redis.call('ZREM', KEYS[3], ARGV[1])
return {1, #removed == 0 and '[]' or cjson.encode(removed)}
`;

const RELEASE = `
local raw = redis.call('GET', KEYS[1])
if raw and cjson.decode(raw).id == ARGV[1] then
  redis.call('DEL', KEYS[1]); redis.call('ZREM', KEYS[2], ARGV[1])
end
return 1
`;

const LIST = `
local count = redis.call('ZCARD', KEYS[2])
if count > tonumber(ARGV[2]) then return redis.error_reply('gallery index requires migration') end
local offset = tonumber(ARGV[1])
local handles = redis.call('ZREVRANGE', KEYS[2], offset, offset + 49)
local bounded = {}
for _, handle in ipairs(handles) do
  local raw = redis.call('HGET', KEYS[1], handle)
  if raw and string.len(handle) <= 15 and string.len(raw) <= 32768 then
    table.insert(bounded, handle); table.insert(bounded, raw)
  end
end
local cursor = '0'
if offset + 50 < count then cursor = tostring(offset + 50) end
return {cursor, bounded}
`;

const READ = `
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if raw and string.len(raw) <= 32768 then return raw end
return false
`;

module.exports = { RESERVE, STORE, RELEASE, LIST, READ };
