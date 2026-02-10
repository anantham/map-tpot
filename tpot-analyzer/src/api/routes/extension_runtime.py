"""Shared runtime dependencies for extension routes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.config import get_snapshot_dir
from src.data.account_tags import AccountTagStore
from src.data.feed_firehose import FeedFirehoseWriter
from src.data.feed_scope_policy import FeedScopePolicyStore
from src.data.feed_signals import FeedSignalsStore
from src.data.feed_signals_admin import FeedSignalsAdminStore

_feed_store: Optional[FeedSignalsStore] = None
_feed_admin_store: Optional[FeedSignalsAdminStore] = None
_feed_policy_store: Optional[FeedScopePolicyStore] = None
_tag_store: Optional[AccountTagStore] = None
_firehose_writer: Optional[FeedFirehoseWriter] = None


def _snapshot_db_path(name: str) -> Path:
    return Path(get_snapshot_dir()) / name


def get_feed_store() -> FeedSignalsStore:
    global _feed_store
    if _feed_store is None:
        _feed_store = FeedSignalsStore(_snapshot_db_path("feed_signals.db"))
    return _feed_store


def get_feed_admin_store() -> FeedSignalsAdminStore:
    global _feed_admin_store
    if _feed_admin_store is None:
        _feed_admin_store = FeedSignalsAdminStore(_snapshot_db_path("feed_signals.db"))
    return _feed_admin_store


def get_feed_policy_store() -> FeedScopePolicyStore:
    global _feed_policy_store
    if _feed_policy_store is None:
        _feed_policy_store = FeedScopePolicyStore(_snapshot_db_path("feed_signals.db"))
    return _feed_policy_store


def get_tag_store() -> AccountTagStore:
    global _tag_store
    if _tag_store is None:
        _tag_store = AccountTagStore(_snapshot_db_path("account_tags.db"))
    return _tag_store


def get_firehose_writer() -> FeedFirehoseWriter:
    global _firehose_writer
    if _firehose_writer is None:
        default_path = _snapshot_db_path("indra_net/feed_events.ndjson")
        env_override = os.getenv("TPOT_EXTENSION_FIREHOSE_PATH")
        if env_override and env_override.strip():
            default_path = Path(env_override).expanduser().resolve()
        _firehose_writer = FeedFirehoseWriter(default_path=default_path)
    return _firehose_writer


def reset_extension_runtime() -> None:
    """Test helper: clear singleton stores so each fixture gets fresh state."""
    global _feed_store, _feed_admin_store, _feed_policy_store, _tag_store, _firehose_writer
    _feed_store = None
    _feed_admin_store = None
    _feed_policy_store = None
    _tag_store = None
    _firehose_writer = None
