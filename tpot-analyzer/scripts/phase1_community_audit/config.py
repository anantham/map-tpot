"""Shared config for the Phase 1 community-correctness audit."""
from __future__ import annotations

from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "archive_tweets.db"
DEFAULT_MODEL = "x-ai/grok-4.20-multi-agent-beta"
DEFAULT_OUTPUT_DIR = DATA_DIR / "outputs" / "phase1_membership_audit"
DEFAULT_MANIFEST_PATH = DATA_DIR / "evals" / "phase1_membership_audit_accounts.json"
DEFAULT_REVIEW_CSV_PATH = DATA_DIR / "evals" / "phase1_membership_audit_review_sheet.csv"
DEFAULT_RESULTS_JSONL_PATH = DEFAULT_OUTPUT_DIR / "membership_audit_results.jsonl"
DEFAULT_HARD_NEGATIVE_PATH = DEFAULT_OUTPUT_DIR / "hard_negative_suggestions.json"
DEFAULT_MEMBERSHIP_PROMPT_PATH = (
    PROJECT_ROOT / "docs" / "reference" / "evals" / "prompts" / "grok-420-membership-audit.md"
)
DEFAULT_HARD_NEGATIVE_PROMPT_PATH = (
    PROJECT_ROOT / "docs" / "reference" / "evals" / "prompts" / "grok-420-hard-negatives.md"
)


BUCKET_ORDER = ("core", "boundary", "hard_negative")
EXPECTED_BUCKET_COUNTS = {"core": 12, "boundary": 12, "hard_negative": 12}
try:
    from scripts.phase1_community_audit.slate import PHASE1_SLATE
except ImportError:  # pragma: no cover - direct script execution from scripts/
    from phase1_community_audit.slate import PHASE1_SLATE
