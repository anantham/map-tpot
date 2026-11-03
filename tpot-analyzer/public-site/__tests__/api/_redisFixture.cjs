// Explicitly opt in to a disposable test Redis; never accept production URLs.
const Redis = require('ioredis');
const lib = require('../../api/_lib');
function testRedis(db) {
  const socket = process.env.TPOT_TEST_REDIS_SOCKET;
  const ciUrl = process.env.CI === 'true' && process.env.TPOT_TEST_REDIS_URL;
  let raw;
  if (socket && /^\/tmp\/tpot-security-redis-[a-zA-Z0-9_-]+\.sock$/.test(socket)) {
    raw = new Redis({path:socket,db,lazyConnect:true,maxRetriesPerRequest:0});
  } else if (ciUrl === 'redis://127.0.0.1:6379') {
    raw = new Redis(ciUrl,{db,lazyConnect:true,maxRetriesPerRequest:0});
  } else return null;
  return {raw,kv:lib._wrapRedis(raw)};
}
module.exports = {testRedis};
