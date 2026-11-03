// Test intent: grants remain tab-local, expire promptly, and are sent only to the site.
import {beforeEach,expect,it,vi} from 'vitest';
import {setCardCapability,getCardCapability} from './cardCapabilities';
import {generateServerless,publishApprovedCard} from './cardTransport';
const token = (overrides={}) => btoa(JSON.stringify({kind:'generate',handle:'alice',expiresAt:Math.floor(Date.now()/1000)+300,...overrides})).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')+'.synthetic';
beforeEach(()=>{localStorage.clear();sessionStorage.clear();globalThis.fetch=vi.fn();});
it('keeps grants in memory without persistent browser storage',()=>{
  const grant=token();expect(setCardCapability(grant)).toBe('alice');
  expect(getCardCapability('Alice','generate')).toBe(grant);
  expect(localStorage.length).toBe(0);expect(sessionStorage.length).toBe(0);
});
it('rejects expired, malformed and overly long grants',()=>{
  expect(()=>setCardCapability(token({expiresAt:1}))).toThrow();
  expect(()=>setCardCapability('bad')).toThrow();
  expect(()=>setCardCapability('a'.repeat(4097))).toThrow();
});
it('passes the grant to same-site generation and preserves force',async()=>{
  const grant=token();setCardCapability(grant);
  fetch.mockResolvedValue({ok:true,status:200,json:async()=>({imageUrl:'https://example.test/card.png',cached:false})});
  await generateServerless({handle:'alice',communities:[]},undefined,0,true);
  expect(fetch.mock.calls[0][0]).toBe('/api/generate-card');
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer '+grant);
  expect(JSON.parse(fetch.mock.calls[0][1].body).force).toBe(true);
});
it('publishes approved existing pixels without another paid generation',async()=>{
  const grant=token({kind:'gallery'});setCardCapability(grant);
  const body={handle:'alice',imageUrl:'data:image/png;base64,c3ludGhldGlj',communities:[]};
  fetch.mockResolvedValue({ok:true,json:async()=>({stored:true,imageUrl:'https://example.test/card.png'})});
  await publishApprovedCard(body);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe('/api/gallery-submit');
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer '+grant);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(body);
});
