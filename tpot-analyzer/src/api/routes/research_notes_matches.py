"""Curator-private recovered person-card association review, no identity merges."""
import logging
import os
from pathlib import Path
import sqlite3

from flask import Blueprint,jsonify,request

from src.api.curator_auth import curator_only
from src.api.curation_source import require_curation_source
from src.api.responses import error_response
from src.config import get_snapshot_dir
from src.data.contact_matches import contact_match_preview,record_contact_match,normalize_match_subject
from src.data.saved_evidence import saved_profile_locators
from src.data.person_card_claims import attach_website_claims

logger=logging.getLogger(__name__)
research_notes_matches_bp=Blueprint('research_notes_matches',__name__)


@research_notes_matches_bp.route('/accounts/<account_id>/contact-matches',methods=['GET','POST'])
@curator_only
def contact_matches(account_id):
    try:
        aid,ego=normalize_match_subject(account_id,request.args.get('ego'))
        catalogue=os.getenv('MAP_TPOT_CONTACT_CANDIDATES')
        if not catalogue:
            if request.method=='POST':return error_response('Recovered matches are not configured',status=503)
            return jsonify({'status':'not_configured','accountId':aid,'ego':ego,'matches':[]})
        graph=os.getenv('MAP_TPOT_RELATIONSHIP_DB')
        if not graph or aid not in saved_profile_locators(graph,[aid]):
            return error_response('No admitted independent profile for this account',status=404)
        journal=Path(os.getenv('MAP_TPOT_CONTACT_MATCH_DB') or Path(get_snapshot_dir())/'person_card_reviews.db')
        if request.method=='GET':
            result=contact_match_preview(catalogue,journal,account_id=aid,ego=ego)
        else:
            source=require_curation_source(request)
            data=request.get_json(silent=True)
            if not isinstance(data,dict) or set(data)!={'candidateId','state'}:
                raise ValueError('Body requires only candidateId and state')
            result=record_contact_match(catalogue,journal,account_id=aid,ego=ego,
                candidate_id=data['candidateId'],state=data['state'],source=source)
        response=jsonify(attach_website_claims(result,graph));response.headers['Cache-Control']='private, no-store'
        return response
    except LookupError:
        return error_response('Candidate does not belong to this account',status=404)
    except ValueError as error:
        # Validation of user inputs is useful; catalogue errors must not leak private values.
        if request.method=='POST' and str(error) in (
                'Body requires only candidateId and state','State must be possible, confirmed or rejected',
                'Candidate ID is required'):
            return error_response(str(error))
        if str(error) in ('Exact numeric account ID is required','Reviewer identity is required') or 'X-TPOT-Curation-Source' in str(error):
            return error_response(str(error))
        logger.warning('Recovered matches unavailable (%s)',type(error).__name__)
        return error_response('Recovered matches could not be read or saved; existing dossier and tags are unchanged',status=503)
    except (OSError,RuntimeError,sqlite3.Error) as error:
        logger.warning('Recovered matches unavailable (%s)',type(error).__name__)
        return error_response('Recovered matches could not be read or saved; existing dossier and tags are unchanged',status=503)
