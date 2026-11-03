"""Curator-only evidence search/source routes, nested under Research Notes."""
import logging
import os
import sqlite3

from flask import Blueprint, current_app, jsonify, request
from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.data.published_profile_access import load_published_profile_access
from src.data.post_search import search_posts, post_network_sources
from src.data.unified_evidence import search_all_evidence
from src.data.saved_evidence import saved_social_sources, search_saved_evidence, read_saved_store
from src.data.saved_api_paths import api_reference_sources
from src.data.social_paths import NetworkCoverageError
from src.data.channel_lookup import lookup_saved_channel

logger = logging.getLogger(__name__)
research_notes_search_bp = Blueprint('research_notes_search', __name__)


@research_notes_search_bp.post('/channels/lookup')
@curator_only
def lookup_channel():
    try:
        return jsonify(lookup_saved_channel(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),request.get_json(silent=True)))
    except ValueError as error:
        return error_response(str(error),status=400)
    except (OSError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Saved channel lookup unavailable (%s)',type(error).__name__)
        return error_response('Saved channel lookup is unavailable,not a completed no-match check. Retry after checking the local store.',status=503)


@research_notes_search_bp.get('/search')
@curator_only
def search_saved():
    try:
        access = load_published_profile_access(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT'))
        return jsonify(search_saved_evidence(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            request.args.get('q', ''), from_account_id=request.args.get('fromAccountId'),
            max_hops=int(request.args.get('maxHops', '2')), published_access=access))
    except NetworkCoverageError as error:
        return error_response(str(error), status=422)
    except ValueError as error:
        return error_response(str(error), status=400)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Saved evidence search unavailable (%s)', type(error).__name__)
        return error_response('Saved evidence search is unavailable; check the local import and API log.', status=503)


@research_notes_search_bp.get('/network/sources')
@curator_only
def get_saved_social_sources():
    try:
        kind = request.args.get('networkKind', 'follows')
        if kind == 'saved_api_refs':
            with read_saved_store(os.getenv('MAP_TPOT_RELATIONSHIP_DB')) as db:
                return jsonify(api_reference_sources(db, kinds=request.args['types'].split(',') if 'types' in request.args else None))
        if kind != 'follows': raise ValueError('Unknown saved network kind')
        return jsonify(saved_social_sources(os.getenv('MAP_TPOT_RELATIONSHIP_DB')))
    except ValueError as error:
        return error_response(str(error), status=400)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Saved follow sources unavailable (%s)', type(error).__name__)
        return error_response('Saved follow sources are unavailable; text search remains independent.', status=503)


@research_notes_search_bp.get('/search/all')
@curator_only
def search_combined():
    try:
        return jsonify(search_all_evidence(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            os.getenv('MAP_TPOT_POST_INDEX'),request.args.get('q',''),
            from_account_id=request.args.get('fromAccountId'),max_hops=int(request.args.get('maxHops','2')),
            network_kind=request.args.get('networkKind','follows'),direction=request.args.get('direction','outgoing'),
            interaction_types=request.args['types'].split(',') if 'types' in request.args else None,
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT')))
    except NetworkCoverageError as error:
        return error_response(str(error),status=422)
    except ValueError as error:
        return error_response(str(error),status=400)
    except (OSError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Combined evidence search unavailable (%s)',type(error).__name__)
        return error_response('Combined evidence search could not finish; narrow the words or retry. No stale results are retained.',status=503)


@research_notes_search_bp.get('/posts/search')
@curator_only
def search_current_posts():
    try:
        return jsonify(search_posts(os.getenv('MAP_TPOT_POST_INDEX'), request.args.get('q', ''),
            relationship_path=os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            from_account_id=request.args.get('fromAccountId'), max_hops=int(request.args.get('maxHops', '2')),
            network_kind=request.args.get('networkKind', 'follows'), direction=request.args.get('direction', 'outgoing'),
            interaction_types=request.args['types'].split(',') if 'types' in request.args else None,
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT')))
    except NetworkCoverageError as error:
        return error_response(str(error), status=422)
    except ValueError as error:
        return error_response(str(error), status=400)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Current post search unavailable (%s): %s', type(error).__name__, error)
        return error_response('Current post search is unavailable. Try more specific words or retry; if it persists, check the index and API log. Profile/work search remains separate.', status=503)


@research_notes_search_bp.get('/posts/network/sources')
@curator_only
def get_post_reference_sources():
    try:
        return jsonify(post_network_sources(os.getenv('MAP_TPOT_POST_INDEX'),
            kinds=request.args['types'].split(',') if 'types' in request.args else None,
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT')))
    except ValueError as error:
        return error_response(str(error), status=400)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Post-reference paths unavailable (%s): %s', type(error).__name__, error)
        return error_response('Post-reference paths are unavailable; check the current index projection. Unscoped post search remains available.', status=503)
