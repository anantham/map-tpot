# Handover: 2026-03-28 (Session 11 Final)

## Architecture

**ADR 016 accepted:** Four-part epistemic architecture.
```
Events → Fingerprints → Derived Views → Task Heads
```
Graph is the backbone, not the ontology. Fingerprints are the primary representation. See `docs/adr/016-four-part-epistemic-architecture.md` and `docs/ROADMAP_NEXT.md` for details.

## What's Running

**Bulk archive-only labeling** — 86 core accounts, free-tier LLMs, ~20h total.
```bash
# Check progress:
grep -c "triage=" /tmp/archive_labeling.log
# When done, re-run fingerprint rollup:
.venv/bin/python3 -m scripts.rollup_fingerprints
```

## Resume Instructions

1. **Check bulk labeling** — how many of 86 accounts finished?
2. **Re-run fingerprint rollup** — `scripts/rollup_fingerprints.py` (produces ~330 fingerprints with coverage metadata)
3. **Wire quote_graph (549K) + mention_graph (3.8M)** into `src/propagation/typed_graph.py` — ~20 lines
4. **Re-propagate + re-export + deploy** — fresh graph with all edge types
5. **Fingerprint → confidence** — use fingerprints at task-head layer (not inside solver)

## Session 11 Summary

### Built
- **TypedGraph** — 5 edge types as separate sparse matrices (follow, reply, like, RT, cofollowed)
- **Fingerprint rollup** — simulacrum + posture + theme + domain + cadence + coverage metadata for 61 accounts
- **Multi-scale tweet fetching** — Top + Recent + Latest + 3-month-old window, 30-day TTL
- **Archive-first loading** — check archive tweets before API (saves $0.10-0.15/account)
- **Reply fetching** — tweet/replies API, cached, selective (>= 3 replies)
- **Co-followed context** — "shares audience with" in labeling prompt
- **Modular context budget** — `--context all|minimal|bio,graph_signal,...` CLI flag
- **Sub-community facets** — 10 AI-Safety, 5 Contemplative, 4 LLM-Whisperers in glossary
- **Evidence summary** — frontend component showing per-community neighbor counts below card
- **Cache everything** — thread tweets, reply tweets, archive tweets all go into enriched_tweets
- **About page** — honest data story (330 archive contributors, not 26K)

### Key Experiments (see docs/EXPERIMENT_LOG.md)
- EXP-005: NMF vs tweets agree 42% — they capture different dimensions
- EXP-006: Phase 1 audit substrate ready
- EXP-007: Archive-only labeling confirmed ($0 API cost)

### Data State
- 359 seeds (317 NMF + 42 LLM)
- 61 accounts with fingerprints (growing to ~330 after bulk labeling)
- 881K edges in TypedGraph (follow 804K + reply 12K + like 24K + RT 7K + cofollowed 33K)
- 549K quote edges + 3.8M mention edges NOT YET WIRED
- 9,367 profiles, 15,182 bio embeddings
- 19,892 tweet tags, 1,985 label sets

### Key Design Decisions
- **Don't change the propagation solver.** Keep independent harmonic solve. Use fingerprints at the confidence/task-head layer, not inside the solver.
- **Keep bits/fingerprints separate from graph propagation.** Fingerprints are posterior evidence. Graph is structural. Combine at decision time.
- **Source rule for propagation:** only Core + stable Enriched can propagate outward. Graph-only accounts should never become sources.
- **Hypothesis-driven API spending:** rich core calibrates, graph frontier generates hypotheses, API validates specific accounts.

### Commits (session 11)
See `git log --oneline` — ~25 commits across TypedGraph, fingerprints, labeling enrichment, frontend, caching, architecture docs.

---
*Handover by Claude Opus 4.6 (session 11 final, ~95% context)*
