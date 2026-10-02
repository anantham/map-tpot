// @vitest-environment node
// Test intent: anonymous/force, missing Redis and lock failures must never spend;
// valid signed content has one admission, bounded budget and concurrency.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import lib from '../../api/_lib.js';
import handler from '../../api/generate-card.js';
import { mockReq, mockRes, makeMockRedis } from './_helpers';

beforeEach(() => {
  process.env.OPENROUTER_API_KEY = 'synthetic-key';
  lib.__reset();
  lib.__setForTesting({ kv: makeMockRedis(), blobPut: vi.fn() });
  globalThis.fetch = vi.fn();
});
afterEach(() => lib.__reset());
const body = () => ({ handle: 'alice', communities: [{name:'EA',color:'#123456',weight:1}] });
describe('paid admission fails closed', () => {
  it('rejects anonymous forced regeneration before any paid call', async () => {
    const res = mockRes();
    await handler(mockReq({method:'POST',body:{...body(),force:true}}), res);
    expect(res.statusCode).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('denies missing quota storage before any paid call', async () => {
    lib.__setForTesting({kv:null});
    const res = mockRes();
    await handler(mockReq({method:'POST',body:body()}), res);
    expect(res.statusCode).toBe(503);
    expect(fetch).not.toHaveBeenCalled();
  });
});
