// @vitest-environment node
// Test intent: corrupt Redis types/counters reject admission without partial
// lock/nonce/budget mutations; public generation cannot reach a paid provider.
import { beforeAll, beforeEach, afterAll, describe, it, expect, vi } from 'vitest';
import admission from '../../api/_cardAdmission.js';
import budget from '../../api/_cardBudget.js';
import lib from '../../api/_lib.js';
import handler from '../../api/generate-card.js';
import fixture from './_redisFixture.cjs';
import { mockReq, mockRes } from './_helpers';
const redis = fixture.testRedis(6);
const prefix = 'card:{admission}:';
const body = { handle:'synthetic',bio:'graphs',communities:[{name:'EA',color:'#123456',weight:0.6}],tweets:['synthetic'],force:true };
const makeGrant = () => ({kind:'generate',handle:body.handle,digest:admission.digestBody(body),
  subject:'synthetic-owner',jti:'synthetic-corruption-nonce',expiresAt:Math.floor(Date.now()/1000)+300,force:true});
const keys = grant => [prefix+'budget:'+new Date().toISOString().slice(0,10),
  prefix+'lock:'+body.handle,prefix+'active',prefix+'nonce:'+grant.jti];
const state = async list => Promise.all(list.map(key=>redis.raw.dumpBuffer(key)));
describe.skipIf(!redis)('paid admission corrupt-state boundaries',()=>{
  beforeAll(async()=>redis.raw.connect());
  beforeEach(async()=>{
    await redis.raw.flushdb();lib.__reset();
    Object.assign(process.env,{OPENROUTER_API_KEY:'synthetic-key',CARD_CAPABILITY_SECRET:'synthetic-signing-key-with-at-least-32-bytes',
      CARD_SPONSORED_ENABLED:'true',CARD_DAILY_BUDGET:'5',CARD_REQUEST_RESERVATION_USD:'0.5',CARD_MAX_CONCURRENCY:'2',
      CARD_BLOB_BASE_URL:'https://teststore.public.blob.vercel-storage.com'});
    lib.__setForTesting({kv:redis.kv,blobPut:vi.fn()});globalThis.fetch=vi.fn();
  });
  afterAll(async()=>{lib.__reset();await redis.raw.quit();});
  it.each([0,1,2,3])('rejects unexpected key type at slot %s without mutations or provider work',async slot=>{
    const grant=makeGrant(),list=keys(grant);
    await redis.raw.hset(list[slot],'synthetic','corrupt');
    const prior=await state(list),res=mockRes();
    const token=admission.signCapability(grant);
    await handler(mockReq({method:'POST',body,headers:{authorization:'Bearer '+token}}),res);
    expect(res.statusCode).toBe(503);
    expect(await state(list)).toEqual(prior);
    expect(fetch).not.toHaveBeenCalled();expect(lib.getBlobPut()).not.toHaveBeenCalled();
  });
  it.each(['0.5','01','+1','1e2','-1','NaN','1000000001','9223372036854775808'])('rejects noncanonical/out-of-range budget %s without partial reservation',async value=>{
    const grant=makeGrant(),list=keys(grant);
    await redis.raw.set(list[0],value);
    await redis.raw.zadd(list[2],Date.now()-1000,'expired-synthetic');
    const prior=await state(list);
    await expect(budget.reserveGeneration(redis.kv,{handle:body.handle,grant})).rejects.toMatchObject({status:503});
    expect(await state(list)).toEqual(prior);
  });
  it('preserves both keys when release coordination has an unexpected type',async()=>{
    const reservation=await budget.reserveGeneration(redis.kv,{handle:body.handle,grant:makeGrant()});
    await redis.raw.del(reservation.keys[2]);await redis.raw.hset(reservation.keys[2],'synthetic','corrupt');
    const list=[reservation.keys[1],reservation.keys[2]],prior=await state(list);
    await expect(budget.releaseGeneration(redis.kv,reservation)).rejects.toThrow();
    expect(await state(list)).toEqual(prior);
  });
  it('leaves expired slots unchanged when an otherwise valid ledger exhausts the quota',async()=>{
    const grant=makeGrant(),list=keys(grant);
    await redis.raw.set(list[0],'5000000');
    await redis.raw.zadd(list[2],Date.now()-1000,'expired-synthetic');
    const prior=await state(list);
    await expect(budget.reserveGeneration(redis.kv,{handle:body.handle,grant})).rejects.toMatchObject({status:429});
    expect(await state(list)).toEqual(prior);
  });
  it('allows canonical integer ledger state and releases only coordination',async()=>{
    const grant=makeGrant(),list=keys(grant);await redis.raw.set(list[0],'1');
    const reservation=await budget.reserveGeneration(redis.kv,{handle:body.handle,grant});
    expect(await redis.raw.get(list[0])).toBe('500001');
    await budget.releaseGeneration(redis.kv,reservation);
    expect(await redis.raw.exists(list[1])).toBe(0);expect(await redis.raw.zcard(list[2])).toBe(0);
    expect(await redis.raw.get(list[0])).toBe('500001');expect(await redis.raw.exists(list[3])).toBe(1);
  });
});
