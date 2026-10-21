# Project: pensieve

## Mission

<!-- Purpose + who it serves. One paragraph. -->

A tiny MCP memory server for coding agents. One instance serves one store:
a directory of markdown memories the user owns (usually a git checkout).
A user who keeps separate stores (say, personal and work) runs one
instance per store, side by side, and each tells the agent what belongs
in it.

Hard constraints:

- Public repo (github.com/kusimari/pensieve). No employer, internal tool
  or internal store names anywhere: code, specs, commits, PR text.
- Nothing is written outside the store. No network, no telemetry, no
  downloads at run time.
- Python standard library only at run time.

## Architecture

<!-- Logical shape: components + responsibilities. Words mandatory. -->

One Python module. It speaks MCP (JSON-RPC 2.0, one message per line) over
stdin/stdout. At start it reads the store's `about.md` and sends it as the
MCP `instructions`. Its tools are Anthropic's memory tool commands over the
store's `memory/` directory, plus a keyword search. No state outside the
files in the store.

Binding choices: tool paths start with `/memories` and mean `<store>/memory/`,
so the agent cannot reach `about.md` (the user's text) or `.git`. The agent,
not the server, keeps `memory/MEMORY.md` in step, told by the tool
descriptions, as Claude Code's own memory does.

## Tech Stack

<!-- Languages, runtimes, frameworks. Versions where they matter. -->

Python 3.11+ (tests pass on 3.11, 3.13 and 3.14), standard library only. Packaged with
`pyproject.toml` (setuptools backend) and a small `flake.nix`.

## Layout

<!-- Directory tree, one-line annotation per entry. -->

```
pensieve.py         the server
tests/              unittest suite, drives the server over stdio
pyproject.toml      package metadata, `pensieve` entry point
flake.nix/.lock     nix package
README.md           what it is, how to run and register it
specs/              project, feature and backlog specs
```

## Testing

<!-- Test layers + which is load-bearing. Command strings live in
     a repo-root AGENTS.md where one exists (SKILL.md §2 Context
     layers); here, carry the layer semantics, not duplicated
     commands. -->

One layer, and it is the load-bearing one: `python3 -m unittest discover
-s tests`. Each test starts the real server as a subprocess on a temp
store, with a temp HOME and temp working directory, and talks MCP to it
over stdio. No test touches the real home, config or network.

A paid end-to-end check (`claude --print` against two instances, temp
HOME) runs only when a review needs proof that an agent uses the tools.

## Deployment

<!-- Build / release / install path, or how it's consumed. -->

Consumed from a pinned git commit, two ways: `nix profile install
github:kusimari/pensieve/<rev>` (or the flake as an input), or
`pipx install git+https://github.com/kusimari/pensieve@<rev>`. Then
registered per store with `claude mcp add -s user <name> -- pensieve
--store <dir>`.

## Agent Development

### kdevkit

```yaml
prefer_worktree: false
code_review:
  reviewer: host-native
```
