/** The server caps the gallery at 500 records and pages at 50 records. */
export async function fetchGalleryCards(signal) {
  const cards = new Map();
  let cursor = null;
  for (let page=0;page<10;page++) {
    const response = await fetch(cursor ? `/api/gallery?cursor=${cursor}` : '/api/gallery',{signal});
    if (response.ok === false) throw new Error('Gallery unavailable');
    const data = await response.json();
    if (!Array.isArray(data.cards) || data.cards.length>50) throw new Error('Invalid gallery page');
    for (const card of data.cards) cards.set(card.handle,card);
    if (!data.nextCursor) return [...cards.values()];
    if (!/^\d{1,3}$/.test(data.nextCursor) || Number(data.nextCursor)<=Number(cursor || 0) || Number(data.nextCursor)>500) {
      throw new Error('Invalid gallery cursor');
    }
    cursor=data.nextCursor;
  }
  throw new Error('Gallery page limit reached');
}
