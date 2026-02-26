"""Communities API — read and write curated community memberships.

Blueprint: /api/communities
Data source: communities.store (Layer 2 of archive_tweets.db)
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.communities import store
from src.communities import preview as account_preview

logger = logging.getLogger(__name__)

communities_bp = Blueprint("communities", __name__, url_prefix="/api/communities")

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "archive_tweets.db"


def _get_db() -> sqlite3.Connection:
    db_path = os.getenv("ARCHIVE_DB_PATH", str(_DEFAULT_DB))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Read endpoints ───────────────────────────────────────────────────────


@communities_bp.route("", methods=["GET"])
def list_communities_route():
    """List all communities with member counts."""
    conn = _get_db()
    try:
        rows = store.list_communities(conn)
        result = []
        for cid, name, color, desc, sfrun, sfidx, count, created, updated in rows:
            result.append({
                "id": cid,
                "name": name,
                "color": color,
                "description": desc,
                "seeded_from_run": sfrun,
                "seeded_from_idx": sfidx,
                "member_count": count,
                "created_at": created,
                "updated_at": updated,
            })
        return jsonify(result)
    finally:
        conn.close()


@communities_bp.route("/<community_id>/members", methods=["GET"])
def get_members_route(community_id):
    """Member list for a community, with optional ego I-follow badge."""
    ego = request.args.get("ego")
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM community WHERE id = ?", (community_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        members = store.get_community_members(conn, community_id)
        ego_following = store.get_ego_following_set(conn, ego) if ego else set()

        result = []
        for acct_id, username, weight, source, bio in members:
            result.append({
                "account_id": acct_id,
                "username": username,
                "weight": weight,
                "source": source,
                "bio": bio,
                "i_follow": acct_id in ego_following,
            })
        return jsonify({"community_id": community_id, "members": result})
    finally:
        conn.close()


@communities_bp.route("/account/<account_id>", methods=["GET"])
def get_account_communities_route(account_id):
    """Which communities does this account belong to?"""
    conn = _get_db()
    try:
        rows = store.get_account_communities(conn, account_id)
        result = []
        for cid, name, color, weight, source in rows:
            result.append({
                "community_id": cid,
                "name": name,
                "color": color,
                "weight": weight,
                "source": source,
            })
        return jsonify({"account_id": account_id, "communities": result})
    finally:
        conn.close()


# ── Write endpoints ──────────────────────────────────────────────────────


@communities_bp.route("/<community_id>/members/<account_id>", methods=["PUT"])
def assign_member_route(community_id, account_id):
    """Manually assign account to community (source='human', weight=1.0)."""
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM community WHERE id = ?", (community_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        store.upsert_community_account(
            conn, community_id, account_id, weight=1.0, source="human"
        )
        conn.commit()
        return jsonify({
            "community_id": community_id,
            "account_id": account_id,
            "weight": 1.0,
            "source": "human",
        })
    finally:
        conn.close()


@communities_bp.route("/<community_id>/members/<account_id>", methods=["DELETE"])
def remove_member_route(community_id, account_id):
    """Remove account from community."""
    conn = _get_db()
    try:
        conn.execute(
            "DELETE FROM community_account WHERE community_id = ? AND account_id = ?",
            (community_id, account_id),
        )
        conn.commit()
        return jsonify({"removed": True})
    finally:
        conn.close()


@communities_bp.route("/<community_id>", methods=["PATCH"])
def update_community_route(community_id):
    """Update community name, color, or description."""
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT name, color, description FROM community WHERE id = ?",
            (community_id,),
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        body = request.get_json() or {}
        name = body.get("name", exists[0])
        color = body.get("color", exists[1])
        description = body.get("description", exists[2])

        store.upsert_community(
            conn, community_id, name=name, color=color, description=description
        )
        conn.commit()
        return jsonify({
            "id": community_id,
            "name": name,
            "color": color,
            "description": description,
        })
    finally:
        conn.close()


@communities_bp.route("/<community_id>", methods=["DELETE"])
def delete_community_route(community_id):
    """Delete a community and all its memberships (cascade)."""
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM community WHERE id = ?", (community_id,)
        ).fetchone()
        if not exists:
            return jsonify({"error": "community not found"}), 404

        store.delete_community(conn, community_id)
        return jsonify({"deleted": True, "community_id": community_id})
    finally:
        conn.close()


# ── Account preview + notes ─────────────────────────────────────────────


@communities_bp.route("/account/<account_id>/preview", methods=["GET"])
def get_account_preview_route(account_id):
    """Rich preview: profile, mutual follows (with communities), tweets, RT targets, note."""
    ego = request.args.get("ego")
    conn = _get_db()
    try:
        # Ensure account_note table exists (created by init_db but may be missing on older DBs)
        conn.execute("""CREATE TABLE IF NOT EXISTS account_note (
            account_id TEXT PRIMARY KEY, note TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        preview_data = account_preview.get_account_preview(conn, account_id, ego_account_id=ego)
        return jsonify(preview_data)
    finally:
        conn.close()


@communities_bp.route("/account/<account_id>/note", methods=["PUT"])
def put_account_note_route(account_id):
    """Save curator's free-form note about an account."""
    conn = _get_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS account_note (
            account_id TEXT PRIMARY KEY, note TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        body = request.get_json() or {}
        note = body.get("note", "")
        store.upsert_account_note(conn, account_id, note)
        conn.commit()
        return jsonify({"account_id": account_id, "note": note})
    finally:
        conn.close()


@communities_bp.route("/account/<account_id>/weights", methods=["PUT"])
def put_account_weights_route(account_id):
    """Update community weights for an account. Body: {weights: [{community_id, weight}, ...]}"""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        weights = body.get("weights", [])
        for w in weights:
            cid = w.get("community_id")
            weight = w.get("weight")
            if cid is None or weight is None:
                continue
            exists = conn.execute(
                "SELECT 1 FROM community WHERE id = ?", (cid,)
            ).fetchone()
            if not exists:
                return jsonify({"error": f"community {cid} not found"}), 404
            store.upsert_community_account(
                conn, cid, account_id, weight=float(weight), source="human"
            )
        conn.commit()
        # Return updated communities
        rows = store.get_account_communities(conn, account_id)
        result = [{"community_id": r[0], "name": r[1], "color": r[2],
                    "weight": r[3], "source": r[4]} for r in rows]
        return jsonify({"account_id": account_id, "communities": result})
    finally:
        conn.close()
