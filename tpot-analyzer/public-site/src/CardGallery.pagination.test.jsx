// Test intent: pagination preserves all public cards and cannot loop indefinitely.
import {render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import CardGallery from './CardGallery';
vi.mock('./GenerateCard',()=>({getAllCachedCards:()=>[],cacheCard:vi.fn()}));
beforeEach(()=>{globalThis.fetch=vi.fn();});
it('loads cards beyond the first server page',async()=>{
  fetch.mockResolvedValueOnce({ok:true,json:async()=>({cards:[{handle:'alice',url:'https://example.test/alice.png'}],nextCursor:'50'})})
    .mockResolvedValueOnce({ok:true,json:async()=>({cards:[{handle:'bob',url:'https://example.test/bob.png'}],nextCursor:null})});
  render(<CardGallery onMemberClick={()=>{}} onBack={()=>{}} />);
  await waitFor(()=>expect(screen.getByText('@bob')).toBeTruthy());
  expect(fetch.mock.calls.map(call=>call[0])).toEqual(['/api/gallery','/api/gallery?cursor=50']);
});
