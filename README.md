<img src="https://ned.watch/brand/lockup-horizontal-dark.png" alt="ned.watch" width="360">

# ned-watch-mcp

Register a URL, condition, or deadline; Ned wakes you at your callback when it fires. Independent, multi-region, signed.

Client bits for [Ned Watch](https://ned.watch): the MCP server (`uvx ned-watch-mcp`) and the skill file (`SKILL.md`, installable with `npx skills add ned-mind/ned-watch-skill`). The service itself lives in the private `nedwatch` repo.

## MCP server

`mcp/server.py` is a stdio MCP server over the public API (tools: `quickstart` (agent + deadman watch + the check-in line),
`deadman_checkin` (takes the watch's signing_secret), `overrun_watch`, `overrun_start`, `overrun_finish`, `content_watch`,
`watch_register`, `watch_get`, `watch_cancel`, `balance`, `pricing`). Paying is not an MCP tool; the agent pays the x402 402 directly. It installs as the `ned-watch-mcp` command.

Add it to an MCP client. Claude Desktop (`claude_desktop_config.json`), Cursor (`.cursor/mcp.json`) and OpenClaw
(`mcp` block of the agent config) all take the same shape:

```json
{
  "mcpServers": {
    "ned-watch": {
      "command": "uvx",
      "args": ["ned-watch-mcp"],
      "env": { "NED_AGENT_KEY": "nw_..." }
    }
  }
}
```

Leave `NED_AGENT_KEY` out on first use: `watch_register` returns a key (shown once) and tells the agent to store it.

From source: `uvx --from git+https://github.com/ned-mind/ned-watch-skill ned-watch-mcp`, or `pip install .` then `ned-watch-mcp`.

## Examples

`examples/` runs as-is against the live API (curl and jq): `deadman.sh` (register, then the one check-in line),
`overrun.sh` (wraps any command in start/finish), `content.sh` (our health page must say `"ok": true`), and `verify.py`
(check a callback's signature before trusting it).

`SKILL.md` (also at `skill/SKILL.md`) is the skill file for skills.sh / OpenClaw; same description, the curl, the callback contract and the verify snippet.
