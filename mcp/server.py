#!/usr/bin/env python3
"""
Ned Watch MCP server (stdio). Wraps https://api.ned.watch for any MCP-speaking agent.

    uvx ned-watch-mcp                      # or: ned-watch-mcp after pip install
    env: NED_AGENT_KEY (optional; issued on your first watch_register and shown once)
         NED_WATCH_API (default https://api.ned.watch)
"""
import os
import sys

# In the source tree this file lives in a directory named `mcp/`; keep that directory and the repo root off sys.path
# so `import mcp` finds the library. When installed (as ned_watch_mcp) the parent is site-packages, so leave it alone.
_here = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_here) == "mcp":
    sys.path = [p for p in sys.path if os.path.abspath(p or ".") not in (_here, os.path.dirname(_here))]

import contextvars  # noqa: E402
import httpx  # noqa: E402
try:                                   # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server  # noqa: E402
    _V2 = True
except ImportError:                    # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # noqa: E402
    _V2 = False

VERSION = "1.1.0"
DESCRIPTION = ("Register a URL, condition, or deadline; Ned wakes you at your callback when it fires. "
               "Independent, multi-region, signed.")
API = os.environ.get("NED_WATCH_API", "https://api.ned.watch").rstrip("/")
_key = os.environ.get("NED_AGENT_KEY") or None
# Remote mode (remote.py, https://api.ned.watch/mcp): each HTTP request carries the caller's own key and IP; they ride here
# for the length of that request and are passed straight to the API. Nothing is stored.
REQUEST_HEADERS = contextvars.ContextVar("ned_mcp_request_headers", default=None)
PASS_THROUGH = ("authorization", "cf-connecting-ip", "x-forwarded-for")

def _icons():
    try:
        from mcp.types import Icon
        return [Icon(src="https://ned.watch/brand/sweepthrough-dark-512.png", mimeType="image/png", sizes=["512x512"])]
    except Exception:
        return None


mcp = (_Server(name="Ned Watch", description=DESCRIPTION, instructions=DESCRIPTION, version=VERSION, website_url="https://ned.watch", icons=_icons())
       if _V2 else _Server("Ned Watch", instructions=DESCRIPTION))


def _headers():
    req = REQUEST_HEADERS.get()
    if req is not None:                                   # remote: the caller's key and IP, never ours
        h = {"User-Agent": "ned-watch-mcp-remote/1.0"}
        h.update({k: req[k] for k in PASS_THROUGH if req.get(k)})
        return h
    h = {"User-Agent": "ned-watch-mcp/1.0"}
    if _key:
        h["Authorization"] = f"Bearer {_key}"
    return h


def _call(method, path, json=None, timeout=30):
    """Returns a dict the agent can act on; never raises for HTTP errors."""
    try:
        r = httpx.request(method, f"{API}{path}", json=json, headers=_headers(), timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
    if r.status_code == 204:
        return {"ok": True, "status": 204}
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}
    if 200 <= r.status_code < 300:
        return {"ok": True, **(body if isinstance(body, dict) else {"data": body})}
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if r.status_code == 401:
        detail = {"error": "unknown or missing agent key",
                  "hint": ("send Authorization: Bearer <agent_key> on the MCP connection" if REQUEST_HEADERS.get() is not None else "set NED_AGENT_KEY")
                  + ", or call watch_register without one to be issued a key"}
    return {"ok": False, "status": r.status_code, "error": detail}


@mcp.tool()
def watch_register(type: str, callback_url: str, target: str | None = None, interval_s: int = 300,
                   condition: dict | None = None) -> dict:
    """Register a watch. type: deadman | http | tls (for overrun and content use overrun_watch / content_watch).
    target: URL (http/tls); omit for deadman. interval_s >= 300 on the free tier. condition: e.g. {"grace_s": 600} for
    deadman, {"max_ms": 2000} for http latency, {"warn_days": 14} for tls. Ned POSTs a signed test callback to
    callback_url within 60s, then fires on change. No agent key yet? Call this without one: the response includes
    agent_key (shown once). Store it and pass it as NED_AGENT_KEY next time."""
    global _key
    body = {"type": type, "target": target, "interval_s": interval_s, "callback_url": callback_url,
            "condition": condition or {}}
    res = _call("POST", "/v1/watches", json=body, timeout=75)   # the test callback is delivered before the API answers
    if res.get("ok") and res.get("agent_key"):
        _key = res["agent_key"]
        res["store_this"] = ("agent_key is shown ONCE. Save it now and start this server with NED_AGENT_KEY=<agent_key> "
                             "so watch_get / watch_cancel / balance work in future sessions.")
    return res


PUBLIC_API = os.environ.get("NED_PUBLIC_API", "https://api.ned.watch").rstrip("/")


@mcp.tool()
def quickstart(callback_url: str, every_minutes: int = 60) -> dict:
    """The fastest way to be watched, in one call. Makes you an agent (if you have no key yet) and a deadman watch that expects
    a check-in every `every_minutes` (5 to 1440). Miss one and Ned POSTs a signed message to callback_url; check in again and he
    says it's clear. Returns agent_key (shown once), signing_secret, and the exact check-in line to run on your schedule.
    The first 5 watches are free."""
    minutes = max(5, min(int(every_minutes or 60), 1440))
    res = _call("POST", "/v1/watches", json={"type": "deadman", "callback_url": callback_url, "interval_s": minutes * 60}, timeout=75)
    if not res.get("ok"):
        return res
    wid, secret = res.get("watch_id"), res.get("signing_secret")
    res["check_in"] = {
        "every_minutes": minutes,
        "curl": f"curl -s -X POST {PUBLIC_API}/v1/checkin/{wid} -H 'Authorization: Bearer {secret}'",
        "mcp": f"deadman_checkin(watch_id='{wid}', signing_secret='<signing_secret>')",
    }
    res["next"] = ("Store agent_key (shown once) and signing_secret. Run the check-in at least every "
                   f"{minutes} minutes; miss one and your callback gets a signed 'fire', check in again and it gets a 'clear'. "
                   "Verify X-Ned-Signature = hex(HMAC-SHA256(signing_secret, X-Ned-Timestamp + '.' + raw_body)).")
    return res


@mcp.tool()
def watch_get(watch_id: str) -> dict:
    """Current state of one of your watches: status, fired, fire_count, next_check, last_state."""
    return _call("GET", f"/v1/watches/{watch_id}")


@mcp.tool()
def watch_cancel(watch_id: str) -> dict:
    """Cancel a watch you registered. Frees a free-tier slot."""
    res = _call("DELETE", f"/v1/watches/{watch_id}")
    if res.get("ok"):
        res.update({"watch_id": watch_id, "status": "cancelled"})
    return res


@mcp.tool()
def deadman_checkin(watch_id: str, signing_secret: str) -> dict:
    """Check in on a deadman watch to keep it from firing. Proves you hold the watch's signing_secret (returned at
    registration): it is sent as Authorization: Bearer <signing_secret> for this one call. No agent key needed."""
    try:
        r = httpx.post(f"{API}/v1/checkin/{watch_id}", headers={"Authorization": f"Bearer {signing_secret}", "User-Agent": "ned-watch-mcp/1.0"}, timeout=30)
    except Exception as e:
        return {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    return {"ok": True, **body} if r.status_code == 200 else {"ok": False, "status": r.status_code, "error": body.get("detail", body)}


@mcp.tool()
def overrun_watch(callback_url: str, max_runtime_s: int, label: str | None = None) -> dict:
    """Fire when something is STILL running past its deadline (the other side of a deadman). Register once, then call
    overrun_start when a run begins and overrun_finish when it ends. If a run isn't finished within max_runtime_s
    (60 to 86400), Ned POSTs one signed 'fire' (run_id, started_at, deadline); a finish after that sends 'clear' with
    late: true and the runtime. A start while a run is open closes the old one as superseded (no callback). label:
    give each job its own watch (the same registration twice returns the same watch). 1c/day; counts toward the free 5."""
    global _key
    body = {"type": "overrun", "max_runtime_s": max_runtime_s, "callback_url": callback_url, "condition": {"label": label} if label else {}}
    res = _call("POST", "/v1/watches", json=body, timeout=75)
    if res.get("ok") and res.get("agent_key"):
        _key = res["agent_key"]
        res["store_this"] = "agent_key and signing_secret are shown once. Save both; overrun_start/overrun_finish need the signing_secret."
    return res


def _run(watch_id: str, signing_secret: str, action: str, run_id: str | None) -> dict:
    try:
        r = httpx.post(f"{API}/v1/watches/{watch_id}/{action}", json={"run_id": run_id} if run_id else {},
                       headers={"Authorization": f"Bearer {signing_secret}", "User-Agent": "ned-watch-mcp/1.1"}, timeout=30)
    except Exception as e:
        return {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    return body if r.status_code == 200 else {"ok": False, "status": r.status_code, "error": body.get("detail", body)}


@mcp.tool()
def overrun_start(watch_id: str, signing_secret: str, run_id: str | None = None) -> dict:
    """A run began on an overrun watch. Returns run_id and deadline. Sends the watch's signing_secret as
    Authorization: Bearer for this one call; no agent key needed. run_id is optional (your own id, 1-64 chars)."""
    return _run(watch_id, signing_secret, "start", run_id)


@mcp.tool()
def overrun_finish(watch_id: str, signing_secret: str, run_id: str | None = None) -> dict:
    """The run ended. Returns runtime_s and late. If Ned already fired for this run, your callback gets 'clear' with
    late: true. Finishing with no run open is an error (409)."""
    return _run(watch_id, signing_secret, "finish", run_id)


@mcp.tool()
def content_watch(target: str, callback_url: str, expect: dict, interval_s: int = 300) -> dict:
    """Fire when a URL answers but says the wrong thing. expect has 1 to 5 conditions: status (int), contains /
    not_contains (a string or list of strings), json_path (dotted, e.g. "data.items.0.state") with equals (a JSON
    scalar) or exists (true/false). No regex. Pages over 256 KB fail as 'size'. The callback names the condition that
    failed, never the page's content. 2c/day at >= 60s, 7c at >= 30s; free within the first 5 at >= 300s.
    Example: expect={"status": 200, "json_path": "status", "equals": "ok"}"""
    global _key
    res = _call("POST", "/v1/watches", json={"type": "content", "target": target, "interval_s": interval_s,
                                              "expect": expect, "callback_url": callback_url}, timeout=75)
    if res.get("ok") and res.get("agent_key"):
        _key = res["agent_key"]
        res["store_this"] = "agent_key is shown ONCE. Save it and start this server with NED_AGENT_KEY=<agent_key>."
    return res


@mcp.tool()
def balance() -> dict:
    """Your balance in cents, free allowance used, burn per day, days left, and the top-up routes."""
    return _call("GET", "/v1/balance")


@mcp.tool()
def pricing() -> dict:
    """Ned Watch pricing: 5 free watches at >=300s, then per-day rates (http/tls/content 2c, fast 7c, deadman 1c, overrun 1c) from a prepaid
    balance topped up over x402 (USDC on Base). Public, no key needed. Paying is done against POST /v1/topup/{5,20,50}, not here."""
    return _call("GET", "/v1/pricing")


def main():
    if "--version" in sys.argv:
        print(f"ned-watch-mcp {VERSION}")
        return 0
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
