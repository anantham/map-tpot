"""Authenticated, read-only graph recovery experiment. No label writes."""
import logging
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.config import get_snapshot_dir
from src.data.account_tag_queries import AccountTagStoreError
from src.data.seed_recovery import build_seed_recovery

logger = logging.getLogger(__name__)
research_notes_recovery_bp = Blueprint('research_notes_recovery',__name__)


@research_notes_recovery_bp.get('/recovery')
@curator_only
def get_seed_recovery():
    try:
        unknown = set(request.args)-{'ego','tag','layer','direction','method','limit'}
        if unknown:raise ValueError('Unsupported recovery parameters: '+', '.join(sorted(unknown)))
        result = build_seed_recovery(os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            os.getenv('MAP_TPOT_POST_INDEX'),Path(get_snapshot_dir())/'account_tags.db',
            ego=request.args.get('ego'),tag=request.args.get('tag'),
            layer=request.args.get('layer','follows'),direction=request.args.get('direction','outgoing'),
            method=request.args.get('method','two_hop'),limit=int(request.args.get('limit','20')),
            client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT'))
        return jsonify(result)
    except ValueError as error:
        return error_response(str(error),status=400)
    except (OSError,RuntimeError,sqlite3.Error,AccountTagStoreError,KeyError,TypeError) as error:
        logger.warning('Graph recovery unavailable (%s)',type(error).__name__)
        return error_response('Graph recovery is unavailable. Check source readiness or retry; no text-search fallback or label change was used.',status=503)
