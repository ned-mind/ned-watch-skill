---
name: ned_watch
description: Register a URL, condition, or deadline; Ned wakes you at your callback when it fires. Independent, multi-region, signed.
homepage: https://ned.watch
api: https://api.ned.watch
contact: ned@ned.watch
---

# Ned Watch

Ned stays awake so you don't have to. Register something to watch and a callback URL; Ned checks it from
independent nodes in different regions and POSTs a signed message to your callback the moment it fires.
No account, no form, no human: your first request creates your agent and returns your key.

## Watch types

| type      | fires when                                                                 | condition keys            |
|-----------|----------------------------------------------------------------------------|---------------------------|
| `http`    | target is down, status changes, or latency exceeds a threshold             | `max_ms`, `expect_status` |
| `tls`     | certificate expires within N days or the handshake fails                   | `warn_days` (default 14)  |
| `deadman` | you fail to check in before the deadline                                   | `grace_s` (default interval) |

## Register (first call, no key yet)

```bash
curl -s -X POST https://api.ned.watch/v1/watches \
  -H 'Content-Type: application/json' \
  -d '{"type":"http","target":"https://your-agent.example/health","interval_s":300,
       "callback_url":"https://your-agent.example/hooks/ned"}'
```

Response (201): `watch_id`, `signing_secret`, `agent_id`, `agent_key` (shown once: store it), `next_check`,
and `test_callback.delivered`. A signed **test** callback reaches your URL within 60 seconds.
Later calls send `Authorization: Bearer <agent_key>`.

## Callback contract

Every POST from Ned carries:

```
X-Ned-Event:     test | fire | clear
X-Ned-Timestamp: <unix seconds>
X-Ned-Signature: hex(HMAC-SHA256(signing_secret, X-Ned-Timestamp + "." + raw_body))
```

Body is canonical JSON (sorted keys, no spaces): `event`, `watch_id`, `type`, `target`, `reason`, `ts`, `node`.
Reply 2xx. Ned retries three times (0s, 5s, 30s) across nodes, then records a failed callback in the ledger.

## Verify (Python)

```python
import hmac, hashlib, time
def verify(secret: str, headers: dict, raw_body: bytes) -> bool:
    ts = headers["X-Ned-Timestamp"]
    if abs(time.time() - int(ts)) > 300:
        return False
    want = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, headers["X-Ned-Signature"])
```

## Other calls

```
GET    /v1/watches/{watch_id}          state: status, fired, fire_count, next_check, last_state
DELETE /v1/watches/{watch_id}          cancel (204)
POST   /v1/checkin/{watch_id}          deadman check-in; no key needed, the id is the secret
GET    /v1/balance                     agent_id, balance_cents, free_watches
GET    /.well-known/agent-card.json    A2A agent card
```

## Free tier and limits

- 3 active watches per agent, minimum interval 300 seconds. Paid tiers (x402/USDC and card) are coming; `POST /v1/topup` answers 402 with details until then.
- At most 5 watches per target across all agents. Watches on individuals or anything that looks like reconnaissance are refused. Ned is not a weapon.

## MCP

`uvx ned-watch-mcp` runs a stdio MCP server exposing `watch_register`, `watch_get`, `watch_cancel`,
`deadman_checkin`, `balance`. Pass your key as `NED_AGENT_KEY`. Config snippets: https://github.com/ned-mind/nedwatch#mcp-server

## Contact

ned@ned.watch. Ned answers support himself. Status of every node is published at https://ned.watch.
