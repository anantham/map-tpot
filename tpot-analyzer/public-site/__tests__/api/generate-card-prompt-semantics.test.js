// @vitest-environment node

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import lib from "../../api/_lib.js";
import handlerModule from "../../api/generate-card.js";
import { mockReq, mockRes } from "./_helpers";

const handler = handlerModule.default || handlerModule;
const { __reset, __setForTesting } = lib.default || lib;

describe("generate-card prompt semantics", () => {
  beforeEach(() => {
    process.env.OPENROUTER_API_KEY = "test-key";
    __reset();
    __setForTesting({ kv: null, blobPut: null });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        choices: [{
          message: {
            images: [{ image_url: { url: "https://example.test/card.png" } }],
          },
        }],
      }),
    });
  });

  afterEach(() => {
    __reset();
  });

  it("sends rank-only legacy affinity context to OpenRouter", async () => {
    const res = mockRes();
    await handler(mockReq({
      method: "POST",
      body: {
        handle: "alice",
        communities: [
          { name: "Small", color: "#222", weight: 0.01 },
          { name: "Large", color: "#111", weight: 73.3335 },
          { name: "Signed", color: "#333", weight: -2 },
        ],
        tweets: [],
      },
    }), res);

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
