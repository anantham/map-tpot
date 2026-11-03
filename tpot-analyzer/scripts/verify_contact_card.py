#!/usr/bin/env python3
"""Verify contact-card source preservation and preview priority with invented data."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--priority-only', action='store_true', help='Run the focused regression cases only')
    args = parser.parse_args()
    state = Path(tempfile.mkdtemp(prefix='tpot-contact-card-check-'))
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
    files = ['tests/test_contact_card_priority.py']
    if not args.priority_only:
        files += ['tests/test_contact_card.py', 'tests/test_contact_card_deduplication.py',
                  'tests/test_contact_card_routes.py', 'tests/test_contact_catalog.py',
                  'tests/test_profile_contact_clues.py']
    command = [sys.executable, '-B', '-m', 'pytest', '-q', *files]
    print(f'Contact-card verification: {len(files)} synthetic test modules; isolated state: {state}', flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        output, passed = result.stdout+'\n'+result.stderr, result.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as error:
        output, passed = str(error), False
    (state/'checks.log').write_text(output)
    print(output, flush=True)
    print(f'{"✓" if passed else "✗"} Contact affordances, source/identity guards and displayed counts')
    print('Next: combined Research Notes acceptance, code-only review, then approved private serving.'
          if passed else f'STOP: inspect {state}/checks.log; do not retry unchanged checks.')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
