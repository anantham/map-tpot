/** Cache-only waiting endpoint: never reserves capacity, consumes grants or pays. */
const {getKv}=require('./_lib');
const {normalizeHandle}=require('./_imagePolicy');
const {readCachedCard}=require('./_cardCache');
module.exports=async function handler(req,res) {
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  if (req.method!=='GET') return res.status(405).json({code:'method_not_allowed'});
  try {
    const handle=normalizeHandle(req.query?.handle);
    const kv=getKv();
    if (!kv) return res.status(503).json({code:'quota_unavailable'});
    // A forced refresh must not return its previous cached image while work continues.
    if (await kv.get(`card:{admission}:lock:${handle}`)) return res.status(202).json({code:'in_progress',retryAfter:5});
    const imageUrl=await readCachedCard(kv,handle);
    return imageUrl ? res.status(200).json({imageUrl,cached:true}) : res.status(404).json({code:'image_unavailable'});
  } catch (error) {
    return res.status(error.status || 503).json({code:error.code || 'image_unavailable'});
  }
};
