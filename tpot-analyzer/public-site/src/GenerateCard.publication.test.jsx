// Intent: navigation finds an existing grant and publishing never regenerates pixels.
import {renderHook,waitFor,act} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {useCardGeneration} from './GenerateCard';
import {cacheCard} from './cardCache';
import {setCardCapability} from './cardCapabilities';
const raster='data:image/png;base64,c3ludGhldGlj';
const grant=handle=>btoa(JSON.stringify({kind:'gallery',handle,expiresAt:Math.floor(Date.now()/1000)+300}))+'.synthetic';
const params=handle=>({handle,bio:'synthetic',memberships:[['c1',0.5]],sampleTweets:[],communityMap:new Map([['c1',{name:'Synthetic',color:'#123456'}]])});
beforeEach(()=>{localStorage.clear();globalThis.fetch=vi.fn();});
it('offers publication after navigating to a previously granted cached BYOK card',async()=>{
  cacheCard('navfixture',raster);setCardCapability(grant('navfixture'));
  const {result}=renderHook(()=>useCardGeneration(params('navfixture')));
  await waitFor(()=>expect(result.current.publicationStatus).toBe('ready'));
  expect(fetch).not.toHaveBeenCalled();
  fetch.mockResolvedValue({ok:true,json:async()=>({stored:true,imageUrl:'https://store.public.blob.vercel-storage.com/cards/navfixture-published.png'})});
  await act(()=>result.current.publish());
  expect(result.current.publicationStatus).toBe('published');expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe('/api/gallery-submit');
  expect(JSON.parse(fetch.mock.calls[0][1].body).imageUrl).toBe(raster);
});
it('ignores grant notifications safely when no account is selected',()=>{
  renderHook(()=>useCardGeneration(params(null)));
  expect(()=>setCardCapability(grant('emptyfixture'))).not.toThrow();expect(fetch).not.toHaveBeenCalled();
});
