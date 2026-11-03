#!/usr/bin/env python3
"""Verify exact-account saved API dossier behavior with disposable synthetic state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = Path(tempfile.mkdtemp(prefix='tpot-api-dossier-check-'))
    state.chmod(0o700)
    env = dict(os.environ)
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH', 'MAP_TPOT_RELATIONSHIP_DB', 'MAP_TPOT_POST_INDEX',
                'MAP_TPOT_ARCHIVE_CACHE_DIR', 'TPOT_LEASE_ROOT', 'TPOT_RESOURCE_LEASE_ROOT',
                'RESEARCH_NOTES_SOURCE_PATH', 'RESEARCH_NOTES_PROPOSALS_PATH'):
        env[key] = str(state/key)
    for key in ('SUPABASE_KEY', 'TWITTERAPIIO_API_KEY', 'OPENROUTER_API_KEY'):
        env.pop(key, None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT),
               PYTEST_ADDOPTS='-p no:cacheprovider', NO_COLOR='1')
    checks = [('Saved API dossier, identity and refusal behavior',
        [sys.executable, '-B', '-m', 'pytest', '-q', 'tests/test_saved_api_dossier.py',
         'tests/test_saved_api_posts.py', 'tests/test_saved_api_timeline.py'])]
    passed = True
    print(f'Synthetic state: {state}', flush=True)
    for label, command in checks:
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            output, ok = result.stdout+'\n'+result.stderr, result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            output, ok = str(error), False
        (state/'checks.log').write_text(output)
        print(output, flush=True)
        print(f'{"✓" if ok else "✗"} {label}', flush=True)
        passed &= ok
    print('Next: UI behavior, combined acceptance and code-only review before private serving.'
          if passed else f'STOP: inspect {state}/checks.log before another attempt.')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
