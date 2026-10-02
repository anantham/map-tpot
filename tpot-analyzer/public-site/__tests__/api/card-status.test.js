// @vitest-environment node
// Intent: waiting is anonymous, cache-only, bounded and never exposes legacy URLs.
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import lib from '../../api/_lib.js';
import handler from '../../api/card-status.js';
import {mockReq,mockRes,makeMockRedis} from './_helpers';
let kv;
beforeEach(()=>{
  process.env.CARD_BLOB_BASE_URL='https://store.public.blob.vercel-storage.com';
  lib.__reset();kv=makeMockRedis();kv.eval=vi.fn().mockResolvedValue(null);lib.__setForTesting({kv});globalThis.fetch=vi.fn();
});
afterEach(()=>lib.__reset());
const read=async(query={handle:'Alice'})=>{const res=mockRes();await handler(mockReq({query}),res);return res;};
it('returns pending while the paid lock exists even if a prior forced image is cached',async()=>{
  kv.get.mockResolvedValue('lock-owner');const res=await read();
  expect(res.statusCode).toBe(202);expect(kv.get).toHaveBeenCalledExactlyOnceWith('card:{admission}:lock:alice');
  expect(res.headers['Cache-Control']).toBe('no-store');expect(fetch).not.toHaveBeenCalled();
});
it('returns only a retained owned schema2 image after the lock clears',async()=>{
  const url='https://store.public.blob.vercel-storage.com/cards/alice-synthetic.png';
  kv.get.mockResolvedValueOnce(null).mockResolvedValueOnce(JSON.stringify({schema:2,url,expiresAt:Date.now()+1000}));
  const res=await read();expect(res.statusCode).toBe(200);expect(res.body).toEqual({imageUrl:url,cached:true});
  expect(fetch).not.toHaveBeenCalled();expect(kv.set).not.toHaveBeenCalled();
});
it('fails closed for missing storage and malformed handles',async()=>{
  lib.__setForTesting({kv:null});expect((await read()).statusCode).toBe(503);
  expect((await read({handle:'../alice'})).statusCode).toBe(400);
});
it('rejects legacy external URLs without fetching them',async()=>{
  kv.get.mockResolvedValueOnce(null).mockResolvedValueOnce('https://evil.test/track.png').mockResolvedValueOnce(null);
  expect((await read()).statusCode).toBe(404);expect(fetch).not.toHaveBeenCalled();
});
