#!/usr/bin/env python3
"""Verify independent recovery channels on invented state; never read live tags."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = Path(tempfile.mkdtemp(prefix='tpot-recovery-channels-check-'))
    state.chmod(0o700)
    env = dict(os.environ)
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH', 'MAP_TPOT_RELATIONSHIP_DB', 'MAP_TPOT_POST_INDEX',
                'MAP_TPOT_ARCHIVE_CACHE_DIR', 'TPOT_LEASE_ROOT', 'TPOT_RESOURCE_LEASE_ROOT',
                'RESEARCH_NOTES_SOURCE_PATH', 'RESEARCH_NOTES_PROPOSALS_PATH',
                'MAP_TPOT_CONTACT_CANDIDATES', 'MAP_TPOT_CONTACT_MATCH_DB'):
        env[key] = str(state/key)
    env.pop('MAP_TPOT_FOLLOWING_CAPTURE', None)
    env.pop('MAP_TPOT_FOLLOWING_COVERAGE', None)
    for key in ('SUPABASE_KEY', 'TWITTERAPIIO_API_KEY', 'OPENROUTER_API_KEY'):
        env.pop(key, None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT), NO_COLOR='1',
               PYTEST_ADDOPTS='-p no:cacheprovider')
    graph = ROOT/'graph-explorer'
    checks = [
        ('Seven independent channels plus optional shared following, exact sources, cancellation and retry',
         [str(graph/'node_modules/.bin/vitest'), 'run', '--configLoader', 'runner',
          '--maxWorkers', '2', 'src/researchNotes/RecoveryChannelComparison.test.jsx',
          'src/researchNotes/SeedRecoveryPanel.test.jsx', 'src/researchNotes/SavedApiPaths.test.jsx',
          'src/researchNotes/PostInteractionSearch.test.jsx',
          'src/researchNotes/SharedFollowingPanel.test.jsx', 'src/researchNotes/researchNotesApi.test.js'], graph),
        ('Unchanged seed engine, qualified API sources and auth',
         [sys.executable, '-B', '-m', 'pytest', '-q', 'tests/test_seed_recovery.py',
          'tests/test_seed_recovery_routes.py', 'tests/test_seed_recovery_references.py',
          'tests/test_saved_api_paths.py', 'tests/test_shared_following_review.py',
          'tests/test_cofollow_recovery.py', 'tests/test_historical_handle_recovery.py',
          'tests/test_graph_imports.py'], ROOT),
    ]
    passed = 0
    print(f'Synthetic state: {state}', flush=True)
    for number, (label, command, cwd) in enumerate(checks, 1):
        try:
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
            output, ok = result.stdout+'\n'+result.stderr, result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            output, ok = str(error), False
        (state/f'check-{number}.log').write_text(output)
        print(output, flush=True)
        print(f'{"✓" if ok else "✗"} {label}', flush=True)
        passed += int(ok)
    print(f'Checks: {passed}/{len(checks)}; seven channels and separate experimental shared following; no tag writes.')
    print('Next: scoped lint/build, combined acceptance, independent code-only review and isolated browser flow.'
          if passed == len(checks) else f'STOP: inspect retained logs in {state} before another attempt.')
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
