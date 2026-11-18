---
id: MYLA-763
title: "Agent harness: edit_file, grep and run_command"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

- [x] `edit_file(path, old, new)`: `old` must occur exactly once
- [x] `grep(pattern, path?, glob?)`: a regular expression (std.regex) over the files below `path`, `file:line: text`, capped; skips `.git`, `build`, binary and large files
- [x] `run_command(command)`: `sh -c` in the workspace, with a time limit, stdout, stderr and the status, capped. The policy `commands` is `ask` (the default: the user says yes or no, and with no terminal it is no), `allow` (`--yes`) or `deny`
- [x] Tool parameters of any kind (optional strings too)

On a pseudo-terminal (`script`, 2026-11-17) the agent asked before `ls selfhost | wc -l`, ran it after `y`, and answered 47. Without a terminal the tool result says how to allow commands. An absolute path inside the workspace is accepted, since the model wrote one.
