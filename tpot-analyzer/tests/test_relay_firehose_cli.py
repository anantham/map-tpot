from __future__ import annotations

import pytest

from scripts.relay_firehose_to_indra import (
    DEFAULT_INDRA_FIREHOSE_ENDPOINT,
    parse_args,
)


@pytest.mark.unit
def test_relay_cli_default_endpoint_is_local_indra(monkeypatch) -> None:
    monkeypatch.delenv("INDRA_FIREHOSE_ENDPOINT", raising=False)
    args = parse_args([])
    assert args.endpoint_url == DEFAULT_INDRA_FIREHOSE_ENDPOINT


@pytest.mark.unit
def test_relay_cli_uses_env_endpoint_when_present(monkeypatch) -> None:
    monkeypatch.setenv("INDRA_FIREHOSE_ENDPOINT", "http://localhost:9090/custom/firehose")
    args = parse_args([])
    assert args.endpoint_url == "http://localhost:9090/custom/firehose"


@pytest.mark.unit
def test_relay_cli_blank_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("INDRA_FIREHOSE_ENDPOINT", "   ")
    args = parse_args([])
    assert args.endpoint_url == DEFAULT_INDRA_FIREHOSE_ENDPOINT
