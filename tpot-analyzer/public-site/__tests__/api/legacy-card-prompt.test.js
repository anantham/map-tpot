// @vitest-environment node

import { describe, expect, it } from "vitest";
import promptModule from "../../api/_legacyCardPrompt.js";

const { buildLegacyCardPrompt } = promptModule.default || promptModule;

describe("server buildLegacyCardPrompt", () => {
  it("turns mixed-scale scores into rank-only exploratory motifs", () => {
    const prompt = buildLegacyCardPrompt({
      handle: "alice",
      bio: "thinks about graphs",
      communities: [
        { name: "Small", short_name: "small", color: "#222", weight: 0.01 },
        { name: "Large", short_name: "large", color: "#111", weight: 73.3335 },
        { name: "Signed", short_name: "signed", color: "#333", weight: -2 },
      ],
      tweets: ["Networks are contextual."],
      iconography: {
        large: {
          mascot: "a lantern",
          sigil: "a branching star",
          color_names: "indigo and gold",
          elemental_vibe: "patient inquiry",
          card_integration: "lantern-light tracing a graph",
          flag_motif: "nested arcs",
          accent_when_secondary: "a small thread of light",
          texture_when_tertiary: "faint branching lines",
        },
      },
    });

    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 1: Large");
    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 2: Small");
    expect(prompt).toContain("LEGACY EXPLORATORY AFFINITY RANK 3: Signed");
    expect(prompt).toContain("Mascot energy: a lantern");
    expect(prompt).not.toMatch(/73\.3335|0\.01|%/);
  });

  it("explicitly rejects membership semantics in the generated art direction", () => {
    const prompt = buildLegacyCardPrompt({
      handle: "alice",
      bio: null,
      communities: [{ name: "Large", color: "#111", weight: 73.3335 }],
      tweets: [],
      iconography: null,
    });

    expect(prompt).toMatch(/uncalibrated/i);
    expect(prompt).toMatch(/not membership probabilities/i);
    expect(prompt).toMatch(/visual motifs/i);
    expect(prompt).not.toMatch(/PRIMARY COMMUNITY|SECONDARY COMMUNITY|TERTIARY COMMUNITY/);
    expect(prompt).not.toMatch(/FEEL (?:the )?community membership/i);
  });
});
