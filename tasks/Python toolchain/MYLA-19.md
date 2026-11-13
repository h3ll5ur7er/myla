---
id: MYLA-19
title: REPL
type: feature
status: done
priority: low
labels: [cli]
---
`myla repl` is still the "planned for v0.0.2" stub (`src/myla/cli.py#L202-L203` (removed with the Python toolchain, D101)), and the README lists it as planned.

## Done when

- [x] Line-by-line input with multi-line blocks (open braces continue the input) (done in Myla by [[MYLA-82]]: `myla repl`)
- [x] Declarations accumulate; expressions print their value (done in Myla by [[MYLA-82]]: `myla repl`)
- [x] Errors are reported without ending the session (done in Myla by [[MYLA-82]]: `myla repl`)

## Superseded

Closed without a fix: superseded by [[MYLA-82]] (the REPL will be written in Myla on the self-hosted interpreter, see [[Project/Roadmap]]).
