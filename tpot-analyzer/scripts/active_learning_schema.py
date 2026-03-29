"""Schema definitions for active learning pipeline tables."""
import sqlite3

ENRICHED_TWEETS_DDL = """\
CREATE TABLE IF NOT EXISTS enriched_tweets (
    tweet_id      TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL,
    username      TEXT NOT NULL,
    text          TEXT NOT NULL,
    like_count    INTEGER DEFAULT 0,
    retweet_count INTEGER DEFAULT 0,
    reply_count   INTEGER DEFAULT 0,
    view_count    INTEGER DEFAULT 0,
    created_at    TEXT,
    lang          TEXT,
    is_reply      INTEGER DEFAULT 0,
    in_reply_to_user TEXT,
    has_media     INTEGER DEFAULT 0,
    mentions_json TEXT DEFAULT '[]',
    fetch_source  TEXT NOT NULL,
    fetch_query   TEXT,
    fetched_at    TEXT NOT NULL
);
"""

ENRICHED_TWEETS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_enriched_tweets_account ON enriched_tweets(account_id);",
    "CREATE INDEX IF NOT EXISTS idx_enriched_tweets_source ON enriched_tweets(fetch_source);",
]

ENRICHMENT_LOG_DDL = """\
CREATE TABLE IF NOT EXISTS enrichment_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     TEXT NOT NULL,
    username       TEXT NOT NULL,
    round          INTEGER NOT NULL,
    action         TEXT NOT NULL,
    query          TEXT,
    api_calls      INTEGER DEFAULT 1,
    tweets_fetched INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0.03,
    created_at     TEXT NOT NULL
);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Create enriched_tweets and enrichment_log tables. Idempotent."""
    conn.execute(ENRICHED_TWEETS_DDL)
    for idx in ENRICHED_TWEETS_INDEXES:
        conn.execute(idx)
    conn.execute(ENRICHMENT_LOG_DDL)
    conn.commit()
