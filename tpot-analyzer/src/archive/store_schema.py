"""SQLite schema for bounded archive persistence."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id          TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL,
    username          TEXT NOT NULL,
    full_text         TEXT NOT NULL,
    created_at        TEXT,
    reply_to_tweet_id TEXT,
    reply_to_username TEXT,
    favorite_count    INTEGER DEFAULT 0,
    retweet_count     INTEGER DEFAULT 0,
    lang              TEXT,
    is_note_tweet     INTEGER DEFAULT 0,
    fetched_at        TEXT
);

CREATE TABLE IF NOT EXISTS likes (
    liker_account_id  TEXT NOT NULL,
    liker_username    TEXT NOT NULL,
    tweet_id          TEXT NOT NULL,
    full_text         TEXT,
    expanded_url      TEXT,
    fetched_at        TEXT,
    PRIMARY KEY (liker_account_id, tweet_id)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    username          TEXT PRIMARY KEY,
    account_id        TEXT,
    status            TEXT,
    tweet_count       INTEGER DEFAULT 0,
    like_count        INTEGER DEFAULT 0,
    error_message     TEXT,
    fetched_at        TEXT
);

CREATE TABLE IF NOT EXISTS thread_context_cache (
    tweet_id      TEXT PRIMARY KEY,
    raw_json      TEXT NOT NULL,
    fetched_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tweets_account ON tweets(account_id);
CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_likes_account  ON likes(liker_account_id);

CREATE TABLE IF NOT EXISTS profiles (
    account_id    TEXT PRIMARY KEY,
    username      TEXT NOT NULL,
    display_name  TEXT,
    bio           TEXT,
    location      TEXT,
    website       TEXT,
    created_at    TEXT,
    fetched_at    TEXT
);

-- Who an account follows (their intentional choices — strongest community signal)
CREATE TABLE IF NOT EXISTS account_following (
    account_id           TEXT NOT NULL,
    following_account_id TEXT NOT NULL,
    PRIMARY KEY (account_id, following_account_id)
);
CREATE INDEX IF NOT EXISTS idx_following_account ON account_following(account_id);
CREATE INDEX IF NOT EXISTS idx_following_target  ON account_following(following_account_id);

-- Who follows an account (inbound, separate from following because archive stores both)
CREATE TABLE IF NOT EXISTS account_followers (
    account_id          TEXT NOT NULL,
    follower_account_id TEXT NOT NULL,
    PRIMARY KEY (account_id, follower_account_id)
);
CREATE INDEX IF NOT EXISTS idx_followers_account ON account_followers(account_id);

-- Retweet metadata: who they amplify, without storing the RT text (not their words)
CREATE TABLE IF NOT EXISTS retweets (
    tweet_id         TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL,
    username         TEXT NOT NULL,
    rt_of_username   TEXT,
    created_at       TEXT,
    fetched_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_retweets_account ON retweets(account_id);
CREATE INDEX IF NOT EXISTS idx_retweets_rt_of   ON retweets(rt_of_username);
"""
