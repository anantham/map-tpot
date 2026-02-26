"""Branches API — branch/snapshot versioning for community maps.

Blueprint: /api/communities/branches
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, jsonify, request

from src.communities import store

logger = logging.getLogger(__name__)

branches_bp = Blueprint("branches", __name__, url_prefix="/api/communities/branches")

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "archive_tweets.db"


def _get_db() -> sqlite3.Connection:
    db_path = os.getenv("ARCHIVE_DB_PATH", str(_DEFAULT_DB))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    # Ensure branch/snapshot tables exist (idempotent CREATE IF NOT EXISTS)
    store.init_db(conn)
    return conn


@branches_bp.route("", methods=["GET"])
def list_branches_route():
    """List all branches. Auto-creates 'main' on first call."""
    conn = _get_db()
    try:
        store.ensure_main_branch(conn)
        rows = store.list_branches(conn)
        return jsonify([
            {
                "id": r[0], "name": r[1], "description": r[2],
                "base_run_id": r[3], "is_active": bool(r[4]),
                "snapshot_count": r[5], "created_at": r[6], "updated_at": r[7],
            }
            for r in rows
        ])
    finally:
        conn.close()


@branches_bp.route("", methods=["POST"])
def create_branch_route():
    """Create a new branch forked from current state."""
    conn = _get_db()
    try:
        store.ensure_main_branch(conn)
        body = request.get_json() or {}
        name = body.get("name")
        if not name:
            return jsonify({"error": "name is required"}), 400

        # Check uniqueness
        exists = conn.execute(
            "SELECT 1 FROM community_branch WHERE name = ?", (name,)
        ).fetchone()
        if exists:
            return jsonify({"error": f"branch '{name}' already exists"}), 409

        # Auto-save current branch
        current = store.get_active_branch(conn)
        if current:
            store.capture_snapshot(conn, current["id"], name="auto-save before fork")

        # Create new branch
        branch_id = str(uuid4())
        latest_run = conn.execute(
            "SELECT run_id FROM community_run ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        base_run_id = body.get("base_run_id") or (latest_run[0] if latest_run else None)

        store.create_branch(
            conn, branch_id, name,
            description=body.get("description"),
            base_run_id=base_run_id,
        )
        store.set_active_branch(conn, branch_id)
        conn.commit()

        # Snapshot current state onto new branch
        store.capture_snapshot(
            conn, branch_id,
            name="forked from " + (current["name"] if current else "scratch"),
        )

        branch = store.get_active_branch(conn)
        return jsonify(branch), 201
    finally:
        conn.close()


@branches_bp.route("/<branch_id>", methods=["PATCH"])
def update_branch_route(branch_id):
    """Rename or update branch description."""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        name = body.get("name")
        description = body.get("description")

        if name:
            conn.execute(
                "UPDATE community_branch SET name = ?, updated_at = ? WHERE id = ?",
                (name, store.now_utc(), branch_id),
            )
        if description is not None:
            conn.execute(
                "UPDATE community_branch SET description = ?, updated_at = ? WHERE id = ?",
                (description, store.now_utc(), branch_id),
            )
        conn.commit()
        return jsonify({"updated": True})
    finally:
        conn.close()


@branches_bp.route("/<branch_id>", methods=["DELETE"])
def delete_branch_route(branch_id):
    """Delete a non-active branch."""
    conn = _get_db()
    try:
        try:
            store.delete_branch(conn, branch_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"deleted": True})
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/switch", methods=["POST"])
def switch_branch_route(branch_id):
    """Switch to a different branch."""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        action = body.get("action", "save")
        save_current = action == "save"

        store.switch_branch(conn, branch_id, save_current=save_current)
        branch = store.get_active_branch(conn)
        return jsonify(branch)
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/dirty", methods=["GET"])
def dirty_check_route(branch_id):
    """Check if working state differs from latest snapshot."""
    conn = _get_db()
    try:
        dirty = store.is_branch_dirty(conn, branch_id)
        return jsonify({"branch_id": branch_id, "dirty": dirty})
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/snapshots", methods=["GET"])
def list_snapshots_route(branch_id):
    """List snapshots on a branch."""
    conn = _get_db()
    try:
        snaps = store.list_snapshots(conn, branch_id)
        return jsonify(snaps)
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/snapshots", methods=["POST"])
def save_snapshot_route(branch_id):
    """Save a snapshot on the current branch."""
    conn = _get_db()
    try:
        body = request.get_json() or {}
        snap_id = store.capture_snapshot(conn, branch_id, name=body.get("name"))
        snap = conn.execute(
            "SELECT id, branch_id, name, created_at FROM community_snapshot WHERE id = ?",
            (snap_id,),
        ).fetchone()
        return jsonify({
            "id": snap[0], "branch_id": snap[1],
            "name": snap[2], "created_at": snap[3],
        }), 201
    finally:
        conn.close()


@branches_bp.route("/<branch_id>/snapshots/<snapshot_id>/restore", methods=["POST"])
def restore_snapshot_route(branch_id, snapshot_id):
    """Restore a snapshot."""
    conn = _get_db()
    try:
        # Verify snapshot belongs to branch
        snap = conn.execute(
            "SELECT 1 FROM community_snapshot WHERE id = ? AND branch_id = ?",
            (snapshot_id, branch_id),
        ).fetchone()
        if not snap:
            return jsonify({"error": "snapshot not found on this branch"}), 404

        store.restore_snapshot(conn, snapshot_id)
        return jsonify({"restored": True, "snapshot_id": snapshot_id})
    finally:
        conn.close()
