#!/bin/sh
# Deadman: Ned wakes CALLBACK if you stop checking in for an hour. Needs curl and jq.
#   CALLBACK=https://webhook.site/YOUR-BIN sh deadman.sh
set -eu
API=${NED_WATCH_API:-https://api.ned.watch}
R=$(curl -s -X POST "$API/v1/watches" -H 'Content-Type: application/json' ${NED_AGENT_KEY:+-H "Authorization: Bearer $NED_AGENT_KEY"} \
  -d "{\"type\":\"deadman\",\"interval_s\":3600,\"callback_url\":\"$CALLBACK\"}")
echo "$R" | jq '{watch_id, agent_key, test_callback}'
WATCH_ID=$(echo "$R" | jq -r .watch_id); SIGNING_SECRET=$(echo "$R" | jq -r .signing_secret)
# the one line to run on your schedule (every run, every loop, at least hourly):
curl -s -X POST "$API/v1/checkin/$WATCH_ID" -H "Authorization: Bearer $SIGNING_SECRET"; echo
