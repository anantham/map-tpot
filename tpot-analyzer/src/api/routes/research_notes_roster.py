"""Authenticated browsing of retained following custody, never graph admission."""
import logging
import os
from pathlib import Path
import sqlite3

from flask import Blueprint, current_app, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.config import DEFAULT_CACHE_DB, get_snapshot_dir
from src.data.following_roster import load_following_roster
from src.data.contact_matches import attach_roster_clue_counts
from src.data.following_evidence_coverage import attach_following_evidence

logger = logging.getLogger(__name__)
research_notes_roster_bp = Blueprint('research_notes_roster', __name__)


@research_notes_roster_bp.get('/following')
@curator_only
def get_following_roster():
    try:
        if request.args.get('coverage') not in (None,'1'):
            raise ValueError('coverage must be omitted or explicitly set to 1')
        roster=load_following_roster(
            Path(os.getenv('CACHE_DB_PATH') or DEFAULT_CACHE_DB),
            Path(get_snapshot_dir())/'account_tags.db', ego=request.args.get('ego', ''),
            graph_path=os.getenv('MAP_TPOT_RELATIONSHIP_DB'),
            capture_path=os.getenv('MAP_TPOT_FOLLOWING_CAPTURE'),
            source=request.args.get('source', 'latest'))
        roster=attach_roster_clue_counts(roster,os.getenv('MAP_TPOT_CONTACT_CANDIDATES'))
        if request.args.get('coverage')=='1':
            roster=attach_following_evidence(roster,
                graph_path=os.getenv('MAP_TPOT_RELATIONSHIP_DB'),post_path=os.getenv('MAP_TPOT_POST_INDEX'),
                catalogue=os.getenv('MAP_TPOT_CONTACT_CANDIDATES'),journal=os.getenv('MAP_TPOT_CONTACT_MATCH_DB'),
                coverage_dir=os.getenv('MAP_TPOT_FOLLOWING_COVERAGE'),
                capture_path=os.getenv('MAP_TPOT_FOLLOWING_CAPTURE'),
                client=current_app.config.get('COMMUNITY_ARCHIVE_HTTP_CLIENT'))
        response=jsonify(roster)
        response.headers['Cache-Control']='private, no-store'
        return response
    except ValueError as error:
        return error_response(str(error), status=400)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.warning('Saved following roster unavailable (%s)', type(error).__name__)
        return error_response('Saved following source is unavailable. No empty or current list was inferred; '
                              'your existing queue and tags are unchanged.', status=503)
