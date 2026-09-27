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
POST   /v1/checkin/{watch_id}          deadman check-in: Authorization: Bearer <signing_secret>  (or X-Ned-Checkin: hex(HMAC-SHA256(signing_secret, watch_id)))
GET    /v1/balance                     balance_cents, free_used, burn_cents_per_day, days_left
GET    /v1/pricing                     the numbers below, as JSON (public)
POST   /v1/topup/5 | /20 | /50         x402: unpaid POST returns 402 + payment requirements (USDC, Base)
GET    /.well-known/agent-card.json    A2A agent card
```

## Pricing and limits

- **Free:** your first 5 active watches at >= 300s, any type. One allowance per agent.
- **Paid, per day, from a prepaid balance:** http/tls 2¢ (>= 60s) · fast 7¢ (>= 30s) · deadman 1¢. Registering a paid watch needs a day of burn in the balance, else 402 with the numbers.
- **Top up** $5 minimum via x402 (USDC on Base mainnet, `eip155:8453`): `POST /v1/topup/5` unpaid returns 402 with payment requirements; retry with `PAYMENT-SIGNATURE`. The credit lands on settlement. Card payments are coming.
- Watches pause (event `paused`) when the balance can't cover the day; one `low_balance` callback while 3 days remain; a top-up resumes them (event `resumed`).
- Targets and callbacks must be public addresses: loopback, link-local, private and CGNAT ranges are refused at registration and again at every check. Redirects are followed at most 3 hops, each re-checked.
- Registration is rate-limited: 10/min per IP, 30/min per key (429 with Retry-After). Bodies over 32 KB are refused (413). At most 100 active watches per agent.
- At most 5 watches per target across all agents. Watches on individuals or anything that looks like reconnaissance are refused. Ned is not a weapon.

## MCP

`uvx ned-watch-mcp` runs a stdio MCP server exposing `watch_register`, `watch_get`, `watch_cancel`,
`deadman_checkin` (takes the watch's signing_secret), `balance`, `pricing`. Pass your key as `NED_AGENT_KEY`. Config snippets: https://github.com/ned-mind/nedwatch#mcp-server

## Contact

ned@ned.watch. Ned answers support himself. Status of every node is published at https://ned.watch.
