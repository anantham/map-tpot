import { describe, expect, it } from "vitest";
import { buildLegacyCardPrompt } from "./legacyCardPrompt";

const communities = [
  {
    name: "Tiny Affinity",
    color: "#222222",
    description: "A low-valued but still ranked signal",
    weight: 0.01,
  },
  {
    name: "Large-Scale Affinity",
    color: "#111111",
    description: "A score from a producer whose scale exceeds one",
    weight: 73.3335,
  },
  {
    name: "Negative Affinity",
    color: "#333333",
    description: "A signed score",
    weight: -2,
  },
];

describe("buildLegacyCardPrompt", () => {
  it("uses score order only, without rendering mixed-scale values or thresholds", () => {
    const prompt = buildLegacyCardPrompt({
      handle: "alice",
      bio: "thinks about graphs",
      communities,
      tweets: ["Networks are contextual."],
    });

    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 1: Large-Scale Affinity");
    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 2: Tiny Affinity");
    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 3: Negative Affinity");
    expect(prompt).not.toContain("73.3335");
    expect(prompt).not.toContain("0.01");
    expect(prompt).not.toContain("%");
  });

  it("states that the ranked motifs are uncalibrated and not membership", () => {
    const prompt = buildLegacyCardPrompt({
      handle: "alice",
      bio: null,
      communities,
      tweets: [],
    });

    expect(prompt).toMatch(/uncalibrated/i);
    expect(prompt).toMatch(/not membership probabilities/i);
    expect(prompt).toMatch(/visual motifs/i);
    expect(prompt).not.toMatch(/PRIMARY COMMUNITY|SECONDARY COMMUNITY|TERTIARY COMMUNITY/);
    expect(prompt).not.toMatch(/FEEL (?:the )?community membership/i);
  });
});
