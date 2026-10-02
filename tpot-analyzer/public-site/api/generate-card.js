/** Sponsored generation requires an offline-issued, content-bound capability.
 * Anonymous readers retain cache access. BYOK generation remains in the browser.
 */
const {getKv,getBlobPut} = require('./_lib');
const {AdmissionError,digestBody,requestCapability} = require('./_cardAdmission');
const {validateCardRequest} = require('./_cardRequest');
const {reserveGeneration,releaseGeneration} = require('./_cardBudget');
const {MODEL,generateImage} = require('./_cardProvider');
const {readCachedCard} = require('./_cardCache');
const {buildLegacyCardPrompt} = require('./_legacyCardPrompt');
let iconography;
try { iconography = require('../config/community_iconography.json').communities; } catch {}

module.exports = async function handler(req,res) {
  if (req.method !== 'POST') return res.status(405).json({error:'Method not allowed',code:'method_not_allowed'});
  let generation, publication, kv;
  let providerStarted = false;
  let completed = false;
  try {
    const body = validateCardRequest(req.body);
    // Force cannot bypass anonymous cache reads or begin work without a grant.
    let grant;
    if (body.force) grant = requestCapability(req,{kind:'generate',handle:body.handle,digest:digestBody(req.body)});
    kv = getKv();
    if (!kv) throw new AdmissionError(503,'quota_unavailable');
    const {uploadRawCard,assertImageInfrastructure} = require('./_imagePolicy');
    const {reservePublication,storePublication,normalizeCommunities} = require('./_galleryPolicy');
    if (!body.force) {
      const imageUrl=await readCachedCard(kv,body.handle);
      if (imageUrl) return res.status(200).json({imageUrl,cached:true,model:MODEL});
    }
    grant ||= requestCapability(req,{kind:'generate',handle:body.handle,digest:digestBody(req.body)});
    if (body.force && !grant.force) throw new AdmissionError(403,'regeneration_not_authorized');
    const apiKey = process.env.OPENROUTER_API_KEY;
    const blobPut = getBlobPut();
    if (!apiKey || !blobPut) throw new AdmissionError(503,'config_error');
    assertImageInfrastructure(blobPut);
    const communities = normalizeCommunities(body.communities.slice(0,5));
    // Reserve gallery capacity before paying; ownership and storage are admission gates.
    publication = await reservePublication(kv,{handle:body.handle,grant,trusted:true});
    generation = await reserveGeneration(kv,{handle:body.handle,grant});
    const prompt = buildLegacyCardPrompt({...body,iconography});
    providerStarted = true;
    const generated = await generateImage(apiKey,prompt);
    const uploaded = await uploadRawCard(blobPut,{handle:body.handle,imageUrl:generated.imageUrl});
    await storePublication(kv,publication,{url:uploaded.url,bytes:uploaded.bytes,generatedAt:Date.now(),
      communities});
    // Primary cache is disposable. A write failure cannot undermine the budget ledger.
    try { await kv.set(`card:${body.handle}`,JSON.stringify({schema:2,url:uploaded.url,expiresAt:Date.now()+86400000}),{ex:86400}); } catch {}
    completed = true;
    return res.status(200).json({imageUrl:uploaded.url,cached:false,model:MODEL});
  } catch (err) {
    const known = err instanceof AdmissionError || Number.isInteger(err.status);
    const code = known ? err.code : 'quota_or_generation_unavailable';
    console.warn('[generate-card]', {code,providerStarted});
    return res.status(known ? err.status : 503).json({error:code,code,...(err.status===202?{retryAfter:5}:{})});
  } finally {
    // Retain the lease on uncertain provider failures; no spend/nonce refund ever occurs.
    if (generation && (completed || !providerStarted)) {
      try { await releaseGeneration(kv,generation); } catch {}
    }
    if (publication && !completed) {
      try { await require('./_galleryPolicy').releasePublication(kv,publication); } catch {}
    }
  }
};
