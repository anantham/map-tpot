# Handover: 2026-03-24 (Session 10c — Edge Enrichment + Independent Propagation + Deploy)

## Session Summary
Massive edge enrichment session: +123K edges (441K → 564K, +28%). Found and fixed critical API bug (`followings` key, not `data`). Built resumable edge fetcher with cursor persistence. Deployed independent propagation mode to production (13,360 accounts, 1,362 bridges). Chrome-audited 28 accounts. Fixed export UUID bug. Updated About page (dejargoned, linked sources, honest recall). Tech debt scan completed (14 items).

## Resume Instructions
1. **Check Round 1**: `sqlite3 data/archive_tweets.db "SELECT COUNT(DISTINCT account_id) FROM enrichment_log WHERE round = 1"` (was 23/50)
2. **If Round 1 done**: run `--measure`, re-propagate (independent mode), re-export, deploy
3. **Fix seed-neighbor counting**: use `community_account` weights instead of processed boundary (threshold > 0.1 → > 0 is a hack, need proper fix using raw weights)
4. **Continue Tier 2 edge fetch**: `scripts/fetch_edges_resumable.py --continue-incomplete --max-pages 15`
5. **Label 6 accounts**: `--accounts AaronBergman18,ilex_ulmus,eenthymeme,dissproportion,bayeslord,AlexKrusz`
6. **About page voice rewrite**: Path C needs Scott Alexander style, not technical changelog. See `memory/feedback_about_page_voice.md`

## Key Context

### API Bug (CRITICAL for future work)
twitterapi.io `user/followings` returns `{"followings": [...]}` NOT `{"data": [...]}`. Our ad-hoc scripts read `data` and got empty arrays. `fetch_following_for_frontier.py` was already correct. `fetch_edges_resumable.py` is correct. Schema Guesser anti-pattern added to CLAUDE.md.

### Graph State
- **564,293 edges** (was 441K at session start)
- **6,865 source accounts** with outbound edges
- `edge_fetch_state` table tracks cursor per account for resume
- `tier2_fetch_queue.txt`: 1,711 prioritized accounts to fetch
- 5 truly private accounts (Chrome can't see either): @tracewoodgrains, @lioninawhat
- API credits ran out once (402), recharged within minutes

### Independent Propagation (deployed)
- `--mode independent`: each community propagated separately, scores don't sum to 1
- 13,360 accounts exported (t=0.02, seed_neighbors >= 1)
- 1,362 bridges detected (was 0 in classic mode)
- Seed-neighbor counting has a bug: threshold `> 0.1` on processed boundary filters out all seeds after class balancing. Needs fix: use `community_account.weight` directly.
- NPZ saves `seed_neighbor_counts` + `mode` for downstream use

### Export Pipeline
- `_extract_bits_accounts` now resolves short_name → UUID (was showing "Unknown")
- CI formula adapts: independent mode uses `weight × neighbor_factor`
- `min_weight=0.02` in `config/public_site.json`
- 338 exemplars (317 NMF + 21 LLM)

### Recall (honest numbers on About page)
| Source | In-graph | Total |
|--------|----------|-------|
| Multi-source (3+) | 65% | 65% |
| Strangest Loop | 64% | 52% |
| Orange TPOT | 54% | 33% |
| Ego follows | 30% | 30% |

### DB Tables Created This Session
- `chrome_audit_log`: 57 tweet-level audit records
- `chrome_audit_findings`: 5 systemic findings
- `quality_candidates`: 256 accounts ranked by TPOT-following concentration
- `edge_fetch_state`: cursor persistence for resumable edge fetching
- `None` community row in `community` table

### Running Processes
- **Round 1 active learning**: check `SELECT COUNT(DISTINCT account_id) FROM enrichment_log WHERE round = 1`
- **Tier 2 edge fetch**: may still be running, check `edge_fetch_state` for progress

### Files Created/Modified
- `scripts/fetch_edges_resumable.py` — NEW: resumable edge fetcher
- `docs/HOLDOUT_SOURCES.md` — NEW: 4 ground truth sources documented
- `docs/PROPAGATION_ANALYSIS.md` — NEW: independent mode analysis
- `docs/TECH_DEBT_SCAN_2026-03-24.md` — NEW: 14 tech debt items
- `docs/superpowers/specs/2026-03-24-independent-community-propagation-design.md` — NEW

---
*Handover by Claude Opus 4.6 at ~75% context*
