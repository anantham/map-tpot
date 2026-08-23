from __future__ import annotations

from datetime import datetime, timezone

import httpx

from scripts.refresh_community_archive_snapshot import (
    DEFAULT_MAX_BYTES,
    build_parser,
    main as refresh_main,
)
from scripts.verify_community_archive_snapshot import main as verify_main


URL = "https://example.test/enriched_tweets.parquet"


def test_refresh_parser_is_probe_only_by_default():
    args = build_parser().parse_args([])

    assert args.download is False
    assert args.max_bytes == DEFAULT_MAX_BYTES


def test_refresh_probe_does_not_issue_get(tmp_path, capsys):
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.method == "HEAD"
        return httpx.Response(
            200,
            headers={
                "ETag": '"v1"',
                "Last-Modified": "Sat, 25 Jul 2026 04:51:22 GMT",
                "Content-Length": "12",
                "Content-Type": "application/octet-stream",
            },
        )

    def client_factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler))

    result = refresh_main(
        [
            "--url",
            URL,
            "--output-root",
            str(tmp_path),
            "--observed-at",
            datetime(2026, 7, 26, tzinfo=timezone.utc).isoformat(),
        ],
        client_factory=client_factory,
    )

    assert result == 0
    assert methods == ["HEAD"]
    output = capsys.readouterr().out
    assert "✓ remote metadata" in output
    assert "Probe only" in output


def test_verifier_reports_missing_manifest_as_failure(tmp_path, capsys):
    result = verify_main([str(tmp_path / "missing")])

    assert result == 1
    output = capsys.readouterr().out
    assert "✗ manifest exists" in output
    assert "Next steps" in output
