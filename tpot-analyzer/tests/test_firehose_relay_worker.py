from __future__ import annotations

import json

import pytest

from scripts.firehose_relay.worker import RelayConfig, run_relay


@pytest.mark.integration
def test_firehose_relay_dry_run_processes_spectator_only(tmp_path) -> None:
    firehose_path = tmp_path / "feed_events.ndjson"
    checkpoint_path = tmp_path / "relay_checkpoint.json"
    firehose_path.write_text(
        "\n".join(
            [
                json.dumps({"payload": {"engagementType": "spectator", "id": "1"}}),
                json.dumps({"payload": {"engagementType": "participant", "id": "2"}}),
                "invalid-json-line",
                json.dumps({"payload": {"engagementType": "spectator", "id": "3"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    checkpoint = run_relay(
        RelayConfig(
            firehose_path=firehose_path,
            checkpoint_path=checkpoint_path,
            endpoint_url="http://localhost/dry-run",
            once=True,
            dry_run=True,
            batch_size=10,
            allow_participant=False,
        )
    )

    assert checkpoint.events_read_total == 3
    assert checkpoint.events_forwarded_total == 2
    assert checkpoint.events_skipped_participant_total == 1
    assert checkpoint.parse_errors_total == 1
    assert checkpoint.byte_offset == firehose_path.stat().st_size
    assert checkpoint.batches_sent_total == 1
    assert checkpoint.batches_failed_total == 0


@pytest.mark.integration
def test_firehose_relay_resume_from_checkpoint(tmp_path) -> None:
    firehose_path = tmp_path / "feed_events.ndjson"
    checkpoint_path = tmp_path / "relay_checkpoint.json"
    firehose_path.write_text(
        json.dumps({"payload": {"engagementType": "spectator", "id": "1"}}) + "\n",
        encoding="utf-8",
    )

    first = run_relay(
        RelayConfig(
            firehose_path=firehose_path,
            checkpoint_path=checkpoint_path,
            endpoint_url="http://localhost/dry-run",
            once=True,
            dry_run=True,
            batch_size=10,
        )
    )
    assert first.events_forwarded_total == 1

    with firehose_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"payload": {"engagementType": "spectator", "id": "2"}}) + "\n")

    second = run_relay(
        RelayConfig(
            firehose_path=firehose_path,
            checkpoint_path=checkpoint_path,
            endpoint_url="http://localhost/dry-run",
            once=True,
            dry_run=True,
            batch_size=10,
        )
    )
    assert second.events_forwarded_total == 2
    assert second.events_read_total == 2
    assert second.byte_offset == firehose_path.stat().st_size
