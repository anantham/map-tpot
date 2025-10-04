"""Seed selection utilities."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Set

_DEFAULT_SEED_FILE = Path(__file__).resolve().parents[2] / "docs" / "seed_presets.json"

DEFAULT_SEEDS: Set[str] = set()
if _DEFAULT_SEED_FILE.exists():
    DEFAULT_SEEDS = set(json.loads(_DEFAULT_SEED_FILE.read_text()).get("adi_tpot", []))


def extract_usernames_from_html(html: str) -> List[str]:
    """Pull Twitter usernames from list HTML or text."""

    pattern = re.compile(r"@([A-Za-z0-9_]{1,15})")
    usernames = {match.group(1).lower() for match in pattern.finditer(html)}
    # Sort alphabetically while preferring handles without underscores.
    return sorted(usernames, key=lambda u: (u.replace("_", ""), u.count("_"), u))


def load_seed_candidates(*, additional: Iterable[str] = ()) -> Set[str]:
    """Return combined seed set (defaults + user provided)."""

    seeds = set(DEFAULT_SEEDS)
    seeds.update(username.lower() for username in additional)
    return seeds
