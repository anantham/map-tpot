/**
 * Shared lazy-singleton initialization for Redis (kv) and Vercel Blob (blobPut).
 *
 * Each serverless handler imports `getKv()` / `getBlobPut()` and calls them
 * inside the handler body. In production, the singleton initializes once per
 * cold start; in tests, `__setForTesting({ kv, blobPut })` injects mocks and
 * `__reset()` clears them between cases.
 *
 * Centralising this here removes the ~30 LOC of try/catch require boilerplate
 * that was previously duplicated across generate-card / og / gallery /
 * gallery-submit / card-image.
 */

let _kv = null;
let _blobPut = null;
let _initialized = false;

function _wrapRedis(raw) {
  const connect = async () => {
    try { await raw.connect(); } catch {}
  };
  return {
    async get(key) {
      await connect();
      return raw.get(key);
    },
    async set(key, value, opts) {
      await connect();
      const v = typeof value === "object" ? JSON.stringify(value) : value;
      if (opts && opts.nx && opts.ex) {
        const r = await raw.set(key, v, "EX", opts.ex, "NX");
        return r === "OK";
      }
      if (opts && opts.ex) {
        return raw.set(key, v, "EX", opts.ex);
      }
      return raw.set(key, v);
    },
    async del(key) {
      await connect();
      return raw.del(key);
    },
    async incrbyfloat(key, amount) {
      await connect();
      return raw.incrbyfloat(key, amount);
    },
    async expire(key, seconds) {
      await connect();
      return raw.expire(key, seconds);
    },
    async hset(key, field, value) {
      await connect();
      return raw.hset(key, field, value);
    },
    async hget(key, field) {
      await connect();
      return raw.hget(key, field);
    },
    async hgetall(key) {
      await connect();
      return raw.hgetall(key);
    },
  };
}

function _loadKv() {
  const redisUrl = process.env.KV_REDIS_URL;
  if (!redisUrl) return null;
  try {
    const Redis = require("ioredis");
    const raw = new Redis(redisUrl, {
      maxRetriesPerRequest: 1,
      connectTimeout: 3000,
      lazyConnect: true,
    });
    return _wrapRedis(raw);
  } catch {
    return null;
  }
}

function _loadBlobPut() {
  try {
    const { put } = require("@vercel/blob");
    return put;
  } catch {
    return null;
  }
}

let _blobGet = null;

function _loadBlobGet() {
  try {
    const { get } = require("@vercel/blob");
    return get;
  } catch {
    return null;
  }
}

function _ensureInit() {
  if (_initialized) return;
  _kv = _loadKv();
  _blobPut = _loadBlobPut();
  _blobGet = _loadBlobGet();
  _initialized = true;
}

function getKv() {
  // Test override via globalThis. Backed by globalThis (not module state) so
  // it works even if the test and handler load _lib via separate module
  // instances (a known vitest CJS interop quirk).
  if (globalThis.__TPOT_TEST_KV !== undefined) return globalThis.__TPOT_TEST_KV;
  _ensureInit();
  return _kv;
}

function getBlobPut() {
  if (globalThis.__TPOT_TEST_BLOB !== undefined) return globalThis.__TPOT_TEST_BLOB;
  _ensureInit();
  return _blobPut;
}

function getBlobGet() {
  if (globalThis.__TPOT_TEST_BLOB_GET !== undefined) return globalThis.__TPOT_TEST_BLOB_GET;
  _ensureInit();
  return _blobGet;
}

// Test-only hooks. Production handlers never call these.
function __setForTesting({ kv, blobPut, blobGet } = {}) {
  if (kv !== undefined) globalThis.__TPOT_TEST_KV = kv;
  if (blobPut !== undefined) globalThis.__TPOT_TEST_BLOB = blobPut;
  if (blobGet !== undefined) globalThis.__TPOT_TEST_BLOB_GET = blobGet;
}

function __reset() {
  delete globalThis.__TPOT_TEST_KV;
  delete globalThis.__TPOT_TEST_BLOB;
  delete globalThis.__TPOT_TEST_BLOB_GET;
  _kv = null;
  _blobPut = null;
  _blobGet = null;
  _initialized = false;
}

module.exports = {
  getKv,
  getBlobPut,
  getBlobGet,
  __setForTesting,
  __reset,
  // Exposed for unit tests of the wrapper itself.
  _wrapRedis,
};
