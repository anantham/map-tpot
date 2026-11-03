# T13/T14 outbound enrichment security — 2026-10-02

Scope: the local Flask rich-enrichment fetch boundary. This document does not
assert that Flask is publicly deployed. Authentication and other Flask workloads
are handled in the separate security boundary patch. No private archive/chat
records, live exploit targets, paid APIs or production settings were accessed.

## Assessment and intent

T13 is validated: the previous `validate_url` checked one DNS answer, then
`urllib` resolved independently before connecting. A synthetic rebinding
resolver returned a public address first and loopback second; the original
`safe_urlopen` connected its fake socket to `127.0.0.1`. That regression now
observes exactly one lookup and a socket pinned to the checked public address.

T14 is validated: HTML and images were fully read before HTML truncation and
image base64 encoding. Synthetic large/chunked/compressed responses now fail
closed before the configured byte budget is exceeded. Valid small HTML remains
cacheable, valid JSON remains usable, and valid raster images remain data URLs.
Unsupported/oversized content returns the existing empty/no-image fallback.

Assumptions: only public HTTP(S) destinations are needed for rich enrichment;
HTTP GET is sufficient; runtime dependencies are installed from requirements.
Predicted outcomes: no second DNS lookup, every redirect pinned, original TLS
hostname/Host authority retained, no oversized payload/cache write, and no
handshake/header/body trickle can outlive the fetch deadline. Initial confidence
was 0.85; focused tests and independent review support 0.93 for this scope.
Fallback: enrich without rejected links/images. Missing Pillow fails closed.

## Decisions and resulting behavior

- `url_guard.py` parses authorities, rejects credentials/control characters,
  invalid ports and scoped addresses, and rejects any non-public DNS answer.
  IPv4-mapped/transition IPv6 cannot smuggle a private IPv4 destination.
- `outbound_dns.py` uses at most four simultaneous daemon resolver calls and no
  waiting queue. Callers time out against the absolute deadline. System DNS
  cannot be safely killed: a stuck call retains one fixed slot until it ends;
  capacity exhaustion rejects new outbound work without adding threads.
- `outbound_transport.py` connects numeric validated sockaddrs directly,
  verifies the connected peer, and uses the default verifying TLS context with
  the original hostname. The Host header is server-owned; proxy variables,
  cookies and authorization headers do not affect requests. All five allowed
  redirect hops are resolved, validated and pinned independently.
- A socket shutdown timer enforces the same absolute deadline through TCP,
  TLS, headers and body. It retains the socket after HTTPConnection's automatic
  close for close-delimited bodies. The TLS socket-swap race identified during
  independent review now checks expiration before handshake and before return.
- `response_limits.py` bounds encoded and decoded payloads incrementally and
  HTTP framing to the encoded limit plus 64 KiB. It rejects ambiguous framing,
  unsupported encodings, malformed/truncated/concatenated compressed streams.
- `enrichment_fetch.py` caps HTML at 100,000 bytes, syndication JSON at 1 MiB,
  and images at 5 MiB encoded/decoded. Pillow validates actual PNG/JPEG/GIF/WebP
  bytes and decodes at most 16,000,000 pixels in one frame; detected MIME replaces
  extension guessing. Animation is skipped to prevent multiplying pixel work.
- `tweet_enrichment.py` imports the extracted fetch/cache helpers, preserves
  its public function names, and caps each enrichment at five links/three images.
  Network responses and SQLite connections close on success and failure.

## Files and modularity

Modified: `requirements.txt`, `src/api/url_guard.py`,
`src/api/tweet_enrichment.py`, `tests/test_url_guard.py`.

Added: `src/api/outbound_dns.py`, `src/api/outbound_transport.py`,
`src/api/response_limits.py`, `src/api/enrichment_fetch.py`,
`src/api/enrichment_cache.py`, `tests/test_outbound_transport.py`,
`tests/test_outbound_response_edges.py`, `tests/test_outbound_deadlines.py`,
`tests/test_enrichment_fetch.py`, `scripts/verify_security_outbound.py`, and this
diagnostic document. No files were staged or committed by this delegated agent.

The inherited enrichment monolith was 403 LOC; extraction leaves 273 LOC
(32.3% reduction). Guard was 132 LOC and is now 111 LOC. New production modules
range from 17 to 150 LOC. No JS bundle changed in this slice. No `any` types
were removed. Complexity remains concentrated in the security boundary's
parse/transport/stream checks; existing local enrichment orchestration is kept
separate. Focused statement coverage is 93% over five boundary modules, compared
with 19 legacy URL checks and no enrichment/transport stream tests previously.
Synthetic regression/verifier runs complete in about 1–3 seconds; no production
performance claim is made. All touched/new Python modules remain below 300 LOC.

AST decision-count complexity (base 1; if/loop/except/conditional-expression,
boolean branches and comprehensions counted) before → after extraction:
`fetch_syndication` 3 → 5 (ID/result validation), `resolve_tco_url` 2 → 2,
`fetch_link_content` 8 → 8, `download_image_base64` 5 → 2. The extracted image
validator is 4. Baseline statement coverage was not measured, so no numerical
coverage increase is claimed.

## Experiments, validation and calibration

Actual start: 11:24:38 UTC / 16:54:38 IST. Original estimate: 80 minutes,
with milestones at +35 minutes (pinned transport), +60 minutes (stream/image
boundary), and +80 minutes (review/evidence/regression). Dependencies were the
read-only canonical Python 3.11 environment and a usable raster decoder.

| Milestone | Original elapsed estimate | Observed elapsed | Result |
|---|---:|---:|---|
| Assessment/pinned transport | 35 minutes | 12m 53s (11:37:31 UTC) | 34 focused tests passed |
| Image/cache boundary | 60 minutes | 15m 20s (11:39:58 UTC) | 47 focused tests passed |
| Deadline/review strengthening | within 80 minutes | 24m 39s (11:49:17 UTC) | 72 focused tests passed |
| TLS swap regression/focused coverage | within 80 minutes | by 11:51:40 UTC | 74 tests passed; 93% coverage |

The early milestones benefited from a small, isolated boundary and stdlib HTTP
transport. Review added framing, bounded DNS and cancellation work within the
original margin. At 11:37 the estimate was revised to 35–45 minutes remaining;
at 11:49 it was revised to 10–20 minutes remaining pending independent review.
No completion certainty was inferred from these estimates. An intermediate
message's mistyped milestone time was corrected using the tool clock.

Experiments:

1. Rebinding hypothesis: original synthetic connect went to loopback despite
   public validation; pinned transport now connects only to the approved IP.
2. Size hypothesis: no-length/chunked payloads and gzip/deflate bombs reject at
   the encoded/decoded cap; oversized HTML leaves zero rows in the temp cache.
3. Parser review: raw framing/trailer budget added; the first wrapper run
   exposed an omitted file `flush` contract on close, corrected with cleanup
   regression coverage and a `finally` connection close.
4. Deadline review: stuck DNS, in-progress header/body reads and TLS handshakes
   terminate via synthetic events; occupied DNS slots cap at four and recover
   after workers finish. TLS socket-swap expiry cannot start a handshake.

Commands (use canonical Python; optional temporary Pillow path shown below):

```sh
PYTHONPATH=/tmp/tpot-security-outbound-deps "$TPOT_PYTHON" scripts/verify_security_outbound.py
PYTHONPATH=/tmp/tpot-security-outbound-deps "$TPOT_PYTHON" -m pytest tests/test_url_guard.py tests/test_outbound_transport.py tests/test_outbound_response_edges.py tests/test_outbound_deadlines.py tests/test_enrichment_fetch.py -q
```

`TPOT_PYTHON` is `/Volumes/AirBackup/home/Documents/Ongoing Local/Project 2 - Map TPOT - clean-main/tpot-analyzer/.venv/bin/python`.
The verifier passed all 74 tests plus module-size and declared/installed decoder
checks. A coverage run gave 93% statement coverage across URL guard, DNS,
transport, response limits and enrichment fetch. Only Pillow 12.3.0 was downloaded
into `/tmp/tpot-security-outbound-deps`; the shared venv was not changed.

Adjacent aggregate: `test_golden_routes.py`, `test_golden_support_routes.py`,
`test_label_ensemble.py`, `test_security_integration.py` produced 58 passed and
five failed. The failures are old anonymous-read expectations receiving the
new intended 401 response for communities/members/branches/seeds/extension
settings. The Flask agent owns updating those contracts and final aggregate
validation. No outbound test failed in this run.

Final independent review: the reviewer reran all 74 scoped tests successfully
and reviewed DNS slot lifetime, TLS swap checks, timer/socket cleanup, redirects
and all response budgets. No remaining exploitable blocker was identified in
this scope. Handoff clock: 11:55:39 UTC / 17:25:39 IST, 31m 01s actual versus
80 minutes originally estimated. Authentication aggregate integration remains
owned by the parent/Flask agent; the outbound slice itself is ready for review.

## Residuals and activation

The DNS worker cap deliberately trades availability for safety if the operating
system resolver stalls. The limits apply to new outbound fetches; existing cache
contents were not inspected, invalidated or deleted. Large HTML and animated
images now fall back gracefully. Other operator-configured transports outside
the rich-enrichment pipeline are outside T13/T14's scoped patch.

Install the updated requirements (Pillow 12.3.0 requires Python ≥3.10), rerun the
verifier and composed regression suite, then restart the local Flask process
under the separately approved access policy. Keep any public exposure gated on
the full authentication/workload review. Deployment, production configuration,
credential rotation, repository publication and cache/data cleanup remain
unperformed and require the user's separate authorization.
