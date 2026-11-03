#!/usr/bin/env python3
"""Verify saved-following Review with disposable state, never private inputs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = Path(tempfile.mkdtemp(prefix='tpot-following-verify-'))
    state.chmod(0o700)
    env = dict(os.environ)
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH', 'MAP_TPOT_RELATIONSHIP_DB', 'MAP_TPOT_POST_INDEX',
                'MAP_TPOT_ARCHIVE_CACHE_DIR', 'TPOT_LEASE_ROOT', 'TPOT_RESOURCE_LEASE_ROOT',
                'RESEARCH_NOTES_SOURCE_PATH', 'RESEARCH_NOTES_PROPOSALS_PATH',
                'MAP_TPOT_CONTACT_CANDIDATES','MAP_TPOT_CONTACT_MATCH_DB'):
        env[key] = str(state/key)
    env.pop('MAP_TPOT_FOLLOWING_CAPTURE', None)
    env.pop('MAP_TPOT_FOLLOWING_COVERAGE', None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT),
               PYTEST_ADDOPTS='-p no:cacheprovider', NO_COLOR='1')
    checks = [
        ('Reader and authenticated route', ROOT, [sys.executable, '-B', '-m', 'pytest', '-q',
            'tests/test_following_roster.py', 'tests/test_following_roster_routes.py',
            'tests/test_following_capture_roster.py','tests/test_following_evidence_coverage.py']),
        ('Browse, identity refusal and live tag revisions', ROOT/'graph-explorer',
            [str(ROOT/'graph-explorer/node_modules/.bin/vitest'), 'run',
             '--configLoader', 'runner', '--maxWorkers', '2',
             'src/researchNotes/FollowingRoster.test.jsx',
             'src/researchNotes/FollowingRosterApi.test.js',
             'src/researchNotes/FollowingEvidenceCoverage.test.jsx',
             'src/ResearchNotesInbox.following.test.jsx']),
    ]
    passed = 0
    print('Saved following Review verification (synthetic sources only)', flush=True)
    for index, (name, cwd, command) in enumerate(checks):
        try:
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                    text=True, timeout=60)
            output = result.stdout + '\n' + result.stderr
            good = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            output, good = str(error), False
        (state/f'check-{index}.log').write_text(output)
        print(f'{"✓" if good else "✗"} {name}', flush=True)
        print('\n'.join(output.splitlines()[-8:]), flush=True)
        if not good:
            print(f'STOP: inspect retained output at {state}; no automatic retry.')
            return 1
        passed += 1
    print(f'✓ {passed}/{len(checks)} check groups passed; isolated logs: {state}')
    print('Next: combined Research Notes acceptance, independent code review, then approved private serving.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
