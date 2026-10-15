# Claude delegation bridge

Installed local stdio MCP server: `claude_executor` in Codex configuration.
Uses existing Claude Code 2.1.284 and its authenticated subscription. No public
endpoint, API key copied into settings, or third-party executor package.

Tools: `claude_status`, `claude_start`, `claude_result`, `claude_cancel`.
Start returns an asynchronous job ID; receipts persist in `jobs/<job_id>`.
Review exposes Read/Glob/Grep; edit additionally exposes Edit/Write. No Bash,
other MCP tools, or permission bypass. The supervising agent runs tests and owns
commits and pushes. Use a dedicated checkout for edit work; this tool selection
is not an OS sandbox. Model and account billing follow the existing Claude account.
Worker has a 30-minute timeout. Do not blindly retry a task after an ambiguous
receipt; inspect its files and state first.

Connection verified by MCP initialization, discovery of all four tools,
authentication status and a Claude model reply `CLAUDE_BRIDGE_OK`.
Receipt: `jobs/a002a68f-945a-407c-8b02-ff42b43a06b0/`.

New Codex sessions load the configured MCP tools. This active session can use
the same bridge through the Python MCP client without restarting the desktop app.
Recheck using `venv/bin/python check_bridge.py` (makes one small Claude request).
Remove registration using `codex mcp remove claude_executor`.
Original Codex configuration backup: `codex-config.before.toml` (may contain
private settings; keep local). Job prompts/results may also be private.

If the desktop app updates and removes the pinned executable, update CLAUDE in
server.py to the newly installed binary, then repeat the connection check.
