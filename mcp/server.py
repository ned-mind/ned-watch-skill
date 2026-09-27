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

import httpx  # noqa: E402
try:                                   # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server  # noqa: E402
    _V2 = True
except ImportError:                    # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # noqa: E402
    _V2 = False

DESCRIPTION = ("Register a URL, condition, or deadline; Ned wakes you at your callback when it fires. "
               "Independent, multi-region, signed.")
API = os.environ.get("NED_WATCH_API", "https://api.ned.watch").rstrip("/")
_key = os.environ.get("NED_AGENT_KEY") or None

mcp = (_Server(name="Ned Watch", description=DESCRIPTION, instructions=DESCRIPTION, version="1.0.0", website_url="https://ned.watch")
       if _V2 else _Server("Ned Watch", instructions=DESCRIPTION))


def _headers():
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
        detail = {"error": "unknown or missing agent key", "hint": "set NED_AGENT_KEY, or call watch_register without one to be issued a key"}
    return {"ok": False, "status": r.status_code, "error": detail}


@mcp.tool()
def watch_register(type: str, callback_url: str, target: str | None = None, interval_s: int = 300,
                   condition: dict | None = None) -> dict:
    """Register a watch. type: http | tls | deadman. target: URL (http/tls); omit for deadman.
    interval_s >= 300 on the free tier. condition: e.g. {"warn_days": 14} for tls, {"grace_s": 600} for deadman,
    {"max_ms": 2000} for http latency. Ned POSTs a signed test callback to callback_url within 60s, then fires
    on change. No agent key yet? Call this without one: the response includes agent_key (shown once). Store it
    and pass it as NED_AGENT_KEY next time."""
    global _key
    body = {"type": type, "target": target, "interval_s": interval_s, "callback_url": callback_url,
            "condition": condition or {}}
    res = _call("POST", "/v1/watches", json=body, timeout=75)   # the test callback is delivered before the API answers
    if res.get("ok") and res.get("agent_key"):
        _key = res["agent_key"]
        res["store_this"] = ("agent_key is shown ONCE. Save it now and start this server with NED_AGENT_KEY=<agent_key> "
                             "so watch_get / watch_cancel / balance work in future sessions.")
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
def balance() -> dict:
    """Your balance in cents, free allowance used, burn per day, days left, and the top-up routes."""
    return _call("GET", "/v1/balance")


@mcp.tool()
def pricing() -> dict:
    """Ned Watch pricing: 5 free watches at >=300s, then per-day rates (http/tls 2c, fast 7c, deadman 1c) from a prepaid
    balance topped up over x402 (USDC on Base). Public, no key needed. Paying is done against POST /v1/topup/{5,20,50}, not here."""
    return _call("GET", "/v1/pricing")


def main():
    if "--version" in sys.argv:
        print("ned-watch-mcp 1.0")
        return 0
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
