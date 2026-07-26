"""Shared constants and result types for Community Archive snapshots."""
from __future__ import annotations

from dataclasses import dataclass


MANIFEST_FILENAME = "manifest.json"
DATA_FILENAME = "enriched_tweets.parquet"
MANIFEST_SCHEMA_VERSION = 1
SNAPSHOT_KIND = "community_archive_enriched_tweets"
REQUIRED_COLUMNS = {
    "tweet_id",
    "account_id",
    "username",
    "created_at",
    "full_text",
    "archive_upload_id",
}


@dataclass(frozen=True)
class SnapshotCheck:
    name: str
    passed: bool
    detail: str
