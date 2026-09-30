#!/bin/sh
# Overrun: wrap a job so Ned wakes CALLBACK if it's still running after MAX seconds (60 to 86400). Needs curl and jq.
#   CALLBACK=https://webhook.site/YOUR-BIN MAX=900 sh overrun.sh your-job --its-args
set -eu
API=${NED_WATCH_API:-https://api.ned.watch}
R=$(curl -s -X POST "$API/v1/watches" -H 'Content-Type: application/json' ${NED_AGENT_KEY:+-H "Authorization: Bearer $NED_AGENT_KEY"} \
  -d "{\"type\":\"overrun\",\"max_runtime_s\":${MAX:-900},\"condition\":{\"label\":\"${LABEL:-my-job}\"},\"callback_url\":\"$CALLBACK\"}")
WATCH_ID=$(echo "$R" | jq -r .watch_id); SIGNING_SECRET=$(echo "$R" | jq -r .signing_secret)
curl -s -X POST "$API/v1/watches/$WATCH_ID/start" -H "Authorization: Bearer $SIGNING_SECRET" | jq '{run_id, deadline}'
"$@" || true                                     # your job; the finish below runs either way
curl -s -X POST "$API/v1/watches/$WATCH_ID/finish" -H "Authorization: Bearer $SIGNING_SECRET" | jq '{run_id, runtime_s, late}'
