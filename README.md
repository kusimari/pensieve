# pensieve

A tiny MCP memory server for coding agents. One instance serves one store:
a directory of markdown memories you own, usually a git checkout.

- Standing text: at start it reads `<store>/about.md` and sends it to the
  agent as the server's instructions, so each store says what belongs in it.
- Tools: Anthropic's memory tool commands (`memory_view`, `memory_create`,
  `memory_str_replace`, `memory_insert`, `memory_delete`, `memory_rename`)
  plus `memory_search`, a keyword search.
- Every path is under `/memories`, which means `<store>/memory/`. Paths that
  leave it (`..`, symlinks out, anything else) are refused. The agent cannot
  reach `about.md` or `.git`.
- Nothing is written outside the store. No network, no telemetry, no
  dependencies beyond the Python standard library (3.11+).

## What goes in

What the agent decides on its own to remember for its next session: who you
are, your corrections and feedback on how to work, project context it will
need next time, and pointers to where things live. These are the things
Claude Code's automatic memory saves unprompted, kept in a store you own so
they travel with you across machines. When you tell the agent where to store
something, it does that instead; pensieve is not for user-directed saves or
for notes. Which store a session uses follows its persona (work or personal),
as each store's `about.md` says; the agent asks once when it is unclear.

## Install

From a pinned commit, either way:

```sh
nix profile install github:kusimari/pensieve/<rev>
pipx install git+https://github.com/kusimari/pensieve@<rev>
```

or run `python3 pensieve.py --store <dir>` from a checkout.

## Run two stores side by side

Register one instance per store with Claude Code:

```sh
claude mcp add -s user personal-memory -- pensieve --store ~/stores/personal
claude mcp add -s user work-memory -- pensieve --store ~/stores/work
```

The instances share nothing; each sees only its own store. Turn off Claude
Code's automatic memory (`"autoMemoryEnabled": false` in settings) so it does
not save to its own memory directory instead. That also drops Claude's own
guidance on when to save; pensieve's standing text carries it.

## Store layout

```
<store>/
  about.md          what belongs here and what does not, plus a short profile
  memory/
    MEMORY.md       the index, one line per memory
    coffee.md       one file per memory
```

Memories use Claude Code's auto-memory format:

```markdown
---
name: coffee
description: Pour-over grind setting
metadata:
  type: user
---

Grind 18 clicks for pour-over.
```

`type` is one of `user`, `feedback`, `project`, `reference`. Each memory has
one line in `MEMORY.md`, such as `- [Coffee](coffee.md) - pour-over grind`.
The agent keeps the index in step; the tool descriptions tell it to.

## about.md

Plain markdown, short. Put what belongs here and what does not first, then
a short profile. For example:

```markdown
Belongs here: my personal life, hobbies, home setup.
Not here: anything about my employer or its projects; those go to the work store.

Profile: I live in Lisbon and drink a lot of coffee.
```

The agent receives a fixed lead of about 700 characters (when to search, what
to save and what not to), then this file. Claude Code cuts server instructions
at 2,048 characters, so keep `about.md` under about 1,300. With no `about.md`,
the agent is told the store has no description and to ask before saving.

## Test

```sh
python3 -m unittest discover -s tests
```

The tests start the server on temp stores with a temp HOME.

## License

MIT, see [LICENSE](LICENSE).
