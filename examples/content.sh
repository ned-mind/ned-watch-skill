#!/bin/sh
# Content: the page answers 200 but should also say the right thing. Here: our own health page must say "ok": true.
#   CALLBACK=https://webhook.site/YOUR-BIN sh content.sh
set -eu
API=${NED_WATCH_API:-https://api.ned.watch}
curl -s -X POST "$API/v1/watches" -H 'Content-Type: application/json' ${NED_AGENT_KEY:+-H "Authorization: Bearer $NED_AGENT_KEY"} \
  -d "{\"type\":\"content\",\"target\":\"${TARGET:-https://api.ned.watch/health}\",\"interval_s\":300,
       \"expect\":{\"status\":200,\"json_path\":\"ok\",\"equals\":true},\"callback_url\":\"$CALLBACK\"}" | jq '{watch_id, expect, agent_key, test_callback}'
