#!/usr/bin/env python3
"""Verify recovered person-card decisions with synthetic state, never live tags."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    state=Path(tempfile.mkdtemp(prefix='tpot-person-card-verification-'))
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NO_COLOR':'1'}
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','ARCHIVE_DB_PATH','CACHE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
                'MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT',
                'RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH',
                'MAP_TPOT_CONTACT_CANDIDATES','MAP_TPOT_CONTACT_MATCH_DB','MAP_TPOT_FOLLOWING_CAPTURE'):
        env[key]=str(state/key)
    commands=[('HTTP persistence, reversal, identity and refusal',ROOT,
        [sys.executable,'-B','-m','pytest','tests/test_contact_matches.py','tests/test_contact_card_routes.py',
         'tests/test_following_roster_routes.py','tests/test_person_card_claims.py','-q']),
        ('Dossier controls, failed save and stale-account response',ROOT/'graph-explorer',
        [str(ROOT/'graph-explorer/node_modules/.bin/vitest'),'run','--configLoader','runner',
         '--maxWorkers','2','src/researchNotes/PersonCardMatches.test.jsx',
         'src/researchNotes/AccountContactCard.test.jsx','src/researchNotes/RawDossier.test.jsx',
         'src/researchNotes/FollowingRoster.test.jsx'])]
    failed=0
    for name,cwd,command in commands:
        try:
            result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=60)
            passed=result.returncode==0;output=result.stdout+result.stderr
        except (OSError,subprocess.TimeoutExpired) as error:
            passed=False;output=f'{type(error).__name__}: verification could not finish'
        log=state/(name.split(',')[0].replace(' ','-')+'.log')
        log.write_text(output);log.chmod(0o600)
        print(('✓' if passed else '✗')+' '+name,flush=True)
        print('\n'.join(output.splitlines()[-8:]),flush=True)
        print('Retained synthetic log:',log,flush=True)
        failed+=not passed
    print(f'Checks: {len(commands)} | Passed: {len(commands)-failed} | Failed: {failed}')
    print('Next: independently review exact source, then verify private candidate -> card -> source; use synthetic state for browser writes.')
    return int(bool(failed))


if __name__=='__main__':raise SystemExit(main())
