---
id: MYLA-700
title: "Windows step 1: a target record, and each target's tools named by it"
type: feature
status: todo
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). The part of [[MYLA-262]] the port needs before it starts: the targets are strings today, and the driver runs the tools through `/usr/bin/env`, which Windows lacks.

- [ ] A `Target` record (operating system, architecture, object format, executable suffix, the tools to assemble and link) in place of the target string, with `x86_64-windows` recognised by `--target`
- [ ] The driver runs each target's tools by the record, without `/usr/bin/env`; a missing tool is named in the error ([[MYLA-262]])
- [ ] Behaviour unchanged for the three targets there are: the bootstrap's fixed point and the suites the proof
