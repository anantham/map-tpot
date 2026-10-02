// @vitest-environment node
// Test intent: public cache and signed generation preserve UX while no denied,
// replayed, concurrent or storage-failed request can reach the paid provider.
import {beforeAll,beforeEach,afterAll,describe,it,expect,vi} from 'vitest';
import {randomUUID} from 'node:crypto';
import sharp from 'sharp';
import lib from '../../api/_lib.js';
import handler from '../../api/generate-card.js';
import admission from '../../api/_cardAdmission.js';
import fixture from './_redisFixture.cjs';
import {mockReq,mockRes} from './_helpers';
const redis = fixture.testRedis(2);
const body = (handle='alice',force=false) => ({handle,bio:'graphs',communities:[{name:'EA',color:'#123456',weight:0.6}],tweets:['hello'],force});
const req = (payload,options={}) => mockReq({method:'POST',body:payload,headers:{authorization:'Bearer '+admission.signCapability({kind:'generate',handle:payload.handle,digest:admission.digestBody(payload),subject:'synthetic-owner',expiresAt:Math.floor(Date.now()/1000)+300,force:payload.force,...options})}});
let image;
const success = () => new Response(JSON.stringify({choices:[{message:{images:[{image_url:{url:image}}]}}],usage:{cost:0.04}}),{status:200,headers:{'content-type':'application/json'}});
const run = async request => {const res=mockRes();await handler(request,res);return res;};
describe.skipIf(!redis)('generate-card contracts against disposable Redis',()=>{
  beforeAll(async()=>{await redis.raw.connect();image='data:image/png;base64,'+(await sharp({create:{width:2,height:3,channels:3,background:'#123456'}}).png().toBuffer()).toString('base64');});
  beforeEach(async()=>{
    await redis.raw.flushdb();lib.__reset();
    Object.assign(process.env,{OPENROUTER_API_KEY:'synthetic-key',CARD_CAPABILITY_SECRET:'synthetic-signing-key-with-at-least-32-bytes',CARD_DAILY_BUDGET:'5',CARD_REQUEST_RESERVATION_USD:'0.5',CARD_MAX_CONCURRENCY:'2',CARD_SPONSORED_ENABLED:'true',CARD_BLOB_BASE_URL:'https://teststore.public.blob.vercel-storage.com'});
    lib.__setForTesting({kv:redis.kv,blobPut:vi.fn(async path=>({url:process.env.CARD_BLOB_BASE_URL+'/'+path}))});
    globalThis.fetch=vi.fn(async()=>success());
  });
  afterAll(async()=>{lib.__reset();await redis.raw.quit();});
  it('rejects methods and bounded invalid payloads',async()=>{
    expect((await run(mockReq({method:'GET'}))).statusCode).toBe(405);
    for(const payload of [{},body('../alice'),{...body(),bio:'a'.repeat(2001)},{...body(),force:'yes'},{...body(),surprise:true}]) {
      expect((await run(mockReq({method:'POST',body:payload}))).statusCode).toBe(400);
    }
    expect(fetch).not.toHaveBeenCalled();
  });
  it('serves an anonymous validated cache without an API key',async()=>{
    await redis.raw.set('card:alice',JSON.stringify({schema:2,url:process.env.CARD_BLOB_BASE_URL+'/cards/alice-cached.png',expiresAt:Date.now()+10000}));
    delete process.env.OPENROUTER_API_KEY;
    const res=await run(mockReq({method:'POST',body:body()}));
    expect(res.statusCode).toBe(200);expect(res.body.cached).toBe(true);expect(fetch).not.toHaveBeenCalled();
  });
  it('does not trust legacy arbitrary primary cache URLs',async()=>{
    await redis.raw.set('card:alice','https://attacker.test/image.png');
    expect((await run(mockReq({method:'POST',body:body()}))).statusCode).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('denies a mismatched or expired signed body',async()=>{
    const request=req(body());request.body.bio='tampered';
    expect((await run(request)).statusCode).toBe(403);
    expect((await run(req(body(),{expiresAt:1}))).statusCode).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('requires an explicit regeneration grant',async()=>{
    expect((await run(req(body('alice',true),{force:false}))).statusCode).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('reserves spend before provider work and stores normalized owned raster',async()=>{
    fetch.mockImplementation(async()=>{
      expect(Number(await redis.raw.get('card:{admission}:budget:'+new Date().toISOString().slice(0,10)))).toBe(500000);
      return success();
    });
    const res=await run(req(body()));
    expect(res.statusCode).toBe(200);expect(res.body.cached).toBe(false);
    expect(res.body.imageUrl).toMatch(/^https:\/\/teststore.public.blob.vercel-storage.com\/cards\/alice-/);
    expect(JSON.parse(await redis.raw.hget('gallery','alice'))[0].schema).toBe(2);
    const request=JSON.parse(fetch.mock.calls[0][1].body);
    expect(request.max_tokens).toBe(4096);expect(request.provider.allow_fallbacks).toBe(false);
  });
  it('allows one paid duplicate while another receives in-progress',async()=>{
    let complete;fetch.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
    const first=run(req(body('alice',true)));
    while(!complete) await new Promise(resolve=>setTimeout(resolve,1));
    const second=await run(req(body('alice',true)));
    expect(second.statusCode).toBe(202);expect(fetch).toHaveBeenCalledTimes(1);
    complete(success());expect((await first).statusCode).toBe(200);
  });
  it('admits at most two concurrent unique paid requests',async()=>{
    const completions=[];fetch.mockImplementation(()=>new Promise(resolve=>completions.push(resolve)));
    const first=run(req(body('alice',true))),second=run(req(body('bob',true)));
    while(completions.length<2) await new Promise(resolve=>setTimeout(resolve,1));
    expect((await run(req(body('carol',true)))).statusCode).toBe(429);
    expect(fetch).toHaveBeenCalledTimes(2);completions.forEach(resolve=>resolve(success()));
    expect((await first).statusCode).toBe(200);expect((await second).statusCode).toBe(200);
  });
  it('cannot race unique calls past the final budget reservation',async()=>{
    process.env.CARD_DAILY_BUDGET='0.5';
    const responses=await Promise.all(['alice','bob','carol','dave'].map(h=>run(req(body(h,true)))));
    expect(responses.filter(r=>r.statusCode===200)).toHaveLength(1);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(Number(await redis.raw.get('card:{admission}:budget:'+new Date().toISOString().slice(0,10)))).toBe(500000);
  });
  it('blocks replay even after a forced generation succeeds',async()=>{
    const request=req(body('alice',true));expect((await run(request)).statusCode).toBe(200);
    expect((await run(request)).statusCode).toBe(409);expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('holds spend and lease when provider billing is uncertain',async()=>{
    fetch.mockResolvedValue(new Response('failure',{status:502}));
    expect((await run(req(body('alice',true)))).statusCode).toBe(502);
    expect((await run(req(body('alice',true)))).statusCode).toBe(202);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(Number(await redis.raw.get('card:{admission}:budget:'+new Date().toISOString().slice(0,10)))).toBe(500000);
  });
  it('denies unavailable, corrupt and misconfigured quota stores',async()=>{
    process.env.CARD_DAILY_BUDGET='NaN';expect((await run(req(body()))).statusCode).toBe(503);
    process.env.CARD_DAILY_BUDGET='5';
    await redis.raw.set('card:{admission}:budget:'+new Date().toISOString().slice(0,10),'not-a-number');
    expect((await run(req(body()))).statusCode).toBe(503);
    lib.__setForTesting({kv:{get:async()=>null,eval:async()=>{throw Error('offline');}}});
    expect((await run(req(body()))).statusCode).toBe(503);expect(fetch).not.toHaveBeenCalled();
  });
  it('fails closed before paid work when image storage is not configured',async()=>{
    delete process.env.CARD_BLOB_BASE_URL;
    expect((await run(req(body()))).statusCode).toBe(503);expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects oversized or external provider images without public writes',async()=>{
    fetch.mockResolvedValue(new Response(JSON.stringify({choices:[{message:{images:[{url:'https://attacker.test/card.png'}]}}]}),{status:200}));
    expect((await run(req(body()))).statusCode).toBe(502);expect(await redis.raw.hlen('gallery')).toBe(0);
  });
});
