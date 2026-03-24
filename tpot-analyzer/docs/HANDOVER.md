# Handover: 2026-03-24 (Session 10 Final — Edge Enrichment + Independent Propagation + NMF v2 + Deploy)

## Session Summary
Massive session across 10a/10b/10c: graph grew 85% (441K → 815K edges, 297K nodes). Found and fixed critical API bug (`followings` key). Built resumable edge fetcher. Shifted propagation from zero-sum to independent mode (17,634 searchable accounts, 1,974 bridges). Chrome-audited 28 accounts (57 tweets). NMF v2 validated ontology (11/16 strong match). Round 1 active learning: 26/50 accounts, $2.55. About page dejargoned + honest recall. Tech debt scan (14 items).

## Resume Instructions
1. **Seed-neighbor fix**: ~~DONE~~ (session 11) — uses raw `community_account.weight` instead of class-balanced boundary
2. **Re-propagate + re-export + deploy**: now that seed-neighbor fix is in, re-run propagation and export
3. **About page voice rewrite**: Path C needs Scott Alexander style. See `memory/feedback_about_page_voice.md`
4. **Round 1 remaining 24 accounts**: `--round 1 --top 24 --budget 2.50`
5. **Label 6 accounts**: `--accounts AaronBergman18,ilex_ulmus,eenthymeme,dissproportion,bayeslord,AlexKrusz`
6. **Continue Tier 2 edge fetch**: `scripts/fetch_edges_resumable.py --continue-incomplete --max-pages 15`
7. **NMF v2 promotion decision**: needs formal factor alignment score, then human review of 3 shifted communities

## Key Context

### API Bug (CRITICAL for future work)
twitterapi.io `user/followings` returns `{"followings": [...]}` NOT `{"data": [...]}`. Schema Guesser anti-pattern added to CLAUDE.md.

### Graph State (final)
- **815,363 edges** (was 441K at session start, +85%)
- **297,402 nodes** (was 201K, +47%)
- **352 seeds** (338 NMF + 14 Round 1)
- `edge_fetch_state` table tracks cursor per account for resume
- 5 protected accounts: @tracewoodgrains, @lioninawhat, @teleosistem, @grantadever, @HamishDoodles
- 3 deleted/renamed: @sashachapin, @chairsign, @prerationalist

### Independent Propagation (deployed)
- `--mode independent`: each community propagated separately, scores don't sum to 1
- 17,634 accounts exported (t=0.02, seed_neighbors >= 1)
- 1,974 bridges detected (was 0 in classic mode)
- Seed-neighbor counting fix: now uses raw `community_account.weight` directly (not class-balanced boundary)
- NPZ saves `seed_neighbor_counts` + `mode` for downstream use

### NMF v2 Validation
- Re-ran NMF (k=16, with likes) on 800K-edge graph
- 11/16 communities strongly match v1, 3 partial (Core TPOT narrowed, Sensemaking split, Essayists merged)
- Saved as branch `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95` — NOT promoted to primary yet
- See `docs/NMF_V2_VALIDATION.md`

### Export Pipeline
- `_extract_bits_accounts` resolves short_name → UUID
- CI formula: independent mode uses `weight × neighbor_factor`
- `min_weight=0.02` in `config/public_site.json`
- 338 exemplars, 4,831 specialists, 1,974 bridges, 1,097 frontier

### Key Numbers
| Metric | Session start | Session end |
|--------|-------------|-------------|
| Graph edges | 441,226 | 815,363 |
| Graph nodes | 201,723 | 297,402 |
| Searchable accounts | 13,360 | 17,634 |
| Bridges | 1,362 | 1,974 |
| Seeds | 338 | 352 |

### DB Tables Created This Session
- `chrome_audit_log`: 57 tweet-level audit records
- `chrome_audit_findings`: 5 systemic findings
- `quality_candidates`: 256 accounts ranked by TPOT-following concentration
- `edge_fetch_state`: cursor persistence for resumable edge fetching
- `protected_accounts`: 5 protected + 3 deleted/renamed
- `None` community row in `community` table

### Documentation Created
- `docs/SESSION10_IDEAS_INVENTORY.md` — 45 shipped, 6 designed, 4 blocked, 9 deferred
- `docs/HOLDOUT_SOURCES.md` — 4 ground truth sources
- `docs/PROPAGATION_ANALYSIS.md` — independent mode analysis
- `docs/NMF_V2_VALIDATION.md` — v2 factor alignment
- `docs/TECH_DEBT_SCAN_2026-03-24.md` — 14 tech debt items

---
*Handover updated by Claude Opus 4.6 (session 11)*
