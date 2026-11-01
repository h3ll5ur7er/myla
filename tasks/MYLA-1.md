---
id: MYLA-1
title: Introduce Genbeya tasks and wiki
type: chore
status: done
priority: medium
labels: [docs, genbeya]
---
Set the repository up for [Genbeya](https://github.com/genbeya/genbeya): the task board in `tasks/`, the wiki in `docs/`, and the agent files that teach coding agents to use both.

- [x] `.genbeya.yml` (prefix `MYLA`, default workflow)
- [x] Agent skill in `.claude/skills/genbeya/` and `.agents/skills/genbeya/`, Genbeya block in `AGENTS.md`, `CLAUDE.md` importing it
- [x] Move the earlier hand-written docs to [[Archive]] (links between them fixed)
- [x] Write the wiki: [[Home]], [[Language]], [[Architecture]], [[Development]], [[Project]]
- [x] One task per finding of the October 2026 code review, grouped by component (epics)
- [x] Point the README at the wiki
- [x] Review the wiki and the task priorities: done by the review of 31 October 2026 ([[Project/Review-2026-10]]); the stale status text it found is [[MYLA-191]], the board's open points [[MYLA-194]]
- [x] Open the repository in Genbeya and check that every reference resolves (no red links): a scan of every `[[…]]` in `tasks/` and `docs/` resolves (the nine links to files deleted with the Python language server and `selfhost/floatlit.my` are plain paths now)
