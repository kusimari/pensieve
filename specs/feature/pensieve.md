# Feature: pensieve

## Git Setup

- Branch: `feat/pensieve`
- Base: none (first feature of a new repo)

## Feature Brief

A user can give a coding agent memory that lives in a directory they own,
and keep separate memories apart: one `pensieve` per store, each telling
the agent what belongs in it, each able to read, write and search only its
own store.

## Handoff

- **Stage:** closed
- **Ready for:** nothing; the feature is done
- **Carry forward:** filed as backlog: `license`, `mcp-stateless-era`
- **Deliberately left:** the low review notes, accepted as left by the
  agent-dev review

### Crossings

<!-- Append one line per crossing; never edit or delete a line. -->
- planning → dev
- dev → review
- review → closure
- closure → closed

## Requirements

- `pensieve --store <dir>` runs an MCP server on stdio for that one
  store. A missing or non-directory `<dir>` exits with an error and
  writes nothing.
- The agent receives the store's `about.md` as the server's standing
  text, after one fixed lead line: search here before answering from
  memory, save here only what the text below says belongs here, and ask
  the user when unsure which store. Without `about.md` the text says the
  store has no description and to ask before saving.
- The agent gets seven tools: `memory_view`, `memory_create`,
  `memory_str_replace`, `memory_insert`, `memory_delete`,
  `memory_rename` (Anthropic's memory tool commands, same arguments and
  behaviour) and `memory_search` (keyword).
- Every path is `/memories` or under it, and means the store's `memory/`
  directory. A path outside it, with a `..` part, or reaching outside
  through a symlink is refused with an error the agent can read.
  `about.md` and `.git` are out of reach.
- Each tool's description says it serves this store only, and to save
  only what the standing text says belongs here, asking when unsure.
  The write tools' descriptions give the file format: one file per
  memory with frontmatter `name`, `description`, `metadata.type`
  (`user|feedback|project|reference`), and one line per memory in
  `/memories/MEMORY.md`, kept in step by the agent on create, delete and
  rename.
- Two instances on two stores share nothing. Nothing is written outside
  the store; nothing goes to the network.
- Installs pinned with no run-time fetch: a nix flake package, or
  pip/pipx from a git commit. README covers what it is, running two
  instances, `claude mcp add -s user <name> -- pensieve --store <dir>`,
  the store layout and `about.md`.

## Test Strategy

Python's `unittest` (no install). Each test starts `pensieve.py` as a
subprocess on a temp store with a temp HOME and temp cwd, and speaks
JSON-RPC to it over stdio.

- **initialize**: `instructions` carries the lead line and `about.md`'s
  text; without `about.md`, the fallback text. Breaks if the file is not
  read or the lead is dropped.
- **tools/list**: the seven names, each description carrying the
  store-only sentence.
- **each command**, checked on disk: view of a dir lists files and hides
  dot files; view of a file numbers lines and honours `view_range`;
  create writes and refuses an existing file; str_replace replaces one
  match and refuses zero or several; insert at line N; delete of a file
  and a dir, refusing `/memories`; rename, refusing an existing target;
  search finds a file by a word in its body, case-insensitive, and not
  one missing a word.
- **path escapes**: `/etc/passwd`, `memory/x`, `/memories/../about.md`,
  `/memories/a/../../x`, `/memoriesX`, and a symlink in `memory/` to a
  dir outside: each refused, and the outside dir unchanged.
- **isolation**: two servers on two stores at once; a memory created in
  A is not found by B's search or view.
- **nothing outside the store**: after a session of writes, temp HOME
  and cwd are still empty and only the expected files changed in the
  store.
- **packaging**: `pip install` of the repo into a temp venv gives a
  working `pensieve`; `nix build` gives one. Run once each, by hand,
  output recorded in the Session Log.
- **paid, at most one run**: `claude --print`, temp HOME, Claude's
  automatic memory off, two stores; a prompt with one personal and one
  work fact. Passes if each fact lands only in its store, with
  frontmatter and an index line. Run at the agent-dev review, because
  the index rule lives only in descriptions and has not been seen to
  work.

Not tested: no network access (none by construction: the module imports
only `argparse`, `json`, `os`, `shutil`, `sys`, `pathlib`).

## Design

**Stdlib JSON-RPC over the official SDK.** Measured 2026-10-12 in a temp
venv: `mcp` 2.3.0 from PyPI pulls 28 packages (54 MB), among them
`cryptography`, `pydantic-core`, `uvicorn`, `starlette` and
`opentelemetry-api`. nixpkgs ships `mcp` 1.29.0, and 2.x renamed
`FastMCP` to `MCPServer`, so one source cannot use the decorator API from
both install paths without a shim, and the pip path needs its 28
packages pinned. The SDK version would be about 80 lines; stdlib came to 308
(after `ruff format`; most of the growth is tool descriptions and
schemas), zero dependencies, nothing to pin. Stdlib wins.

**Protocol.** Newline-delimited JSON-RPC 2.0 on stdio, legacy era:
`initialize` (the client's `protocolVersion` if it is one of
`2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`, else `2025-11-25`;
capabilities
`{tools: {}}`; `instructions`), `notifications/*` ignored, `ping`,
`tools/list`, `tools/call`; anything else `-32601`. Tool failures return
`isError: true` with the message, so the agent can read it. Checked:
Claude Code 2.1.296 sends `initialize` with `2025-11-25`, then
`notifications/initialized`, then `tools/list` (stub server under
`claude mcp list`, temp HOME).

**Instructions.** Lead line, a blank line, then `about.md` as is. Claude
Code truncates instructions and each tool description at 2,048 chars
(its MCP docs); codex asks for the first 512 to stand alone (its MCP
docs). The lead is under 300 chars and the README asks for a short
`about.md` with its "belongs here" lines first. No server-side cut.

**Commands.** Ported from the Anthropic Python SDK's
`BetaLocalFilesystemMemoryTool` (anthropic-sdk-python `main` at
`b4b7916`, `src/anthropic/lib/tools/_beta_builtin_memory_tool.py`):

- `view(path, view_range?)`: a dir lists entries two levels deep, dot
  files hidden, with sizes; a file returns numbered lines, `view_range`
  `[start, end]` with `-1` for the end.
- `create(path, file_text)`: makes parent dirs; refuses an existing file.
- `str_replace(path, old_str, new_str)`: exactly one match, else error
  naming the count or lines.
- `insert(path, insert_line, insert_text)`: `0..len(lines)`.
- `delete(path)`: file or dir; refuses the root.
- `rename(old_path, new_path)`: refuses an existing target.

Kept from the SDK: the `/memories` prefix (the paths the model is
trained on), resolve-then-contain as the escape check (`resolve()`
follows symlinks, so it also catches a link out). Tightened: any `..`
part is refused outright, and `/memoriesX` is refused (the SDK's prefix
test lets it through). Dropped: atomic temp-file writes and permission
bits on new dirs; the store is a git checkout and the user's own.

`/memories` maps to `<store>/memory/`, not the store root, so the agent
cannot edit `about.md` (the user's text) or `.git` (hooks run code).
`memory/` is created at start if missing.

**Search.** `memory_search(query)`: split the query on whitespace; a
`.md` file under `memory/` matches if it contains every word,
case-insensitive; return each match's path and the lines holding any
word, at most 20 files. No ranking, no index.

**Index.** The server does not touch `MEMORY.md`. Claude Code's own auto
memory works the same way (the model edits the index), and keeping it in
step in code would mean parsing frontmatter and owning the line format.

**Format** (from Claude Code's own memory files): frontmatter `name`,
`description`, and `metadata:` with `type:`; index lines
`- [Title](file.md) - hook`. Not validated by the server.

**Packaging.** `pyproject.toml`, setuptools backend, `py-modules =
["pensieve"]`, script `pensieve = "pensieve:main"`. `flake.nix` builds it
with `python3Packages.buildPythonApplication` from the locked nixpkgs.
pip fetches setuptools at install time; nothing is fetched at run time.

## Implementation Plan

- [x] `pensieve.py`: stdio loop, initialize with instructions, the seven
  tools, path check; tests for each Test Strategy case but packaging
  and paid.
- [x] `pyproject.toml` and `flake.nix` (+ lock); pip and nix install
  checked in temp dirs.
- [x] README.
- [x] Paid run at the agent-dev review.

- *Risk note:* the agent may skip the index line; the paid run shows it.
- *Risk note:* a client on the 2026-07-28 MCP revision only would not
  connect; add `server/discover` when one appears.

## Session Log

- 2026-10-12: closure. Backlog: no items existed, so none closed; filed
  `license` and `mcp-stateless-era`. project.md Architecture now carries
  the `/memories` -> `memory/` mapping and the agent-kept index.
- 2026-10-12: review rulings. `memory_create`'s description now says to
  search first and update rather than duplicate, with one line per
  type; `initialize` answers `2025-11-25` for a version it does not
  know (test seen to fail on the old code). Paid run 2 of 2, same
  prompt, fresh stores: Claude searched both stores first, viewed both
  indexes, then wrote each fact and index line to its own store, the
  work fact typed `project`. 12 turns, USD 0.16. 24 tests pass on 3.11
  and 3.13; ruff clean.
- 2026-10-12: paid run, 1 of 1: `claude --print`, Sonnet 4.6, temp HOME,
  `autoMemoryEnabled: false`, two pensieve instances from
  `--strict-mcp-config`, prompt "Please remember two things for later:
  our team's on-call handoff moved to Mondays at 10:00, and I've started
  learning the cello." Claude viewed each `MEMORY.md`, then created
  `oncall-handoff.md` and its index in the work store and `hobbies.md`
  and its index in the personal store, each with `name`, `description`,
  `metadata.type`. Nothing else changed in either store or the cwd.
  9 turns, USD 0.10.
- 2026-10-12: code review cycle 2: PASS WITH NOTES, nothing high. Fixed
  its two mediums: a non-string tool name, invalid UTF-8 and very deep
  JSON still ended the server (now one catch around each request,
  -32603, and -32700 for bad input). Fixed two lows: search now numbers
  lines as view does; `/memories/.` works again. New tests failed on the
  old code. 23 tests pass on 3.11, 3.13, 3.14; ruff clean.
- 2026-10-12: code review (fresh context, correctness lens): PASS WITH
  NOTES, nothing high. Fixed its four mediums, each with a test seen to
  fail on the old code: non-object messages or params ended the server
  (now -32600 / -32602); delete and rename followed a final symlink and
  removed its target (the last part is now kept unresolved and both it
  and its parent are confined); a dangling link broke a directory view
  (`lstat`); insert split on form feeds and similar, and edits turned
  CRLF into LF (now `\n` only, `newline=""`). Also added escape rows for
  str_replace, insert and rename's old path, and a link outside that
  points in. Left, as low: `initialize` echoes any protocol version;
  OS error text can name the host path; a trailing slash on create
  makes a file; `memory/` as a symlink is followed at start.
- 2026-10-12: packaging. `pip install git+file://...@ea6f0a6` into a
  temp venv (temp HOME, no pip cache) gave `pensieve` with no other
  package; its tools/list answered; HOME stayed empty. pip fetched
  setuptools at install time only. `nix build` of the committed flake
  (nixpkgs locked at `6510408`, 2026-10-10) gave `bin/pensieve`, which
  answered initialize and created a file in a temp store.
- 2026-10-12: server and tests. 18 tests pass on Python 3.11, 3.13 and
  3.14 (nixpkgs). Each guard was broken in a scratch copy (11 mutations:
  `..` rule, containment, `/memoriesX`, search through a file link, lead
  line, dot files, root delete, rename overwrite, multi-match replace,
  any-word search, narrow catch) and a test failed every time. `ruff`
  0.16.10 check and format clean. `requires-python` set to 3.11, the
  oldest checked.
- 2026-10-12: grounding. Read the Anthropic SDK memory helper (commit
  above), Claude Code and codex MCP docs, the MCP lifecycle page
  (2026-07-28), and Claude Code's memory files for the format. Stub
  server under `claude mcp list` in a temp HOME showed the handshake.
  Installed `mcp` into a temp venv to count dependencies.

## Decision Log

- Stdlib JSON-RPC, not the MCP SDK: zero dependencies and one source for
  both install paths; costs about 230 more lines than the SDK would.
- `/memories` maps to `memory/`, not the store root: keeps `about.md`
  and `.git` out of the agent's reach with no extra rule.
- The agent keeps `MEMORY.md` in step, told by the tool descriptions:
  matches how Claude Code's own memory works; less code.
- Seven `memory_*` tools, not one `memory` tool with a `command` field:
  each gets its own required arguments, and with deferred tool loading
  the names alone say what they are.
- Agent-dev review: wording, not code, steers search-before-save and
  the type; one more paid run, then no further loop. Low notes left.
- Planning review: `/memories` -> `memory/` kept; host-native reviewer,
  no worktree; no LICENSE file until the user chooses one.
