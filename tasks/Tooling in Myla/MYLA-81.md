---
id: MYLA-81
title: "`myla test` parity in the self-hosted CLI"
type: improvement
status: backlog
priority: medium
labels: [testing, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). [[selfhost/main.my]] already has `test`; make it a drop-in replacement for the Python `myla test`.

- [ ] Same output format, summary line and exit status as `myla test` ([[src/myla/cli.py]]), including tests in imported modules ([[MYLA-11]])
- [ ] A burn gate that runs every example's and every selfhost module's `#test`s through both and compares the output
