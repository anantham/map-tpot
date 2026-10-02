// Intent: waiting never re-enters paid admission or treats an empty 202 as an image.
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {generateServerless} from './cardTransport';
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body});
beforeEach(()=>{globalThis.fetch=vi.fn();vi.useFakeTimers();});
afterEach(()=>vi.useRealTimers());
it('polls a cache-only GET after the single generation POST',async()=>{
  fetch.mockResolvedValueOnce(response(202,{code:'in_progress'}))
    .mockResolvedValueOnce(response(200,{imageUrl:'https://owned.test/card.png',cached:true}));
  const pending=generateServerless({handle:'Alice'},undefined,0,true);
  await vi.runAllTimersAsync();
  expect(await pending).toEqual({imageUrl:'https://owned.test/card.png',cached:true});
  expect(fetch.mock.calls.map(([url])=>url)).toEqual(['/api/generate-card','/api/card-status?handle=Alice']);
  expect(fetch.mock.calls[1][1].method).toBe('GET');
  expect(fetch.mock.calls[1][1].headers).toBeUndefined();
});
it('returns an explicit waiting error when all bounded polls remain pending',async()=>{
  fetch.mockResolvedValue(response(202,{code:'in_progress'}));
  const result=generateServerless({handle:'alice'}).catch(error=>error);
  await vi.runAllTimersAsync();
  expect((await result).code).toBe('in_progress');
  expect(fetch).toHaveBeenCalledTimes(4);
  expect(fetch.mock.calls.filter(([,options])=>options.method==='POST')).toHaveLength(1);
});
it('preserves concurrency and publication quota errors instead of calling every 429 a budget failure',async()=>{
  fetch.mockResolvedValue(response(429,{code:'concurrency_limited',error:'Busy'}));
  await expect(generateServerless({handle:'alice'})).rejects.toMatchObject({code:'concurrency_limited'});
});
it('rejects a successful response without an image',async()=>{
  fetch.mockResolvedValue(response(200,{cached:true}));
  await expect(generateServerless({handle:'alice'})).rejects.toMatchObject({code:'invalid_image_response'});
});
it('aborts a pending wait without another request',async()=>{
  fetch.mockResolvedValue(response(202,{code:'in_progress'}));
  const controller=new AbortController();
  const pending=generateServerless({handle:'alice'},controller.signal).catch(error=>error);
  await Promise.resolve();await Promise.resolve();controller.abort();
  await vi.runAllTimersAsync();
  expect((await pending).name).toBe('AbortError');expect(fetch).toHaveBeenCalledTimes(1);
});
