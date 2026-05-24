"""Per-tweet LLM labeling: low-text enrichment + ensemble call + per-account aggregations."""
from __future__ import annotations

import datetime
import logging
import sqlite3
from collections import defaultdict

from scripts.assemble_context import assemble_tweet_context
from scripts.label_tweets_ensemble import (
    MODELS,
    build_consensus,
    build_prompt,
    call_model,
    parse_label_json,
    store_labels,
)
from src.archive.thread_fetcher import format_thread_for_prompt, get_thread_context

logger = logging.getLogger(__name__)


def _enrich_low_text_tweet(tweet_text: str, context_json: str) -> str:
    """Enrich tweets with minimal text by fetching linked content.

    For URL-only or image-only tweets, the LLM has nothing to tag.
    This fetches article titles/descriptions from URLs to provide
    actual content for labeling.
    """
    import json as _json
    import re

    # Extract URLs from tweet text
    urls = re.findall(r'https?://\S+', tweet_text)

    # Also check context_json for URLs
    try:
        context_items = _json.loads(context_json) if context_json else []
    except (ValueError, TypeError):
        context_items = []

    for item in context_items:
        if isinstance(item, str):
            urls.extend(re.findall(r'https?://\S+', item))

    # Strip text to check if it's "low text" (only URLs, no real content)
    stripped = re.sub(r'https?://\S+', '', tweet_text).strip()
    if len(stripped) >= 30:
        # Enough real text — no enrichment needed
        return tweet_text

    # Try to fetch article metadata for each URL
    enrichments = []
    for url in urls[:2]:  # max 2 URLs to keep costs down
        # Skip t.co, image URLs, and media
        if 't.co/' in url or 'pbs.twimg.com' in url or 'video.twimg.com' in url:
            continue
        try:
            import httpx
            resp = httpx.get(
                url, follow_redirects=True, timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            )
            if resp.status_code == 200:
                html = resp.text[:5000]  # first 5KB
                # Extract title
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                # Extract og:description
                desc_match = re.search(
                    r'<meta[^>]+(?:property|name)=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                    html, re.IGNORECASE,
                )
                parts = []
                if title_match:
                    parts.append(f"[Article: {title_match.group(1).strip()[:150]}]")
                if desc_match:
                    parts.append(f"[Description: {desc_match.group(1).strip()[:200]}]")
                if parts:
                    enrichments.append("\n".join(parts))
        except Exception:
            pass  # network errors are fine — we just lose enrichment

    if enrichments:
        return tweet_text + "\n" + "\n".join(enrichments)

    # If we couldn't enrich, add a cue so the LLM knows to be cautious
    if len(stripped) < 10:
        return tweet_text + "\n[This tweet has minimal text — only links/media. Assign 0 bits unless the linked content is clearly community-specific.]"

    return tweet_text


def _label_single_tweet(
    conn: sqlite3.Connection,
    openrouter_key: str,
    tweet: dict,
    account_ctx: dict,
    current_prior: str = "",
    allow_paid_api: bool = True,
) -> list[dict]:
    """Label a single tweet with all models, store consensus.

    Args:
        current_prior: accumulating bits profile so far, e.g.
            "LLM-Whisperers:40%, Qualia-Research:30%, AI-Safety:20%"
            The LLM uses this to focus on surprising/extending evidence.

    Returns list of per-model label dicts (for agreement tracking).
    """
    # Build enriched tweet text: original text + context (quotes, images, links)
    tweet_text = tweet["text"]
    context_json = tweet.get("context_json", "[]")
    if context_json and context_json != "[]":
        import json as _json
        try:
            context_items = _json.loads(context_json)
            if context_items:
                tweet_text += "\n" + "\n".join(context_items)
        except (ValueError, TypeError):
            pass

    # Enrich reply tweets with thread context (parent tweets)
    # Also store thread tweets in enriched_tweets for future use
    if tweet.get("is_reply") and tweet.get("tweet_id"):
        try:
            from src.config import DEFAULT_ARCHIVE_DB
            thread = get_thread_context(
                tweet["tweet_id"],
                DEFAULT_ARCHIVE_DB,
                allow_api=allow_paid_api,
            )
            if thread and len(thread) > 1:
                thread_text = format_thread_for_prompt(thread, tweet["tweet_id"])
                tweet_text = f"[Thread context]\n{thread_text}\n[End thread]"
                # Store thread tweets we fetched (they're tweets from other accounts)
                now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
                for t in thread:
                    t_id = str(t.get("id", ""))
                    t_author = t.get("author", {}).get("userName", "")
                    t_author_id = str(t.get("author", {}).get("id", ""))
                    if t_id and t_id != tweet["tweet_id"]:
                        conn.execute(
                            """INSERT OR IGNORE INTO enriched_tweets
                            (tweet_id, account_id, username, text,
                             like_count, retweet_count, reply_count, view_count,
                             created_at, lang, is_reply, in_reply_to_user,
                             has_media, mentions_json, fetch_source, fetched_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (t_id, t_author_id, t_author, t.get("text", ""),
                             t.get("likeCount", 0), t.get("retweetCount", 0),
                             t.get("replyCount", 0), t.get("viewCount", 0),
                             t.get("createdAt", ""), t.get("lang", ""),
                             0, None, 0, "[]", "thread_context", now_ts),
                        )
                conn.commit()
        except Exception as e:
            logger.debug("Thread fetch failed for %s: %s", tweet["tweet_id"], e)

    # Enrich low-text tweets by fetching linked content (#1: bias leak fix)
    tweet_text = _enrich_low_text_tweet(tweet_text, context_json)

    tweet_ctx = assemble_tweet_context(
        conn,
        tweet_id=tweet["tweet_id"],
        tweet_text=tweet_text,
        engagement_stats=f"likes={tweet.get('like_count', 0)} rt={tweet.get('retweet_count', 0)} replies={tweet.get('reply_count', 0)}",
        mentions=tweet.get("mentions_json", "[]"),
    )

    # Resolve mention communities, RT source, and reply communities for richer context
    from scripts.assemble_context import resolve_mention_communities, get_rt_source_community, get_reply_communities
    mention_communities = resolve_mention_communities(conn, tweet.get("mentions_json", "[]"))
    rt_source = get_rt_source_community(tweet_text, conn)

    # Fetch replies for tweets with enough engagement (reply_count >= 3)
    reply_communities = ""
    reply_count = tweet.get("reply_count", 0)
    if allow_paid_api and reply_count and reply_count >= 3:
        try:
            import os
            twitter_key = os.getenv("TWITTERAPI_IO_API_KEY") or os.getenv("TWITTERAPI_API_KEY") or os.getenv("API_KEY")
            reply_communities = get_reply_communities(
                conn, tweet["tweet_id"],
                op_username=account_ctx.get("username", ""),
                api_key=twitter_key,
            )
        except Exception as e:
            logger.debug("Reply community fetch failed: %s", e)

    prompt_text = build_prompt(
        username=account_ctx["username"],
        bio=account_ctx.get("bio", ""),
        graph_signal=account_ctx["graph_signal"],
        other_tweets=current_prior,
        tweet_text=tweet_ctx["tweet_text"],
        engagement=tweet_ctx["engagement_stats"],
        mentions=tweet_ctx["mentions"],
        engagement_context=tweet_ctx["engagement_context"],
        community_descriptions=account_ctx["community_descriptions"],
        community_short_names=account_ctx["community_short_names"],
        content_profile=account_ctx.get("content_profile", ""),
        engagement_partners=account_ctx.get("engagement_partners", ""),
        mention_communities=mention_communities,
        rt_source=rt_source,
        reply_communities=reply_communities,
        cofollowed=account_ctx.get("cofollowed", ""),
    )

    # Split prompt into system + user at the --- delimiter
    parts = prompt_text.split("\n---\n\n", 1)
    system_prompt = parts[0] if len(parts) == 2 else prompt_text
    user_prompt = parts[1] if len(parts) == 2 else ""

    model_labels: list[dict] = []

    for model in MODELS:
        try:
            raw = call_model(openrouter_key, model, system_prompt, user_prompt)
            parsed = parse_label_json(raw)
            if parsed:
                model_labels.append(parsed)
            else:
                logger.warning(
                    "Failed to parse label from %s for tweet %s",
                    model, tweet["tweet_id"],
                )
        except Exception:
            logger.exception(
                "Error calling model %s for tweet %s",
                model, tweet["tweet_id"],
            )

    if len(model_labels) >= 2:
        consensus = build_consensus(model_labels)
        store_labels(conn, tweet["tweet_id"], consensus, reviewer="llm_ensemble")

    return model_labels


def _resolve_bio(conn: sqlite3.Connection, account_id: str) -> str:
    """Resolve bio from profiles or resolved_accounts."""
    row = conn.execute(
        "SELECT bio FROM profiles WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row and row[0]:
        return row[0]

    row = conn.execute(
        "SELECT bio FROM resolved_accounts WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row and row[0]:
        return row[0]

    return ""


def _compute_account_bits_pct(
    conn: sqlite3.Connection, account_id: str
) -> dict[str, float]:
    """Compute bits percentage distribution for an account from tweet_tags.

    Returns {community_short_name: pct} where pct sums to ~100.
    """
    rows = conn.execute(
        """
        SELECT tt.tag
        FROM tweet_tags tt
        JOIN enriched_tweets e ON e.tweet_id = tt.tweet_id
        WHERE e.account_id = ? AND tt.category = 'bits'
        """,
        (account_id,),
    ).fetchall()

    if not rows:
        return {}

    community_bits: dict[str, int] = defaultdict(int)
    for (tag,) in rows:
        parts = tag.split(":")
        if len(parts) == 3 and parts[0] == "bits":
            try:
                community_bits[parts[1]] += abs(int(parts[2]))
            except ValueError:
                continue

    total = sum(community_bits.values())
    if total == 0:
        return {}

    return {comm: (val / total * 100) for comm, val in community_bits.items()}
