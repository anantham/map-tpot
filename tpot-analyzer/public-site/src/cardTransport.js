import {getCardCapability} from "./cardCapabilities";
const MODEL="google/gemini-2.5-flash-image";
const OPENROUTER_URL="https://openrouter.ai/api/v1/chat/completions";
const RETRY_DELAY_MS=5000;
const MAX_RETRIES=3;
export async function publishApprovedCard(body,signal) {
  const grant=getCardCapability(body.handle,'gallery');
  if (!grant) throw new Error('An approved publication grant is required');
  const response=await fetch('/api/gallery-submit',{method:'POST',signal,
    headers:{'Content-Type':'application/json',Authorization:`Bearer ${grant}`},body:JSON.stringify(body)});
  const result=await response.json();
  if (!response.ok || !result.stored) throw new Error(result.error || 'Publication unavailable');
  return result.imageUrl;
}
/**
 * Call OpenRouter directly with a user-provided API key (BYOK path).
 */
export async function generateDirect(apiKey, prompt, signal) {
  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": window.location.origin,
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [{ role: "user", content: prompt }],
      modalities: ["image", "text"],
      image_config: { aspect_ratio: "2:3", image_size: "1K" },
    }),
    signal,
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`OpenRouter ${response.status}: ${errText.slice(0, 200)}`);
  }

  const data = await response.json();
  const images = data.choices?.[0]?.message?.images;
  if (!images || images.length === 0) {
    throw new Error("Model returned no image");
  }

  const imageUrl = images[0].image_url?.url || images[0].url;
  if (!imageUrl) {
    throw new Error("Malformed image object in response");
  }

  return imageUrl;
}

function waitForPoll(signal) {
  return new Promise((resolve,reject)=>{
    const abort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
    const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},RETRY_DELAY_MS);
    if (signal?.aborted) return abort();
    signal?.addEventListener('abort',abort,{once:true});
  });
}
/** One paid-admission POST; subsequent waiting requests read only the cache. */
export async function generateServerless(cardRequest, signal, _retryCount = 0, force = false) {
  const grant=getCardCapability(cardRequest.handle,'generate');
  let response = await fetch("/api/generate-card", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(grant ? {Authorization:`Bearer ${grant}`} : {}) },
    body: JSON.stringify({ ...cardRequest, force }),
    signal,
  });

  for (let poll=0;response.status===202 && poll<MAX_RETRIES;poll++) {
    await waitForPoll(signal);
    response=await fetch(`/api/card-status?handle=${encodeURIComponent(cardRequest.handle)}`,{method:'GET',signal,cache:'no-store'});
  }
  if (response.status===202) {
    throw Object.assign(new Error('Generation is still in progress; check the card again shortly'),{code:'in_progress'});
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(new Error(body.error || `Server error ${response.status}`), {code:body.code});
  }

  const data = await response.json();
  if (typeof data.imageUrl!=='string' || !data.imageUrl) throw Object.assign(new Error('No card image returned'),{code:'invalid_image_response'});
  return { imageUrl: data.imageUrl, cached: data.cached };
}
