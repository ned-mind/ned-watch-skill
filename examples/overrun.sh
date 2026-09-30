#!/bin/sh
# Overrun: wrap a job so Ned wakes CALLBACK if it's still running after MAX seconds (60 to 86400). Needs curl and jq.
#   CALLBACK=https://webhook.site/YOUR-BIN MAX=900 LABEL=nightly-backup sh overrun.sh your-job --its-args
# The watch is registered once and remembered in $STATE (default ~/.ned-overrun-<label>); later runs reuse it.
# Set NED_AGENT_KEY so every job lives under one agent. The job's exit code is passed through.
set -eu
API=${NED_WATCH_API:-https://api.ned.watch}
LABEL=${LABEL:-my-job}
STATE=${STATE:-$HOME/.ned-overrun-$LABEL}
if [ ! -s "$STATE" ]; then
  R=$(curl -s -w '\n%{http_code}' -X POST "$API/v1/watches" -H 'Content-Type: application/json' ${NED_AGENT_KEY:+-H "Authorization: Bearer $NED_AGENT_KEY"} \
    -d "{\"type\":\"overrun\",\"max_runtime_s\":${MAX:-900},\"condition\":{\"label\":\"$LABEL\"},\"callback_url\":\"$CALLBACK\"}")
  CODE=$(echo "$R" | tail -n1); BODY=$(echo "$R" | sed '$d')
  case "$CODE" in 200|201) ;; *) echo "overrun.sh: registration failed ($CODE): $BODY" >&2; exit 1 ;; esac
  (umask 077; echo "$BODY" | jq '{watch_id, signing_secret}' > "$STATE")
  echo "$BODY" | jq -r 'if .agent_key then "new agent_key (store it, shown once): \(.agent_key)" else empty end' >&2
fi
WATCH_ID=$(jq -r .watch_id "$STATE"); SIGNING_SECRET=$(jq -r .signing_secret "$STATE")
RUN_ID="$LABEL-$(date -u +%Y%m%dT%H%M%S)-$$"             # our own id: a retried start or finish is safe
run() {                                                   # start/finish; a failure here never stops the job
  curl -s -f -X POST "$API/v1/watches/$WATCH_ID/$1" -H "Authorization: Bearer $SIGNING_SECRET" -H 'Content-Type: application/json' \
    -d "{\"run_id\":\"$RUN_ID\"}" || echo "overrun.sh: $1 failed; the job runs anyway" >&2
  echo
}
run start
rc=0; "$@" || rc=$?
run finish
exit $rc
