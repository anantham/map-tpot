#!/usr/bin/env python3
"""Verify reading/editor regressions; CSS acceptance still needs a real browser."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    graph = root/'graph-explorer'
    output = Path(tempfile.mkdtemp(prefix='tpot-reading-checks-'))
    output.chmod(0o700)
    environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'NO_COLOR':'1'}
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
        'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
        'MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT',
        'RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH'):
        environment[key] = str(output/'state'/key)
    binary = graph/'node_modules/.bin'
    jobs = [
        ('Existing reading and judgment behavior', [str(binary/'vitest'),'run',
            '--configLoader','runner','--maxWorkers','2',
            'src/ResearchNotesInbox.tagging.test.jsx',
            'src/ResearchNotesInbox.persistence.test.jsx',
            'src/ResearchNotesInbox.disclosure.test.jsx',
            'src/ResearchNotesInbox.search.test.jsx',
            'src/researchNotes/SavedApiPost.test.jsx',
            'src/researchNotes/RecoveryChannelComparison.test.jsx']),
        ('Scoped lint', [str(binary/'eslint'),'src/researchNotes/AccountJudgmentDrawer.jsx']),
        ('Production bundle', [str(binary/'vite'),'build','--configLoader','runner',
            '--outDir',str(output/'ui')]),
    ]
    failures = 0
    print('Review reading workspace checks (synthetic, no live writes)',flush=True)
    for index,(name,command) in enumerate(jobs):
        try:
            result = subprocess.run(command,cwd=graph,env=environment,
                text=True,capture_output=True,timeout=60)
            detail = result.stdout+'\n'+result.stderr
            passed = result.returncode == 0
        except subprocess.TimeoutExpired as error:
            partial = [part.decode(errors='replace') if isinstance(part,bytes) else part
                for part in (error.stdout,error.stderr) if part]
            detail = '\n'.join([str(error),*partial])
            passed = False
        except OSError as error:
            detail = str(error)
            passed = False
        log = output/f'{index+1}.log'
        log.write_text(detail);log.chmod(0o600)
        print(f'{"✓" if passed else "✗"} {name}: {log}',flush=True)
        for line in detail.splitlines():
            if any(marker in line for marker in ('Test Files','Tests ','Duration')):
                print(line.strip(),flush=True)
        print('\n'.join(detail.splitlines()[-5:]),flush=True)
        failures += not passed
    print(f'Checks: {len(jobs)} | Passed: {len(jobs)-failures} | Failed: {failures}')
    print('Next: browser sidebar search -> source -> dossier -> editor; check')
    print('independent scroll, keyboard exit and narrow/short normal flow.')
    print('This script does not claim CSS geometry or browser acceptance.')
    return int(bool(failures))


if __name__ == '__main__':raise SystemExit(main())
