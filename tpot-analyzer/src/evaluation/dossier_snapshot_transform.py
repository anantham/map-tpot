"""Transform verified acquisition evidence into blind Research Notes dossiers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.data.research_notes_snapshot import (
    ResearchNotesSnapshotError,
    build_research_notes_snapshot,
)

from .dossier_evidence_artifact import (
    DossierEvidenceArtifactError,
    verify_dossier_evidence_artifact,
)
from .dossier_executor_types import AcquisitionExecutionError, TransportResponse
from .dossier_response_contract import parse_profile, parse_tweets


class DossierSnapshotTransformError(ValueError):
    """Raised when raw evidence cannot safely become a display snapshot."""


_TWITTER_TIME = "%a %b %d %H:%M:%S %z %Y"


def _response(record: dict[str, Any]) -> TransportResponse:
    return TransportResponse(
        status_code=record["status_code"],
        body=record["body"],
        requested_at=record["requested_at"],
        received_at=record["received_at"],
    )


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DossierSnapshotTransformError(f"{field} must be a string or null")
    return value


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise DossierSnapshotTransformError(f"{field} must be a string")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise DossierSnapshotTransformError(f"{field} must be a nonnegative integer")
    return value


def _created_at(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DossierSnapshotTransformError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, _TWITTER_TIME)
        except ValueError as exc:
            raise DossierSnapshotTransformError(
                f"{field} is not ISO or Twitter createdAt format"
            ) from exc
    if parsed.tzinfo is None:
        raise DossierSnapshotTransformError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _external_website(profile: dict[str, Any]) -> str | None:
    bio = profile.get("profile_bio")
    if bio is None:
        return None
    if not isinstance(bio, dict):
        raise DossierSnapshotTransformError("profile website bio must be an object")
    entities = bio.get("entities")
    if entities is None:
        return None
    if not isinstance(entities, dict):
        raise DossierSnapshotTransformError(
            "profile website entities must be an object"
        )
    url = entities.get("url")
    if url is None:
        return None
    if not isinstance(url, dict):
        raise DossierSnapshotTransformError("profile website url must be an object")
    urls = url.get("urls")
    if urls is None or urls == []:
        return None
    if not isinstance(urls, list):
        raise DossierSnapshotTransformError("profile website urls must be an array")
    first = urls[0]
    if not isinstance(first, dict):
        raise DossierSnapshotTransformError(
            "profile website first url must be an object"
        )
    return _optional_string(
        first.get("expanded_url"),
        "profile website expanded_url",
    )


def _profile_dossier(
    *,
    target: dict[str, Any],
    records: list[dict[str, Any]],
    record_index: int,
) -> tuple[dict[str, Any], int]:
    handle = target["handle"]
    profile_record = records[record_index]
    profile_response = _response(profile_record)
    try:
        account_id, _ = parse_profile(profile_response, handle)
    except AcquisitionExecutionError as exc:
        raise DossierSnapshotTransformError(str(exc)) from exc
    profile = profile_response.body["data"]
    account = {
        "accountId": account_id,
        "username": profile["userName"],
        "displayName": _optional_string(
            profile.get("name"), "profile display name"
        ),
        "bio": _optional_string(profile.get("description"), "profile description"),
        "location": _optional_string(profile.get("location"), "profile location"),
        "website": _external_website(profile),
        "fetchedAt": profile_record["received_at"],
    }
    tweets: list[dict[str, Any]] = []
    record_index += 1
    if len(target["actions"]) == 2:
        action = target["actions"][1]
        tweet_record = records[record_index]
        tweet_response = _response(tweet_record)
        try:
            parse_tweets(
                tweet_response,
                expected_handle=handle,
                expected_account_id=account_id,
                maximum_returned=action["maximum_returned"],
            )
        except AcquisitionExecutionError as exc:
            raise DossierSnapshotTransformError(str(exc)) from exc
        for index, tweet in enumerate(tweet_response.body["tweets"]):
            tweet_id = tweet["id"]
            if isinstance(tweet_id, int) and not isinstance(tweet_id, bool):
                tweet_id = str(tweet_id)
            tweets.append({
                "tweetId": tweet_id,
                "text": _required_string(tweet.get("text"), f"tweet[{index}].text"),
                "createdAt": _created_at(
                    tweet.get("createdAt"), f"tweet[{index}].createdAt"
                ),
                "favoriteCount": _nonnegative_int(
                    tweet.get("likeCount"), f"tweet[{index}].likeCount"
                ),
                "retweetCount": _nonnegative_int(
                    tweet.get("retweetCount"), f"tweet[{index}].retweetCount"
                ),
                "fetchedAt": tweet_record["received_at"],
            })
        record_index += 1
    return {"account": account, "tweets": tweets}, record_index


def build_research_notes_snapshot_from_evidence(
    *,
    snapshot_id: str,
    evidence_artifact: dict[str, Any],
    plan: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Create the blind display snapshot after revalidating every identity."""
    try:
        verified = verify_dossier_evidence_artifact(
            evidence_artifact,
            plan=plan,
            receipt=receipt,
        )
    except DossierEvidenceArtifactError as exc:
        raise DossierSnapshotTransformError(str(exc)) from exc
    records = verified["records"]
    record_index = 1  # Skip before-balance telemetry.
    dossiers = []
    for target in plan["targets"]:
        dossier, record_index = _profile_dossier(
            target=target,
            records=records,
            record_index=record_index,
        )
        dossiers.append(dossier)
    if record_index != len(records) - 1:
        raise DossierSnapshotTransformError(
            "evidence action records did not terminate before after-balance telemetry"
        )
    try:
        return build_research_notes_snapshot(
            snapshot_id=snapshot_id,
            created_at=records[-1]["received_at"],
            provenance={
                "source": "bounded_private_acquisition",
                "acquisitionPlanSha256": verified["plan_sha256"],
                "acquisitionReceiptSha256": verified[
                    "execution_receipt_sha256"
                ],
            },
            dossiers=dossiers,
        )
    except ResearchNotesSnapshotError as exc:
        raise DossierSnapshotTransformError(str(exc)) from exc
