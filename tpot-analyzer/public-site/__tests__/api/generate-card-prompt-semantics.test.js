// @vitest-environment node

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import lib from "../../api/_lib.js";
import handlerModule from "../../api/generate-card.js";
import admission from "../../api/_cardAdmission.js";
import fixture from "./_redisFixture.cjs";
import sharp from "sharp";
import { mockReq, mockRes } from "./_helpers";

const handler = handlerModule.default || handlerModule;
const { __reset, __setForTesting } = lib.default || lib;
const redis = fixture.testRedis(3);

describe.skipIf(!redis)("generate-card prompt semantics", () => {
  beforeEach(async () => {
    Object.assign(process.env,{OPENROUTER_API_KEY:"test-key",CARD_CAPABILITY_SECRET:"synthetic-signing-key-with-at-least-32-bytes",CARD_SPONSORED_ENABLED:"true",CARD_DAILY_BUDGET:"5",CARD_REQUEST_RESERVATION_USD:"0.5",CARD_BLOB_BASE_URL:"https://teststore.public.blob.vercel-storage.com"});
    await redis.raw.connect();await redis.raw.flushdb();__reset();
    __setForTesting({kv:redis.kv,blobPut:async path=>({url:process.env.CARD_BLOB_BASE_URL+"/"+path})});
    const image="data:image/png;base64,"+(await sharp({create:{width:2,height:3,channels:3,background:"#123456"}}).png().toBuffer()).toString("base64");
    globalThis.fetch=vi.fn(async()=>new Response(JSON.stringify({choices:[{message:{images:[{image_url:{url:image}}]}}]}),{status:200}));
  });
  afterEach(async () => {__reset();await redis.raw.quit();});
  it("sends rank-only legacy affinity context to OpenRouter", async () => {
    const res = mockRes();
    const body = {
        handle: "alice",
        communities: [
          { name: "Small", color: "#222", weight: 0.01 },
          { name: "Large", color: "#111", weight: 73.3335 },
          { name: "Signed", color: "#333", weight: -2 },
        ],
        tweets: [],
      };
    const token=admission.signCapability({kind:"generate",handle:body.handle,digest:admission.digestBody(body),subject:"synthetic-owner",expiresAt:Math.floor(Date.now()/1000)+300});
    await handler(mockReq({method:"POST",body,headers:{authorization:"Bearer "+token}}),res);

    const requestBody = JSON.parse(globalThis.fetch.mock.calls[0][1].body);
    const prompt = requestBody.messages[0].content;

    expect(res.statusCode).toBe(200);
    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 1: Large");
    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 3: Signed");
    expect(prompt).toMatch(/uncalibrated and not membership probabilities/i);
    expect(prompt).not.toMatch(/73\.3335|0\.01|%/);
    expect(prompt).not.toMatch(/PRIMARY COMMUNITY|SECONDARY COMMUNITY|TERTIARY COMMUNITY/);
  });
});
