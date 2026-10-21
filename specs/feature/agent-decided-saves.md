# Feature: agent-decided-saves

## Git Setup

- Branch: `feat/agent-decided-saves`
- Base: `feat/pensieve`

## Feature Brief

A store holds what the agent decides on its own to remember for its next
session, the things Claude Code's automatic memory saves unprompted. With
that memory turned off, its guidance on when to save is gone too, so
pensieve's standing text carries it. User-directed saves go where the user
says, not here.

## Handoff

- **Stage:** dev
- **Ready for:** closure; text change only
- **Carry forward:** lead is 685 chars; with the real about.md files
  (under 800 bytes) the instructions stay under 2,048
- **Deliberately left:** nothing

### Crossings

<!-- Append one line per crossing; never edit or delete a line. -->
- planning → dev · EXCEPTION · skipping: the planning gate · why: text
  change, the user gave the wording to carry
- dev → review · EXCEPTION · skipping: the code review gate · why: text
  change, on the user's instruction

## Requirements

- The fixed lead before `about.md` says: search this store first when
  context on the user or the work would help; save on your own what helps
  a future session, by the four types; skip what the repo, git history or
  conversation records, and anything ephemeral; name the repo or project
  in a project memory's description; follow the user when they say where
  to store something; ask once if the store may not fit the session.
- The lead with its separator stays under 1,200 chars; its first 512 hold
  the search, save and type lines on their own.
- `memory_create`'s description says the same in short.
- README says what goes in and what does not.

## Test Strategy

One startup test pins the lead's parts, the first-512 rule and the
2,048 total with an 800-char `about.md`; the tools test pins the new
`memory_create` lines. Both fail on the old text.
