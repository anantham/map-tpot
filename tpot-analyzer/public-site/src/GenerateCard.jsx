/**
 * GenerateCard.jsx — Custom hook for JIT collectible card generation.
 *
 * Handles two paths:
 *  1. BYOK (Bring Your Own Key): calls OpenRouter directly from the browser
 *  2. Serverless: calls /api/generate-card which manages cache + budget
 *
 * Returns { imageUrl, status } where status is one of:
 *   'idle' | 'generating' | 'generated' | 'error' | 'exhausted'
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { buildCardRequest } from "./cardPrompt";
import { buildLegacyCardPrompt } from "./legacyCardPrompt";

const LOCALSTORAGE_KEY = "openrouter_key";
const MAX_FREE_GENS = 10;

import {getCachedCard,cacheCard,clearCachedCard,getGenCount,incrementGenCount} from "./cardCache";
export {getCachedVersions,getAllCachedCards,cacheCard} from "./cardCache";
import {generateDirect,generateServerless,publishApprovedCard} from "./cardTransport";
import {getCardCapability} from "./cardCapabilities";
/**
 * Custom hook for card generation.
 *
 * @param {Object} params
 * @param {string} params.handle
 * @param {string|null} params.bio
 * @param {Array} params.memberships
 * @param {string[]} params.sampleTweets
 * @param {Map} params.communityMap
 * @param {string} params.tier
 * @returns {{ imageUrl: string|null, status: 'idle'|'generating'|'generated'|'error'|'exhausted' }}
 */
export function useCardGeneration({ handle, bio, memberships, sampleTweets, communityMap, tier }) {
  const [imageUrl, setImageUrl] = useState(null);
  const [status, setStatus] = useState("idle");
  const [publicationStatus,setPublicationStatus] = useState("idle");
  const [remaining, setRemaining] = useState(() => Math.max(0, MAX_FREE_GENS - getGenCount()));
  const inflightRef = useRef(null); // tracks current in-flight handle
  const abortRef = useRef(null);
  const skipCacheRef = useRef(false);

  const generate = useCallback(async () => {
    // Only generate for accounts with communities
    if (!handle || !memberships || memberships.length === 0) {
      return;
    }

    // Debounce: skip if already generating for this handle
    if (inflightRef.current === handle) {
      return;
    }

    // Check cache first — skip API call if we have a cached card
    const isForceRegen = skipCacheRef.current;
    if (!isForceRegen) {
      const cached = getCachedCard(handle);
      if (cached) {
        setImageUrl(cached.url);
        setStatus("generated");
        return;
      }
    }
    skipCacheRef.current = false; // reset after use

    // Check per-user limit (skip for BYOK users)
    let byokKey = null;
    try { byokKey = localStorage.getItem(LOCALSTORAGE_KEY); } catch {}

    if (!byokKey && getGenCount() >= MAX_FREE_GENS) {
      setStatus("user_exhausted");
      setRemaining(0);
      return;
    }

    // Abort any previous in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }

    inflightRef.current = handle;
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("generating");
    setImageUrl(null);

    try {
      const cardRequest = buildCardRequest({
        handle,
        bio,
        memberships,
        sampleTweets,
        communityMap,
      });

      let url;
      let isCached = false;
      if (byokKey) {
        // Direct call with user's key
        const prompt = buildLegacyCardPrompt(cardRequest);
        url = await generateDirect(byokKey, prompt, controller.signal);
      } else {
        // Serverless path — force=true when regenerating to bust server cache
        const res = await generateServerless(cardRequest, controller.signal, 0, isForceRegen);
        url = res.imageUrl;
        isCached = res.cached;
      }

      // Only update state if this is still the current request
      if (inflightRef.current === handle) {
        setImageUrl(url);
        setStatus("generated");
        // Cache the generated card for instant recall
        cacheCard(handle, url);
        // Increment per-user generation count (only for serverless path and if not cached)
        if (!byokKey && !isCached) {
          const newCount = incrementGenCount();
          setRemaining(Math.max(0, MAX_FREE_GENS - newCount));
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        // Request was superseded, don't update state
        return;
      }

      if (inflightRef.current === handle) {
        if (["authorization_required","invalid_grant","regeneration_not_authorized"].includes(err.code)) {
          setStatus("authorization_required");
        } else if (err.code === "budget_exhausted") {
          setStatus("exhausted");
        } else if (err.code === "in_progress") {
          setStatus("waiting");
        } else {
          setStatus("error");
          console.error("[GenerateCard] Generation failed:", err.message);
        }
      }
    } finally {
      if (inflightRef.current === handle) {
        inflightRef.current = null;
      }
    }
  }, [handle, bio, memberships, sampleTweets, communityMap]);

  // Trigger generation when handle changes
  useEffect(() => {
    if (handle && memberships && memberships.length > 0) {
      generate();
    }

    return () => {
      // Cleanup on unmount or handle change
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [handle]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const refresh = event => {
      if (!handle || event.detail?.handle !== handle.toLowerCase()) return;
      if (event.detail.kind==='gallery') setPublicationStatus('ready');
      else generate();
    };
    window.addEventListener("card-capability-added",refresh);
    return () => window.removeEventListener("card-capability-added",refresh);
  },[generate]);

  useEffect(()=>{
    setPublicationStatus(handle && imageUrl?.startsWith('data:image/') && getCardCapability(handle,'gallery') ? 'ready' : 'idle');
  },[handle,imageUrl]);

  const publish = useCallback(async () => {
    if (!imageUrl || !imageUrl.startsWith('data:image/')) return;
    setPublicationStatus('publishing');
    try {
      const cardRequest=buildCardRequest({handle,bio,memberships,sampleTweets,communityMap});
      const communities=cardRequest.communities.slice(0,5).map(({name,color,weight})=>({name,color,weight}));
      await publishApprovedCard({handle,imageUrl,communities});
      setPublicationStatus('published');
    } catch {setPublicationStatus('error');}
  },[handle,imageUrl,bio,memberships,sampleTweets,communityMap]);

  const regenerate = useCallback(() => {
    if (!handle) return;
    // Clear local cache
    clearCachedCard(handle);
    // Clear inflight lock so generate() doesn't skip
    inflightRef.current = null;
    // Skip cache on next generate call
    skipCacheRef.current = true;
    // Trigger
    generate();
  }, [handle, generate]);

  return { imageUrl, status, remaining, regenerate, publish, publicationStatus };
}
