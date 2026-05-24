"""Private helpers for `scripts/active_learning.py`.

Split by phase: account selection (frontier_ranking + handle resolution),
LLM labeling (per-tweet enrichment + ensemble call), reporting (profile
classification + inter-model agreement), measurement (rollup + seed insert).

active_learning.py re-exports each function so tests using
`from scripts.active_learning import X` keep working.
"""
