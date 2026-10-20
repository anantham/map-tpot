"""Curator-only raw account dossiers for Research Notes preview."""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from flask import Blueprint, current_app, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.config import DEFAULT_ARCHIVE_DB, get_snapshot_dir
from src.data.account_tag_queries import AccountTagStoreError
from src.data.archive_dossier import DossierNotFoundError, load_archive_dossier
from src.data.community_archive_dossier import PublicAccountRestricted, load_public_archive_dossier
from src.data.joined_dossier import joined_preview, supplement_for_account
from src.data.relationship_dossier import relationship_preview
from src.data.cached_websites import cached_website_preview
from src.data.contact_card import contact_card_preview
from src.data.published_profile_access import load_published_profile_access
from src.data.post_tag_frontier import build_post_tag_frontier, build_saved_api_tag_frontier
from src.data.saved_evidence import combine_previews, saved_preview
from src.api.routes.research_notes_search import research_notes_search_bp
from src.api.routes.research_notes_recovery import research_notes_recovery_bp
from src.data.shadow_aliases import shadow_alias_preview
from src.data.follow_frontier_archive import TargetFrontierError
from src.graph.target_follow_frontier import build_target_follow_frontier

logger = logging.getLogger(__name__)

research_notes_bp = Blueprint(
    "research_notes",
    __name__,
    url_prefix="/api/research-notes",
)
research_notes_bp.register_blueprint(research_notes_search_bp)
research_notes_bp.register_blueprint(research_notes_recovery_bp)

_DEFAULT_TWEET_LIMIT = 20
_MAX_TWEET_LIMIT = 100
_DEFAULT_FRONTIER_LIMIT = 20
_MAX_FRONTIER_LIMIT = 100


def _parse_limit(raw: Optional[str]) -> int:
    try:
        parsed = int(raw or _DEFAULT_TWEET_LIMIT)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed < 1 or parsed > _MAX_TWEET_LIMIT:
        raise ValueError(
            f"limit must be between 1 and {_MAX_TWEET_LIMIT}"
        )
    return parsed


def _required_query_param(name: str) -> str:
    value = (request.args.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} query param is required")
    return value


def _parse_frontier_limit(raw: Optional[str]) -> int:
    try:
        parsed = int(raw or _DEFAULT_FRONTIER_LIMIT)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed < 1 or parsed > _MAX_FRONTIER_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_FRONTIER_LIMIT}")
    return parsed


@research_notes_bp.get("/dossiers/<handle>")
@curator_only
def get_dossier(handle: str):
    """Return current public archive evidence plus independent stored observations."""

    published_status = {}
    try:
        if "frameId" in request.args:
            raise ValueError(
                "frame-bound dossiers are not implemented; "
                "use the unbound preview"
            )
        limit = _parse_limit(request.args.get("limit"))
        expected_id = request.args.get("accountId") or None
        access = load_published_profile_access(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT'))
        preview = joined_preview(os.getenv("MAP_TPOT_DOSSIER_PATH"), handle=handle, account_id=expected_id)
        saved = saved_preview(os.getenv('MAP_TPOT_RELATIONSHIP_DB'), handle=handle, account_id=expected_id,
            published_access=access)
        published_status = saved.get('publishedProfiles', {'status': access.status,
            'checkedAt': access.checked_at, 'exportId': access.export_id})
        preview = combine_previews(preview, saved)
        archive_status = "available"
        provenance = {"source": "community_archive_public_rest", "snapshotBound": False}
        try:
            source = os.getenv("MAP_TPOT_ARCHIVE_SOURCE", "community_archive_rest")
            if source == "community_archive_rest":
                account, tweets, provenance = load_public_archive_dossier(
                    handle, limit, expected_id or preview.get("accountId"),
                    client=current_app.config.get("COMMUNITY_ARCHIVE_HTTP_CLIENT"),
                )
            elif source == "local_custody":
                # Explicit diagnostic input only; not current consent eligibility.
                account, tweets = load_archive_dossier(handle, limit, preview.get("account"))
                provenance = {"source": "mutable_local_archive", "snapshotBound": False}
            else:
                raise RuntimeError("Review archive source is not configured")
        except PublicAccountRestricted:
            raise  # Explicit restriction must not become a historical archive fallback.
        except (DossierNotFoundError, FileNotFoundError, sqlite3.DatabaseError, RuntimeError):
            if preview.get("status") != "available":
                raise
            account, tweets, archive_status = preview["account"], [], "unavailable"
            provenance = {"source": "offline_joined_read_view", "snapshotBound": False}
        if expected_id and expected_id != account["accountId"]:
            raise ValueError("requested account ID and archive handle disagree")
        evidence = supplement_for_account(preview, account["accountId"])
        graph_path = os.getenv('MAP_TPOT_RELATIONSHIP_DB')
        relationships = relationship_preview(graph_path, account_id=account['accountId'], published_access=access)
        cached = cached_website_preview(os.getenv('ARCHIVE_DB_PATH', str(DEFAULT_ARCHIVE_DB)),
            graph_path, account_id=account['accountId'], published_access=access)
        try:
            contact_card = contact_card_preview(graph_path, account_id=account['accountId'],
                account=account, joined=evidence, relationships=relationships,
                cached=cached, published_access=access)
        except Exception as exc:  # Isolate this optional projection from healthy dossier evidence.
            logger.warning('Saved contact card projection unavailable (%s)', type(exc).__name__)
            contact_card = {'status': 'unavailable', 'accountId': account['accountId'],
                'items': [], 'coverage': [], 'truncated': False}
        return jsonify(
            {
                "bindingStatus": "unbound",
                "provenance": provenance,
                "account": account,
                "tweets": tweets,
                "archiveStatus": archive_status,
                "joinedEvidence": evidence,
                "savedEvidenceStatus": saved['status'],
                "shadowAliasEvidence": shadow_alias_preview(
                    os.getenv('MAP_TPOT_RELATIONSHIP_DB'),handle=account.get('username') or handle),
                "publishedProfiles": published_status,
                "relationshipEvidence": relationships,
                "cachedWebsiteEvidence": cached,
                "contactCard": contact_card,
            }
        )
    except DossierNotFoundError as exc:
        if published_status.get('status') in ('unchecked', 'unavailable', 'withdrawn', 'superseded', 'partial'):
            return error_response(str(exc)+' Saved Archive profile evidence is hidden by the current publication check, not known to be absent.',
                status=404, details={'publishedProfiles': published_status})
        return error_response(str(exc), status=404)
    except ValueError as exc:
        return error_response(str(exc))
    except (FileNotFoundError, sqlite3.DatabaseError, RuntimeError) as exc:
        logger.error("Research Notes dossier unavailable: %s", exc)
        return error_response(
            "Research Notes dossier is unavailable",
            status=500,
        )
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.exception("Unexpected Research Notes dossier failure: %s", exc)
        return error_response("internal_error", status=500)


@research_notes_bp.get("/frontier")
@curator_only
def get_target_frontier():
    """Return an exact-tag follow ranking with observable diagnostics."""
    try:
        ego = _required_query_param("ego")
        tag = _required_query_param("tag")
        limit = _parse_frontier_limit(request.args.get("limit"))
        archive_path = Path(os.getenv("ARCHIVE_DB_PATH", str(DEFAULT_ARCHIVE_DB)))
        payload = build_target_follow_frontier(
            tag_db_path=Path(get_snapshot_dir()) / "account_tags.db",
            archive_db_path=archive_path,
            ego=ego,
            tag=tag,
            limit=limit,
            ranking=request.args.get("ranking", "selectivity"),
        )
        return jsonify(payload)
    except ValueError as exc:
        return error_response(str(exc))
    except (
        AccountTagStoreError,
        TargetFrontierError,
        FileNotFoundError,
        sqlite3.DatabaseError,
    ) as exc:
        logger.error("Research Notes target frontier unavailable: %s", exc)
        return error_response(
            "Research Notes target frontier is unavailable; inspect the API log",
            status=500,
        )
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.exception("Unexpected Research Notes frontier failure: %s", exc)
        return error_response("internal_error", status=500)




@research_notes_bp.get('/posts/frontier')
@curator_only
def get_post_tag_frontier():
    try:
        source = request.args.get('source', 'archive')
        if source not in ('archive', 'saved_api_refs'):
            raise ValueError('Tag reference source must be archive or saved_api_refs')
        if source == 'saved_api_refs':
            unsupported = set(request.args) - {'source','ego','tag','limit','types','direction','minSupport'}
            if unsupported:
                raise ValueError('Saved API tag discovery does not support these filters: '+', '.join(sorted(unsupported)))
            return jsonify(build_saved_api_tag_frontier(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
                Path(get_snapshot_dir())/'account_tags.db',ego=_required_query_param('ego'),
                tag=_required_query_param('tag'),limit=int(request.args.get('limit','20')),
                min_support=int(request.args.get('minSupport','1')),
                direction=request.args.get('direction','outgoing'),
                kinds=request.args['types'].split(',') if 'types' in request.args else None))
        return jsonify(build_post_tag_frontier(os.getenv('MAP_TPOT_POST_INDEX'),
            Path(get_snapshot_dir())/'account_tags.db',ego=_required_query_param('ego'),
            tag=_required_query_param('tag'),limit=int(request.args.get('limit','20')),
            query=request.args.get('q',''),post_within_days=int(request.args.get('postWithinDays','90')),
            min_posts=int(request.args.get('minPosts','3')),
            latest_within_days=int(request.args.get('latestWithinDays','90')),
            min_support=int(request.args.get('minSupport','1')),
            direction=request.args.get('direction','outgoing'),
            kinds=request.args['types'].split(',') if 'types' in request.args else None,
            as_of=current_app.config.get('DISCOVERY_AS_OF'),
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT')))
    except ValueError as error:
        return error_response(str(error),status=400)
    except (OSError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Tag post-reference discovery unavailable (%s): %s',type(error).__name__,error)
        if request.args.get('source') == 'saved_api_refs':
            return error_response('Saved API tag discovery is unavailable. Retry or check the saved relationship and tag stores; no Archive or follow fallback was used.',status=503)
        return error_response('Tag post-reference discovery is unavailable. Try more specific content words, a shorter post window, or retry; if it persists, check the index and tag store. Saved-follow discovery remains separate.',status=503)
