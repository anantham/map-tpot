"""Curator-only historical-handle discovery, independent of Archive access."""
import logging
import os
import sqlite3

from flask import Blueprint, jsonify, request
from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.data.shadow_search import search_shadow_evidence
from src.data.social_paths import NetworkCoverageError

research_notes_shadow_bp = Blueprint('research_notes_shadow', __name__, url_prefix='/api/research-notes')
logger = logging.getLogger(__name__)


@research_notes_shadow_bp.get('/shadow/search')
@curator_only
def search_historical():
    try:
        return jsonify(search_shadow_evidence(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            request.args.get('q', ''), from_handle=request.args.get('fromHandle') or None,
            max_hops=int(request.args.get('maxHops', '2')), limit=int(request.args.get('limit', '25'))))
    except NetworkCoverageError as error:
        return error_response(str(error), status=422)
    except ValueError as error:
        return error_response(str(error), status=400)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Historical shadow search unavailable (%s)', type(error).__name__)
        return error_response('Historical shadow search is unavailable; inspect the local graph. Other search modes remain separate.', status=503)
