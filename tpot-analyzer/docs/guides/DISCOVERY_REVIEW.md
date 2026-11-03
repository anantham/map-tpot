# Private discovery review

Implemented 2026-10-01 to collect actual usefulness feedback on the existing
28-account Dharma discovery packet. This is a small formative comparison, not
calibrated membership or proof that a ranking generalizes.

## Retreat-purpose extension (2026-10-05)

The same review can load a separate purpose-bound packet. The exploratory
retreat packet is `data/private/retreat-review-20261005/manifest.json`; use a
separate adjacent `answers.db`, not the existing Dharma answer database.
It includes 12 India-connected leads, not 12 verified India residents or invitees.
Only two have checked primary-source work evidence; other leads are bio-only.
The cards show proposed contribution, observed follow, location caveats and
unknowns. A follow is not an endorsement or a promised introduction.

The question is **Worth considering for the retreat?**, not Dharma membership.
Saved relevance Yes + known No + glad Yes increases the visible useful-new count;
revising the answer updates the count. This does not yet change the ranking.
No confidence percentage is claimed. The batch is curated research triage, not
the method-masked ranking comparison; don't use it to declare a method winner.

To start the existing owner-only server with this packet (only when port 5364
is free and its current owner has been safely stopped):

```sh
TPOT_DISCOVERY_REVIEW_PACKET="$PWD/data/private/retreat-review-20261005/manifest.json" \
TPOT_DISCOVERY_REVIEW_DB="$PWD/data/private/retreat-review-20261005/answers.db" \
sh scripts/start_discovery_review.sh
```

The launcher still defaults to the preserved Dharma packet; both manifests and
answer stores remain separate. Old open pages fail to save after packet changes,
and must reload. Independent review and served-preview verification are separate
gates, not implied by packet generation or green synthetic checks.

Current :5444 private preview serves the retreat packet (verified 2026-10-05).
On mobile use **Your take ↓** to jump to the questions; the panel names the
account so its identity stays visible while answering. Independent review is
still pending; this is not a public or reviewed release.

## Use it

Open the review with Tailscale connected on an owner-signed-in device:
<https://adityas-macbook-pro.tail4741ad.ts.net:5444/>.

Read the saved profile and up to three saved posts. Open the X profile or
original post for more context if needed. Answer relevance to your Dharma
search, prior familiarity, and whether you are glad it surfaced. “Not sure” is
valid, especially when evidence is missing. Add an optional note and choose
**Save & next**. Saving is explicit: ordinary Next only browses, not saves.

The progress count includes saved answers only. Reopening resumes at the first
unanswered account; use the account dropdown or Back to revisit. Edits append a
correction instead of deleting the earlier answer. Unsaved choices survive
in-page browsing, but not a reload; the page warns before leaving.

## What is used and what stays separate

- Frozen source: `data/private/discovery-review-20260922-v2/manifest.json`.
- Answers: `data/private/discovery-review-20260922-v2/answers.db`.
- Existing 93 personal tags, the archive and acquired-post stores are unchanged.
- The UI/API expose evidence only, not method names, ranks, support or seeds.
- A saved answer is your review of this suggestion, not an automatic new tag,
  gold judgment, social affiliation claim, or competence assessment.

After review, compare useful-new finds (relevant Yes, known No, glad Yes),
abstentions and missing evidence by the frozen recipes. Report small counts and
limitations, not calibrated percentages. Keeping recipe details out of view
reduces anchoring while judging; it does not make this a sealed benchmark.

## Start or verify

Run from the canonical `tpot-analyzer` directory with AirBackup attached:

```sh
.venv/bin/python scripts/verify_discovery_review.py
cd graph-explorer
VITE_TPOT_CURATOR_TOKEN='' npm run build
cd ..
sh scripts/start_discovery_review.sh
```

The foreground server listens only on `127.0.0.1:5364`. For a detached session:

```sh
screen -dmS tpot-discovery-review sh scripts/start_discovery_review.sh
tailscale serve --bg --https=5444 http://127.0.0.1:5364
tailscale serve status
```

Do not start another server when one already owns port 5364. The launcher derives
the owner's identity and hostname from the connected Tailscale device. A fresh
server-only curator token is generated internally; the build above deliberately
omits the browser curator token. Verified owner headers are trusted only from
the loopback proxy; writes also require this review's exact Origin. No Funnel.
This uses Tailscale Serve's
[identity-header boundary](https://tailscale.com/docs/features/tailscale-serve).

Existing root and :5443 routes are unrelated and must not be reset. To disable
only this route, use `tailscale serve --https=5444 off`; keep the answer DB.

The Mac must remain awake with AirBackup attached. If loading or saving fails,
the UI reports the problem and retains the unsaved choices in that page. Server
errors are in `data/private/discovery-review-server.log`. The verifier writes
only temporary synthetic answers; it never creates human judgments.

Verification includes API persistence, corrections, access rejection, UI retry
and resume, and desktop/375px responsive presentation. Actual phone Safari and
cross-device answer editing are still operator acceptance checks.
