import {expect,it,vi} from 'vitest';
import {fetchGalleryCards} from './galleryPages';
it('rejects repeated cursors without unlimited requests',async()=>{
  globalThis.fetch=vi.fn(async()=>({ok:true,json:async()=>({cards:[],nextCursor:'50'})}));
  await expect(fetchGalleryCards()).rejects.toThrow('Invalid gallery cursor');
  expect(fetch).toHaveBeenCalledTimes(2);
});
it('bounds public page size',async()=>{
  globalThis.fetch=vi.fn(async()=>({ok:true,json:async()=>({cards:Array(51).fill({handle:'alice'}),nextCursor:null})}));
  await expect(fetchGalleryCards()).rejects.toThrow('Invalid gallery page');
});
