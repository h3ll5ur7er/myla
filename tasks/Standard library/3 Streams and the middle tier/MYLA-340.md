---
id: MYLA-340
title: Streaming processes
type: feature
status: backlog
priority: medium
labels: [stdlib, process, streams, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #46. Today `run` and `Command.output` capture a child's whole output.

- **Owns:** `lib/std/process.my`, `docs/Language/Standard-library/Process.md`
- **Needs:** [[MYLA-336]], [[MYLA-338]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Command.spawn() -> Result<Child, SpawnError>` with the child's stdin a `Write` and its stdout and stderr `Read`s
- [ ] `wait`, `kill`, `try_wait`; async forms
- [ ] A pipeline of two children joined by a pipe
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
