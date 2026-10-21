# Backlog: mcp-stateless-era

## What

Answer `server/discover` and per-request `_meta` versions (MCP revision
2026-07-28), alongside the `initialize` handshake pensieve speaks now.

## Why

The 2026-07-28 revision drops the handshake. A client that speaks only
that revision cannot use pensieve. Claude Code 2.1.296 still opens with
`initialize` (2025-11-25), so no client needs this yet.

## Open questions

- Which client first needs it; whether codex already does.
