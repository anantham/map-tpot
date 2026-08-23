"""Canonical, content-addressed dossiers for formative Research Notes trials."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any


class ResearchNotesSnapshotError(ValueError):
    """Raised when a private dossier snapshot cannot be trusted."""


_SHA256 = re.compile(r"[0-9a-f]{64}")
_HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")
_SNAPSHOT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_TOP_FIELDS = {
    "schemaVersion", "kind", "visibility", "snapshotId", "createdAt",
    "provenance", "dossiers", "snapshotHash",
}
_PROVENANCE_FIELDS = {
    "source", "acquisitionPlanSha256", "acquisitionReceiptSha256",
}
_BUILD_DOSSIER_FIELDS = {"account", "tweets"}
_STORED_DOSSIER_FIELDS = {"accountHash", "account", "tweets"}
_ACCOUNT_FIELDS = {
    "accountId", "username", "displayName", "bio", "location", "website",
    "fetchedAt",
}
_TWEET_FIELDS = {
    "tweetId", "text", "createdAt", "favoriteCount", "retweetCount",
    "fetchedAt",
}


def _require_fields(value: Any, allowed: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchNotesSnapshotError(f"{context} must be an object")
    unexpected = set(value) - allowed
    if unexpected:
        names = ", ".join(sorted(str(name) for name in unexpected))
        raise ResearchNotesSnapshotError(
            f"unexpected field(s) in {context}: {names}"
        )
    missing = allowed - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise ResearchNotesSnapshotError(f"missing field(s) in {context}: {names}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ResearchNotesSnapshotError(
            "snapshot must contain canonical JSON values"
        ) from exc
    return text.encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _timestamp(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise ResearchNotesSnapshotError(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchNotesSnapshotError(
            f"{field} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ResearchNotesSnapshotError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _string(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ResearchNotesSnapshotError(f"{field} must be a string")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ResearchNotesSnapshotError(f"{field} must be a nonnegative integer")
    return value


def _normalize_provenance(value: Any) -> dict[str, str]:
    row = _require_fields(value, _PROVENANCE_FIELDS, "provenance")
    if row["source"] != "bounded_private_acquisition":
        raise ResearchNotesSnapshotError(
            "provenance.source must be bounded_private_acquisition"
        )
    result = {"source": row["source"]}
    for field in ("acquisitionPlanSha256", "acquisitionReceiptSha256"):
        digest = row[field]
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ResearchNotesSnapshotError(f"provenance.{field} must be SHA-256")
        result[field] = digest
    return result


def _normalize_account(value: Any) -> dict[str, Any]:
    row = _require_fields(value, _ACCOUNT_FIELDS, "dossier.account")
    account_id = _string(row["accountId"], "account.accountId")
    username = _string(row["username"], "account.username")
    if not account_id:
        raise ResearchNotesSnapshotError("account.accountId must not be empty")
    if _HANDLE.fullmatch(username) is None:
        raise ResearchNotesSnapshotError("account.username must be a valid X handle")
    return {
        "accountId": account_id,
        "username": username,
        "displayName": _string(row["displayName"], "account.displayName", nullable=True),
        "bio": _string(row["bio"], "account.bio", nullable=True),
        "location": _string(row["location"], "account.location", nullable=True),
        "website": _string(row["website"], "account.website", nullable=True),
        "fetchedAt": _timestamp(row["fetchedAt"], "account.fetchedAt"),
    }


def _normalize_tweet(value: Any, index: int) -> dict[str, Any]:
    row = _require_fields(value, _TWEET_FIELDS, f"dossier.tweets[{index}]")
    tweet_id = _string(row["tweetId"], f"tweets[{index}].tweetId")
    if not tweet_id:
        raise ResearchNotesSnapshotError(f"tweets[{index}].tweetId must not be empty")
    return {
        "tweetId": tweet_id,
        "text": _string(row["text"], f"tweets[{index}].text"),
        "createdAt": _timestamp(
            row["createdAt"], f"tweets[{index}].createdAt", nullable=True
        ),
        "favoriteCount": _nonnegative_int(
            row["favoriteCount"], f"tweets[{index}].favoriteCount"
        ),
        "retweetCount": _nonnegative_int(
            row["retweetCount"], f"tweets[{index}].retweetCount"
        ),
        "fetchedAt": _timestamp(row["fetchedAt"], f"tweets[{index}].fetchedAt"),
    }


def _normalize_dossier(value: Any, *, stored: bool) -> dict[str, Any]:
    allowed = _STORED_DOSSIER_FIELDS if stored else _BUILD_DOSSIER_FIELDS
    row = _require_fields(value, allowed, "dossier")
    if not isinstance(row["tweets"], list):
        raise ResearchNotesSnapshotError("dossier.tweets must be an array")
    account = _normalize_account(row["account"])
    tweets = [_normalize_tweet(tweet, i) for i, tweet in enumerate(row["tweets"])]
    tweet_ids = [tweet["tweetId"] for tweet in tweets]
    if len(tweet_ids) != len(set(tweet_ids)):
        raise ResearchNotesSnapshotError(
            f"duplicate tweetId in dossier for @{account['username']}"
        )
    account_hash = _hash({"account": account, "tweets": tweets})
    if stored:
        declared = row["accountHash"]
        if not isinstance(declared, str) or _SHA256.fullmatch(declared) is None:
            raise ResearchNotesSnapshotError("accountHash must be SHA-256")
        if declared != account_hash:
            raise ResearchNotesSnapshotError(
                f"accountHash mismatch for @{account['username']}"
            )
    return {"accountHash": account_hash, "account": account, "tweets": tweets}


def _normalize_dossiers(values: Any, *, stored: bool) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise ResearchNotesSnapshotError("dossiers must be a nonempty array")
    dossiers = [_normalize_dossier(value, stored=stored) for value in values]
    ids = [row["account"]["accountId"] for row in dossiers]
    handles = [row["account"]["username"].casefold() for row in dossiers]
    tweet_ids = [
        tweet["tweetId"] for row in dossiers for tweet in row["tweets"]
    ]
    if len(ids) != len(set(ids)):
        raise ResearchNotesSnapshotError("duplicate accountId in dossiers")
    if len(handles) != len(set(handles)):
        raise ResearchNotesSnapshotError("duplicate username in dossiers")
    if len(tweet_ids) != len(set(tweet_ids)):
        raise ResearchNotesSnapshotError("duplicate tweetId across dossiers")
    canonical = sorted(
        dossiers,
        key=lambda row: (
            row["account"]["username"].casefold(),
            row["account"]["accountId"],
        ),
    )
    if stored and ids != [row["account"]["accountId"] for row in canonical]:
        raise ResearchNotesSnapshotError("dossiers are not in canonical order")
    return canonical


def build_research_notes_snapshot(
    *,
    snapshot_id: str,
    created_at: str,
    provenance: dict[str, Any],
    dossiers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a blind, private snapshot without retaining caller-owned objects."""
    if not isinstance(snapshot_id, str) or _SNAPSHOT_ID.fullmatch(snapshot_id) is None:
        raise ResearchNotesSnapshotError("snapshot_id has an invalid format")
    manifest = {
        "schemaVersion": 1,
        "kind": "research-notes-dossier-snapshot",
        "visibility": "private",
        "snapshotId": snapshot_id,
        "createdAt": _timestamp(created_at, "created_at"),
        "provenance": _normalize_provenance(provenance),
        "dossiers": _normalize_dossiers(deepcopy(dossiers), stored=False),
    }
    return {**manifest, "snapshotHash": _hash(manifest)}


def verify_research_notes_snapshot(snapshot: Any) -> dict[str, Any]:
    """Verify strict shape, canonical order, and every declared content hash."""
    row = _require_fields(snapshot, _TOP_FIELDS, "snapshot")
    if row["schemaVersion"] != 1:
        raise ResearchNotesSnapshotError("schemaVersion must be 1")
    if row["kind"] != "research-notes-dossier-snapshot":
        raise ResearchNotesSnapshotError("unexpected snapshot kind")
    if row["visibility"] != "private":
        raise ResearchNotesSnapshotError("snapshot visibility must be private")
    snapshot_id = row["snapshotId"]
    if not isinstance(snapshot_id, str) or _SNAPSHOT_ID.fullmatch(snapshot_id) is None:
        raise ResearchNotesSnapshotError("snapshotId has an invalid format")
    dossiers = _normalize_dossiers(row["dossiers"], stored=True)
    manifest = {
        "schemaVersion": 1,
        "kind": row["kind"],
        "visibility": row["visibility"],
        "snapshotId": snapshot_id,
        "createdAt": _timestamp(row["createdAt"], "createdAt"),
        "provenance": _normalize_provenance(row["provenance"]),
        "dossiers": dossiers,
    }
    declared = row["snapshotHash"]
    if not isinstance(declared, str) or _SHA256.fullmatch(declared) is None:
        raise ResearchNotesSnapshotError("snapshotHash must be SHA-256")
    if declared != _hash(manifest):
        raise ResearchNotesSnapshotError("snapshotHash mismatch")
    verified = {**manifest, "snapshotHash": declared}
    if row != verified:
        raise ResearchNotesSnapshotError("snapshot representation is not canonical")
    return verified


def canonical_snapshot_bytes(snapshot: Any) -> bytes:
    """Return deterministic UTF-8 JSON after fully verifying the snapshot."""
    return _canonical_bytes(verify_research_notes_snapshot(snapshot))
