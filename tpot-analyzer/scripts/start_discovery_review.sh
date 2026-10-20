#!/bin/sh
# Foreground private review server. Keep Tailscale Serve on :5444 pointed at :5364.
set -eu
review_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$review_root"
review_python="$review_root/.venv/bin/python"
review_tailnet=$(/usr/local/bin/tailscale status --json)
review_identity=$(printf '%s' "$review_tailnet" | "$review_python" -c '
import json, sys
status = json.load(sys.stdin)
if status.get("BackendState") != "Running":
    raise SystemExit("Tailscale must be connected before starting the review")
self = status["Self"]
owner = status["User"][str(self["UserID"])]["LoginName"]
if owner == "tagged-devices":
    raise SystemExit("Review requires an owner-signed-in device")
print(owner)
print("https://" + self["DNSName"].rstrip(".") + ":5444")
')
TPOT_DISCOVERY_REVIEW_OWNER=$(printf '%s\n' "$review_identity" | sed -n '1p')
TPOT_DISCOVERY_REVIEW_ORIGIN=$(printf '%s\n' "$review_identity" | sed -n '2p')
TPOT_DISCOVERY_REVIEW_PACKET=${TPOT_DISCOVERY_REVIEW_PACKET:-"$review_root/data/private/discovery-review-20260922-v2/manifest.json"}
TPOT_DISCOVERY_REVIEW_DB=${TPOT_DISCOVERY_REVIEW_DB:-"$review_root/data/private/discovery-review-20260922-v2/answers.db"}
export TPOT_DISCOVERY_REVIEW_OWNER TPOT_DISCOVERY_REVIEW_ORIGIN
export TPOT_DISCOVERY_REVIEW_PACKET TPOT_DISCOVERY_REVIEW_DB
printf 'Private discovery review: %s\n' "$TPOT_DISCOVERY_REVIEW_ORIGIN"
exec "$review_python" -m gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5364 \
    --error-logfile "$review_root/data/private/discovery-review-server.log" \
    'scripts.serve_discovery_review:create_review_app()'
