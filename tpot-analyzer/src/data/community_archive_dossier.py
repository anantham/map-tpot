"""Current public Community Archive dossier reader and private observations.

Only the provider's anonymous role is used. Re-query upstream before display;
retained observations are reusable evidence, never an automatic stale fallback.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from src.archive.fetcher import ANON_KEY
from src.config import get_snapshot_dir
from src.data.archive_dossier import DossierNotFoundError

PUBLIC_REST = "https://fabxmporizzqflnftavs.supabase.co/rest/v1/"
FIELDS = {
    "all_account": "account_id,username,account_display_name,is_tombstone,updated_at",
    "all_profile": "account_id,bio,website,location,archive_upload_id,updated_at",
    "enriched_tweets": "tweet_id,account_id,username,created_at,full_text,favorite_count,retweet_count,reply_to_tweet_id,reply_to_user_id,quoted_tweet_id,conversation_id,archive_upload_id",
}
CONTEXT_FIELDS = {'replyToTweetId': 'reply_to_tweet_id', 'replyToAccountId': 'reply_to_user_id',
                  'quotedTweetId': 'quoted_tweet_id', 'conversationId': 'conversation_id'}

class PublicReadUnavailable(RuntimeError):
    """A bounded upstream read failed; other public resources may still work."""

class PublicAccountRestricted(DossierNotFoundError):
    """An explicit provider restriction, not mere absence or a transport outage."""


def _rows(client, resource, params, account_id=None):
    try:
        with client.stream("GET", PUBLIC_REST + resource, params=params,
                           headers={"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}"}) as response:
            if response.status_code != 200:
                raise PublicReadUnavailable(f"Community Archive public read unavailable (HTTP {response.status_code})")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise RuntimeError("Community Archive public response exceeds read limit")
        rows = json.loads(content)
    except httpx.HTTPError as exc:
        raise PublicReadUnavailable("Community Archive public read unavailable") from exc
    except ValueError as exc:
        raise RuntimeError("Community Archive public response schema is invalid JSON") from exc
    if not isinstance(rows, list) or len(rows) > int(params["limit"]):
        raise RuntimeError("Community Archive public response schema is not a bounded row list")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("account_id"), str) or not re.fullmatch(r'[0-9]+', row['account_id']):
            raise RuntimeError("Community Archive public response has invalid account identity")
        if account_id and row["account_id"] != account_id:
            raise RuntimeError("Community Archive public response account identity mismatch")
        fields = FIELDS[resource].split(",")
        required = [field for field in fields if field not in ("is_tombstone", "updated_at", "archive_upload_id")]
        if any(field not in row for field in required):
            raise RuntimeError("Community Archive public response schema is missing fields")
        string_fields = {
            "all_account": ("username", "account_display_name", "updated_at"),
            "all_profile": ("bio", "website", "location", "updated_at"),
            "enriched_tweets": ("tweet_id", "username", "created_at", "full_text", "reply_to_tweet_id",
                                "reply_to_user_id", "quoted_tweet_id", "conversation_id"),
        }[resource]
        if any(row.get(field) is not None and not isinstance(row[field], str) for field in string_fields):
            raise RuntimeError("Community Archive public response schema has invalid field types")
        if resource == "enriched_tweets" and (not isinstance(row.get("tweet_id"), str) or not re.fullmatch(r'[0-9]+', row['tweet_id'])):
            raise RuntimeError("Community Archive public response schema requires string post IDs")
        if resource == 'enriched_tweets' and any(row.get(field) is not None
                and not re.fullmatch(r'[0-9]+', row[field]) for field in CONTEXT_FIELDS.values()):
            raise RuntimeError('Community Archive public response has invalid context identity')
    return rows


def _capture(cache_dir, resource, account_id, params, rows, observed_at):
    """Append a source observation; failure is visible, never a live-data rewrite."""
    record = {"kind": "community-archive-public-rest-observation", "visibility": "private",
              "source": PUBLIC_REST + resource, "resource": resource, "accountId": account_id,
              "observedAt": observed_at, "params": params, "rows": rows,
              "boundary": "Historical observation; revalidate upstream before active display."}
    try:
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if cache_dir.is_symlink() or cache_dir.stat().st_mode & 0o077:
            return False
        name = f"{account_id}-{resource}-{uuid4().hex}.json"
        descriptor = os.open(cache_dir / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False)
            output.write("\n")
        return True
    except OSError:
        return False


def load_public_archive_dossier(handle, limit, expected_account_id=None, *, client=None, cache_dir=None):
    """Resolve one current public account, retain observations and map its dossier."""
    handle = str(handle or "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        raise ValueError("a valid X handle is required")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if expected_account_id and not re.fullmatch(r"[0-9]+", expected_account_id):
        raise DossierNotFoundError("Current archive data is unavailable for this unresolved identity")
    cache_dir = Path(cache_dir or os.getenv("MAP_TPOT_ARCHIVE_CACHE_DIR") or
                     get_snapshot_dir() / "private" / "community-archive-rest")
    saved = []
    errors = {}
    manager = nullcontext(client) if client is not None else httpx.Client(timeout=httpx.Timeout(10, connect=3), follow_redirects=False)
    with manager as client:
        pattern = handle.replace("_", "\\_")
        params = {"select": FIELDS["all_account"], "username": f"ilike.{pattern}", "limit": "2"}
        accounts = _rows(client, "all_account", params)
        if not accounts:
            raise DossierNotFoundError("No current public archive account was returned for this handle")
        if len({row["account_id"] for row in accounts}) != 1:
            raise ValueError("handle resolves to multiple current account IDs")
        identity = accounts[0]
        account_id = identity["account_id"]
        if str(identity.get("username") or "").casefold() != handle.casefold():
            raise RuntimeError("Community Archive public response identity does not match handle")
        if expected_account_id and expected_account_id != account_id:
            raise ValueError("requested account ID and current archive handle disagree")
        if identity.get('is_tombstone') is not None and type(identity['is_tombstone']) is not bool:
            raise PublicAccountRestricted('Archive restriction status cannot be validated; historical dossier fallback is disabled.')
        if identity.get("is_tombstone") is True:
            raise PublicAccountRestricted("Current archive marks this account unavailable; historical dossier fallback is disabled. Independent sources are retained.")
        observed_at = datetime.now(timezone.utc).isoformat()
        saved.append(_capture(cache_dir, "all_account", account_id, params, accounts, observed_at))

        params = {"select": FIELDS["all_profile"], "account_id": f"eq.{account_id}",
                  "order": "updated_at.desc.nullslast,archive_upload_id.desc", "limit": "1"}
        try:
            profiles = _rows(client, "all_profile", params, account_id)
            profile_status = "available" if profiles else "not_returned"
        except PublicReadUnavailable as exc:
            profiles, profile_status = [], "unavailable"
            errors["profile"] = str(exc)
        observed_at = datetime.now(timezone.utc).isoformat()
        if profile_status != "unavailable":
            saved.append(_capture(cache_dir, "all_profile", account_id, params, profiles, observed_at))
        profile = profiles[0] if profiles else {}
        account = {"accountId": account_id, "username": identity["username"],
                   "displayName": identity.get("account_display_name"), "bio": profile.get("bio"),
                   "location": profile.get("location"), "website": profile.get("website"), "fetchedAt": observed_at}

        params = {"select": FIELDS["enriched_tweets"], "account_id": f"eq.{account_id}",
                  "order": "created_at.desc,tweet_id.desc", "limit": str(limit)}
        try:
            posts = _rows(client, "enriched_tweets", params, account_id)
            posts_status = "available"
        except PublicReadUnavailable as exc:
            posts, posts_status = [], "unavailable"
            errors["posts"] = str(exc)
        observed_at = datetime.now(timezone.utc).isoformat()
        if posts_status != "unavailable":
            saved.append(_capture(cache_dir, "enriched_tweets", account_id, params, posts, observed_at))
    tweets = [{"tweetId": row["tweet_id"], "text": row.get("full_text") or "",
               "createdAt": row.get("created_at"), "favoriteCount": row.get("favorite_count"),
               "retweetCount": row.get("retweet_count"), "fetchedAt": observed_at,
               "source": "community_archive_rest", "fetchSource": "public_rest",
               "context": {key: row.get(field) for key, field in CONTEXT_FIELDS.items()}} for row in posts]
    provenance = {"source": "community_archive_public_rest", "snapshotBound": False,
                  "capturedAt": observed_at, "cacheStatus": "saved" if all(saved) else "unavailable",
                  "profileStatus": profile_status, "postsStatus": posts_status, "readErrors": errors}
    return account, tweets, provenance
