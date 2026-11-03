"""Read only the ID extension of a retained provider following capture.

Raw profiles, contacts and billing receipts are never returned to the client.
Profile locators still pass through the existing saved-evidence reader.
"""
from datetime import datetime
import json
import logging
from pathlib import Path
import re

logger=logging.getLogger(__name__)


def read_following_capture(path, *, ego, account_id):
    """Return an exact-owner, count-reconciled saved list, not live verification."""
    try:
        root = Path(path)
        receipt = json.loads((root/'receipt.json').read_bytes())
        seeds = receipt['seeds']
        if receipt['status'] != 'captured' or len(seeds) != 1:
            raise ValueError('one completed curator capture required')
        seed = seeds[0]
        if seed['handle'].strip().lstrip('@').casefold() != ego:
            return None
        roster = json.loads((root/'roster.json').read_bytes())
        if not (seed['account_id'] == roster['accountId'] == account_id):
            raise ValueError('curator account ID mismatch')
        if not (seed['complete'] is True and seed['api_terminal_page'] is True
                and roster['completeByProviderCount'] is True):
            raise ValueError('capture is incomplete')
        rows = roster['accounts']
        if not isinstance(rows, list) or len(rows) > 20_000:
            raise ValueError('invalid capture size')
        if any(type(seed[key]) is not int or seed[key] != len(rows)
               for key in ('following_claim', 'following_claim_after')):
            raise ValueError('capture counts do not reconcile')
        start, end = (datetime.fromisoformat(roster[key])
                      for key in ('capturedFrom', 'capturedTo'))
        if start.utcoffset() is None or end.utcoffset() is None or start > end:
            raise ValueError('capture requires ordered timezone-aware dates')
        observed = {}
        for index, row in enumerate(rows):
            target = row['id']
            if not isinstance(target, str) or not re.fullmatch(r'[0-9]+', target):
                raise ValueError('capture target must be an exact numeric string ID')
            if target in observed:
                raise ValueError('duplicate capture target')
            observed[target] = {'uploadedAt': None, 'importedAt': None,
                                'sourcePointer': f'/accounts/{index}'}
        return {'observed': observed, 'capturedFrom': roster['capturedFrom'],
                'capturedTo': roster['capturedTo']}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise RuntimeError('Configured following capture is unavailable or invalid') from error


def read_following_coverage(path, roster, capture_path):
    """Dated acquisition outcomes for this exact saved capture, never live facts."""
    if not path:return {'status':'not_configured'},{}
    if roster.get('rosterKind')!='saved_provider_following_capture':
        return {'status':'outside_capture'},{}
    try:
        def read(name):
            file=(Path(path)/name).resolve(strict=True)
            if not file.is_file() or file.stat().st_mode & 0o077 or file.stat().st_size>20_000_000:
                raise ValueError('Coverage requires bounded private files')
            return json.loads(file.read_bytes())
        cohort,ledger=read('cohort.json'),read('coverage-ledger.json')
        if Path(cohort['sourceCapture']).resolve()!=Path(capture_path).resolve():
            raise ValueError('Coverage belongs to a different following capture')
        when=cohort['createdAt']
        if not isinstance(when,str) or datetime.fromisoformat(when).utcoffset() is None:
            raise ValueError('Coverage date must have a timezone')
        accounts=cohort['accounts']
        if not isinstance(accounts,list) or not isinstance(ledger,list) or not 1<=len(accounts)<=20_000:
            raise ValueError('Coverage account arrays are invalid')
        ids=[r['accountId'] for r in accounts];rows={}
        if len(set(ids))!=len(ids) or any(not isinstance(a,str) or not re.fullmatch('[0-9]+',a) for a in ids):
            raise ValueError('Coverage requires unique exact numeric IDs')
        states={'bounded_pass_with_pages','bounded_pass_unavailable','no_saved_bio_website','privacy_hold'}
        for row in ledger:
            aid=row['accountId']
            if aid in rows or aid not in ids or row['status'] not in states:
                raise ValueError('Coverage subject or outcome is invalid')
            fields={'retainedPages':'retainedPageObservations','connectedPages':'connectedPages',
                    'remainingRoots':'remainingAdmittedRootUrls'}
            if any(type(row.get(field)) is not int or row[field]<0 for field in fields.values()):
                raise ValueError('Coverage counts must be nonnegative integers')
            rows[aid]={'status':row['status'],'createdAt':when,
                       **{public:row[private] for public,private in fields.items()}}
        if set(rows)!=set(ids):raise ValueError('Coverage cohort and ledger disagree')
        return {'status':'available','createdAt':when},rows
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        logger.warning('Saved following coverage unavailable (%s)',type(error).__name__)
        return {'status':'unavailable'},{}
