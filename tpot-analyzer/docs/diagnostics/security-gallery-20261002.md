# Public gallery and card image security — 2026-10-02

Scope: findings T02 and T18, validated against the isolated security worktree.
No live exploit, paid model request, private data inspection, Blob write, production
configuration change, deployment, legacy-data deletion or history rewrite was performed.

## Evidence and intent

The source accepted unauthenticated gallery POSTs, arbitrary remote URLs and bytes
merely labelled as PNG/JPEG/WebP. Redis and Blob failures still returned success.
Public gallery reads echoed legacy remote/data URLs; the crawler endpoint redirected
any persisted HTTPS URL or served undecoded bytes labelled as raster images.

Four initial endpoint contracts reproduced these behaviors (4/4 expected failures).
The resulting boundary requires an operator-approved signed publication and actual
bounded raster decoding, while public reads remain anonymous. Direct own-key
creation can continue in the browser and local cache. Anonymous own-key creation
alone does not prove ownership or authorize shared-gallery publication.

Confidence in the reproduced findings: 0.95. Confidence in the implemented boundary
under the documented configuration: 0.90; deployment and legacy migration have not
been exercised. The fallback is fail closed for publication and hide unverified
legacy gallery entries, preserving their stored data for review.

## Publication contract

`POST /api/gallery-submit` accepts `{handle, imageUrl, communities?}` and a Bearer
capability from the root `_cardAdmission.js` implementation. The capability has
kind `gallery`, a normalized handle, SHA256 of the exact request body using stable
recursive key order, an approved owner subject, unique nonce and expiry. Unknown
request fields, malformed handles and community metadata are rejected before the
image is processed. The token is valid for at most ten minutes. The browser does
not receive a signing key and there is no anonymous signing endpoint.

Both publication grants and trusted generation grants consume an independent,
kind-separated gallery nonce in the same Lua operation that reserves quotas and
concurrency. A root generation request reserves gallery capacity before paying its
provider. Root generation admission separately consumes its paid-generation nonce.
Releasing a failed reservation does not restore the nonce or attempted-upload quota.
A replay cannot increment those counters a second time.

A handle's schema2 record belongs to the signed subject. Another subject cannot
append to it. The atomic store checks ownership again to cover two different owners
racing to reserve a previously empty handle. This is approved publication ownership,
not a claim that the subject has authenticated to the underlying social account.
The operator issuing capabilities must choose subjects based on the site's intended
account/publication approval policy; subject transfer is a separate reviewed change.

Failures return explicit 400/403/409/413/429/503 responses rather than claiming a
successful publication. There is no fallback to the original external/data URL.

## Image and storage boundary

`_imagePolicy.js` accepts strict canonical base64 PNG, JPEG or WebP data only.
Raster signatures are checked before entering the native decoder; active/vector
formats cannot reach their decoder through a forged raster MIME label. The image
must then fully decode with Sharp 0.35.5, match its declared format, be a single
frame and fit 2048×2048 pixels. Encoded source bytes are capped at 3 MiB; emitted
PNG bytes at 4 MiB. The output is a newly encoded PNG with source metadata stripped.
Decoder processing has a five-second Sharp timeout. Missing decoder, Blob uploader
or owned-storage configuration fails closed before a paid generation can begin.
The existing Vercel request-body limit is an additional platform boundary, not a
replacement for the application byte and dimension checks.
Decoder settings were checked against Sharp's primary [constructor](https://sharp.pixelplumbing.com/api-constructor/)
and [output](https://sharp.pixelplumbing.com/api-output/) documentation.

`CARD_BLOB_BASE_URL` must be the exact HTTPS origin of the intended public Vercel
Blob store, e.g. `https://<storeid>.public.blob.vercel-storage.com`. It cannot have a
port, credentials, path, query or fragment. New uploads use
`cards/<normalized-handle>-<UUID>.png`, a PNG content type, and no random suffix.
The returned URL is validated against that origin and handle path before storage.
Public URLs reject other stores, suffix lookalikes, encoded or dot path segments,
credentials, explicit ports, active formats, queries, fragments and other objects
such as the public dataset. No remote image fetching is introduced.

Public readers require retained schema2 entries. Legacy bare URLs, old data URLs,
old unverified raster paths, corrupted records, expired records and future timestamps
are hidden. Their stored values are not deleted or changed by reads. `/api/card-image`
only redirects to such a retained owned raster URL and adds `nosniff`. Its redirect
cache is five minutes plus one minute of stale reuse.

## Resource ceilings and retention

| Limit | Enforcement |
|---|---|
| 2 simultaneous publication/generation uploads | Expiring Redis active reservations |
| 180 seconds per unfinished reservation | Stored deadline and Redis expiry |
| 100 attempted publications globally per UTC day | Atomic admission counter |
| 5 attempted publications per handle per UTC day | Atomic admission counter |
| 500 handle records | Atomic admission cardinality ceiling |
| 1500 attempted uploads for the configured store's lifetime | Persistent admission counter |
| 3 retained versions per handle | Atomic store truncation |
| 90 days of public visibility per version | Retained timestamps checked on reads |
| 50 handles per gallery response | Indexed bounded page, each raw record ≤32 KiB |

The lifetime ceiling bounds new upload attempts, including failed/orphaned and
superseded objects, to at most 6000 MiB of emitted image bytes before maintenance.
It does not measure existing legacy storage or guarantee the provider's bill. Quotas
are intentionally consumed on failures so repeated bad work cannot bypass limits.
Superseded URLs are returned to trusted callers, and only their count is logged.
There is no automatic deletion of existing production objects.

The `gallery:published` sorted index is written atomically with schema2 publication.
Pagination uses a numeric offset and returns `nextCursor`; an unchanged 55-item
compact index yields all 55 records in two pages. Concurrent publications can alter
page order, so pagination is weakly consistent and clients should deduplicate handles.
The root client follows these bounded pages. Legacy records are not implicitly added
to the index.

These multi-key Lua scripts require the configured standalone Redis implementation
used by `_lib.js`. Redis Cluster cross-slot operation is unsupported and fails closed;
cluster adoption requires a reviewed same-slot key migration.

## Reviewable migration and physical cleanup plan

Production execution requires separate authorization. No production state has been
read or changed for this plan.

1. Configure the capability secret and exact Blob origin in an approved preview
   environment. Use a disposable Redis and synthetic pixels to test a signed publish,
   cached public read, own-key local creation, crawler redirect and denial cases.
2. Prepare a restricted, dry-run inventory of legacy gallery record schemas and owned
   `cards/` object references. Do not treat old URLs or record ownership as trusted.
   Preserve a protected backup and request review of any ownership assignments.
3. For explicitly approved legacy entries, validate bounded raster bytes, emit a new
   clean PNG, assign the reviewed owner, create schema2 metadata and index the handle.
   Do not fetch arbitrary legacy external URLs or admit unknown storage objects.
4. Produce a separate dry-run deletion manifest for objects older than the approved
   retention period, superseded versions and confirmed orphans. Reconcile every exact
   owned `cards/` URL against all retained gallery/cache references. Never include
   `public-site/` datasets or another store's objects. Allow for cached redirects.
5. Obtain explicit approval for the exact manifest before deleting Blob objects or
   legacy metadata. Record actual deletion outcomes and remaining storage. Reset or
   raise the lifetime counter only after confirmed cleanup and a reviewed budget.

A physical Blob retention/deletion process, owner migration and capability issuance
policy remain operational decisions. Publication will stop at its ceilings until
approved maintenance; it does not grow storage indefinitely while waiting.

## Verification and calibration

First measured assessment timestamp: 11:25 UTC / 16:55 IST. The exact earlier task
start was not recorded; a previous approximate 11:21 estimate was withdrawn rather
than presented as an observed start. Original scoped estimate: 70–90 minutes, with
validation by 11:40, implementation by 12:05 and focused verification/review by 12:35.

| Milestone | Original target UTC | Observed UTC | Outcome |
|---|---|---|---|
| Reproduce and validate boundaries | 11:40 | 11:37 | Four expected failures; reader fixes green |
| Image/atomic gallery implementation | 12:05 | 11:42 | 47 focused contracts passed |
| Independent review follow-up | 12:35 | 11:46 | Trusted nonce replay fix; 52 focused contracts passed |

Elapsed time at the independent-review milestone was approximately 21 minutes since
the first measured assessment, ahead of the original scoped estimate. Dependency
work ran in parallel through root: Sharp installation/update and disposable Redis
compilation. The initial sandbox denied the test socket with EPERM; approved scoped
escalation permitted synthetic DB4 tests. Neither was a production operation. No
completion estimate is treated as certainty; final aggregate integration belongs to
root and can reveal cross-scope regressions.

Focused command (explicit disposable local Redis DB4 only):

```sh
TPOT_TEST_REDIS_SOCKET=/tmp/tpot-security-redis-20261002.sock \
  node node_modules/vitest/vitest.mjs run \
  __tests__/api/gallery.test.js __tests__/api/gallery-security.test.js \
  __tests__/api/image-policy.test.js __tests__/api/gallery-policy.integration.test.js \
  --configLoader runner
```

Result at 11:46 UTC: **52/52 passed**, including 16 actual Redis Lua contracts and
23 actual decoder/URL contracts. Integration tests use the shared guarded Redis
fixture and DB4; they skip if no explicitly allowed disposable target is configured.
The root CI Redis service supplies an allowed local URL. No paid model calls are
made. Root independently reviews the final combined diff and runs aggregate tests.

The 11:49 UTC aggregate public-site run passed 246 tests and exposed two cross-scope
integration follow-ups: root's forced-generation replay test still expected 403
after gallery-first admission began returning 409, and Vitest collected a separate
Node test script whose transformed `import.meta.url` was not a filesystem URL.
Both were reported to root for the relevant owners; neither was a gallery focused
contract failure. A final combined green aggregate result must be recorded by root.

Changed files owned by this scope:

- `public-site/api/gallery-submit.js`, `gallery.js`, `card-image.js`
- `public-site/api/_galleryPolicy.js`, `_galleryScripts.js`, `_imagePolicy.js`
- `public-site/__tests__/api/gallery.test.js`, `gallery-security.test.js`,
  `image-policy.test.js`, `gallery-policy.integration.test.js`
- This diagnostics document

All new/changed scope modules and tests remain below 300 lines. Shared admission,
Redis wrapper, package/lockfile, CI, client pagination, verification script and shared
worklog/roadmap are owned and integrated by root.
