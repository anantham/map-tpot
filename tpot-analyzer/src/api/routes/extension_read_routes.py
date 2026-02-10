"""Read-only routes for extension feed summaries and exposure ranking."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from src.api.routes.extension_runtime import get_feed_store
from src.api.routes.extension_utils import parse_positive_int, require_scope

logger = logging.getLogger(__name__)


def register_extension_read_routes(blueprint: Blueprint) -> None:
    @blueprint.route("/accounts/<account_id>/summary", methods=["GET"])
    def get_account_feed_summary(account_id: str):
        """Return feed exposure/content summary for a single account."""
        try:
            workspace_id, ego = require_scope(request)
            days = parse_positive_int(request, "days", 30, minimum=1, maximum=3650)
            keyword_limit = parse_positive_int(request, "keyword_limit", 12, minimum=1, maximum=100)
            sample_limit = parse_positive_int(request, "sample_limit", 8, minimum=1, maximum=100)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            summary = get_feed_store().account_summary(
                workspace_id=workspace_id,
                ego=ego,
                account_id=str(account_id),
                days=days,
                keyword_limit=keyword_limit,
                sample_limit=sample_limit,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.exception(
                "feed summary failed workspace=%s ego=%s account=%s: %s",
                workspace_id,
                ego,
                account_id,
                exc,
            )
            return jsonify({"error": "account feed summary failed", "details": str(exc)}), 500
        return jsonify(summary)

    @blueprint.route("/exposure/top", methods=["GET"])
    def get_top_exposed_accounts():
        """Return top exposed accounts in the feed for a scope/lookback window."""
        try:
            workspace_id, ego = require_scope(request)
            days = parse_positive_int(request, "days", 30, minimum=1, maximum=3650)
            limit = parse_positive_int(request, "limit", 20, minimum=1, maximum=200)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            accounts = get_feed_store().top_exposed_accounts(
                workspace_id=workspace_id,
                ego=ego,
                days=days,
                limit=limit,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.exception("top exposure query failed workspace=%s ego=%s: %s", workspace_id, ego, exc)
            return jsonify({"error": "top exposure query failed", "details": str(exc)}), 500
        return jsonify(
            {
                "workspaceId": workspace_id,
                "ego": ego,
                "lookbackDays": days,
                "accounts": accounts,
            }
        )
