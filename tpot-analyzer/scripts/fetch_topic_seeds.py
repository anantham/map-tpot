#!/usr/bin/env python3
"""Fetch tweets by semantic topic to seed active learning.

Runs searches for nuanced AI Safety and Alignment topics, dumping the tweets into `enriched_tweets`
and inserting the authors into `frontier_ranking` with an artificially high info_value
so the active learning ensemble naturally grades them next run.
"""
from __future__ import annotations

import argparse
import collections
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

from scripts.fetch_tweets_for_account import (
    BudgetExhaustedError,
    check_budget,
    fetch_advanced_search,
    log_api_call,
    parse_tweet,
    store_tweets,
)

logger = logging.getLogger(__name__)
TOPIC_SEED_ACCOUNT_ID = "__topic_seed_search__"
TOPIC_SEED_USERNAME = "topic_seed"

# Core topic queries derived from LessWrong state of AI Safety mapping
DEFAULT_QUERIES = [
    '"mechanistic interpretability" OR "sparse autoencoders" OR SAEs OR "features" -is:retweet min_faves:4',
    '"iterative alignment" OR "inoculation prompting" OR "capability removal" -is:retweet min_faves:3',
    '"agent foundations" OR "embedded agency" OR "logical induction" OR "decision theory" -is:retweet min_faves:4',
    '"developmental interpretability" OR "dev-interp" OR "singular learning theory" -is:retweet min_faves:3',
    '"corrigibility" OR "deceptive alignment" OR "mesa-optimization" -is:retweet min_faves:5',
    '"synthetic data for alignment" OR "data poisoning defense" -is:retweet min_faves:3',
]

def run_topic_fetch(
    conn: sqlite3.Connection,
    api_key: str,
    budget: float,
    queries: list[str] = DEFAULT_QUERIES,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    total_tweets = 0
    total_new_authors = 0
    
    unique_authors: dict[str, dict[str, str]] = {}

    for query in queries:
        logger.info("Executing search: %s", query)
        
        try:
            check_budget(conn, limit=budget, raise_on_exceed=True)
            
            # Fetch from Twitter
            raw_tweets = fetch_advanced_search(api_key, query=query, query_type="Top")
            fetch_count = len(raw_tweets)

            # Dynamic cost calculation
            cost = max(fetch_count * 0.00015, 0.00015) 
            log_api_call(
                conn,
                account_id=TOPIC_SEED_ACCOUNT_ID,
                username=TOPIC_SEED_USERNAME,
                round_num=0,
                action="advanced_search_topic_seed",
                tweets_fetched=fetch_count,
                query=query,
                cost=cost,
            )

            if not raw_tweets:
                logger.info("  No results found.")
                continue

            parsed = []
            for raw_tweet in raw_tweets:
                author = raw_tweet.get("author") or {}
                author_id = str(author.get("id") or "").strip()
                username = (author.get("userName") or "").strip()
                if not raw_tweet.get("id") or not author_id or not username:
                    logger.warning(
                        "  Skipping malformed advanced_search tweet: id=%s author_id=%s username=%s",
                        raw_tweet.get("id"),
                        author.get("id"),
                        author.get("userName"),
                    )
                    continue
                parsed.append(parse_tweet(raw_tweet, username))
                unique_authors[author_id] = {
                    "username": username,
                    "bio": (author.get("description") or "").strip(),
                }

            if not parsed:
                logger.info("  Search returned tweets, but none had parsable author/tweet fields.")
                continue

            # Store tweets
            inserted_tweets = store_tweets(
                conn, 
                parsed, 
                fetch_source="topic_seed", 
                fetch_query=query
            )
            total_tweets += inserted_tweets
            logger.info("  Stored %d new tweets for query", inserted_tweets)
        except BudgetExhaustedError as e:
            logger.error("Budget exhausted: %s", e)
            break
        except Exception as e:
            logger.exception("Error executing search `%s`: %s", query, e)
            continue
            
    # Stage authors into frontier_ranking so active learning picks them up
    if unique_authors:
        logger.info("Staging %d unique generic authors into frontier_ranking.", len(unique_authors))
        new_authors = 0
        for author_id, author in unique_authors.items():
            username = author["username"]
            bio = author.get("bio", "")
            # Ensure they are in profiles
            conn.execute(
                """
                INSERT INTO profiles (account_id, username, bio)
                VALUES (?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    username = excluded.username,
                    bio = CASE
                        WHEN COALESCE(profiles.bio, '') = '' THEN excluded.bio
                        ELSE profiles.bio
                    END
                """,
                (author_id, username, bio),
            )
            
            # Upsert into frontier_ranking with a 99.0 info_value
            conn.execute("""
                INSERT INTO frontier_ranking (
                    account_id, band, info_value, top_community, top_weight, degree, in_holdout, created_at
                ) VALUES (?, 'topic_seed', 99.0, 'AI-Safety', 1.0, 1, 0, ?)
                ON CONFLICT(account_id) DO UPDATE SET 
                    info_value = MAX(info_value, excluded.info_value),
                    band = 'topic_seed'
            """, (author_id, now))
            
            new_authors += 1
                
        conn.commit()
        total_new_authors = new_authors
        
    logger.info(
        "Finished topic ingestion. Stored %d new tweets and staged %d authors for active learning.",
        total_tweets, total_new_authors
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="Fetch tweets by semantic topic.")
    parser.add_argument("--budget", type=float, default=2.50, help="Dollar budget for this run.")
    parser.add_argument("--query", type=str, action="append", help="Specific query to run. Can be passed multiple times.")
    args = parser.parse_args()

    api_key = os.getenv("TWITTERAPI_IO_API_KEY") or os.getenv("TWITTERAPI_API_KEY")
    if not api_key:
        logger.error("TWITTERAPI_IO_API_KEY environment variable is required.")
        sys.exit(1)
        
    from pathlib import Path
    db_path = Path(__file__).resolve().parents[1] / "data" / "archive_tweets.db"
    
    with sqlite3.connect(db_path) as conn:
        queries = args.query if args.query else DEFAULT_QUERIES
        run_topic_fetch(conn, api_key, args.budget, queries)
