#!/usr/bin/env python3
"""Synthetic history/source regressions; never opens the real graph or tags."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root=Path(__file__).resolve().parents[1];ui=root/'graph-explorer'
    output=Path(tempfile.mkdtemp(prefix='tpot-profile-history-checks-'));output.chmod(0o700)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NO_COLOR':'1'}
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
        'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
        'MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT',
        'RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH'):
        env[key]=str(output/'state'/key)
    binary=ui/'node_modules/.bin'
    jobs=[('Profile history and source gates',[sys.executable,'-B','-m','pytest',
        'tests/test_profile_history_search.py','tests/test_stored_post_text.py','-q'],root),
        ('Visible dated evidence',[str(binary/'vitest'),'run','--configLoader','runner',
         '--maxWorkers','2','src/researchNotes/ProfileEvidence.test.jsx',
         'src/researchNotes/SavedEvidenceSearch.test.jsx','src/researchNotes/UnifiedSearch.test.jsx'],ui),
        ('Scoped lint',[str(binary/'eslint'),'src/researchNotes/SavedEvidenceMatches.jsx',
         'src/researchNotes/ProfileEvidence.test.jsx'],ui),
        ('Production bundle',[str(binary/'vite'),'build','--configLoader','runner',
         '--outDir',str(output/'ui')],ui)]
    failures=0
    print('Historical profile evidence verification; synthetic sources only',flush=True)
    for number,(name,command,cwd) in enumerate(jobs,1):
        try:
            result=subprocess.run(command,cwd=cwd,env=env,text=True,capture_output=True,timeout=60)
            passed=result.returncode==0;detail=result.stdout+'\n'+result.stderr
        except subprocess.TimeoutExpired as error:
            parts=[value.decode(errors='replace') if isinstance(value,bytes) else value
                for value in (error.stdout,error.stderr) if value]
            passed=False;detail='\n'.join([str(error),*parts])
        except OSError as error:passed=False;detail=str(error)
        log=output/f'{number}.log';log.write_text(detail);log.chmod(0o600)
        print(f'{"✓" if passed else "✗"} {name}: {log}',flush=True)
        metrics=[line.strip() for line in detail.splitlines()
            if any(token in line for token in (' passed',' failed','Test Files','Duration'))]
        print('\n'.join(metrics or detail.splitlines()[-4:]),flush=True)
        failures+=not passed
    print(f'Checks: {len(jobs)} | Passed: {len(jobs)-failures} | Failed: {failures}')
    print('Next: required combined acceptance and independent source-only review,')
    print('then frozen private examples and actual search -> retained field -> exact dossier.')
    print('No import,source/tag write,live serving,paid fetching or outreach.')
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
