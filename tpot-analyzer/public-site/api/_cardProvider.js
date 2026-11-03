const { AdmissionError } = require('./_cardAdmission');
const MODEL = 'google/gemini-2.5-flash-image';
const MAX_RESPONSE_BYTES = 8 * 1024 * 1024;
async function readProviderJson(response) {
  const length = Number(response.headers?.get('content-length'));
  if (length > MAX_RESPONSE_BYTES) {
    await response.body?.cancel(); throw new AdmissionError(502,'upstream_too_large');
  }
  if (!response.body || !response.body.getReader) throw new AdmissionError(502,'invalid_upstream_response');
  const reader = response.body.getReader();
  const chunks = []; let bytes = 0;
  try {
    for (;;) {
      const {done,value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) throw new AdmissionError(502,'upstream_too_large');
      chunks.push(Buffer.from(value));
    }
    return JSON.parse(Buffer.concat(chunks,bytes).toString('utf8'));
  } finally { await reader.cancel(); }
}
async function generateImage(apiKey, prompt) {
  // Fixed model and caps: no caller-selected paid parameters or provider fallbacks.
  if (Buffer.byteLength(prompt) > 16000) throw new AdmissionError(413,'prompt_too_large');
  const controller = new AbortController();
  const configured = Number(process.env.CARD_GENERATION_TIMEOUT_MS || 45000);
  const timeoutMs = Number.isSafeInteger(configured) ? Math.max(5000, Math.min(configured,45000)) : 45000;
  const timeout = setTimeout(() => controller.abort(),timeoutMs);
  try {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method:'POST', signal:controller.signal,
      headers:{Authorization:`Bearer ${apiKey}`,'Content-Type':'application/json','X-Title':'TPOT Collectible Cards'},
      body:JSON.stringify({model:MODEL,messages:[{role:'user',content:prompt}],max_tokens:4096,
        modalities:['image','text'],image_config:{aspect_ratio:'2:3',image_size:'1K'},
        provider:{allow_fallbacks:false,require_parameters:true,
          max_price:{prompt:1,completion:50,image:0,request:0}}}),
    });
    if (!response.ok) { await response.body?.cancel(); throw new AdmissionError(502,'upstream_error'); }
    const data = await readProviderJson(response);
    const images = data.choices?.[0]?.message?.images;
    const imageUrl = images?.length === 1 && (images[0].image_url?.url || images[0].url);
    if (typeof imageUrl !== 'string' || !imageUrl.startsWith('data:image/')) {
      throw new AdmissionError(502,'generation_failed');
    }
    return {imageUrl,cost:data.usage?.cost};
  } catch (err) {
    if (err.name === 'AbortError') throw new AdmissionError(504,'generation_timeout');
    throw err;
  } finally { clearTimeout(timeout); }
}
module.exports = { MODEL, generateImage, readProviderJson };
