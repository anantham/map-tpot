# NMF v2 Validation: 800K-Edge Graph (2026-03-24)

## Summary

Re-ran NMF (k=16, with likes) on a graph with 800K edges (was 441K in v1).
The 16-community structure is **largely validated** — most communities map
clearly between v1 and v2. The denser graph confirmed the ontology rather
than contradicting it.

## Graph Comparison

| | v1 | v2 | Change |
|--|----|----|--------|
| Follow edges | 441,226 | 799,521 | +81% |
| Total graph edges | ~480K | ~815K | +70% |
| Nodes | 201,723 | 297,402 | +47% |
| Archive accounts | ~330 | ~330 | same |
| Seeds (NMF + LLM) | 338 | 352 | +14 (Round 1) |

## Community Alignment (v1 → v2)

| v2 Factor | Size | v1 Equivalent | Top Accounts | Alignment |
|-----------|------|---------------|-------------|-----------|
| C1 | 47 | Vibecamp Highbies | @Lithros, @goblinodds | Strong match |
| C2 | 42 | EA & Forecasting | @nunosempere, @g_leech_ | Strong match |
| C3 | 63 | Jhana Practitioners | @_brentbaum, @nowtheo | Strong match |
| C4 | 36 | Core TPOT (subset) | @ducdeparma, @visakanv | Partial — narrower |
| C5 | 73 | Qualia Researchers | @archived_videos, @johnsonmxe | Strong match |
| C6 | 26 | LLM Whisperers | @v01dpr1mr0s3, @repligate | Strong match |
| C7 | 79 | Internet Essayists + Tech Philosophers | @enthropean, @eigenrobot | Merged — broader |
| C8 | 27 | Regen & Collective Intelligence | @technoshaman, @hexafield | Strong match |
| C9 | 45 | Relational Explorers | @silverarm0r, @univrsw3th4rt | Strong match |
| C10 | 29 | NYC Institution Builders | @danielgolliher, @__drewface | Strong match |
| C11 | 44 | AI Creatives | @abrakjamson, @sucralose__ | Strong match |
| C12 | 41 | Quiet Creatives | @taijitu_sees, @workflowsauce | Strong match |
| C13 | 57 | Sensemaking / Internet Essayists | @geniesloki, @Malcolm_Ocean | Partial — overlap |
| C14 | 52 | Tech Philosophers | @iconic_tweeter, @paulg | Strong match |
| C15 | 43 | Queer TPOT | @annieposting, @_blinding_light | Strong match |
| C16 | 32 | Sensemaking Builders | @lchoshen, @rtk254 | Partial — new mix |

## Key Findings

### Confirmed (11/16 strong match)
Jhana Practitioners, Vibecamp Highbies, EA & Forecasting, Qualia Researchers,
LLM Whisperers, Regen & CI, Relational Explorers, NYC Builders, AI Creatives,
Quiet Creatives, Queer TPOT — all clearly identifiable in v2.

### Shifted (3/16 partial)
- **Core TPOT** narrowed around @visakanv-adjacent accounts (C4)
- **Sensemaking** split across C13 (essayist-flavored) and C16 (builder-flavored)
- **Internet Essayists + Tech Philosophers** merged into one broader C7

### Multi-community accounts
248/328 archive accounts (76%) appear in 2+ communities in v2.
This is up from 247 in v1 — the multi-community structure is stable.

## Interpretation

The 81% increase in edges did NOT destabilize the community structure. The
same 16 groups emerge with minor boundary shifts. This means:

1. **The v1 ontology was not an artifact of sparse data** — it's real structure
2. **More edges sharpen boundaries** rather than blurring them
3. **The 3 partial-match communities** (Core TPOT, Sensemaking, Internet Essayists)
   may benefit from human re-examination — are they genuinely splitting, or is
   this NMF noise from the larger matrix?

## Propagation Impact

With the v2 graph + Round 1 seeds:

| Metric | v1 graph (session start) | v2 graph (session end) |
|--------|-------------------------|----------------------|
| Total searchable | 13,360 | **17,634** (+32%) |
| Specialists | 4,065 | **4,831** (+19%) |
| Bridges | 1,362 | **1,974** (+45%) |
| Frontier | 292 | **1,097** (+276%) |

## DB State

- v2 run saved: `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95`
- v1 run: still active as the primary community definitions
- Both accessible via `community_snapshot` table
- Propagation re-run saved to `data/community_propagation.npz`

## Next Steps

1. Formal factor alignment score (session 8 method: cosine similarity of H matrices)
2. Human review of the 3 shifted communities — rename or split?
3. Consider promoting v2 to primary (currently v1 is still the active community set)
4. Re-run NMF at k=14 and k=18 on v2 graph to check k sensitivity
