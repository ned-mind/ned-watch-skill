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

## Start here: the deadman

Tell Ned how often you'll check in. If you go quiet longer than that, he wakes your callback.

```bash
curl -s -X POST https://api.ned.watch/v1/watches \
  -H 'Content-Type: application/json' \
  -d '{"type":"deadman","interval_s":3600,"callback_url":"https://your-agent.example/hooks/ned"}'
```

The response carries `watch_id` and `signing_secret` (and, on your first call, `agent_key`: store all three). Then, on
your schedule (every run, every loop, every hour), one line:

```bash
curl -s -X POST https://api.ned.watch/v1/checkin/$WATCH_ID -H "Authorization: Bearer $SIGNING_SECRET"
```

Miss it and your callback gets a signed `fire`. Check in again and it gets a `clear`.

## Watch types

| type      | fires when                                                                  | set with                              |
|-----------|-----------------------------------------------------------------------------|---------------------------------------|
| `deadman` | you stop checking in                                                        | `interval_s`, `condition.grace_s`     |
| `overrun` | a run you started is still going past its limit                             | `max_runtime_s` (60 to 86400)         |
| `http`    | the URL is down, the status changes, or it's slower than a threshold        | `condition.max_ms`, `condition.expect_status` |
| `tls`     | the certificate expires within N days or the handshake fails                | `condition.warn_days` (default 14)    |
| `content` | the URL answers, but says the wrong thing                                   | `expect` (1 to 5 conditions)          |

Quick try (no setup on your side, watches our own health page):

```bash
curl -s -X POST https://api.ned.watch/v1/watches \
  -H 'Content-Type: application/json' \
  -d '{"type":"http","target":"https://api.ned.watch/health","interval_s":300,"callback_url":"https://webhook.site/YOUR-BIN"}'
```

Response (201): `watch_id`, `signing_secret`, `agent_id`, `agent_key` (shown once: store it), `next_check`,
and `test_callback.delivered`. A signed **test** callback reaches your URL within 60 seconds.
Later calls send `Authorization: Bearer <agent_key>`.

## Overrun: still running when it shouldn't be

The other side of a deadman. A deadman notices you stopped; an overrun notices you didn't.

```bash
curl -s -X POST https://api.ned.watch/v1/watches -H "Authorization: Bearer $AGENT_KEY" -H 'Content-Type: application/json' \
  -d '{"type":"overrun","max_runtime_s":900,"condition":{"label":"nightly-backup"},"callback_url":"https://your-agent.example/hooks/ned"}'

# when the run begins, and when it ends:
curl -s -X POST https://api.ned.watch/v1/watches/$WATCH_ID/start  -H "Authorization: Bearer $SIGNING_SECRET"
curl -s -X POST https://api.ned.watch/v1/watches/$WATCH_ID/finish -H "Authorization: Bearer $SIGNING_SECRET"
```

- Not finished within `max_runtime_s`: one `fire` with `run_id`, `started_at`, `deadline`.
- Finished after that: `clear` with `late: true` and `runtime_s`.
- A new `start` while a run is open closes the old run as superseded, with no callback.
- `finish` with no run open is a 409. Both calls take an optional `{"run_id": "..."}` (your own id, 1-64 chars). Send one
  and retries are safe: the same `start` again returns the open run, the same `finish` again returns its result.
- Auth is the watch's signing secret, as a Bearer token, or signed: `X-Ned-Timestamp: <unix>` and
  `X-Ned-Signature: hex(HMAC-SHA256(signing_secret, timestamp + "." + watch_id + "." + action + "." + run_id))`, action
  `start` or `finish`, run_id as in the body (empty if none), within 300 s, each signature accepted once. Signed calls go
  to the node that registered the watch (api.ned.watch unless you used api-eu.ned.watch); Bearer works on either.
- `condition.label` gives each job its own watch. Registering the same thing twice returns the same watch, so two jobs
  with the same limit and callback need different labels.

## Content: 200, but wrong

```bash
curl -s -X POST https://api.ned.watch/v1/watches -H "Authorization: Bearer $AGENT_KEY" -H 'Content-Type: application/json' \
  -d '{"type":"content","target":"https://api.ned.watch/health","interval_s":300,
       "expect":{"status":200,"json_path":"ok","equals":true},"callback_url":"https://your-agent.example/hooks/ned"}'
```

`expect` takes 1 to 5 conditions:

- `status`: the exact status code.
- `contains` / `not_contains`: a string, or a list of strings (each counts as one condition). Plain substring, case-sensitive.
- `json_path` with `equals` (a JSON string, number, true/false or null) or `exists` (true/false). Dotted keys and array
  indexes only, like `data.items.0.state`.

No regex. Ned reads at most 256 KB; a bigger page fails as `size`. The `fire` callback lists which conditions failed
(`failed: [{"condition": "json_path", "path": "ok", "why": "value differs"}]`). It never contains anything from
the page itself, and Ned keeps only a hash of the body.

## Callback contract

Every POST from Ned carries:

```
X-Ned-Event:     test | fire | clear | paused | resumed | low_balance
X-Ned-Timestamp: <unix seconds>
X-Ned-Signature: hex(HMAC-SHA256(signing_secret, X-Ned-Timestamp + "." + raw_body))
```

Body is canonical JSON (sorted keys, no spaces): `event`, `watch_id`, `type`, `target`, `reason`, `state`, `ts`, `node`,
plus `run_id`/`started_at`/`deadline` (overrun fire), `late`/`runtime_s` (overrun clear), `failed` (content).
Reply 2xx. Ned retries three times (0s, 5s, 30s), then keeps re-sending once a minute for 24 hours; if the primary
node is down, the other node sends it (marked `failover: true`). Exactly one callback per change.

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
GET    /v1/watches/{watch_id}          state: status, fired, fire_count, next_check, last_state (+ run for overrun)
DELETE /v1/watches/{watch_id}          cancel (204)
POST   /v1/checkin/{watch_id}          deadman check-in: Authorization: Bearer <signing_secret>  (or X-Ned-Checkin: hex(HMAC-SHA256(signing_secret, watch_id)))
POST   /v1/watches/{watch_id}/start    overrun: a run began
POST   /v1/watches/{watch_id}/finish   overrun: the run ended
GET    /v1/balance                     balance_cents, free_used, burn_cents_per_day, days_left
GET    /v1/pricing                     the numbers below, as JSON (public)
POST   /v1/topup/5 | /20 | /50         x402: unpaid POST returns 402 + payment requirements (USDC, Base)
GET    /.well-known/agent-card.json    A2A agent card
```

## Pricing and limits

- **Free:** your first 5 active watches at >= 300s, any type (an overrun watch always counts as one). One allowance per agent.
- **Paid, per day, from a prepaid balance:** deadman 1¢ · overrun 1¢ · http/tls/content 2¢ (>= 60s) · fast 7¢ (>= 30s).
  Registering a paid watch needs a day of burn in the balance, else 402 with the numbers.
- **Top up** $5 minimum via x402 (USDC on Base mainnet, `eip155:8453`): `POST /v1/topup/5` unpaid returns 402 with payment
  requirements; retry with `PAYMENT-SIGNATURE`. The credit lands on settlement. Card payments are coming.
- Watches pause (event `paused`) when the balance can't cover the day; one `low_balance` callback while 3 days remain; a
  top-up resumes them (event `resumed`).
- Ports: 80, 443, or 1024 and up.
- Targets and callbacks must be public addresses: loopback, link-local, private and CGNAT ranges are refused at
  registration and again at every connection (Ned connects only to the address he checked). Redirects are followed at
  most 3 hops, each re-checked.
- Registration is rate-limited: 10/min per IP, 30/min per key (429 with Retry-After). Overrun start/finish and deadman check-ins: 60/min per
  watch. Bodies over 32 KB are refused (413). At most 100 active watches per agent.
- At most 5 watches per target across all agents. Watches on individuals or anything that looks like reconnaissance are
  refused. Ned is not a weapon.

## MCP

Remote (no install): `https://api.ned.watch/mcp` (streamable HTTP). After your first `watch_register`, send your key as
`Authorization: Bearer <agent_key>` on the connection.

Local (stdio): `uvx ned-watch-mcp`, with your key as `NED_AGENT_KEY`. (The overrun and content tools are on the remote
server now; the local package gets them in its next release, 1.1.0.)

```json
{"mcpServers": {"ned-watch": {"command": "uvx", "args": ["ned-watch-mcp"], "env": {"NED_AGENT_KEY": "<agent_key>"}}}}
```

Tools: `quickstart` (one call: agent + deadman watch + the check-in line), `deadman_checkin` (takes the watch's
signing_secret), `overrun_watch`, `overrun_start`, `overrun_finish`, `content_watch`, `watch_register`, `watch_get`,
`watch_cancel`, `balance`, `pricing`.

## Contact

ned@ned.watch. Ned answers support himself. Status of every node is published at https://ned.watch.
