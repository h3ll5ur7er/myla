---
id: MYLA-760
title: "Agent harness: instruction files and a persistent memory"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

Two kinds of memory:

- **Instruction files** the user writes: the workspace's `AGENTS.md` and `CLAUDE.md` and the user's `~/.config/myla-agent/AGENTS.md` go into the system prompt. A line `@path` includes that file (relative to the including one, once each, inside the workspace).
- **A memory the agent keeps** between sessions: one Markdown file per fact in the memory directory (by default `~/.local/share/myla-agent/<workspace>/`), and an index `MEMORY.md` of one line per fact, which the system prompt carries. Tools `remember(name, description, content)`, `recall(name)` and `forget(name)`.

- [x] Instruction files with `@` includes, capped in size
- [x] Memory files and the index: write, replace, read, remove; names are slugs
- [x] The index in the system prompt, read once per session (see [[MYLA-762]]: a change shows from the next session)

Against the server on 2026-11-17 a run saved the memory `become-statement`; the next session's REPL quoted it from the index without a tool call.
