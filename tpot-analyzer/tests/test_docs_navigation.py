"""Reader-facing docs navigation, using a disposable invented repository.

Test intent: require a README route to the docs hub, catch broken local links,
and allow existing relative file, directory and fragment link forms.
"""
from pathlib import Path

import pytest

from scripts.verify_docs_hygiene import run_checks


def navigation(tmp_path: Path, *, missing_hub: bool = False, broken: bool = False):
    repo = tmp_path / 'repo'
    project = repo / 'tpot-analyzer'
    files = {
        repo / 'README.md': '[App](tpot-analyzer/README.md)' if missing_hub else
            '[Docs](tpot-analyzer/docs/index.md)',
        project / 'README.md': '[Docs](./docs/index.md)',
        project / 'docs/README.md': '[Docs](index.md#start)',
        project / 'docs/index.md': '[Guide](guides/missing.md)' if broken else
            '[Guide](guides/example.md#example) [ADRs](adr/) [Web](https://example.test)',
        project / 'docs/guides/example.md': '# Example\n',
        project / 'docs/archive/legacy-community-map.md': '[Docs](../index.md)',
    }
    for path, body in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    (project / 'docs/adr').mkdir()
    return {check.name: check for check in run_checks(project)
            if check.name in ('README documentation routes', 'Entry-point local links')}


def test_readmes_lead_to_real_docs_with_valid_relative_links(tmp_path):
    checks = navigation(tmp_path)
    assert len(checks) == 2, 'Verifier does not check the reader entrypoints'
    assert all(check.passed for check in checks.values())


@pytest.mark.parametrize('options, failed, detail', [
    ({'missing_hub': True}, 'README documentation routes', 'README.md'),
    ({'broken': True}, 'Entry-point local links', 'guides/missing.md'),
])
def test_missing_hub_and_broken_local_link_are_reported(tmp_path, options, failed, detail):
    checks = navigation(tmp_path, **options)
    assert len(checks) == 2, 'Verifier does not check the reader entrypoints'
    assert not checks[failed].passed
    assert detail in checks[failed].detail
