"""Data models for twitterapi.io shadow audit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set


@dataclass
class RemoteResult:
    usernames: Set[str]
    pages_fetched: int
    requests_made: int
    endpoint: str
    identifier_param: str
    status_codes: List[int]
    errors: List[str]
