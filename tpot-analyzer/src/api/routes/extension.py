"""Routes for extension ingest, firehose forwarding, and feed inspection."""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from src.api.routes.extension_read_routes import register_extension_read_routes
from src.api.routes.extension_runtime import (
    get_feed_admin_store,
    get_feed_policy_store,
    get_feed_store,
    get_firehose_writer,
    get_tag_store,
)
from src.api.routes.extension_utils import (
    parse_iso_optional,
    parse_json_body,
    parse_positive_int,
    require_bool,
    require_ingest_auth,
    require_scope,
    require_string_list,
    resolve_allowlist_accounts,
)

logger = logging.getLogger(__name__)

extension_bp = Blueprint("extension", __name__, url_prefix="/api/extension")
register_extension_read_routes(extension_bp)


@extension_bp.route("/settings", methods=["GET"])
def get_extension_settings():
    """Get extension ingestion policy for the scoped workspace/ego pair."""
    try:
        workspace_id, ego = require_scope(request)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    policy = get_feed_policy_store().get_policy(workspace_id=workspace_id, ego=ego)
    return jsonify(policy.as_dict())


@extension_bp.route("/settings", methods=["PUT"])
def update_extension_settings():
    """Update extension ingestion policy toggles and allowlist controls."""
    try:
        workspace_id, ego = require_scope(request)
        payload = parse_json_body(request)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    update_args: dict[str, Any] = {}
    try:
        if "ingestionMode" in payload:
            update_args["ingestion_mode"] = payload["ingestionMode"]
        if "retentionMode" in payload:
            update_args["retention_mode"] = payload["retentionMode"]
        if "processingMode" in payload:
            update_args["processing_mode"] = payload["processingMode"]
        if "allowlistEnabled" in payload:
            update_args["allowlist_enabled"] = require_bool(
                "allowlistEnabled", payload["allowlistEnabled"]
            )
        if "allowlistAccounts" in payload:
            update_args["allowlist_accounts"] = require_string_list(
                "allowlistAccounts", payload["allowlistAccounts"]
            )
        if "allowlistTags" in payload:
            update_args["allowlist_tags"] = require_string_list(
                "allowlistTags", payload["allowlistTags"]
            )
        if "firehoseEnabled" in payload:
            update_args["firehose_enabled"] = require_bool(
                "firehoseEnabled", payload["firehoseEnabled"]
            )
        if "firehosePath" in payload:
            update_args["firehose_path"] = payload["firehosePath"]
        settings = get_feed_policy_store().upsert_policy(
            workspace_id=workspace_id, ego=ego, **update_args
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("failed to update extension settings workspace=%s ego=%s", workspace_id, ego)
        return jsonify({"error": "settings update failed", "details": str(exc)}), 500

    return jsonify({"status": "ok", "settings": settings.as_dict()})


@extension_bp.route("/feed_events", methods=["POST"])
def ingest_feed_events():
    """Ingest extension-captured feed events for account-level exposure analysis."""
    try:
        workspace_id, ego = require_scope(request)
        policy = get_feed_policy_store().get_policy(workspace_id=workspace_id, ego=ego)
        require_ingest_auth(policy, request)
        payload = parse_json_body(request)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 401
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    events = payload.get("events")
    if not isinstance(events, list):
        return jsonify({"error": "events must be an array"}), 400
    if len(events) > 5000:
        return jsonify({"error": "events batch too large; max 5000"}), 400

    feed_store = get_feed_store()
    admin_store = get_feed_admin_store()
    try:
        ingest_stats = feed_store.ingest_events(
            workspace_id=workspace_id,
            ego=ego,
            events=events,
            collect_inserted_keys=True,
        )
        inserted_keys = ingest_stats.pop("insertedEventKeys", [])
    except ValueError as exc:
        logger.warning("feed event ingest rejected workspace=%s ego=%s: %s", workspace_id, ego, exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("feed event ingest failed workspace=%s ego=%s: %s", workspace_id, ego, exc)
        return jsonify({"error": "feed event ingest failed", "details": str(exc)}), 500

    firehose_status = {
        "enabled": bool(policy.firehose_enabled),
        "path": policy.firehose_path,
        "written": 0,
        "filteredOut": 0,
    }
    if policy.firehose_enabled and inserted_keys:
        inserted_events = admin_store.fetch_events_by_keys(
            workspace_id=workspace_id,
            ego=ego,
            event_keys=inserted_keys,
        )
        tagged_accounts = []
        if policy.allowlist_tags:
            tagged_accounts = get_tag_store().list_account_ids_for_tags(
                ego=ego,
                tags=policy.allowlist_tags,
            )
        allowlist_accounts = resolve_allowlist_accounts(
            policy,
            tagged_accounts=tagged_accounts,
        )
        if allowlist_accounts is not None:
            forwarded = [
                event for event in inserted_events if event.get("accountId") in allowlist_accounts
            ]
            firehose_status["filteredOut"] = len(inserted_events) - len(forwarded)
            firehose_status["allowlistAccountCount"] = len(allowlist_accounts)
        else:
            forwarded = inserted_events
        firehose_status.update(
            get_firehose_writer().append_events(
                workspace_id=workspace_id,
                ego=ego,
                events=forwarded,
                override_path=policy.firehose_path,
            )
        )

    return jsonify(
        {
            "status": "ok",
            "workspaceId": workspace_id,
            "ego": ego,
            "ingest": ingest_stats,
            "settings": policy.as_dict(),
            "firehose": firehose_status,
        }
    )


@extension_bp.route("/feed_events/raw", methods=["GET"])
def get_raw_feed_events():
    """Return raw extension events for scoped inspection and debugging."""
    try:
        workspace_id, ego = require_scope(request)
        limit = parse_positive_int(request, "limit", 100, minimum=1, maximum=500)
        before_seen_at = parse_iso_optional(request, "before_seen_at")
        payload = get_feed_admin_store().list_raw_events(
            workspace_id=workspace_id,
            ego=ego,
            limit=limit,
            before_seen_at=before_seen_at,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("raw feed query failed workspace=%s ego=%s: %s", workspace_id, ego, exc)
        return jsonify({"error": "raw feed query failed", "details": str(exc)}), 500
    return jsonify(payload)


@extension_bp.route("/feed_events/purge_by_tag", methods=["POST"])
def purge_feed_events_by_tag():
    """Delete feed events for accounts matched by a positive account tag."""
    try:
        workspace_id, ego = require_scope(request)
        payload = parse_json_body(request)
        tag = str(payload.get("tag") or "").strip()
        if not tag:
            raise ValueError("tag is required")
        dry_run = bool(payload.get("dryRun", False))
        account_ids = get_tag_store().list_account_ids_for_tag(ego=ego, tag=tag)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("tag-scope lookup failed workspace=%s ego=%s: %s", workspace_id, ego, exc)
        return jsonify({"error": "tag-scope lookup failed", "details": str(exc)}), 500

    if dry_run:
        return jsonify(
            {
                "status": "ok",
                "workspaceId": workspace_id,
                "ego": ego,
                "tag": tag,
                "dryRun": True,
                "accountCount": len(account_ids),
                "accountIds": account_ids[:200],
            }
        )

    result = get_feed_admin_store().purge_events_for_accounts(
        workspace_id=workspace_id,
        ego=ego,
        account_ids=account_ids,
    )
    return jsonify(
        {
            "status": "ok",
            "workspaceId": workspace_id,
            "ego": ego,
            "tag": tag,
            "dryRun": False,
            **result,
        }
    )
